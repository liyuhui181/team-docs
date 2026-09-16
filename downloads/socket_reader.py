"""
米家智能插座3 数据读取核心模块
基于 python-miio 库实现局域网设备通信

设备型号: cuco.plug.v3 (米家智能插座3)
参考: https://home.miot-spec.com/spec/cuco.plug.v3

python-miio 库通过 MIIO 协议与米家设备通信:
    - 局域网内通过 UDP 与设备直接通信 (无需经过小米云)
    - 使用设备 IP + Token 进行认证
    - 通过 raw_command 调用 MIIO Spec 定义的属性读写接口
"""

from typing import Optional, Dict, Any, List
from miio import Device, DeviceException


# ============================================================================
# 米家智能插座3 (cuco.plug.v3) 属性定义
#
# 来源: https://home.miot-spec.com/spec/cuco.plug.v3
# MIIO Spec 使用 siid (Service ID) + piid (Property ID) 定位属性:
#   - siid: 服务 ID，标识设备的一个功能模块 (如开关服务、电量服务等)
#   - piid: 属性 ID，标识该服务下的一个具体属性 (如开关状态、功率值等)
# ============================================================================

SOCKET_PROPERTIES = {
    # ---- 开关控制服务 (siid: 2) ----
    # 管理插座的基本开关操作和故障状态
    "switch": {
        "siid": 2, "piid": 1,
        "name": "开关", "desc": "插座开关状态", "type": "bool"
    },
    "fault": {
        "siid": 2, "piid": 3,
        "name": "故障", "desc": "故障状态 (0无/1过温/2过载)", "type": "uint8"
    },

    # ---- 功率/用电服务 (siid: 11) ----
    # 提供实时功率和累计用电量数据
    "power": {
        "siid": 11, "piid": 2,
        "name": "实时功率", "desc": "当前功率 (W)", "type": "float"
    },
    "power_consumed": {
        "siid": 11, "piid": 1,
        "name": "累计用电量", "desc": "累计用电量 (0.01 kWh)", "type": "uint16"
    },

    # ---- 开关次数/温度服务 (siid: 12) ----
    # 记录设备使用统计数据和内部温度
    "on_off_count": {
        "siid": 12, "piid": 1,
        "name": "开关次数", "desc": "累计开关次数", "type": "uint8"
    },
    "temperature": {
        "siid": 12, "piid": 2,
        "name": "温度", "desc": "设备温度 (°C)", "type": "uint8"
    },

    # ---- 指示灯服务 (siid: 13) ----
    # 控制插座上的指示灯
    "indicator_light": {
        "siid": 13, "piid": 1,
        "name": "指示灯", "desc": "指示灯状态", "type": "bool"
    },
}


