"""
ECM50-A 接入涂鸦云 - MicroPython 主程序
将此脚本上传到 ECM50-A 工控机运行

硬件: 亿佰特 ECM50-A (ESP32-S3, MicroPython)
云平台: 涂鸦 IoT 开发平台 (TuyaLink MQTT 标准协议)

部署步骤:
    1. 修改本文件中的 WiFi_SSID 和 WIFI_PASSWORD
    2. 通过 ECM50-A 的文件管理工具或 IDE 上传脚本
    3. 在 ECM50-A 上执行: import ecm50a_tuya_main; ecm50a_tuya_main.main()
"""

import network
import time
import hmac
import ubinascii
from umqtt.simple import MQTTClient

# ============================================================================
# WiFi 配置 - 部署前必须修改为实际 WiFi 信息
# ============================================================================
WIFI_SSID = "your_wifi_ssid"        # WiFi 名称
WIFI_PASSWORD = "your_wifi_password" # WiFi 密码

# ============================================================================
# 涂鸦云设备凭证 (在涂鸦 IoT 开发平台创建设备时获取)
# ============================================================================
PRODUCT_ID = "deihosbfawqqi8ac"        # 产品 ID
DEVICE_ID = "263c9d32705d72a956qrgj"   # 设备 ID
DEVICE_SECRET = "SnZ9FfQ3zZODjr6e"      # 设备密钥

# ============================================================================
# 涂鸦 MQTT 接入配置 (中国数据中心)
# ============================================================================
MQTT_BROKER = "m1.tuyacn.com"  # 涂鸦 MQTT Broker 地址
MQTT_PORT = 8883               # TLS 加密端口


def connect_wifi():
    """
    连接 WiFi 网络

    ESP32-S3 的 WiFi 连接流程:
        1. 激活 STA 模式 (Station 模式，即客户端模式)
        2. 调用 connect() 发起连接
        3. 阻塞等待连接成功 (轮询 isconnected() 状态)

    Returns:
        network.WLAN: WiFi 接口对象 (已连接状态)
    """
    # 创建 STA 接口 (Station 模式)
    wlan = network.WLAN(network.STA_IF)
    wlan.active(True)  # 激活 WiFi 接口

    if not wlan.isconnected():
        print(f"正在连接 WiFi: {WIFI_SSID}")
        wlan.connect(WIFI_SSID, WIFI_PASSWORD)

        # 阻塞等待连接成功，每 0.5 秒检查一次状态
        while not wlan.isconnected():
            time.sleep(0.5)
            print(".", end="")
        print()

    # 打印分配到的 IP 地址
    print(f"WiFi 已连接, IP: {wlan.ifconfig()[0]}")
    return wlan


def generate_mqtt_credentials():
    """
    生成涂鸦 MQTT 连接三元组 (Client ID / Username / Password)

    签名算法: HMAC-SHA256
    - Client ID: tuyalink_{DeviceID}
    - Username: {DeviceID}|signMethod=hmacSha256,timestamp={时间戳},secureMode=1,accessType=1
    - Password: hmacSha256("deviceId={DeviceID},timestamp={时间戳},secureMode=1,accessType=1", DeviceSecret)

    注意: MicroPython 的 hmac 模块用法与 CPython 相同，
    但 ubinascii 用于二进制数据编码转换。

    Returns:
        tuple: (client_id, username, password)
    """
    # 10 位 Unix 时间戳 (秒级)
    timestamp = str(int(time.time()))

    # Client ID: 固定前缀 + 设备 ID
    client_id = f"tuyalink_{DEVICE_ID}"

    # Username: 设备 ID + 参数列表，用 | 分隔
    username = f"{DEVICE_ID}|signMethod=hmacSha256,timestamp={timestamp},secureMode=1,accessType=1"

    # Password: 对 content 做 HMAC-SHA256 签名，使用 DeviceSecret 作为密钥
    content = f"deviceId={DEVICE_ID},timestamp={timestamp},secureMode=1,accessType=1"
    password = hmac.new(
        DEVICE_SECRET.encode("utf-8"),
        content.encode("utf-8"),
        digestmod="sha256"
    ).hexdigest()

    # 确保结果为 64 位十六进制字符串
    password = password.zfill(64)

    return client_id, username, password


def get_timestamp():
    """获取当前 10 位 Unix 时间戳 (秒级)"""
    return str(int(time.time()))


