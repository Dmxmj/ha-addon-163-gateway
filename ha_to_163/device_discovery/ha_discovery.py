import requests
import re
import logging
import time
from typing import Dict
from .base_discovery import BaseDiscovery

# 扩展属性映射（物模型属性名 ← HA实体属性名/关键词）
# 匹配逻辑：通过实体ID中包含的关键词来映射到物模型属性
PROPERTY_MAPPING = {
    # ========== 温度 ==========
    "temperature": "temp",
    "temp": "temp",
    "temp_c": "temp",
    "temp_f": "temp",
    "temperature_p": "temp",      # sensor.xxx_temperature_p_3_7
    "temp_p": "temp",
    
    # ========== 湿度 ==========
    "humidity": "hum",
    "hum": "hum",
    "humidity_percent": "hum",
    "humidity_p": "hum",
    "hum_p": "hum",
    "relative_humidity": "hum",   # sensor.xxx_relative_humidity_p_3_1
    "relative_humidity_p": "hum",
    
    # ========== 电量/电池 ==========
    "battery": "battery",
    "batt": "battery",
    "battery_level": "battery",   # sensor.xxx_battery_level_p_4_1
    "battery_percent": "battery",
    "battery_p": "battery",
    "batt_p": "battery",
    "battery_level_p": "battery",
    
    # ========== 充电状态 ==========
    "charging_state": "charging",  # sensor.xxx_charging_state_p_4_2
    "charging_state_p": "charging",
    "charging": "charging",
    "charge_state": "charging",
    
    # ========== 二氧化碳 CO2 ==========
    "carbon_dioxide": "co2",
    "co2": "co2",
    "co2_density": "co2",         # sensor.xxx_co2_density_p_3_8
    "co2_level": "co2",
    "carbon_dioxide_p": "co2",
    "co2_p": "co2",
    "co2_density_p": "co2",
    
    # ========== PM2.5 ==========
    "pm25": "pm2_5",
    "pm2_5": "pm2_5",
    "pm25_density": "pm2_5",
    "pm2_5_density": "pm2_5",     # sensor.xxx_pm2_5_density_p_3_4
    "particulate_matter_2_5": "pm2_5",
    "pm25_p": "pm2_5",
    "pm2_5_p": "pm2_5",
    "pm2_5_density_p": "pm2_5",
    
    # ========== PM10 ==========
    "pm10": "pm10",
    "pm10_density": "pm10",       # sensor.xxx_pm10_density_p_3_5
    "particulate_matter_10": "pm10",
    "pm10_p": "pm10",
    "pm10_density_p": "pm10",
    
    # ========== TVOC 挥发性有机物 ==========
    "tvoc": "tvoc",
    "volatile_organic_compounds": "tvoc",
    "voc": "tvoc",
    "tvoc_density": "tvoc",       # sensor.xxx_tvoc_density_p_3_9
    "tvoc_p": "tvoc",
    "voc_p": "tvoc",
    "tvoc_density_p": "tvoc",
    
    # ========== 噪音 ==========
    "noise": "noise",
    "sound_level": "noise",
    "noise_level": "noise",
    "sound": "noise",
    "noise_p": "noise",
    "sound_p": "noise",
    "noise_decibel": "noise",     # sensor.xxx_noise_decibel_p_10_2
    "noise_decibel_p": "noise",
    "decibel": "noise",
    
    # ========== 开关状态 ==========
    "state": "state",
    "switch": "state",
    "power": "state",
    
    # ========== 电力参数 ==========
    "voltage": "voltage",
    "volt": "voltage",
    "current": "current",
    "ampere": "current",
    "power": "active_power",
    "active_power": "active_power",
    "energy": "energy",
    "total_energy": "energy",
    "frequency": "frequency",
    "freq": "frequency",
}


