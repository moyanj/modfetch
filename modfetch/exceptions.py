"""向后兼容 shim — 异常体系已迁入 modfetch.domain.errors"""

from modfetch.domain.errors import *  # noqa: F401,F403
from modfetch.domain.errors import __all__  # noqa: F401
