import paho.mqtt.client as mqtt
import logging
import time
import hmac
import hashlib
import json
import requests
import threading
from typing import Dict, Any, Optional

class MQTTClient:
    """MQTT客户端（修复：连接校验+心跳+非阻塞重连）"""
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.logger = logging.getLogger("mqtt_client")
        self.client: Optional[mqtt.Client] = None
        self.connected = False
        self.last_time_sync = 0
        self.reconnect_delay = 1
        self.running = True  # 控制心跳线程
        self.ha_headers = {
            "Authorization": f"Bearer {config['ha_token']}",
            "Content-Type": "application/json"
        }
        self.start_heartbeat()  # 启动心跳检测

    def start_heartbeat(self, interval: int = 30):
        """启动心跳检测线程（主动维护连接）"""
        def heartbeat_worker():
            while self.running:
                time.sleep(interval)
                if not self.connected:
                    self.logger.warning("心跳检测发现MQTT连接断开，触发重连...")
                    self._schedule_reconnect()
        threading.Thread(target=heartbeat_worker, daemon=True, name="MQTT-Heartbeat").start()

    def _init_mqtt_client(self):
        """初始化MQTT客户端"""
        try:
            client_id = self.config["gateway_device_name"]
            username = self.config["gateway_product_key"]
            password = self._generate_mqtt_password(self.config["gateway_device_secret"])

            self.client = mqtt.Client(client_id=client_id, clean_session=True, protocol=mqtt.MQTTv311)
            self.client.username_pw_set(username=username, password=password)

            if self.config.get("use_ssl", False):
                self.client.tls_set()
                self.logger.info("已启用SSL加密连接")

            self.client.on_connect = self._on_connect
            self.client.on_disconnect = self._on_disconnect
            self.client.on_message = self._on_message
            self.logger.info("MQTT客户端初始化完成")
        except Exception as e:
            self.logger.error(f"MQTT客户端初始化失败: {e}")
            raise

    def _generate_mqtt_password(self, device_secret: str) -> str:
        """生成MQTT动态密码"""
        try:
            if time.time() - self.last_time_sync > 300:
                self._sync_time()
            timestamp = int(time.time())
            counter = timestamp // 300
            self.logger.debug(f"当前counter: {counter}（时间戳: {timestamp}）")

            counter_bytes = str(counter).encode('utf-8')
            secret_bytes = device_secret.encode('utf-8')
            hmac_obj = hmac.new(secret_bytes, counter_bytes, hashlib.sha256)
            token = hmac_obj.digest()[:10].hex().upper()
            return f"v1:{token}"
        except Exception as e:
            self.logger.error(f"生成MQTT密码失败: {e}")
            raise

    def _sync_time(self):
        """NTP时间同步"""
        try:
            import ntplib
            ntp_client = ntplib.NTPClient()
            response = ntp_client.request(
                self.config.get("ntp_server", "ntp.n.netease.com"),
                version=3,
                timeout=5
            )
            self.last_time_sync = time.time()
            self.logger.info(f"NTP时间同步成功: {time.ctime(response.tx_time)}")
        except Exception as e:
            self.logger.warning(f"NTP时间同步失败（使用本地时间）: {e}")

    def connect(self) -> bool:
        """连接MQTT服务器（带超时重试）"""
        self._init_mqtt_client()
        try:
            port = self.config["wy_mqtt_port_ssl"] if self.config.get("use_ssl") else self.config["wy_mqtt_port_tcp"]
            self.logger.info(f"连接MQTT服务器: {self.config['wy_mqtt_broker']}:{port}")
            self.client.connect(self.config["wy_mqtt_broker"], port, keepalive=60)
            self.client.loop_start()

            # 等待连接成功（超时10秒）
            start_time = time.time()
            while not self.connected and (time.time() - start_time) < 10:
                time.sleep(0.1)

            if self.connected:
                self.logger.info("MQTT连接成功")
                return True
            else:
                self.logger.error("MQTT连接超时")
                return False
        except Exception as e:
            self.logger.error(f"MQTT连接失败: {e}")
            return False

    def disconnect(self):
        """断开MQTT连接"""
        self.running = False  # 停止心跳线程
        if self.client:
            self.client.loop_stop()
            self.client.disconnect()
            self.connected = False
            self.logger.info("MQTT连接已断开")

    def _on_connect(self, client: mqtt.Client, userdata: Any, flags: Dict, rc: int):
        """连接回调"""
        if rc == 0:
            self.connected = True
            self.reconnect_delay = 1  # 重置重连延迟
            self.logger.info(f"MQTT连接成功（返回码: {rc}）")

            # 订阅控制主题
            for device in self.config.get("sub_devices", []):
                if not device.get("enabled", True):
                    continue
                standard_topic = f"sys/{device['product_key']}/{device['device_name']}/thing/service/property/set"
                common_topic = f"sys/{device['product_key']}/{device['device_name']}/service/CommonService"
                client.subscribe(standard_topic, qos=1)
                client.subscribe(common_topic, qos=1)
                self.logger.info(f"订阅控制Topic: {standard_topic}")
        else:
            self.connected = False
            self.logger.error(f"MQTT连接失败（返回码: {rc}）")
            self._schedule_reconnect()

    def _on_disconnect(self, client: mqtt.Client, userdata: Any, rc: int):
        """断开连接回调"""
        self.connected = False
        if rc != 0:
            self.logger.warning(f"MQTT异常断开（返回码: {rc}）")
            self._schedule_reconnect()
        else:
            self.logger.info("MQTT正常断开连接")

    def _schedule_reconnect(self):
        """非阻塞重连（指数退避）"""
        if self.reconnect_delay < 60:
            self.reconnect_delay *= 2
        self.logger.info(f"{self.reconnect_delay}秒后尝试重连...")
        
        def reconnect_worker():
            time.sleep(self.reconnect_delay)
            self.connect()
        
        threading.Thread(target=reconnect_worker, daemon=True, name="MQTT-Reconnect").start()

    def _on_message(self, client: mqtt.Client, userdata: Any, msg: mqtt.MQTTMessage):
        """接收控制消息"""
        try:
            payload = json.loads(msg.payload.decode())
            self.logger.info(f"收到消息: {msg.topic} → {json.dumps(payload, indent=2)}")
            topic_parts = msg.topic.split('/')
            if len(topic_parts) >= 3 and topic_parts[0] == "sys":
                product_key = topic_parts[1]
                device_name = topic_parts[2]
                command_id = payload.get("id", int(time.time() * 1000))
                self._handle_control_command(product_key, device_name, payload, command_id)
        except Exception as e:
            self.logger.error(f"解析消息失败: {e}，原始消息: {msg.payload.decode()}")

    def _handle_control_command(self, product_key: str, device_name: str, payload: dict, command_id: int):
        """处理控制指令"""
        target_device = next(
            (d for d in self.config.get("sub_devices", []) if d.get("product_key") == product_key and d.get("device_name") == device_name and d.get("enabled", True)),
            None
        )
        if not target_device:
            self.logger.warning(f"未找到设备: {product_key}/{device_name}")
            self._send_control_reply(product_key, device_name, command_id, success=False, error_msg="设备未找到")
            return

        target_params = payload.get("params", payload)
        if target_device["type"] in ("switch", "socket", "breaker") and "state" in target_params:
            self._control_device(target_device, target_params["state"], product_key, device_name, command_id)
        else:
            self._send_control_reply(product_key, device_name, command_id, success=False, error_msg="不支持的指令")

    def _control_device(self, device: dict, target_state: int, product_key: str, device_name: str, command_id: int):
        """控制设备状态"""
        ha_state = "on" if target_state == 1 else "off"
        entity_prefix = device["ha_entity_prefix"]
        try:
            resp = requests.get(f"{self.config['ha_url']}/api/states", headers=self.ha_headers, timeout=10)
            if resp.status_code != 200:
                self.logger.error(f"查询HA实体失败: {resp.status_code}")
                self._send_control_reply(product_key, device_name, command_id, success=False, error_msg="查询实体失败")
                return

            entities = resp.json()
            candidate_entities = [e["entity_id"] for e in entities if entity_prefix in e["entity_id"] and e["entity_id"].startswith("switch.")]
            if not candidate_entities:
                self.logger.error(f"未找到匹配实体: {entity_prefix}")
                self._send_control_reply(product_key, device_name, command_id, success=False, error_msg="未找到实体")
                return

            matched_entity = candidate_entities[0]
            control_resp = requests.post(
                f"{self.config['ha_url']}/api/services/switch/turn_{ha_state}",
                headers=self.ha_headers,
                json={"entity_id": matched_entity},
                timeout=10
            )
            if control_resp.status_code in (200, 201):
                self.logger.info(f"控制实体{matched_entity}成功（状态: {ha_state}）")
                self._send_control_reply(product_key, device_name, command_id, success=True)
            else:
                self.logger.error(f"控制实体{matched_entity}失败: {control_resp.status_code}")
                self._send_control_reply(product_key, device_name, command_id, success=False, error_msg="控制失败")
        except Exception as e:
            self.logger.error(f"控制设备异常: {e}")
            self._send_control_reply(product_key, device_name, command_id, success=False, error_msg=str(e))

    def _send_control_reply(self, product_key: str, device_name: str, command_id: int, success: bool, error_msg: str = ""):
        """发送控制回复"""
        reply_topic = f"sys/{product_key}/{device_name}/thing/service/property/set_reply"
        reply_payload = {
            "id": command_id,
            "code": 200 if success else 500,
            "msg": "success" if success else error_msg,
            "data": {}
        }
        self.client.publish(reply_topic, json.dumps(reply_payload), qos=1)
        self.logger.info(f"发送回复: {reply_topic} → {json.dumps(reply_payload)}")

    def publish(self, device_config: Dict[str, Any], payload: Dict[str, Any]) -> bool:
        """发布数据（带连接校验和QoS=1）"""
        # 检查连接，无效则重连
        if not self.connected or not self.client:
            self.logger.warning("MQTT连接无效，尝试重连...")
            if not self.connect():
                self.logger.error("重连失败，无法发布数据")
                return False

        # 构建主题
        topic = f"sys/{device_config['product_key']}/{device_config['device_name']}/thing/event/property/post"
        try:
            # QoS=1确保消息可靠传递，等待确认
            result = self.client.publish(
                topic=topic,
                payload=json.dumps(payload),
                qos=1
            )
            result.wait_for_publish(timeout=5)  # 等待服务器确认

            if result.rc == mqtt.MQTT_ERR_SUCCESS:
                self.logger.info(f"数据发布成功: {topic} → {json.dumps(payload, indent=2)}")
                return True
            else:
                self.logger.error(f"数据发布失败（错误码: {result.rc}）: {topic}")
                self._schedule_reconnect()
                return False
        except Exception as e:
            self.logger.error(f"发布数据异常: {str(e)}")
            self._schedule_reconnect()
            return False
