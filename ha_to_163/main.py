import logging
import time
import json
import signal
import requests
from concurrent.futures import ThreadPoolExecutor, as_completed
import threading
from utils.config_loader import ConfigLoader
from utils.mqtt_client import MQTTClient
from device_discovery.ha_discovery import HADiscovery


class HAto163Gateway:
    def __init__(self):
        # 1. 加载配置（优先初始化）
        self.config_loader = ConfigLoader()
        self.config = self.config_loader.config
        self.logger = logging.getLogger("ha_to_163")

        # 2. 初始化HA请求头（在会话之前）
        self.ha_headers = {
            "Authorization": f"Bearer {self.config['ha_token']}",
            "Content-Type": "application/json"
        }

        # 3. 创建HTTP会话（复用连接）
        self.ha_session = requests.Session()
        self.ha_session.headers.update(self.ha_headers)

        # 4. 设备与MQTT客户端初始化（修复：MQTTClient只传config参数）
        self.matched_devices = {}
        self.mqtt_client = MQTTClient(self.config)  # 移除多余的ha_session参数
        self.running = True
        self.executor = None  # 线程池实例

        # 注册退出信号处理
        signal.signal(signal.SIGINT, self._stop)
        signal.signal(signal.SIGTERM, self._stop)

    def _stop(self, signum, frame):
        """处理程序退出，释放资源"""
        self.logger.info("收到停止信号，正在安全退出...")
        self.running = False
        
        # 关闭线程池
        if self.executor:
            self.executor.shutdown(wait=False, cancel_futures=True)
            self.logger.info("线程池已关闭")
        
        # 断开MQTT连接
        if hasattr(self, 'mqtt_client') and self.mqtt_client:
            self.mqtt_client.disconnect()
            self.logger.info("MQTT连接已断开")
        
        # 关闭HTTP会话
        if hasattr(self, 'ha_session'):
            self.ha_session.close()
            self.logger.info("HTTP会话已关闭")

    def _wait_for_ha_ready(self) -> bool:
        """等待Home Assistant服务就绪"""
        timeout = self.config.get("entity_ready_timeout", 600)
        start_time = time.time()
        self.logger.info(f"等待HA就绪（超时时间: {timeout}秒）")

        while time.time() - start_time < timeout:
            try:
                resp = self.ha_session.get(
                    f"{self.config['ha_url']}/api/",
                    timeout=10
                )
                if resp.status_code == 200:
                    self.logger.info("Home Assistant已就绪")
                    return True
            except requests.exceptions.RequestException as e:
                self.logger.warning(f"HA未就绪: {str(e)}，将重试")
            
            time.sleep(10)  # 间隔10秒重试

        self.logger.error(f"HA超时未就绪（超过{timeout}秒）")
        return False

    def _discover_devices(self) -> bool:
        """执行设备发现，匹配HA实体与子设备"""
        try:
            # HADiscovery只需要config和ha_headers两个参数
            discovery = HADiscovery(
                self.config,
                self.ha_headers
            )
            new_matched_devices = discovery.discover()

            # 记录新增实体
            for device_id, new_data in new_matched_devices.items():
                old_data = self.matched_devices.get(device_id, {})
                old_sensors = old_data.get("sensors", {})
                new_sensors = new_data.get("sensors", {})
                added_sensors = {k: v for k, v in new_sensors.items() if k not in old_sensors}
                
                if added_sensors:
                    self.logger.info(f"设备 {device_id} 新增匹配实体: {added_sensors}")

            self.matched_devices = new_matched_devices
            return len(self.matched_devices) > 0

        except Exception as e:
            self.logger.error(f"设备发现失败: {str(e)}")
            return False

    def _get_entity_value(self, entity_id: str, device_type: str) -> float or int or None:
        """获取HA实体值（带超时控制）"""
        try:
            single_entity_timeout = self.config.get("single_entity_timeout", 30)
            start_time = time.time()
            
            while time.time() - start_time < single_entity_timeout:
                try:
                    resp = self.ha_session.get(
                        f"{self.config['ha_url']}/api/states/{entity_id}",
                        timeout=5  # 单次请求超时
                    )
                    
                    if resp.status_code == 200:
                        state = resp.json().get("state")
                        if state in ("unknown", "unavailable", ""):
                            time.sleep(2)
                            continue

                        # 处理开关类设备状态
                        if device_type in ("switch", "socket", "breaker"):
                            if state == "on":
                                return 1
                            elif state == "off":
                                return 0
                            elif state == "trip" and device_type == "breaker":
                                return 2

                        # 处理二进制传感器（如门磁）
                        if device_type == "sensor" and entity_id.startswith("binary_sensor."):
                            return 1 if state == "on" else 0

                        # 提取数值型状态
                        import re
                        match = re.search(r'[-+]?\d*\.\d+|\d+', state)
                        if match:
                            return float(match.group())

                        self.logger.warning(f"实体 {entity_id} 状态无法转换为数值: {state}")
                        return None

                except requests.exceptions.RequestException as e:
                    self.logger.warning(f"获取实体 {entity_id} 临时失败: {str(e)}")
                    time.sleep(2)

            self.logger.error(f"实体 {entity_id} 超时未就绪（{single_entity_timeout}秒）")
            return None

        except Exception as e:
            self.logger.error(f"获取实体 {entity_id} 失败: {str(e)}")
            return None

    def _parse_conversion_factors(self, factors_str: str) -> dict:
        """解析转换系数（字符串转字典）"""
        if not factors_str:
            return {}
        try:
            return json.loads(factors_str)
        except json.JSONDecodeError:
            self.logger.error(f"转换系数格式错误: {factors_str}，将使用默认系数1.0")
            return {}

    def _collect_device_data(self, device_id: str) -> dict:
        """收集设备所有属性数据"""
        device_data = self.matched_devices[device_id]
        device_config = device_data["config"]
        device_type = device_config["type"]
        # 兼容sensors和entities两种键名
        entities = device_data.get("sensors", device_data.get("entities", {}))
        
        # 解析转换系数
        factors_str = device_config.get("conversion_factors", "")
        conversion_factors = self._parse_conversion_factors(factors_str)

        # 构建推送 payload
        payload = {
            "id": int(time.time() * 1000),
            "version": "1.0",
            "params": {}
        }

        for prop, entity_id in entities.items():
            value = self._get_entity_value(entity_id, device_type)
            if value is not None:
                # 状态属性不应用转换系数
                if prop == "state":
                    payload["params"][prop] = value
                    self.logger.info(f"  收集到 {prop} = {value}（实体: {entity_id}）")
                else:
                    # 应用转换系数
                    factor = conversion_factors.get(prop, 1.0)
                    converted_value = value * factor
                    
                    # 根据属性类型保留小数位数
                    if prop in ("current", "active_power"):
                        converted_value = round(converted_value, 3)
                    elif prop in ("voltage", "temp", "hum", "frequency", "co2", "pm2_5", "pm10", "tvoc", "noise"):
                        converted_value = round(converted_value, 1)
                    elif prop == "energy":
                        converted_value = round(converted_value, 4)
                    
                    payload["params"][prop] = converted_value
                    self.logger.info(
                        f"  收集到 {prop} = {value} * {factor} = {converted_value}（实体: {entity_id}）"
                    )
            else:
                self.logger.warning(f"  未获取到 {prop} 数据（实体: {entity_id}）")

        return payload

    def _push_device_data(self, device_id: str) -> bool:
        """推送单设备数据到网易IoT平台"""
        device_data = self.matched_devices[device_id]
        device_config = device_data["config"]

        payload = self._collect_device_data(device_id)
        if not payload["params"]:
            self.logger.warning(f"设备 {device_id} 无有效数据，跳过推送")
            return False
        
        self.logger.info(f"设备 {device_id} 准备推送数据: {payload['params'].keys()}")
        return self.mqtt_client.publish(device_config, payload)

    def _push_device_with_timeout(self, device_id: str, timeout: int) -> bool:
        """带超时控制的设备推送（供线程调用）"""
        def push_task():
            return self._push_device_data(device_id)
        
        # 使用线程实现超时控制
        push_thread = threading.Thread(target=push_task, daemon=True)
        push_thread.start()
        push_thread.join(timeout=timeout)
        
        if push_thread.is_alive():
            self.logger.error(f"设备 {device_id} 推送超时（超过{timeout}秒）")
            return False
        return True

    def start(self):
        """启动网关服务主流程"""
        self.logger.info("===== HA to 163 Gateway 服务启动 =====")

        # 启动延迟（等待依赖服务就绪）
        startup_delay = self.config.get("startup_delay", 30)
        self.logger.info(f"启动延迟 {startup_delay} 秒...")
        time.sleep(startup_delay)

        # 等待HA就绪
        if not self._wait_for_ha_ready():
            self.logger.error("HA未就绪，服务启动失败")
            return

        # 连接MQTT broker
        if not self.mqtt_client.connect():
            self.logger.error("MQTT连接失败，服务启动失败")
            return

        # 初始设备发现
        if not self._discover_devices():
            self.logger.error("未匹配到任何设备，服务启动失败")
            return

        # 启动主循环
        self._run_loop()
        self.logger.info("服务已正常退出")

    def _run_loop(self):
        """服务主循环（定时发现设备和推送数据）"""
        push_interval = self.config.get("wy_push_interval", 60)
        discovery_interval = self.config.get("ha_discovery_interval", 300)
        last_discovery = time.time()
        last_push = time.time()
        
        # 初始化线程池（根据设备数量动态调整）
        max_workers = min(len(self.matched_devices), 10) if self.matched_devices else 1
        self.executor = ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="DevicePush")

        while self.running:
            now = time.time()

            # 定时重新发现设备
            if now - last_discovery >= discovery_interval:
                self.logger.info("执行定时设备发现...")
                self._discover_devices()
                last_discovery = now
                
                # 动态调整线程池大小
                new_max_workers = min(len(self.matched_devices), 10) if self.matched_devices else 1
                if new_max_workers != max_workers:
                    self.logger.info(f"线程池大小调整: {max_workers} → {new_max_workers}")
                    self.executor.shutdown(wait=False)
                    self.executor = ThreadPoolExecutor(max_workers=new_max_workers, thread_name_prefix="DevicePush")
                    max_workers = new_max_workers

            # 定时异步推送数据
            if now - last_push >= push_interval:
                self.logger.info("开始异步数据推送...")
                futures = []
                
                # 提交所有设备推送任务
                for device_id in self.matched_devices:
                    future = self.executor.submit(
                        self._push_device_with_timeout,
                        device_id,
                        timeout=60  # 单个设备推送超时
                    )
                    futures.append((device_id, future))

                # 处理推送结果
                for device_id, future in futures:
                    try:
                        result = future.result(timeout=65)  # 等待结果超时（略长于单个设备超时）
                        if result:
                            self.logger.info(f"设备 {device_id} 异步推送完成")
                        else:
                            self.logger.warning(f"设备 {device_id} 异步推送无有效数据")
                    except Exception as e:
                        self.logger.error(f"设备 {device_id} 异步推送异常: {str(e)}")

                last_push = now

            time.sleep(1)  # 降低CPU占用


if __name__ == "__main__":
    import os
    # 配置日志
    logging.basicConfig(
        level=os.getenv("LOG_LEVEL", "INFO").upper(),
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )
    # 启动网关服务
    gateway = HAto163Gateway()
    gateway.start()
    
