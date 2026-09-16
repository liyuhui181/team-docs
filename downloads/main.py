"""
米家智能插座3 - 主程序示例
演示如何使用 socket_reader 模块读取和控制设备

运行方式:
    python main.py

执行流程:
    1. 验证 .env 配置是否正确
    2. 连接米家插座 (局域网 MIIO 协议)
    3. 获取设备基本信息 (型号、固件版本等)
    4. 批量读取所有属性数据
    5. 演示单个属性读取 (开关、功率、温度等)
    6. 进入功率监控模式 (持续读取并显示)
"""

import sys
import time
from config import Config           # 配置管理模块
from socket_reader import SocketReader  # 设备读写模块


def main():
    """
    主函数 - 演示设备连接和数据读取的完整流程

    流程:
        1. 验证 .env 配置
        2. 创建设备连接
        3. 获取设备基本信息
        4. 批量读取所有数据
        5. 演示单个属性读取
        6. 功率监控模式 (持续循环读取)
    """

    print("米家智能插座3 - 本地开发环境示例")
    print("-" * 50)

    # ---- 步骤 1: 验证配置 ----
    # 检查 .env 文件中的配置是否完整有效
    errors = Config.validate()
    if errors:
        # 配置有误，打印错误信息并退出
        print("[配置错误] 请检查 .env 文件:")
        for err in errors:
            print(f"  - {err}")
        print("\n提示: 将 .env.example 复制为 .env 并填入你的设备信息")
        sys.exit(1)

    # 打印当前配置 (Token 脱敏显示)
    print("当前配置:")
    for key, value in Config.info().items():
        print(f"  {key}: {value}")
    print()

    # ---- 步骤 2: 创建设备连接 ----
    # 使用配置中的 IP 和 Token 创建 SocketReader 实例
    reader = SocketReader(Config.DEVICE_IP, Config.DEVICE_TOKEN)

    print("正在连接设备...")
    if not reader.connect():
        # 连接失败，打印排查建议
        print("连接失败，请检查:")
        print("  1. 电脑和设备是否在同一局域网")
        print("  2. IP 地址是否正确")
        print("  3. Token 是否正确")
        sys.exit(1)

    print()

    # ---- 步骤 3: 获取设备基本信息 ----
    # 获取型号、固件版本、硬件版本、MAC 地址
    print("设备基本信息:")
    info = reader.get_info()
    for key, value in info.items():
        print(f"  {key}: {value}")
    print()

    # ---- 步骤 4: 批量读取所有数据 ----
    # 调用 print_all_data 一次性读取所有属性并格式化打印
    reader.print_all_data()
    print()

    # ---- 步骤 5: 演示单个属性读取 ----
    # 展示如何单独读取各个属性
    print("单个属性读取示例:")
    print(f"  开关状态: {'开启' if reader.get_switch() else '关闭'}")
    print(f"  实时功率: {reader.get_power():.2f} W")           # 功率保留 2 位小数
    print(f"  累计用电: {reader.get_power_consumed():.3f} kWh") # 用电量保留 3 位小数
    print(f"  开关次数: {reader.get_on_off_count()}")
    print(f"  温度: {reader.get_temperature():.1f} °C")        # 温度保留 1 位小数
    print(f"  故障状态: {reader.get_fault()} ({'无' if reader.get_fault() == 0 else '有'}故障)")
    print()

    # ---- 步骤 6: 功率监控模式 (持续读取) ----
    # 循环读取功率和温度，每 2 秒刷新一次
    # 适用于实时监控场景 (按 Ctrl+C 退出)
    print("进入功率监控模式 (按 Ctrl+C 退出)...")
    print("-" * 50)
    try:
        while True:
            power = reader.get_power()             # 读取实时功率
            temperature = reader.get_temperature()  # 读取设备温度
            timestamp = time.strftime("%H:%M:%S")
            print(f"[{timestamp}] 功率: {power:6.2f} W | 温度: {temperature:.1f} °C")
            time.sleep(2)  # 2 秒间隔
    except KeyboardInterrupt:
        # 用户按 Ctrl+C 退出监控
        print("\n监控已停止。")

    print("\n程序结束。")


if __name__ == "__main__":
    main()