# ============================================================================
# 涂鸦 TuyaLink Topic 定义
#
# Topic 命名规则: tylink/{deviceId}/thing/{功能类型}/{操作}
# - property: 属性相关 (上报/设置/查询)
# - model: 物模型相关
# - event: 事件相关
# ============================================================================

def topic_property_report():
    """
    属性上报 Topic: 设备 -> 云

    设备通过此 Topic 主动向涂鸦云上报当前属性值 (如温度、湿度等)。
    涂鸦云端接收后更新设备影子状态，前端可查询到最新数据。
    """
    return f"tylink/{DEVICE_ID}/thing/property/report"

def topic_property_set():
    """
    属性设置 Topic: 云 -> 设备 (需订阅)

    涂鸦云端 (或通过 App/面板) 向设备下发控制指令时使用此 Topic。
    设备必须订阅此 Topic 才能接收属性设置命令。
    """
    return f"tylink/{DEVICE_ID}/thing/property/set"

def topic_property_get():
    """
    属性查询 Topic: 设备 -> 云

    设备主动向涂鸦云查询当前属性值 (较少使用)。
    """
    return f"tylink/{DEVICE_ID}/thing/property/get"

def topic_model_get():
    """
    物模型查询 Topic: 设备 -> 云

    设备通过此 Topic 告知云端自身支持的属性列表 (物模型)。
    """
    return f"tylink/{DEVICE_ID}/thing/model/get"

def topic_event_trigger():
    """
    事件触发 Topic: 设备 -> 云

    设备通过此 Topic 上报事件 (如报警、状态变化等)。
    """
    return f"tylink/{DEVICE_ID}/thing/event/trigger"


def build_property_payload(properties: dict) -> str:
    """
    构建属性上报的 JSON Payload

    涂鸦 TuyaLink 标准协议的属性上报格式:
    {
        "data": {
            "属性标识符": {
                "value": 属性值,
                "time": 13位毫秒时间戳
            }
        }
    }

    Args:
        properties: 属性字典，如 {"switch_1": True, "power": 12.5}

    Returns:
        str: JSON 格式的 payload 字符串 (使用 MicroPython 的 ujson 模块)
    """
    # 13 位毫秒级时间戳
    ts = int(time.time() * 1000)

    # 为每个属性添加 value 和 time 字段
    data = {}
    for key, value in properties.items():
        data[key] = {"value": value, "time": ts}

    # MicroPython 使用 ujson 替代标准库 json
    import ujson
    payload = ujson.dumps({"data": data})
    return payload


def build_event_payload(event_code: str, event_data: dict) -> str:
    """
    构建事件上报的 JSON Payload

    事件上报格式:
    {
        "data": {
            "事件标识符": {
                "value": 事件数据,
                "time": 13位毫秒时间戳
            }
        }
    }

    Args:
        event_code: 事件标识符 (如 "over_temperature_alarm")
        event_data: 事件数据字典

    Returns:
        str: JSON 格式的 payload 字符串
    """
    import ujson
    payload = ujson.dumps({
        "data": {
            event_code: {
                "value": event_data,
                "time": int(time.time() * 1000)
            }
        }
    })
    return payload


# ============================================================================
# MQTT 回调函数
# ============================================================================

def on_mqtt_message(topic, msg):
    """
    收到云端消息的回调函数 (MicroPython umqtt.simple 回调签名)

    umqtt.simple 的回调签名为 (topic, msg)，与 paho-mqtt 不同。
    topic 和 msg 均为 bytes 类型，需 decode 为字符串。

    当收到云端下发的属性设置命令 (property/set) 时，
    可在此函数中解析并控制 ECM50-A 的 IO 端口。

    Args:
        topic: 消息主题 (bytes)
        msg: 消息内容 (bytes)
    """
    # 将 bytes 转换为字符串
    topic_str = topic.decode() if isinstance(topic, bytes) else topic
    msg_str = msg.decode() if isinstance(msg, bytes) else msg

    print(f"\n[收到消息] Topic: {topic_str}")
    print(f"[消息内容] {msg_str}")

    # 处理属性设置命令
    if "property/set" in topic_str:
        print("[处理] 收到属性设置命令")
        # TODO: 解析 msg_str 中的属性值，控制 ECM50-A 的 IO 端口
        # TODO: 收到控制指令后可回复上报确认
        pass


