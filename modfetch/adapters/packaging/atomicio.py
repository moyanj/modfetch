"""
产物原子发布工具

把「临时文件 → 原子替换到最终路径」封装为可复用函数:
- 写入 .tmp-<uuid> 临时文件，成功后 os.replace 原子替换
- Windows 上 os.replace 可能因文件被占用/杀软扫描抛 PermissionError，
  做有限次退避重试后仍失败则报明确错误（供打包错误上下文定位）。
"""

from __future__ import annotations

import os
import time
import uuid
from pathlib import Path
from typing import Callable, Optional

#: os.replace 最大尝试次数（Windows Defender/占用退避）
_REPLACE_ATTEMPTS = 5
#: 每次尝试间退避（秒）
_REPLACE_BACKOFF = 0.2


class AtomicWriteError(Exception):
    """原子替换失败"""


def atomic_replace(src: Path, dst: Path) -> None:
    """原子替换 src → dst，带 Windows PermissionError 退避重试

    Args:
        src: 源（临时）文件
        dst: 最终目标文件

    Raises:
        AtomicWriteError: 所有重试均失败（目标可能为旧内容）
        FileNotFoundError: src 不存在
    """
    for attempt in range(_REPLACE_ATTEMPTS):
        try:
            os.replace(src, dst)
            return
        except PermissionError:
            # Windows: 目标被占用（杀软扫描/用户打开）→ 退避重试
            if attempt == _REPLACE_ATTEMPTS - 1:
                raise AtomicWriteError(
                    f"原子替换失败（目标可能被占用）: {dst}"
                ) from None
            time.sleep(_REPLACE_BACKOFF)
        except OSError:
            raise


def write_atomic(output_path: Path, writer: Callable[[Path], None]) -> None:
    """在 output_path 同目录写临时文件并原子替换

    Args:
        output_path: 最终产物路径（父目录已存在）
        writer: 写入函数，接收临时文件路径，负责把内容写到临时文件

    Raises:
        AtomicWriteError: 写入或原子替换最终失败
    """
    output_path.parent.mkdir(parents=True, exist_ok=True)
    tmp = output_path.with_name(f".tmp-{uuid.uuid4().hex}")
    try:
        writer(tmp)
        atomic_replace(tmp, output_path)
    finally:
        if tmp.exists():
            tmp.unlink(missing_ok=True)
