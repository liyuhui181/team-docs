"""
涂鸦云数据模拟器 - 模拟 ECM50-A 上报冷库数据 (稳定挂机版)
循环上报模拟的温度、湿度、运行模式、在线状态，供前端测试

特性:
  - 断连时静默自动重连 (完全销毁旧 client 重新创建，避免状态残留)
  - 凭证每次重连刷新 (timestamp 过期后重新计算)
  - 异常自恢复 (网络抖动/服务器踢线不影响运行)
  - 简洁日志 (只在数据上报和重连时输出)

依赖: pip install paho-mqtt

运行方式:
  python tuya_simulator.py
  (后台持续运行，按 Ctrl+C 退出并上报离线状态)
"""

import ssl
import time
import hmac
import json
import random
import sys
import traceback
import paho.mqtt.client as mqtt

# ============================================================================
# 涂鸦云设备凭证 (在涂鸦 IoT 开发平台创建设备时获取)
# ============================================================================
PRODUCT_ID = "deihosbfawqqi8ac"        # 产品 ID，标识设备所属产品类型
DEVICE_ID = "263c9d32705d72a956qrgj"   # 设备 ID，全网唯一，用于云端鉴权
DEVICE_SECRET = "SnZ9FfQ3zZODjr6e"      # 设备密钥，用于 HMAC-SHA256 签名计算

# ============================================================================
# 涂鸦 MQTT 接入配置 (中国数据中心)
# 不同区域使用不同域名: 中国 m1.tuyacn.com / 中欧 m1.tuyaeu.com / 美西 m1.tuyaus.com
# ============================================================================
MQTT_BROKER = "m1.tuyacn.com"  # 涂鸦 MQTT Broker 地址
MQTT_PORT = 8883               # TLS 加密端口 (涂鸦强制要求 SSL/TLS 连接)

# ============================================================================
# 运行参数
# ============================================================================
REPORT_INTERVAL = 5        # 数据上报间隔 (秒)，前端轮询频率可据此设置
RECONNECT_DELAY = 3        # 断线后重连等待时间 (秒)

# 运行模式枚举定义，与涂鸦平台 DP110 的枚举值一致
# 0=制热, 1=制冷, 2=除霜
RUN_MODE_NAME = {0: "制热", 1: "制冷", 2: "除霜"}

# ============================================================================
# 全局状态变量
# ============================================================================
current_mode = 1       # 当前运行模式 (默认制冷)，可被云端指令修改
report_count = 0       # 累计上报次数 (用于日志显示)
reconnect_count = 0    # 连续重连次数 (用于判断首次连接还是重连)


def log(msg):
    """
    带时间戳的日志输出函数

    统一的日志格式: [YYYY-MM-DD HH:MM:SS] 消息内容
    每次输出后 flush 确保日志实时写入文件，不因缓冲区延迟

    Args:
        msg: 日志消息字符串
    """
    ts = time.strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{ts}] {msg}")
    sys.stdout.flush()


def generate_credentials():
    """
    生成涂鸦 MQTT 连接三元组 (Client ID / Username / Password)

    涂鸦 MQTT 标准协议的鉴权方式:
      - Client ID: tuyalink_{DeviceID}
      - Username: {DeviceID}|signMethod=hmacSha256,timestamp={10位时间戳},secureMode=1,accessType=1
      - Password: hmacSha256(content, DeviceSecret)
        其中 content = "deviceId={DeviceID},timestamp={时间戳},secureMode=1,accessType=1"
        结果为 64 位十六进制字符串，不足 64 位前面补零

    注意: timestamp 每次调用都会重新生成，因为涂鸦云端会校验时间戳有效性

    Returns:
        tuple: (client_id, username, password)
    """
    # 获取当前 10 位 Unix 时间戳 (秒级)
    timestamp = str(int(time.time()))

    # Client ID 固定前缀 tuyalink_ + DeviceID
    client_id = f"tuyalink_{DEVICE_ID}"

    # Username 中携带签名方法和时间戳，供云端验证
    username = f"{DEVICE_ID}|signMethod=hmacSha256,timestamp={timestamp},secureMode=1,accessType=1"

    # Password 的明文内容，按固定顺序拼接
    content = f"deviceId={DEVICE_ID},timestamp={timestamp},secureMode=1,accessType=1"

    # 使用 DeviceSecret 作为 HMAC 密钥，对 content 做 SHA256 签名
    password = hmac.new(
        DEVICE_SECRET.encode("utf-8"),
        content.encode("utf-8"),
        digestmod="sha256"
    ).hexdigest().zfill(64)  # zfill 确保结果为 64 位，不足前面补零

    return client_id, username, password


