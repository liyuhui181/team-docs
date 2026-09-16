"""
本地测试脚本 - 验证涂鸦云 MQTT 连接
在 PC 上运行，模拟 ECM50-A 的连接和数据上报

用途:
    在部署到 ECM50-A 设备之前，先在 PC 上验证 MQTT 连接是否正常、
    凭证计算是否正确、数据上报是否成功。验证通过后再移植到设备端。

依赖:
    pip install paho-mqtt

运行方式:
    python test_tuya_mqtt.py

paho-mqtt v2 API 说明:
    paho-mqtt 2.x 使用 callback_api_version=VERSION2，
    回调函数签名为 (client, userdata, flags, reason_code, properties)，
    与 1.x 的 (client, userdata, flags, rc) 不同。
"""

import ssl
import time
import hmac
import json
import paho.mqtt.client as mqtt

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


def generate_credentials():
    """
    生成涂鸦 MQTT 连接三元组 (Client ID / Username / Password)

    签名算法: HMAC-SHA256
    - Client ID: tuyalink_{DeviceID}
    - Username: {DeviceID}|signMethod=hmacSha256,timestamp={时间戳},secureMode=1,accessType=1
    - Password: hmacSha256("deviceId={DeviceID},timestamp={时间戳},secureMode=1,accessType=1", DeviceSecret)

    Returns:
        tuple: (client_id, username, password)
    """
    # 10 位 Unix 时间戳 (秒级)
    timestamp = str(int(time.time()))

    # Client ID: 固定前缀 + 设备 ID
    client_id = f"tuyalink_{DEVICE_ID}"

    # Username: 设备 ID + 参数列表，用 | 分隔
    username = f"{DEVICE_ID}|signMethod=hmacSha256,timestamp={timestamp},secureMode=1,accessType=1"

    # Password: 对 content 做 HMAC-SHA256 签名
    content = f"deviceId={DEVICE_ID},timestamp={timestamp},secureMode=1,accessType=1"
    password = hmac.new(
        DEVICE_SECRET.encode("utf-8"),
        content.encode("utf-8"),
        digestmod="sha256"
    ).hexdigest().zfill(64)  # 确保结果为 64 位 hex 字符串

    return client_id, username, password


def on_connect(client, userdata, flags, reason_code, properties):
    """
    MQTT 连接结果回调函数 (paho-mqtt v2 API)

    当客户端成功连接 (或连接失败) 到 MQTT Broker 时触发。
    reason_code == 0 表示连接成功。

    Args:
        client: paho MQTT 客户端实例
        userdata: 用户自定义数据 (未使用)
        flags: 连接标志位
        reason_code: 连接结果码 (0 = 成功)
        properties: MQTT v5 属性 (未使用)
    """
    if reason_code == 0:
        print("[连接成功] 已连接到涂鸦云!")
    else:
        print(f"[连接失败] 返回码: {reason_code}")


def on_message(client, userdata, msg):
    """
    MQTT 消息回调函数

    当收到云端下发的消息时触发 (例如属性设置命令)。

    Args:
        client: paho MQTT 客户端实例
        userdata: 用户自定义数据 (未使用)
        msg: MQTT 消息对象，包含 topic (主题) 和 payload (内容)
    """
    print(f"\n[收到消息] Topic: {msg.topic}")
    print(f"[消息内容] {msg.payload.decode()}")


def on_disconnect(client, userdata, flags, reason_code, properties):
    """
    MQTT 断开连接回调函数 (paho-mqtt v2 API)

    当客户端与 Broker 断开连接时触发。

    Args:
        client: paho MQTT 客户端实例
        userdata: 用户自定义数据 (未使用)
        flags: 断开标志位
        reason_code: 断开原因码
        properties: MQTT v5 属性 (未使用)
    """
    print(f"[断开连接] 返回码: {reason_code}")


