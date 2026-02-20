"""
ModFetch 统一异常体系

提供分层的异常结构，支持错误代码、上下文信息和 JSON 序列化。
"""

from typing import Any, Dict, Optional
import aiohttp


class ModFetchError(Exception):
    """ModFetch 基础异常类"""

    def __init__(
        self,
        message: str,
        code: Optional[str] = None,
        context: Optional[Dict[str, Any]] = None,
    ):
        super().__init__(message)
        self.message = message
        self.code = code or self._get_default_code()
        self.context = context or {}

    def _get_default_code(self) -> str:
        """获取默认错误代码"""
        return "E000"

    def to_dict(self) -> Dict[str, Any]:
        """将异常转换为字典格式"""
        return {
            "error": True,
            "code": self.code,
            "message": self.message,
            "context": self.context,
            "type": self.__class__.__name__,
        }

    def __str__(self) -> str:
        if self.code:
            return f"[{self.code}] {self.message}"
        return self.message


class ConfigError(ModFetchError):
    """配置相关错误"""

    def _get_default_code(self) -> str:
        return "E100"


class ConfigParseError(ConfigError):
    """配置解析错误"""

    def _get_default_code(self) -> str:
        return "E101"


class ConfigValidationError(ConfigError):
    """配置验证错误"""

    def _get_default_code(self) -> str:
        return "E102"


class APIError(ModFetchError):
    """API 相关错误"""

    def __init__(
        self,
        message: str,
        code: Optional[str] = None,
        context: Optional[Dict[str, Any]] = None,
        response: Optional[aiohttp.ClientResponse] = None,
    ):
        super().__init__(message, code, context)
        self.response = response
        if response:
            self.context["status_code"] = response.status
            self.context["url"] = str(response.url)

    def _get_default_code(self) -> str:
        return "E200"


class APINotFoundError(APIError):
    """API 资源不存在"""

    def _get_default_code(self) -> str:
        return "E404"


class APIRateLimitError(APIError):
    """API 速率限制"""

    def _get_default_code(self) -> str:
        return "E429"


class APIServerError(APIError):
    """API 服务器错误"""

    def _get_default_code(self) -> str:
        return "E500"


class DownloadError(ModFetchError):
    """下载相关错误"""

    def _get_default_code(self) -> str:
        return "E300"


class DownloadNetworkError(DownloadError):
    """下载网络错误"""

    def _get_default_code(self) -> str:
        return "E301"


class DownloadChecksumError(DownloadError):
    """下载校验错误"""

    def _get_default_code(self) -> str:
        return "E302"


class DownloadFileError(DownloadError):
    """下载文件操作错误"""

    def _get_default_code(self) -> str:
        return "E303"


class PackagerError(ModFetchError):
    """打包相关错误"""

    def _get_default_code(self) -> str:
        return "E400"


class MrpackError(PackagerError):
    """Mrpack 生成错误"""

    def _get_default_code(self) -> str:
        return "E401"


class ZipError(PackagerError):
    """ZIP 生成错误"""

    def _get_default_code(self) -> str:
        return "E402"


class ValidationError(ModFetchError):
    """验证相关错误"""

    def _get_default_code(self) -> str:
        return "E500"


class ModrinthError(APIError):
    """
    Modrinth API 错误（向后兼容）

    保留此类以兼容现有代码，但建议使用更具体的 APIError 子类。
    """

    def __init__(self, msg: str, response: aiohttp.ClientResponse):
        super().__init__(
            message=msg,
            code=f"E{response.status}" if response.status != 200 else "E200",
            context={"url": str(response.url)},
            response=response,
        )


# 向后兼容导出
__all__ = [
    # 基础异常
    "ModFetchError",
    # 配置异常
    "ConfigError",
    "ConfigParseError",
    "ConfigValidationError",
    # API 异常
    "APIError",
    "APINotFoundError",
    "APIRateLimitError",
    "APIServerError",
    # 下载异常
    "DownloadError",
    "DownloadNetworkError",
    "DownloadChecksumError",
    "DownloadFileError",
    # 打包异常
    "PackagerError",
    "MrpackError",
    "ZipError",
    # 验证异常
    "ValidationError",
    # 向后兼容
    "ModrinthError",
]