def on_message(client, userdata, msg):
    """
    MQTT 消息回调函数 - 处理云端下发的属性设置命令

    当涂鸦云端 (或通过 App/面板) 向设备下发控制指令时，会通过
    tylink/{deviceId}/thing/property/set Topic 发送 JSON 消息。
    本函数解析消息并更新运行模式。

    消息格式示例:
    {
        "data": {
            "cold_storage_run_mode": {
                "value": 0,
                "time": 1789567000000
            }
        }
    }

    Args:
        client: paho MQTT 客户端实例
        userdata: 用户自定义数据 (未使用)
        msg: MQTT 消息对象，包含 topic 和 payload
    """
    global current_mode

    payload_str = msg.payload.decode()
    log(f"收到云端指令: {msg.topic}")
    log(f"  内容: {payload_str}")

    try:
        data = json.loads(payload_str)
        # 检查是否包含属性数据
        if "data" in data:
            # 遍历所有下发的属性
            for prop_code, prop_data in data["data"].items():
                # 如果是运行模式属性，更新当前模式
                if prop_code == "cold_storage_run_mode":
                    new_mode = prop_data.get("value")
                    # 验证值合法性 (0=制热, 1=制冷, 2=除霜)
                    if new_mode in [0, 1, 2]:
                        current_mode = new_mode
                        log(f"  -> 运行模式切换: {RUN_MODE_NAME[current_mode]}")
    except Exception as e:
        log(f"  解析失败: {e}")


def build_report_payload(temp, humidity, run_mode, online):
    """
    构建涂鸦物模型属性上报的 JSON Payload

    涂鸦 TuyaLink 标准协议的属性上报格式:
    {
        "data": {
            "属性标识符": {
                "value": 属性值,
                "time": 13位毫秒时间戳
            }
        }
    }

    本设备上报 4 个功能点 (与涂鸦平台自定义功能定义一致):
      - cold_storage_temp       (DP108): 冷库温度 (°C)
      - cold_storage_humidity   (DP109): 冷库湿度 (%RH)
      - cold_storage_run_mode   (DP110): 运行模式 (0制热/1制冷/2除霜)
      - ECM50A_online           (DP111): 网关在线状态 (bool)

    Args:
        temp: 温度值 (float, °C)
        humidity: 湿度值 (float, %RH)
        run_mode: 运行模式 (int, 0/1/2)
        online: 在线状态 (bool)

    Returns:
        str: JSON 格式的 payload 字符串
    """
    # 13 位毫秒级时间戳，涂鸦要求使用毫秒级
    ts = int(time.time() * 1000)

    return json.dumps({"data": {
        "cold_storage_temp": {"value": temp, "time": ts},
        "cold_storage_humidity": {"value": humidity, "time": ts},
        "cold_storage_run_mode": {"value": run_mode, "time": ts},
        "ECM50A_online": {"value": online, "time": ts}
    }})


