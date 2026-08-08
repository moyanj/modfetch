"""本地文件复制器（file:// 协议）

支持把本地文件或目录作为下载源（file:// 协议），用于离线
场景或引用本地已存在的模组文件，避免走 HTTP。

复制为同步阻塞 IO，移入 ``asyncio.to_thread`` 在事件循环外执行。
"""

import asyncio
import shutil
from pathlib import Path

from modfetch.domain.errors import DownloadError


class LocalFileCopier:
    """file:// 协议的本地文件/目录复制"""

    async def copy(self, src: str, dest: Path) -> int:
        """复制 src（文件或目录）到 dest

        Args:
            src: 源路径（已去掉 file:// 前缀）
            dest: 目标路径

        Returns:
            复制的字节数（目录为 0）

        Raises:
            DownloadError: 源不存在或复制失败

        行为说明：
        - 目录复制：若目标已存在则先整体删除再 copytree，
          保证目标与源目录内容一致（覆盖语义）。
        - 文件复制：copy2 保留元数据（时间戳/权限），
          返回目标文件大小作为字节数。
        """
        try:
            # 复制为同步 IO，移入 worker 线程避免阻塞事件循环
            return await asyncio.to_thread(self._copy_sync, src, dest)
        except Exception as e:
            # 统一包装为 DownloadError，携带源路径便于排查
            raise DownloadError(
                "复制文件失败", context={"error": str(e), "src": src}
            ) from e

    def _copy_sync(self, src: str, dest: Path) -> int:
        """同步复制逻辑（worker 线程内执行）"""
        if Path(src).is_dir():
            # 目录覆盖：先删旧目标，避免 copytree 因目标
            # 已存在而报错，也避免残留旧文件。
            if dest.exists():
                shutil.rmtree(dest)
            shutil.copytree(src, dest)
            return 0

        dest.parent.mkdir(parents=True, exist_ok=True)
        # copy2 保留文件元数据（mtime/权限），对模组文件更友好
        shutil.copy2(src, dest)
        return dest.stat().st_size