class HADiscovery(BaseDiscovery):
    """基于HA实体的设备发现"""
    
    def __init__(self, config, ha_headers):
        super().__init__(config, "ha_discovery")
        self.ha_url = config.get("ha_url")
        self.ha_headers = ha_headers
        self.entities = []  # 存储HA中的实体列表
        self.sub_devices = [d for d in config.get("sub_devices", []) if d.get("enabled", True)]
    
    def load_ha_entities(self) -> bool:
        """从HA API加载实体列表"""
        try:
            self.logger.info(f"从HA获取实体列表: {self.ha_url}/api/states")
            resp = None
            retry_attempts = self.config.get("retry_attempts", 5)
            retry_delay = self.config.get("retry_delay", 3)
            
            # 带重试的API调用
            for attempt in range(retry_attempts):
                try:
                    resp = requests.get(
                        f"{self.ha_url}/api/states",
                        headers=self.ha_headers,
                        timeout=10
                    )
                    resp.raise_for_status()
                    break
                except Exception as e:
                    self.logger.warning(f"获取HA实体尝试 {attempt+1}/{retry_attempts} 失败: {e}")
                    if attempt < retry_attempts - 1:
                        time.sleep(retry_delay)
            
            if not resp or resp.status_code != 200:
                self.logger.error(f"HA实体获取失败，状态码: {resp.status_code if resp else '无响应'}")
                return False
            
            self.entities = resp.json()
            self.logger.info(f"HA共返回 {len(self.entities)} 个实体")
            
            # 输出传感器实体列表（便于排查）
            sensor_entities = [e.get('entity_id') for e in self.entities if e.get('entity_id', '').startswith('sensor.')]
            self.logger.debug(f"HA中的传感器实体列表: {sensor_entities}")
            return True
        except Exception as e:
            self.logger.error(f"加载HA实体失败: {e}")
            return False
    
    def match_entities_to_devices(self) -> Dict:
        """将HA实体匹配到子设备"""
        matched_devices = {}
        
        for device in self.sub_devices:
            device_id = device["id"]
            matched_devices[device_id] = {
                "config": device,
                "sensors": {},  # 存储 {属性: 实体ID} 映射
                "last_data": None
            }
            self.logger.info(f"开始匹配设备: {device_id}（前缀: {device['ha_entity_prefix']}）")
        
        # 遍历HA实体进行匹配
        for entity in self.entities:
            entity_id = entity.get("entity_id", "")
            if not entity_id.startswith("sensor."):
                continue  # 只处理传感器实体
            
            # 【重要】排除单位类实体（如 temperature_unit, tvoc_unit 等）
            # 这些实体返回的是单位字符串（如 "CelUnit", "PPB"），不是数值
            if "_unit_" in entity_id or entity_id.endswith("_unit"):
                self.logger.debug(f"跳过单位实体: {entity_id}")
                continue
            
            # 提取实体属性（用于多维度匹配）
            attributes = entity.get("attributes", {})
            device_class = attributes.get("device_class", "").lower()
            friendly_name = attributes.get("friendly_name", "").lower()
            self.logger.debug(f"处理实体: {entity_id} (device_class: {device_class}, friendly_name: {friendly_name})")
            
            # 匹配到对应的子设备
            for device_id, device_data in matched_devices.items():
                device = device_data["config"]
                prefix = device["ha_entity_prefix"]
                
                # 宽松匹配：前缀包含在实体ID中（解决命名偏差）
                if prefix in entity_id:
                    # 提取实体类型（如"sensor.hz2_01_temperature_p_3_7" → "temperature_p_3_7"）
                    entity_suffix = entity_id.replace(f"sensor.{prefix}", "").strip('_')
                    entity_type_parts = entity_suffix.split('_')
                    if not entity_suffix:
                        continue
                    
                    # 多维度匹配属性
                    property_name = None
                    
                    # 方式1：通过device_class匹配（最可靠）
                    if device_class in PROPERTY_MAPPING:
                        property_name = PROPERTY_MAPPING[device_class]
                        self.logger.debug(f"通过device_class匹配: {device_class} → {property_name}")
                    
                    # 方式2：通过组合关键词匹配（如 "relative_humidity", "co2_density"）
                    if not property_name:
                        # 尝试匹配多词组合（优先级更高）
                        for i in range(len(entity_type_parts)):
                            for j in range(i + 1, min(i + 4, len(entity_type_parts) + 1)):
                                combo = '_'.join(entity_type_parts[i:j])
                                if combo in PROPERTY_MAPPING:
                                    property_name = PROPERTY_MAPPING[combo]
                                    self.logger.debug(f"通过组合关键词匹配: {combo} → {property_name}")
                                    break
                            if property_name:
                                break
                    
                    # 方式3：通过单个实体ID部分匹配
                    if not property_name:
                        for part in entity_type_parts:
                            if part in PROPERTY_MAPPING:
                                property_name = PROPERTY_MAPPING[part]
                                self.logger.debug(f"通过实体ID部分匹配: {part} → {property_name}")
                                break
                    
                    # 方式4：通过friendly_name匹配
                    if not property_name:
                        for key in PROPERTY_MAPPING:
                            if key in friendly_name:
                                property_name = PROPERTY_MAPPING[key]
                                self.logger.debug(f"通过friendly_name匹配: {key} → {property_name}")
                                break
                    
                    # 验证属性是否在设备支持列表中
                    if property_name and property_name in device["supported_properties"]:
                        device_data["sensors"][property_name] = entity_id
                        self.logger.info(f"匹配成功: {entity_id} → {property_name}（设备: {device_id}）")
                        break  # 已匹配到设备，跳出循环
        
        # 输出匹配结果
        for device_id, device_data in matched_devices.items():
            sensors = {k: v for k, v in device_data["sensors"].items()}
            self.logger.info(f"设备 {device_id} 匹配结果: {sensors}")
        
        return matched_devices
    
    def discover(self) -> Dict:
        """执行发现流程（主入口）"""
        self.logger.info("开始基于HA实体的设备发现...")
        
        # 第一步：加载HA实体
        if not self.load_ha_entities():
            return {}
        
        # 第二步：匹配实体到设备
        matched_devices = self.match_entities_to_devices()
        self.logger.info(f"设备发现完成，共匹配 {len(matched_devices)} 个设备")
        return matched_devices
    
