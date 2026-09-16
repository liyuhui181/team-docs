"""
涂鸦云 MQTT 参数计算工具
根据 ProductID / DeviceID / DeviceSecret 计算 MQTT 连接所需的三元组

用途:
    在连接涂鸦云 MQTT 之前，需要用 DeviceSecret 对特定内容做 HMAC-SHA256 签名，
    生成 Client ID / Username / Password 三个参数。本工具用于验证计算逻辑是否正确。

涂鸦 MQTT 标准协议参考:
    https://www.tuyaos.com/viewtopic.php?t=175

运行方式:
    python tuya_mqtt_auth.py
"""

import hmac
import time

# ============================================================================
# 涂鸦云设备凭证 (在涂鸦 IoT 开发平台创建设备时获取)
# ============================================================================
PRODUCT_ID = "deihosbfawqqi8ac"        # 产品 ID，标识设备所属产品类型
DEVICE_ID = "263c9d32705d72a956qrgj"   # 设备 ID，全网唯一
DEVICE_SECRET = "SnZ9FfQ3zZODjr6e"      # 设备密钥，用于 HMAC-SHA256 签名

# ============================================================================
# 涂鸦 MQTT 接入点 (中国数据中心)
# 不同区域使用不同域名:
#   中国区: m1.tuyacn.com
#   中欧区: m1.tuyaeu.com
#   美西区: m1.tuyaus.com
#   印度区: m1.tuyain.com
# ============================================================================
MQTT_BROKER = "m1.tuyacn.com"  # 涂鸦 MQTT Broker 地址
MQTT_PORT = 8883               # TLS 加密端口 (涂鸦强制要求 SSL/TLS 连接)


def generate_mqtt_credentials(device_id: str, device_secret: str) -> dict:
    """
    生成涂鸦 MQTT 连接所需的 Client ID / Username / Password

    涂鸦 MQTT 标准协议的鉴权方式:
        - Client ID: tuyalink_{DeviceID}
        - Username: {DeviceID}|signMethod=hmacSha256,timestamp={10位时间戳},secureMode=1,accessType=1
        - Password: hmacSha256(content, DeviceSecret)
          其中 content = "deviceId={DeviceID},timestamp={时间戳},secureMode=1,accessType=1"
          结果为 64 位十六进制字符串

    参数说明:
        - signMethod: 签名算法，涂鸦使用 hmacSha256
        - timestamp: 10 位 Unix 时间戳 (秒级)，涂鸦云端会校验时间有效性
        - secureMode: 安全模式，1 表示 TLS 连接
        - accessType: 访问类型，1 表示设备直连

    Args:
        device_id: 设备 ID (在涂鸦平台创建设备时获得)
        device_secret: 设备密钥 (在涂鸦平台创建设备时获得)

    Returns:
        dict: 包含 broker, port, client_id, username, password, timestamp 的字典
    """
    # 获取当前 10 位 Unix 时间戳 (秒级)
    timestamp = str(int(time.time()))

    # Client ID 格式: tuyalink_{deviceId}
    # 固定前缀 tuyalink_ 加上设备 ID
    client_id = f"tuyalink_{device_id}"

    # Username 格式: ${deviceId}|signMethod=hmacSha256,timestamp=${timestamp},secureMode=1,accessType=1
    # 用竖线 | 分隔设备 ID 和参数列表
    username = f"{device_id}|signMethod=hmacSha256,timestamp={timestamp},secureMode=1,accessType=1"

    # Password 的签名内容，按固定顺序拼接
    # 注意: 字段顺序必须与 Username 中的参数顺序一致
    content = f"deviceId={device_id},timestamp={timestamp},secureMode=1,accessType=1"

    # 使用 DeviceSecret 作为 HMAC 密钥，对 content 做 SHA256 签名
    # digestmod="sha256" 指定哈希算法
    password = hmac.new(
        device_secret.encode("utf-8"),  # 密钥: DeviceSecret
        content.encode("utf-8"),         # 明文: content 字符串
        digestmod="sha256"               # 哈希算法: SHA-256
    ).hexdigest()  # 返回十六进制字符串

    # 确保密码是 64 位十六进制字符，不足前面补零
    # SHA256 输出固定为 64 位 hex，zfill 是防御性处理
    password = password.zfill(64)

    return {
        "broker": MQTT_BROKER,
        "port": MQTT_PORT,
        "client_id": client_id,
        "username": username,
        "password": password,
        "timestamp": timestamp,
    }


def print_credentials():
    """
    打印 MQTT 连接参数到控制台

    输出格式:
        ========================================
          涂鸦云 MQTT 连接参数
        ========================================
          Broker Address : m1.tuyacn.com
          Broker Port    : 8883
          Client ID      : tuyalink_xxx
          Username       : xxx|signMethod=...
          Password       : 64位十六进制
          Timestamp      : 10位时间戳
        ========================================

    Returns:
        dict: 生成的凭证字典 (同 generate_mqtt_credentials 返回值)
    """
    creds = generate_mqtt_credentials(DEVICE_ID, DEVICE_SECRET)
    print("=" * 60)
    print("  涂鸦云 MQTT 连接参数")
    print("=" * 60)
    print(f"  Broker Address : {creds['broker']}")
    print(f"  Broker Port    : {creds['port']}")
    print(f"  Client ID      : {creds['client_id']}")
    print(f"  Username       : {creds['username']}")
    print(f"  Password       : {creds['password']}")
    print(f"  Timestamp      : {creds['timestamp']}")
    print("=" * 60)
    print()
    print("注意: Password 基于 timestamp 动态生成，每次运行会变化。")
    print("      连接时需要使用当前时间戳重新计算。")
    return creds


if __name__ == "__main__":
    print_credentials()
