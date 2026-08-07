"""重试策略（值对象）"""

from dataclasses import dataclass

from modfetch.domain.errors import (
    DownloadChecksumError,
    DownloadError,
    DownloadNetworkError,
)


@dataclass(frozen=True)
class RetryPolicy:
    """指数退避重试策略"""

    max_retries: int = 3
    base_delay: float = 1.0
    max_delay: float = 60.0
    backoff_multiplier: float = 2.0

    def delay_for(self, attempt: int) -> float:
        """第 attempt 次重试（0 起）的等待秒数"""
        delay = self.base_delay * (self.backoff_multiplier**attempt)
        return min(delay, self.max_delay)

    def should_retry(self, error: Exception, attempt: int) -> bool:
        """判断该错误在第 attempt 次失败后是否值得重试

        - 网络错误 → 重试
        - 校验错误 → 重试（但受 max_retries 限制）
        - 其他错误 → 不重试
        """
        if attempt >= self.max_retries:
            return False
        return isinstance(error, (DownloadNetworkError, DownloadChecksumError))


class ProgressCallbackError(DownloadError):
    """进度回调异常标记（不触发重试）"""

    def _get_default_code(self) -> str:
        return "E304"