def main():
    """
    主函数 - 执行完整的 MQTT 连接测试流程

    测试流程:
        1. 生成 MQTT 连接凭证
        2. 创建 paho 客户端并配置 TLS
        3. 连接涂鸦 MQTT 服务器
        4. 订阅属性设置 Topic (接收云端控制指令)
        5. 发布物模型查询
        6. 上报初始属性数据
        7. 进入主循环，每 10 秒定时上报一次
    """
    print("=" * 60)
    print("  涂鸦云 MQTT 连接测试 (PC 模拟 ECM50-A)")
    print("=" * 60)
    print(f"  ProductID    : {PRODUCT_ID}")
    print(f"  DeviceID     : {DEVICE_ID}")
    print(f"  Broker        : {MQTT_BROKER}:{MQTT_PORT}")
    print()

    # 生成 MQTT 连接凭证
    client_id, username, password = generate_credentials()
    print(f"  Client ID     : {client_id}")
    print(f"  Username      : {username}")
    print(f"  Password      : {password}")
    print("=" * 60)

    # 创建 MQTT 客户端 (使用 paho-mqtt v2 回调 API)
    client = mqtt.Client(
        callback_api_version=mqtt.CallbackAPIVersion.VERSION2,  # v2 回调签名
        client_id=client_id,
        clean_session=True  # 清洁会话: 每次连接不恢复上次订阅状态
    )
    client.username_pw_set(username, password)  # 设置 MQTT 用户名和密码
    client.on_connect = on_connect              # 设置连接回调
    client.on_message = on_message              # 设置消息回调
    client.on_disconnect = on_disconnect        # 设置断开回调

    # TLS/SSL 配置 - 涂鸦要求使用 TLS 加密连接
    context = ssl.create_default_context()
    context.check_hostname = False      # 不校验主机名
    context.verify_mode = ssl.CERT_NONE # 不验证证书 (开发环境简化配置)
    client.tls_set_context(context)

    # 发起连接
    print("\n正在连接涂鸦 MQTT 服务器...")
    try:
        client.connect(MQTT_BROKER, MQTT_PORT, keepalive=60)  # keepalive=60s 心跳
    except Exception as e:
        print(f"[连接异常] {e}")
        print("\n可能原因:")
        print("  1. 设备未在涂鸦平台激活或授权码未分配")
        print("  2. 设备凭证 (DeviceID/DeviceSecret) 错误")
        print("  3. 网络无法访问 m1.tuyacn.com:8883")
        return

    # 订阅下行 Topic: 接收云端下发的属性设置命令
    # Topic 格式: tylink/{deviceId}/thing/property/set
    sub_topic = f"tylink/{DEVICE_ID}/thing/property/set"
    client.subscribe(sub_topic)
    print(f"[已订阅] {sub_topic}")

    # 启动后台网络循环 (paho 在独立线程中处理网络 I/O)
    client.loop_start()

    # 等待连接完全建立
    time.sleep(2)

    # 上报物模型查询 - 告知云端设备支持的属性列表
    # Topic 格式: tylink/{deviceId}/thing/model/get
    model_topic = f"tylink/{DEVICE_ID}/thing/model/get"
    model_payload = json.dumps({"data": {"properties": [{"code": "switch_1", "mode": "rw"}]}})
    client.publish(model_topic, model_payload)
    print(f"[已发布] 物模型查询 -> {model_topic}")
    print(f"  Payload: {model_payload}")

    # 上报初始属性数据 - 设备上线后首次上报当前状态
    # Topic 格式: tylink/{deviceId}/thing/property/report
    report_topic = f"tylink/{DEVICE_ID}/thing/property/report"
    props = {"switch_1": {"value": True, "time": int(time.time() * 1000)}}
    report_payload = json.dumps({"data": props})
    client.publish(report_topic, report_payload)
    print(f"[已发布] 属性上报 -> {report_topic}")
    print(f"  Payload: {report_payload}")

    # 主循环: 保持连接，定时上报数据
    print("\n[运行中] 按 Ctrl+C 退出...")
    try:
        while True:
            time.sleep(10)  # 每 10 秒上报一次

            # 定时上报属性数据
            props = {"switch_1": {"value": True, "time": int(time.time() * 1000)}}
            payload = json.dumps({"data": props})
            client.publish(report_topic, payload)
            print(f"[定时上报] {payload}")
    except KeyboardInterrupt:
        # 用户按 Ctrl+C 退出
        print("\n[退出]")
        client.loop_stop()     # 停止后台网络线程
        client.disconnect()    # 断开 MQTT 连接


if __name__ == "__main__":
    main()