def simulate_cold_storage():
    """
    模拟冷库传感器数据

    根据当前运行模式生成不同范围的模拟数据:
      - 制冷模式 (1): 温度 -25~-18°C, 湿度 40-60% (典型冷冻库环境)
      - 制热模式 (0): 温度 5~15°C, 湿度 30-50% (化冰升温环境)
      - 除霜模式 (2): 温度 5~10°C, 湿度 50-70% (除霜过程温湿度偏高)

    Returns:
        tuple: (温度, 湿度, 运行模式, 在线状态)
    """
    if current_mode == 1:  # 制冷
        temp = round(random.uniform(-25, -18), 1)
        humidity = round(random.uniform(40, 60), 1)
    elif current_mode == 0:  # 制热
        temp = round(random.uniform(5, 15), 1)
        humidity = round(random.uniform(30, 50), 1)
    else:  # 除霜
        temp = round(random.uniform(5, 10), 1)
        humidity = round(random.uniform(50, 70), 1)
    return temp, humidity, current_mode, True


def connect_mqtt():
    """
    创建全新 MQTT 连接

    每次调用都会重新生成凭证 (timestamp 刷新)，创建全新的 paho Client 实例。
    断连重连时使用此函数，确保连接状态干净无残留。

    连接流程:
      1. 生成 MQTT 三元组 (Client ID / Username / Password)
      2. 创建 paho Client 并配置 TLS
      3. 发起连接并启动后台网络循环
      4. 等待连接确认 (最多 6 秒)
      5. 连接成功后订阅属性设置 Topic

    Returns:
        tuple: (client, connected)
            - client: paho MQTT 客户端实例 (连接失败时为 None)
            - connected: 是否连接成功 (bool)
    """
    # 每次连接使用全新凭证，确保 timestamp 是最新的
    client_id, username, password = generate_credentials()

    # 创建 paho MQTT v2 客户端
    client = mqtt.Client(
        callback_api_version=mqtt.CallbackAPIVersion.VERSION2,  # 使用 v2 回调 API
        client_id=client_id
    )
    client.username_pw_set(username, password)  # 设置用户名密码
    client.on_message = on_message              # 设置消息回调

    # TLS/SSL 配置 - 涂鸦要求使用 TLS 连接
    ctx = ssl.create_default_context()
    ctx.check_hostname = False   # 不校验主机名 (涂鸦 Broker 使用 IP 域名)
    ctx.verify_mode = ssl.CERT_NONE  # 不验证证书 (简化开发环境配置)
    client.tls_set_context(ctx)

    # 连接状态标志 (在闭包中修改)
    connected = False

    def on_conn(c, u, f, rc, p):
        """
        连接结果回调 (内嵌函数)

        paho-mqtt v2 的 on_connect 回调签名:
        (client, userdata, flags, reason_code, properties)

        reason_code 为 "Success" 或 0 表示连接成功
        """
        nonlocal connected
        connected = (str(rc) == "Success" or rc == 0)

    client.on_connect = on_conn

    try:
        # 发起 TCP 连接并启动 MQTT 后台网络循环
        client.connect(MQTT_BROKER, MQTT_PORT, keepalive=60)
        client.loop_start()  # 启动后台线程处理网络 I/O

        # 等待连接确认 (最多等待 6 秒 = 20 × 0.3s)
        for _ in range(20):
            if connected:
                break
            time.sleep(0.3)

        # 连接超时，清理资源
        if not connected:
            try:
                client.loop_stop()
                client.disconnect()
            except:
                pass
            return None, False

        # 连接成功，订阅属性设置 Topic (接收云端下发的控制指令)
        # Topic 格式: tylink/{deviceId}/thing/property/set
        set_topic = f"tylink/{DEVICE_ID}/thing/property/set"
        client.subscribe(set_topic)

        return client, True

    except Exception as e:
        log(f"连接异常: {e}")
        try:
            client.loop_stop()
            client.disconnect()
        except:
            pass
        return None, False


