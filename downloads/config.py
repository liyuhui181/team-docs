"""
配置管理模块
从 .env 文件加载设备配置信息

使用 python-dotenv 库从项目根目录的 .env 文件中读取环境变量，
通过 Config 类集中管理设备配置，便于其他模块引用。

.env 文件格式示例:
    DEVICE_IP=192.168.1.9
    DEVICE_TOKEN=your_32_char_token_here
    DEVICE_MODEL=cuco.plug.v3
"""

import os
from dotenv import load_dotenv

# 加载 .env 文件中的环境变量到 os.environ
# load_dotenv 会自动查找当前目录及上级目录的 .env 文件
load_dotenv()


class Config:
    """
    设备配置类

    从环境变量读取配置，提供默认值作为后备。
    使用类属性 + @classmethod 模式，无需实例化即可访问配置。

    配置项:
        - DEVICE_IP: 设备局域网 IP 地址 (米家插座)
        - DEVICE_TOKEN: 设备 Token (32位十六进制字符串，从小米云端获取)
        - DEVICE_MODEL: 设备型号 (用于 miio 库识别设备类型)
    """

    # 设备 IP 地址 - 局域网内米家插座的 IP
    # 可通过米家 App -> 设备信息 -> 局域网通信 或路由器后台查看
    DEVICE_IP = os.getenv("DEVICE_IP", "192.168.1.9")

    # 设备 Token - 32 位十六进制字符串
    # 获取方式: 使用 Xiaomi-cloud-tokens-extractor 工具从小米云端提取
    DEVICE_TOKEN = os.getenv("DEVICE_TOKEN", "")

    # 设备型号 - 米家智能插座3 的型号标识
    # 参考: https://home.miot-spec.com/spec/cuco.plug.v3
    DEVICE_MODEL = os.getenv("DEVICE_MODEL", "cuco.plug.v3")

    @classmethod
    def validate(cls):
        """
        验证配置是否完整有效

        检查项目:
            1. DEVICE_IP 不为空且不是默认值
            2. DEVICE_TOKEN 不为空且长度为 32 位

        Returns:
            list: 错误消息列表 (空列表表示配置有效)
        """
        errors = []

        # 检查 IP 地址
        if not cls.DEVICE_IP or cls.DEVICE_IP == "192.168.1.9":
            errors.append("请在 .env 文件中设置正确的 DEVICE_IP")

        # 检查 Token 是否为空
        if not cls.DEVICE_TOKEN or cls.DEVICE_TOKEN == "your_device_token_here":
            errors.append("请在 .env 文件中设置正确的 DEVICE_TOKEN")

        # 检查 Token 长度 (米家设备 Token 固定为 32 位十六进制)
        if len(cls.DEVICE_TOKEN) != 32 and cls.DEVICE_TOKEN:
            errors.append("DEVICE_TOKEN 长度应为 32 位字符")

        return errors

    @classmethod
    def info(cls):
        """
        返回配置摘要 (脱敏显示 Token)

        Token 做脱敏处理，只显示前 4 位和后 4 位，中间用 **** 代替，
        避免在日志中泄露完整密钥。

        Returns:
            dict: 包含 IP地址、Token(脱敏)、设备型号 的字典
        """
        # Token 脱敏: 显示前4位 + **** + 后4位
        token_preview = (
            cls.DEVICE_TOKEN[:4] + "****" + cls.DEVICE_TOKEN[-4:]
            if len(cls.DEVICE_TOKEN) >= 8
            else "***"
        )
        return {
            "IP地址": cls.DEVICE_IP,
            "Token": token_preview,
            "设备型号": cls.DEVICE_MODEL,
        }
