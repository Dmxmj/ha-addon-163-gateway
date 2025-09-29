import requests
import re
import logging
import time
import threading
from typing import Dict, List
from .base_discovery import BaseDiscovery  # 假设基础类来自base_discovery.py


# 完整属性映射表：覆盖环境传感器与电气设备所有参数
PROPERTY_MAPPING = {
    # -------------------------- 环境传感器属性 --------------------------
    # 温度相关
    "temperature": "temp",
    "temp": "temp",
    "temp_c": "temp",
    "temp_f": "temp",
    "temperature_p": "temp",
    "temp_p": "temp",
    # 湿度相关
    "humidity": "hum",
    "hum": "hum",
    "humidity_percent": "hum",
    "relative_humidity": "relative_hum",
    "hum_p": "hum",
    # 电池相关
    "battery": "battery",
    "batt": "battery",
    "battery_level": "battery",
    "battery_percent": "battery",
    "batt_p": "battery",
    # 空气质量相关
    "smoke_concentration": "smoke",
    "smoke": "smoke",
    "smoke_level": "smoke",
    "carbon_dioxide": "co2",
    "co2": "co2",
    "carbon_dioxide_concentration": "co2",
    "pm25": "pm2_5",
    "pm2.5": "pm2_5",
    "particulate_matter_2_5": "pm2_5",
    "pm10": "pm10",
    "particulate_matter_10": "pm10",
    "tvoc": "tvoc",
    "total_volatile_organic_compounds": "tvoc",
    # 噪音相关
    "noise": "noise",
    "sound_level": "noise",
    "noise_decibel": "noise",
    # 门磁等二进制传感器
    "door": "switch",
    "door_state": "switch",
    "contact": "switch",

    # -------------------------- 电气设备属性 --------------------------
    # 开关状态
    "state": "state",
    "on": "state",
    "off": "state",
    # 功率相关
    "electric_power": "active_power",
    "power": "active_power",
    "active_power": "active_power",
    "elec_power": "active_power",
    "power_w": "active_power",
    # 能耗相关
    "power_consumption": "energy",
    "energy": "energy",
    "kwh": "energy",
    "electricity_used": "energy",
    "energy_kwh": "energy",
    # 电流相关
    "current": "current",
    "electric_current": "current",
    "current_a": "current",
    # 电压相关
    "voltage": "voltage",
    "voltage_v": "voltage",
    # 频率相关
    "frequency": "frequency",
    "frequency_hz": "frequency"
}