def run():
    """
    主运行循环 - 包含自动重连机制

    核心设计: 断连时完全销毁旧 client 并重新创建，避免 paho 内部状态残留导致的问题。

    流程:
      1. 调用 connect_mqtt() 建立连接
      2. 连接成功后进入数据上报循环 (每 REPORT_INTERVAL 秒上报一次)
      3. 发布失败时判定为断线，跳出上报循环
      4. 销毁旧 client，等待 RECONNECT_DELAY 秒后重新连接
      5. 循环以上步骤，实现 7x24 小时稳定运行
      6. Ctrl+C 退出时上报离线状态后干净退出
    """
    global report_count, reconnect_count

    log("=" * 60)
    log("涂鸦云数据模拟器 - 冷库设备 (挂机版)")
    log(f"DeviceID  : {DEVICE_ID}")
    log(f"Broker    : {MQTT_BROKER}:{MQTT_PORT}")
    log(f"上报间隔  : {REPORT_INTERVAL}s")
    log("=" * 60)

    # 属性上报 Topic: tylink/{deviceId}/thing/property/report
    report_topic = f"tylink/{DEVICE_ID}/thing/property/report"

    # 主循环: 连接 -> 上报 -> 断线重连 -> 连接 ...
    while True:
        # ---- 阶段1: 建立连接 ----
        if reconnect_count == 0:
            log("正在连接涂鸦云...")
        else:
            log(f"第{reconnect_count}次重连中...")

        client, ok = connect_mqtt()

        if not ok:
            reconnect_count += 1
            log(f"连接失败, {RECONNECT_DELAY}秒后重试")
            time.sleep(RECONNECT_DELAY)
            continue

        # 连接成功
        if reconnect_count > 0:
            log(f"重连成功 (第{reconnect_count}次)")
        else:
            log("连接成功，开始上报数据")
            log(f"功能点: temp/humidity/run_mode/online")
            log("-" * 60)

        reconnect_count = 0  # 重置重连计数

        # ---- 阶段2: 数据上报循环 ----
        try:
            while True:
                report_count += 1

                # 生成模拟传感器数据
                temp, humidity, run_mode, online = simulate_cold_storage()
                payload = build_report_payload(temp, humidity, run_mode, online)

                try:
                    # 发布属性到涂鸦云
                    info = client.publish(report_topic, payload)

                    # rc != 0 表示发布失败 (MQTT 未连接)
                    if info.rc != 0:
                        raise Exception(f"publish rc={info.rc}")

                    log(f"#{report_count} 温度={temp}°C 湿度={humidity}%RH 模式={RUN_MODE_NAME[run_mode]}({run_mode}) 在线=True")

                except Exception:
                    # 发布失败，说明连接已断开，跳出循环准备重连
                    report_count -= 1  # 不计入失败的上报次数
                    break

                # 等待下一次上报
                time.sleep(REPORT_INTERVAL)

        except KeyboardInterrupt:
            # ---- 用户手动退出 (Ctrl+C) ----
            log("收到退出信号，正在关闭...")
            try:
                # 上报离线状态，让前端感知设备下线
                ts = int(time.time() * 1000)
                off_payload = json.dumps({"data": {
                    "cold_storage_temp": {"value": 0, "time": ts},
                    "cold_storage_humidity": {"value": 0, "time": ts},
                    "cold_storage_run_mode": {"value": current_mode, "time": ts},
                    "ECM50A_online": {"value": False, "time": ts}  # 在线状态置为 False
                }})
                client.publish(report_topic, off_payload)
                log("已上报离线状态")
            except:
                pass
            try:
                client.loop_stop()
                client.disconnect()
            except:
                pass
            log("程序退出")
            return

        except Exception as e:
            # 捕获未预期的异常，记录详细堆栈
            log(f"主循环异常: {e}")
            log(traceback.format_exc())

        # ---- 阶段3: 清理旧连接，准备重连 ----
        try:
            client.loop_stop()      # 停止后台网络线程
            client.disconnect()     # 断开 MQTT 连接
        except:
            pass

        reconnect_count += 1
        log(f"连接已断开, {RECONNECT_DELAY}秒后重新连接...")
        time.sleep(RECONNECT_DELAY)


if __name__ == "__main__":
    run()