# ============================================================================
# 主程序
# ============================================================================

def main():
    """
    主函数 - ECM50-A 接入涂鸦云的完整流程

    流程:
        1. 连接 WiFi 网络
        2. 生成 MQTT 连接凭证
        3. 创建 MQTT 客户端并连接涂鸦云
        4. 订阅云端下行 Topic (接收控制指令)
        5. 上报设备物模型 (可选)
        6. 上报初始属性数据
        7. 进入主循环: 定期上报传感器数据
    """
    print("=" * 50)
    print("  ECM50-A 接入涂鸦云")
    print("  设备 ID:", DEVICE_ID)
    print("=" * 50)

    # ---- 步骤 1: 连接 WiFi ----
    connect_wifi()

    # ---- 步骤 2: 生成 MQTT 凭证 ----
    client_id, username, password = generate_mqtt_credentials()
    print(f"MQTT Client ID: {client_id}")
    print(f"MQTT Username: {username}")

    # ---- 步骤 3: 创建 MQTT 客户端并连接 ----
    # MicroPython 的 SSL 参数: cert_req=0 表示不验证证书
    ssl_params = {"cert_req": 0}

    # 使用 umqtt.simple.MQTTClient 创建客户端
    mqtt = MQTTClient(
        client_id=client_id,
        server=MQTT_BROKER,
        port=MQTT_PORT,
        user=username,
        password=password,
        ssl=True,               # 启用 TLS 加密
        ssl_params=ssl_params,   # SSL 参数
    )
    mqtt.set_callback(on_mqtt_message)  # 设置消息回调

    print(f"\n正在连接涂鸦 MQTT 服务器 {MQTT_BROKER}:{MQTT_PORT}...")
    try:
        mqtt.connect()
        print("[连接成功] 已连接到涂鸦云!")
    except Exception as e:
        print(f"[连接失败] {e}")
        return

    # ---- 步骤 4: 订阅云端下行 Topic ----
    # 订阅属性设置 Topic，接收云端下发的控制指令
    sub_topics = [
        topic_property_set(),  # 属性设置 (云 -> 设备)
    ]
    for t in sub_topics:
        mqtt.subscribe(t)
        print(f"[已订阅] {t}")

    # ---- 步骤 5: 上报设备物模型 (可选) ----
    # 告知云端设备支持的属性列表及读写模式
    model_payload = '{"data":{"properties":[{"code":"switch_1","mode":"rw"},{"code":"power","mode":"r"}]}}'
    mqtt.publish(topic_model_get(), model_payload)
    print(f"[已发布] 物模型查询 -> {topic_model_get()}")

    # ---- 步骤 6: 上报初始属性数据 ----
    # 设备上线后首次上报当前状态
    initial_props = {
        "switch_1": True,
    }
    payload = build_property_payload(initial_props)
    mqtt.publish(topic_property_report(), payload)
    print(f"[已发布] 属性上报 -> {topic_property_report()}")
    print(f"  Payload: {payload}")

    # ---- 步骤 7: 主循环 - 定期上报数据 ----
    report_count = 0
    while True:
        try:
            # 检查是否有云端消息 (非阻塞)
            mqtt.check_msg()
            time.sleep(1)

            # 每 10 秒上报一次属性 (report_count 满 10 次约 10 秒)
            report_count += 1
            if report_count >= 10:
                report_count = 0

                # TODO: 读取 ECM50-A 实际传感器数据 (如温度、湿度、IO 状态等)
                # 示例: 从模拟量输入引脚读取电压值，转换为温度
                # temp = read_temperature_sensor()
                # humidity = read_humidity_sensor()

                props = {
                    "switch_1": True,  # 示例: 上报开关状态
                }
                payload = build_property_payload(props)
                mqtt.publish(topic_property_report(), payload)
                print(f"[定时上报] {payload}")

        except OSError as e:
            # 网络异常处理 - MicroPython 常见 OSError:
            # - ETIMEDOUT: 连接超时
            # - ECONNRESET: 连接被重置
            print(f"[网络异常] {e}, 尝试重连...")
            time.sleep(5)

            try:
                mqtt.connect()
                print("[重连成功]")
            except:
                print("[重连失败, 5秒后重试]")
                time.sleep(5)


if __name__ == "__main__":
    main()
