import logging
import time
import json
import requests
from typing import Dict, List, Any, Optional
from utils.mqtt_client import MQTTClient

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)
logger = logging.getLogger("ha_to_163")

class HA163Gateway:
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.mqtt_client = MQTTClient(config)
        self.ha_headers = {
            "Authorization": f"Bearer {config['ha_token']}",
            "Content-Type": "application/json"
        }
        self.log_level = config.get("log_level", "info").upper()
        logger.setLevel(getattr(logging, self.log_level, logging.INFO))

    def _get_entity_value(self, entity_id: str, property_name: str) -> Optional[float]:
        """获取HA实体值（修复充电状态文本转数值）"""
        try:
            resp = requests.get(
                f"{self.config['ha_url']}/api/states/{entity_id}",
                headers=self.ha_headers,
                timeout=self.config.get("single_entity_timeout", 30)
            )
            if resp.status_code != 200:
                logger.warning(f"获取实体{entity_id}失败，状态码: {resp.status_code}")
                return None

            data = resp.json()
            state = data.get("state")
            if state is None or state == "unknown" or state == "unavailable":
                logger.warning(f"未获取到 {property_name} 数据（实体: {entity_id}）")
                return None

            # 修复：充电状态文本转数值（正在充电→1，未充电→0）
            if "charging_state" in property_name:
                if state == "正在充电":
                    return 1.0
                elif state == "未充电":
                    return 0.0
                else:
                    logger.warning(f"未知充电状态: {state}（实体: {entity_id}）")
                    return None

            # 其他数值型状态转换
            try:
                return float(state)
            except ValueError:
                logger.warning(f"实体 {entity_id} 状态无法转换为数值: {state}")
                return None

        except Exception as e:
            logger.error(f"获取实体{entity_id}异常: {str(e)}")
            return None

    def _collect_device_data(self, device: Dict[str, Any]) -> Dict[str, float]:
        """收集单个设备的所有属性数据"""
        device_id = device["id"]
        entity_prefix = device["ha_entity_prefix"]
        supported_props = device["supported_properties"]
        conversion_factors = json.loads(device.get("conversion_factors", "{}"))
        device_data = {}

        logger.info(f"开始收集设备 {device_id} 数据（前缀: {entity_prefix}）")
        for prop in supported_props:
            # 匹配对应的HA实体（根据属性名拼接）
            entity_suffix_map = {
                "temp": "temperature",
                "hum": "relative_humidity",
                "pm2_5": "pm2_5_density",
                "pm10": "pm10_density",
                "co2": "co2_density",
                "tvoc": "tvoc_density",
                "noise": "noise_decibel",
                "battery": "battery_level",
                "charging_state": "charging_state",
                "voltage": "voltage",
                "current": "current",
                "active_power": "electric_power",
                "energy": "power_consumption",
                "frequency": "frequency"
            }
            entity_suffix = entity_suffix_map.get(prop, prop)
            entity_id = f"sensor.{entity_prefix}_{entity_suffix}"  # 适配传感器实体格式

            # 获取实体值
            value = self._get_entity_value(entity_id, prop)
            if value is None:
                continue

            # 应用转换系数（默认1.0）
            factor = conversion_factors.get(prop, 1.0)
            device_data[prop] = round(value * factor, 1)
            logger.info(f"  收集到 {prop} = {value} * {factor} = {device_data[prop]}（实体: {entity_id}）")

        return device_data

    def run(self):
        """启动网关主流程"""
        # 连接MQTT
        if not self.mqtt_client.connect():
            logger.error("MQTT连接失败，退出程序")
            return

        try:
            while True:
                # 遍历所有启用的子设备
                for device in self.config.get("sub_devices", []):
                    if not device.get("enabled", False):
                        continue

                    device_id = device["id"]
                    logger.info(f"开始处理设备: {device_id}")

                    # 收集设备数据
                    device_data = self._collect_device_data(device)
                    if not device_data:
                        logger.warning(f"设备 {device_id} 无有效数据，跳过推送")
                        continue

                    # 构建推送 payload
                    payload = {
                        "id": int(time.time() * 1000),
                        "version": "1.0",
                        "params": device_data
                    }

                    # 推送数据到MQTT
                    logger.info(f"设备 {device_id} 准备推送数据: dict_keys({list(device_data.keys())})")
                    success = self.mqtt_client.publish(device, payload)
                    if success:
                        logger.info(f"设备 {device_id} 数据推送成功")
                    else:
                        logger.error(f"设备 {device_id} 数据推送失败")

                # 等待下一个推送周期
                logger.info(f"等待 {self.config.get('wy_push_interval', 60)} 秒后继续...")
                time.sleep(self.config.get("wy_push_interval", 60))

        except KeyboardInterrupt:
            logger.info("程序被手动终止")
        finally:
            self.mqtt_client.disconnect()
            logger.info("程序退出，MQTT连接已断开")

def load_config() -> Dict[str, Any]:
    """加载配置文件（从HA插件配置读取）"""
    import os
    config_path = os.getenv("CONFIG_PATH", "/data/options.json")
    with open(config_path, "r") as f:
        return json.load(f)

if __name__ == "__main__":
    try:
        config = load_config()
        gateway = HA163Gateway(config)
        gateway.run()
    except Exception as e:
        logger.critical(f"程序启动失败: {str(e)}", exc_info=True)
        exit(1)