class SocketReader:
    """
    米家智能插座3 读取器

    封装 python-miio 库的底层调用，提供简洁的属性读写方法。
    支持单个属性读写和批量读取。

    使用示例:
        reader = SocketReader("192.168.1.9", "your_token_here")
        reader.connect()
        power = reader.get_power()       # 读取实时功率
        reader.turn_on()                  # 打开插座
        reader.print_all_data()           # 打印所有数据
    """

    def __init__(self, ip: str, token: str):
        """
        初始化设备连接参数

        Args:
            ip: 设备 IP 地址 (局域网内，如 "192.168.1.9")
            token: 设备 Token (32位十六进制字符串，从小米云端提取)
        """
        self.ip = ip
        self.token = token
        self._device: Optional[Device] = None  # miio Device 实例 (connect() 后赋值)

    def connect(self) -> bool:
        """
        连接设备并测试通信

        创建 miio.Device 实例并调用 info() 测试连接是否正常。
        info() 会向设备发送 MIIO 协议的设备信息查询请求。

        Returns:
            True: 连接成功 (设备响应正常)
            False: 连接失败 (IP/Token 错误或设备不可达)
        """
        try:
            # 创建 miio Device 实例 (还未实际通信)
            self._device = Device(self.ip, self.token)

            # 调用 info() 测试连接，获取设备信息
            info = self._device.info()
            print(f"[连接成功] 设备型号: {info.model}, 固件版本: {info.firmware_version}")
            return True

        except DeviceException as e:
            print(f"[连接失败] {e}")
            return False

    def _get_property(self, siid: int, piid: int) -> Any:
        """
        读取单个属性 (底层方法)

        通过 MIIO Spec 的 raw_command 接口读取指定服务的指定属性。
        命令格式: get_properties, 参数: [{"siid": x, "piid": y}]

        Args:
            siid: Service ID (服务 ID)
            piid: Property ID (属性 ID)

        Returns:
            属性值 (类型取决于具体属性: bool/int/float/str)
            如果读取失败返回 None
        """
        if not self._device:
            raise RuntimeError("设备未连接，请先调用 connect()")

        # 调用 MIIO Spec raw_command 读取属性
        result = self._device.raw_command(
            "get_properties",
            [{"siid": siid, "piid": piid}]
        )

        # 返回结果为列表，取第一个元素的 value 字段
        if result and len(result) > 0:
            return result[0].get("value")
        return None

    def _set_property(self, siid: int, piid: int, value: Any) -> bool:
        """
        设置单个属性 (底层方法)

        通过 MIIO Spec 的 raw_command 接口设置指定属性。
        命令格式: set_properties, 参数: [{"siid": x, "piid": y, "value": z}]

        Args:
            siid: Service ID (服务 ID)
            piid: Property ID (属性 ID)
            value: 要设置的值 (类型取决于具体属性)

        Returns:
            True: 设置成功
            False: 设置失败
        """
        if not self._device:
            raise RuntimeError("设备未连接，请先调用 connect()")

        # 调用 MIIO Spec raw_command 设置属性
        result = self._device.raw_command(
            "set_properties",
            [{"siid": siid, "piid": piid, "value": value}]
        )

        # 返回结果中 code=0 表示设置成功
        if result and len(result) > 0:
            return result[0].get("code", -1) == 0
        return False

    def get_info(self) -> Dict[str, str]:
        """
        获取设备基本信息

        通过 miio 的 info() 接口获取设备硬件信息，
        包括型号、固件版本、硬件版本和 MAC 地址。

        Returns:
            dict: 包含型号、固件版本、硬件版本、MAC地址的字典
        """
        if not self._device:
            raise RuntimeError("设备未连接，请先调用 connect()")

        info = self._device.info()
        return {
            "型号": info.model,
            "固件版本": info.firmware_version,
            "硬件版本": info.hardware_version,
            "MAC地址": info.mac_address,
        }

    # ========================================================================
    # 便捷属性读取方法
    # 对 _get_property / _set_property 的语义化封装，方便调用
    # ========================================================================

    def get_switch(self) -> bool:
        """读取开关状态 (siid=2, piid=1)。True=开启, False=关闭"""
        return self._get_property(2, 1) is True

    def set_switch(self, on: bool) -> bool:
        """
        设置开关状态 (siid=2, piid=1)

        Args:
            on: True=开启, False=关闭

        Returns:
            True: 设置成功
        """
        return self._set_property(2, 1, on)

    def turn_on(self) -> bool:
        """打开插座 (设置开关为 True)"""
        return self.set_switch(True)

    def turn_off(self) -> bool:
        """关闭插座 (设置开关为 False)"""
        return self.set_switch(False)

    def get_power(self) -> float:
        """读取实时功率 (siid=11, piid=2)，单位: 瓦特 (W)"""
        return self._get_property(11, 2) or 0.0

    def get_power_consumed(self) -> float:
        """
        读取累计用电量 (siid=11, piid=1)

        原始数据单位为 0.01 kWh (即百分之一度电)，
        需要除以 100 转换为 kWh (度)。

        Returns:
            累计用电量 (kWh, 即度)
        """
        raw = self._get_property(11, 1)
        return (raw or 0) / 100.0  # 转换: 0.01 kWh -> kWh

    def get_on_off_count(self) -> int:
        """读取累计开关次数 (siid=12, piid=1)"""
        return self._get_property(12, 1) or 0

    def get_temperature(self) -> float:
        """读取设备内部温度 (siid=12, piid=2)，单位: °C"""
        return self._get_property(12, 2) or 0.0

    def get_fault(self) -> int:
        """
        读取故障状态 (siid=2, piid=3)

        返回值含义:
            0: 无故障
            1: 过温故障 (设备温度过高)
            2: 过载故障 (电流超过额定值)

        Returns:
            故障码 (0/1/2)
        """
        return self._get_property(2, 3) or 0

    def get_indicator_light(self) -> bool:
        """读取指示灯开关状态 (siid=13, piid=1)"""
        return self._get_property(13, 1) is True

    def set_indicator_light(self, on: bool) -> bool:
        """
        设置指示灯开关 (siid=13, piid=1)

        Args:
            on: True=开启指示灯, False=关闭指示灯

        Returns:
            True: 设置成功
        """
        return self._set_property(13, 1, on)

    # ========================================================================
    # 批量读取方法
    # 一次 MIIO 命令读取所有属性，减少网络往返延迟
    # ========================================================================

    def get_all_data(self) -> Dict[str, Any]:
        """
        读取所有常用数据 (批量读取)

        将 SOCKET_PROPERTIES 中定义的所有属性合并为一次 raw_command 请求，
        减少多次单独读取的网络往返延迟。

        Returns:
            dict: 包含所有属性的字典，每个属性包含 name/desc/value 三个字段
        """
        # 构建批量读取请求参数列表
        props = []
        for key, meta in SOCKET_PROPERTIES.items():
            props.append({"siid": meta["siid"], "piid": meta["piid"]})

        if not self._device:
            raise RuntimeError("设备未连接，请先调用 connect()")

        # 一次性发送所有属性的读取请求
        results = self._device.raw_command("get_properties", props)

        # 初始化返回数据结构
        data = {}
        for key, meta in SOCKET_PROPERTIES.items():
            data[key] = {
                "name": meta["name"],
                "desc": meta["desc"],
                "value": None,  # 待填充
            }

        # 将返回结果按顺序匹配到对应属性
        if results:
            for i, result in enumerate(results):
                keys = list(SOCKET_PROPERTIES.keys())
                if i < len(keys):
                    data[keys[i]]["value"] = result.get("value")

        return data

    def print_all_data(self):
        """
        打印所有数据到控制台 (格式化输出)

        对不同数据类型做格式化处理:
            - 累计用电量: 原始值 0.01 kWh -> 转换为 kWh 显示
            - 布尔值: 显示为 "开启"/"关闭"
            - 浮点数: 保留 2 位小数
            - 其他: 直接显示

        输出示例:
            ========================================
              米家智能插座3 - 实时数据
            ========================================
              开关       : 开启  (插座开关状态)
              实时功率   : 45.23  (当前功率 (W))
              ...
            ========================================
        """
        data = self.get_all_data()

        print("=" * 50)
        print("  米家智能插座3 - 实时数据")
        print("=" * 50)

        for key, item in data.items():
            value = item["value"]

            # 对不同数据类型做格式化处理
            if key == "power_consumed" and isinstance(value, (int, float)):
                # 累计用电量: 原始值 0.01 kWh -> 转换为 kWh
                value_str = f"{value / 100.0:.3f} kWh"
            elif isinstance(value, bool):
                value_str = "开启" if value else "关闭"
            elif isinstance(value, float):
                value_str = f"{value:.2f}"
            else:
                value_str = str(value)

            print(f"  {item['name']:<10} : {value_str}  ({item['desc']})")

        print("=" * 50)
