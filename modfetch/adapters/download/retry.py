"""重试策略（值对象）

定义下载失败后的重试规则：是否重试、每次重试前等待多久。
作为不可变值对象注入 HttpDownloader，使重试行为可配置、可测试。
"""

from dataclasses import dataclass

from modfetch.domain.errors import (
    DownloadChecksumError,
    DownloadError,
    DownloadNetworkError,
)


@dataclass(frozen=True)
class RetryPolicy:
    """指数退避重试策略

    参数：
    - max_retries: 最大重试次数（不含首次尝试）
    - base_delay: 首次重试的基础等待秒数
    - max_delay: 等待秒数上限（防止退避无限增长）
    - backoff_multiplier: 每次重试等待时间的放大倍数
    """

    max_retries: int = 3
    base_delay: float = 1.0
    max_delay: float = 60.0
    backoff_multiplier: float = 2.0

    def delay_for(self, attempt: int) -> float:
        """第 attempt 次重试（0 起）的等待秒数

        公式：base_delay * backoff_multiplier**attempt，并封顶于
        max_delay。attempt 从 0 起，故首次重试等待 base_delay。
        """
        delay = self.base_delay * (self.backoff_multiplier**attempt)
        return min(delay, self.max_delay)

    def should_retry(self, error: Exception, attempt: int) -> bool:
        """判断该错误在第 attempt 次失败后是否值得重试

        - 网络错误 → 重试（瞬时故障，退避后可能恢复）
        - 校验错误 → 重试（但受 max_retries 限制）
        - 其他错误 → 不重试（如配置/路径错误，重试无意义）

        先检查 attempt 是否已达上限：即使错误可重试，超过
        max_retries 也返回 False，由调用方结束重试循环。
        """
        if attempt >= self.max_retries:
            return False
        return isinstance(error, (DownloadNetworkError, DownloadChecksumError))


class ProgressCallbackError(DownloadError):
    """进度回调异常标记（不触发重试）

    进度回调只是旁路通知，其失败不应导致下载重试，故用独立
    错误类型区分，使 should_retry 天然将其排除在重试之外。
    """

    def _get_default_code(self) -> str:
        return "E304"
