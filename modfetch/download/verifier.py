"""向后兼容 shim — FileVerifier 已迁入 modfetch.adapters.download.verifier"""

from modfetch.adapters.download.verifier import FileVerifier  # noqa: F401

__all__ = ["FileVerifier"]
