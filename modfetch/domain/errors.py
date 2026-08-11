"""
领域错误体系

与旧 modfetch.exceptions 的差异:
- 不导入 aiohttp；APIError 以 status_code/url 替代持有 ClientResponse
- ModrinthError 保持向后兼容（接受任意 response 对象，鸭子类型提取）
"""

from typing import Any, Dict, Optional


class ModFetchError(Exception):
    """ModFetch 基础异常类

    所有领域异常的统一基类，携带三要素：
    - message: 人类可读的错误信息
    - code: 稳定错误码（E 开头，供程序判断与 API 输出）
    - context: 附加诊断上下文（如 status_code / url）

    子类通过 _get_default_code 提供各自的默认错误码；
    to_dict 用于 Web 层统一序列化错误响应。
    """

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
    """配置相关错误（E100 段）

    配置读取、解析、验证过程中的失败统一归入此分支。
    """

    def _get_default_code(self) -> str:
        return "E100"


class ConfigParseError(ConfigError):
    """配置解析错误：文件格式非法、字段类型错误等"""

    def _get_default_code(self) -> str:
        return "E101"


class ConfigValidationError(ConfigError):
    """配置验证错误：必填项缺失、枚举值不合法等"""

    def _get_default_code(self) -> str:
        return "E102"


class APIError(ModFetchError):
    """API 相关错误（E200 段）

    外部 API 请求失败的基础类。除通用三要素外，额外把
    status_code 与 url 写入 context，便于日志排查与用户提示。
    """

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
    """API 资源不存在（HTTP 404）"""

    def _get_default_code(self) -> str:
        return "E404"


class APIRateLimitError(APIError):
    """API 速率限制（HTTP 429），应退避后重试"""

    def _get_default_code(self) -> str:
        return "E429"


class APIServerError(APIError):
    """API 服务器错误（HTTP 5xx）"""

    def _get_default_code(self) -> str:
        return "E500"


class DownloadError(ModFetchError):
    """下载相关错误（E300 段）

    下载执行过程中的网络、校验、文件操作失败统一归入此分支。
    """

    def _get_default_code(self) -> str:
        return "E300"


class DownloadNetworkError(DownloadError):
    """下载网络错误：连接失败、超时、断流等"""

    def _get_default_code(self) -> str:
        return "E301"


class DownloadChecksumError(DownloadError):
    """下载校验错误：下载内容与预期哈希不符"""

    def _get_default_code(self) -> str:
        return "E302"


class DownloadFileError(DownloadError):
    """下载文件操作错误：写入失败、磁盘空间不足等"""

    def _get_default_code(self) -> str:
        return "E303"


class PackagerError(ModFetchError):
    """打包相关错误（E400 段）

    mrpack / zip 等产物生成失败统一归入此分支。
    """

    def _get_default_code(self) -> str:
        return "E400"


class MrpackError(PackagerError):
    """Mrpack 生成错误：清单写入、overrides 打包等失败"""

    def _get_default_code(self) -> str:
        return "E401"


class ZipError(PackagerError):
    """ZIP 生成错误：压缩失败、条目冲突等"""

    def _get_default_code(self) -> str:
        return "E402"


class ValidationError(ModFetchError):
    """验证相关错误（历史类型）

    保留用于兼容旧的验证失败路径；新代码请优先使用
    ConfigValidationError 等更具体的错误类型。
    """

    def _get_default_code(self) -> str:
        return "E500"


class PluginError(ModFetchError):
    """插件系统相关错误（Python/Lua 插件加载与执行）

    涵盖插件路径错误、文件格式分发失败、加载器内部异常等。
    错误码 E600 起，为插件系统保留的错误段。
    """

    def _get_default_code(self) -> str:
        return "E600"


class LockError(ModFetchError):
    """Lock 文件相关错误（E700 段）

    lock 文件缺失、格式无效、指纹不匹配、反序列化失败等统一归入此分支。
    """

    def _get_default_code(self) -> str:
        return "E700"


class ModrinthError(APIError):
    """Modrinth API 错误（向后兼容）

    response 以鸭子类型提取 status/url，不依赖 aiohttp 类型，
    便于同时适配 CLI 与 Web 两种运行环境。
    错误码由实际 HTTP 状态码推导（如 E404/E429/E500）。
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
    "LockError",
    "ModrinthError",
]