class HADiscovery(BaseDiscovery):
    """Home Assistant设备发现类：支持环境传感器、开关、插座、断路器等设备"""

    def __init__(self, config: Dict[str, any], ha_headers: Dict[str, str], ha_session: requests.Session):
        super().__init__(config, module_name="ha_discovery")
        # 基础配置
        self.ha_url = config.get("ha_url").rstrip("/")  # 去除URL末尾斜杠，避免拼接错误
        self.ha_headers = ha_headers
        self.ha_session = ha_session  # 复用HTTP会话，减少连接开销
        self.entities: List[Dict[str, any]] = []  # 存储HA所有实体
        self.logger = logging.getLogger("ha_discovery")

        # 设备分类配置
        self.sub_devices = [d for d in config.get("sub_devices", []) if d.get("enabled", True)]
        self.electric_device_types = {"switch", "socket", "breaker"}  # 电气设备类型
        self.environment_types = {"sensor"}  # 环境传感器类型

        # 调试配置（可通过config控制是否开启详细日志）
        self.debug_mode = config.get("log_level", "info").lower() == "debug"

    def load_ha_entities(self) -> bool:
        """
        从HA加载所有实体（含switch、sensor等类型）
        返回：True=加载成功，False=加载失败
        """
        self.logger.info(f"开始从HA加载实体，请求地址：{self.ha_url}/api/states")
        retry_attempts = self.config.get("retry_attempts", 5)
        retry_delay = self.config.get("retry_delay", 3)
        resp = None

        # 带重试的实体请求
        for attempt in range(1, retry_attempts + 1):
            try:
                resp = self.ha_session.get(
                    url=f"{self.ha_url}/api/states",
                    headers=self.ha_headers,
                    timeout=10  # 单次请求超时控制
                )
                resp.raise_for_status()  # 触发HTTP错误（如401、500）
                break
            except requests.exceptions.Timeout:
                self.logger.warning(f"第{attempt}次请求HA实体超时，{retry_delay}秒后重试")
            except requests.exceptions.ConnectionError:
                self.logger.warning(f"第{attempt}次请求HA实体失败（连接错误），{retry_delay}秒后重试")
            except requests.exceptions.HTTPError as e:
                self.logger.error(f"第{attempt}次请求HA实体HTTP错误：{e}，不再重试")
                return False
            except Exception as e:
                self.logger.warning(f"第{attempt}次请求HA实体异常：{str(e)}，{retry_delay}秒后重试")

            # 非最后一次尝试则延迟重试
            if attempt < retry_attempts:
                time.sleep(retry_delay)

        # 检查响应有效性
        if not resp or resp.status_code != 200:
            self.logger.error(f"HA实体加载失败，响应状态码：{resp.status_code if resp else '无响应'}")
            return False

        # 解析实体数据
        try:
            self.entities = resp.json()
            self.logger.info(f"成功加载HA实体，共{len(self.entities)}个实体")

            # 打印关键实体类型（调试用）
            if self.debug_mode:
                self._print_entity_debug_info()

            return True
        except json.JSONDecodeError:
            self.logger.error("HA返回的实体数据不是合法JSON格式")
            return False
        except Exception as e:
            self.logger.error(f"解析HA实体数据异常：{str(e)}")
            return False

    def _print_entity_debug_info(self) -> None:
        """打印实体调试信息：按类型分类显示，帮助排查前缀配置问题"""
        # 分类统计实体
        switch_entities = [e["entity_id"] for e in self.entities if e["entity_id"].startswith("switch.")]
        sensor_entities = [e["entity_id"] for e in self.entities if e["entity_id"].startswith("sensor.")]
        binary_sensor_entities = [e["entity_id"] for e in self.entities if e["entity_id"].startswith("binary_sensor.")]

        # 打印分类结果
        self.logger.debug("=" * 50)
        self.logger.debug("HA实体分类统计（调试信息）：")
        self.logger.debug(f"1. Switch类型实体（共{len(switch_entities)}个）：")
        for ent in switch_entities:
            self.logger.debug(f"   - {ent}")
        self.logger.debug(f"\n2. Sensor类型实体（共{len(sensor_entities)}个，前20个）：")
        for ent in sensor_entities[:20]:  # 只打印前20个，避免日志过长
            self.logger.debug(f"   - {ent}")
        if len(sensor_entities) > 20:
            self.logger.debug(f"   ... （省略{len(sensor_entities)-20}个）")
        self.logger.debug(f"\n3. Binary Sensor类型实体（共{len(binary_sensor_entities)}个）：")
        for ent in binary_sensor_entities:
            self.logger.debug(f"   - {ent}")
        self.logger.debug("=" * 50)

    def discover(self) -> Dict[str, Dict[str, any]]:
        """
        执行设备发现：匹配HA实体到子设备
        返回：匹配结果（key=设备ID，value=设备配置+实体映射）
        """
        # 先加载HA实体
        if not self.load_ha_entities():
            self.logger.error("HA实体加载失败，无法执行设备发现")
            return {}

        # 用线程执行匹配，避免阻塞主线程
        match_result = {}

        def _match_worker():
            nonlocal match_result
            match_result = self._match_entities_to_devices()

        match_thread = threading.Thread(target=_match_worker, name="DeviceMatchWorker")
        match_thread.start()
        match_thread.join(timeout=30)  # 匹配超时控制（30秒）

        if match_thread.is_alive():
            self.logger.error("设备匹配线程超时（超过30秒），可能存在性能问题")
            return {}

        return match_result

    def _match_entities_to_devices(self) -> Dict[str, Dict[str, any]]:
        """
        核心匹配逻辑：将HA实体与子设备关联
        返回：完整匹配结果
        """
        # 初始化每个子设备的匹配容器
        matched_devices = {}
        for device in self.sub_devices:
            device_id = device["id"]
            device_type = device["type"]
            ha_prefix = device["ha_entity_prefix"].strip()  # 保留原始前缀（含switch./sensor.）

            # 初始化设备匹配数据
            matched_devices[device_id] = {
                "config": device,
                "entities": {},  # key=属性名（如state/temp），value=HA实体ID
                "raw_prefix": ha_prefix,  # 保存原始前缀，用于匹配
                "device_type": device_type
            }
            self.logger.info(f"初始化设备匹配：ID={device_id}，类型={device_type}，前缀={ha_prefix}")

        # 并行匹配所有实体（每个实体一个线程，提高效率）
        threads = []
        for entity in self.entities:
            thread = threading.Thread(
                target=self._process_single_entity,
                args=(entity, matched_devices),
                name=f"EntityProcess-{entity['entity_id'][:20]}"
            )
            threads.append(thread)
            thread.start()

        # 等待所有匹配线程完成
        for thread in threads:
            thread.join(timeout=5)  # 单个实体匹配超时5秒

        # 输出匹配结果日志
        self._log_match_result(matched_devices)

        return matched_devices

    def _process_single_entity(self, entity: Dict[str, any], matched_devices: Dict[str, Dict[str, any]]) -> None:
        """
        处理单个HA实体：尝试匹配到所有符合条件的子设备
        参数：
            entity: HA实体数据（含entity_id、attributes等）
            matched_devices: 全局匹配结果容器（需线程安全操作）
        """
        entity_id = entity.get("entity_id", "")
        if not entity_id:
            return

        # 1. 环境传感器匹配（sensor./binary_sensor.类型实体）
        if entity_id.startswith(("sensor.", "binary_sensor.")):
            for device_id, device_data in matched_devices.items():
                if device_data["device_type"] in self.environment_types:
                    self._match_environment_entity(entity, entity_id, device_id, device_data)

        # 2. 电气设备匹配（switch./sensor.类型实体）
        if entity_id.startswith(("switch.", "sensor.")):
            for device_id, device_data in matched_devices.items():
                if device_data["device_type"] in self.electric_device_types:
                    self._match_electric_entity(entity, entity_id, device_id, device_data)

    def _match_environment_entity(self, entity: Dict[str, any], entity_id: str, device_id: str, device_data: Dict[str, any]) -> None:
        """
        匹配环境传感器实体（如温度、湿度、CO2等）
        参数：
            entity: HA实体数据
            entity_id: HA实体ID（如sensor.temp_1）
            device_id: 目标设备ID（如sensor_001）
            device_data: 目标设备的匹配容器
        """
        ha_prefix = device_data["raw_prefix"]
        # 前缀不匹配则直接跳过
        if ha_prefix not in entity_id:
            return

        # 提取实体关键信息
        attributes = entity.get("attributes", {})
        device_class = attributes.get("device_class", "").lower()
        friendly_name = attributes.get("friendly_name", "").lower()
        entity_core = entity_id.replace(ha_prefix, "").strip("_")  # 去除前缀后的核心部分（如"temperature"）

        # 匹配属性名（优先级：device_class > 实体核心名 > friendly_name）
        property_name = None
        # 优先级1：通过device_class匹配（最准确）
        if device_class in PROPERTY_MAPPING:
            property_name = PROPERTY_MAPPING[device_class]
        # 优先级2：通过实体核心名匹配（如"sensor.xxx_temperature" → "temp"）
        elif entity_core:
            for keyword, target_prop in PROPERTY_MAPPING.items():
                if keyword in entity_core or entity_core in keyword:
                    property_name = target_prop
                    break
        # 优先级3：通过friendly_name匹配（如友好名含"温度" → "temp"）
        elif friendly_name:
            for keyword, target_prop in PROPERTY_MAPPING.items():
                if keyword in friendly_name:
                    property_name = target_prop
                    break

        # 保存匹配结果（避免重复匹配同一属性）
        if property_name and property_name not in device_data["entities"]:
            device_data["entities"][property_name] = entity_id
            self.logger.info(f"环境传感器匹配成功 | 设备：{device_id} | 属性：{property_name} | 实体：{entity_id}")

    def _match_electric_entity(self, entity: Dict[str, any], entity_id: str, device_id: str, device_data: Dict[str, any]) -> None:
        """
        匹配电气设备实体（如开关状态、功率、电流等）
        参数：
            entity: HA实体数据
            entity_id: HA实体ID（如switch.relay_1、sensor.power_1）
            device_id: 目标设备ID（如switch_001）
            device_data: 目标设备的匹配容器
        """
        ha_prefix = device_data["raw_prefix"]
        # 前缀不匹配则直接跳过
        if ha_prefix not in entity_id:
            return

        # 提取实体关键信息
        attributes = entity.get("attributes", {})
        device_class = attributes.get("device_class", "").lower()
        friendly_name = attributes.get("friendly_name", "").lower()
        entity_type = entity_id.split(".")[0]  # 实体类型（switch/sensor）

        # 匹配属性名（按实体类型区分逻辑）
        property_name = None
        if entity_type == "switch":
            # Switch类型实体：固定匹配"state"属性（开关状态）
            property_name = "state"
        elif entity_type == "sensor":
            # Sensor类型实体：匹配功率、电流、电压等电气参数
            # 优先级1：通过device_class匹配
            if device_class in PROPERTY_MAPPING:
                property_name = PROPERTY_MAPPING[device_class]
            # 优先级2：通过实体ID关键词匹配
            else:
                for keyword, target_prop in PROPERTY_MAPPING.items():
                    if keyword in entity_id.lower() and target_prop in ["active_power", "energy", "current", "voltage", "frequency"]:
                        property_name = target_prop
                        break
            # 优先级3：通过friendly_name匹配
            if not property_name and friendly_name:
                for keyword, target_prop in PROPERTY_MAPPING.items():
                    if keyword in friendly_name and target_prop in ["active_power", "energy", "current", "voltage", "frequency"]:
                        property_name = target_prop
                        break

        # 保存匹配结果（避免重复）
        if property_name and property_name not in device_data["entities"]:
            device_data["entities"][property_name] = entity_id
            self.logger.info(f"电气设备匹配成功 | 设备：{device_id} | 属性：{property_name} | 实体：{entity_id}")

    def _log_match_result(self, matched_devices: Dict[str, Dict[str, any]]) -> None:
        """打印最终匹配结果日志，按设备类型分类输出"""
        self.logger.info("\n" + "=" * 60)
        self.logger.info("设备匹配结果汇总")
        self.logger.info("=" * 60)

        # 按设备类型分组输出
        environment_devices = [d for d in matched_devices.values() if d["device_type"] in self.environment_types]
        electric_devices = [d for d in matched_devices.values() if d["device_type"] in self.electric_device_types]

        # 1. 环境传感器结果
        self.logger.info(f"\n【环境传感器设备】（共{len(environment_devices)}个）")
        for device in environment_devices:
            device_id = device["config"]["id"]
            entities = device["entities"]
            # 关键属性状态
            temp_status = "✅已匹配" if "temp" in entities else "❌未匹配"
            hum_status = "✅已匹配" if "hum" in entities else "❌未匹配"
            co2_status = "✅已匹配" if "co2" in entities else "❌未匹配"
            pm25_status = "✅已匹配" if "pm2_5" in entities else "❌未匹配"
            battery_status = "✅已匹配" if "battery" in entities else "❌未匹配"
            # 输出日志
            self.logger.info(f"设备ID：{device_id} | 前缀：{device['raw_prefix']}")
            self.logger.info(f"  匹配属性：temp={temp_status}，hum={hum_status}，co2={co2_status}，pm2.5={pm25_status}，battery={battery_status}")
            self.logger.info(f"  实体映射：{entities}")

        # 2. 电气设备结果
        self.logger.info(f"\n【电气设备】（共{len(electric_devices)}个）")
        for device in electric_devices:
            device_id = device["config"]["id"]
            entities = device["entities"]
            # 关键属性状态
            state_status = "✅已匹配" if "state" in entities else "❌未匹配"
            power_status = "✅已匹配" if "active_power" in entities else "❌未匹配"
            energy_status = "✅已匹配" if "energy" in entities else "❌未匹配"
            current_status = "✅已匹配" if "current" in entities else "❌未匹配"
            voltage_status = "✅已匹配" if "voltage" in entities else "❌未匹配"
            # 输出日志（未匹配到实体时提示排查方向）
            self.logger.info(f"设备ID：{device_id} | 类型：{device['device_type']} | 前缀：{device['raw_prefix']}")
            self.logger.info(f"  匹配属性：state={state_status}，power={power_status}，energy={energy_status}，current={current_status}，voltage={voltage_status}")
            if not entities:
                self.logger.warning(f"  ⚠️  未匹配到任何实体！请检查：1. 前缀是否包含在HA实体ID中；2. HA中是否存在该前缀的switch/sensor实体")
            else:
                self.logger.info(f"  实体映射：{entities}")

        self.logger.info("\n" + "=" * 60)
