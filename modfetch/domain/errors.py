"""
领域错误体系

与旧 modfetch.exceptions 的差异:
- 不导入 aiohttp；APIError 以 status_code/url 替代持有 ClientResponse
- ModrinthError 保持向后兼容（接受任意 response 对象，鸭子类型提取）
"""

from typing import Any, Dict, Optional


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
        self.context: Dict[str, Any] = context or {}

    def _get_default_code(self) -> str:
        return "E000"

    def to_dict(self) -> Dict[str, Any]:
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
        status_code: Optional[int] = None,
        url: Optional[str] = None,
    ):
        super().__init__(message, code, context)
        if status_code is not None:
            self.context["status_code"] = status_code
        if url is not None:
            self.context["url"] = url

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


class PluginError(ModFetchError):
    """插件系统相关错误（Python/Lua 插件加载与执行）"""

    def _get_default_code(self) -> str:
        return "E600"


class ModrinthError(APIError):
    """Modrinth API 错误（向后兼容）

    response 以鸭子类型提取 status/url，不依赖 aiohttp 类型。
    """

    def __init__(self, msg: str, response: Any):
        status = getattr(response, "status", None)
        resp_url = getattr(response, "url", None)
        super().__init__(
            message=msg,
            code=f"E{status}" if status and status != 200 else "E200",
            status_code=status,
            url=str(resp_url) if resp_url is not None else None,
        )
        self.response = response


__all__ = [
    "ModFetchError",
    "ConfigError",
    "ConfigParseError",
    "ConfigValidationError",
    "APIError",
    "APINotFoundError",
    "APIRateLimitError",
    "APIServerError",
    "DownloadError",
    "DownloadNetworkError",
    "DownloadChecksumError",
    "DownloadFileError",
    "PackagerError",
    "MrpackError",
    "ZipError",
    "ValidationError",
    "PluginError",
    "ModrinthError",
]
