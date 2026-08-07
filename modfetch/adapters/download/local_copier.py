"""本地文件复制器（file:// 协议）"""

import shutil
from pathlib import Path

from modfetch.domain.errors import DownloadError


class LocalFileCopier:
    """file:// 协议的本地文件/目录复制"""

    async def copy(self, src: str, dest: Path) -> int:
        """复制 src（文件或目录）到 dest

        Returns:
            复制的字节数（目录为 0）

        Raises:
            DownloadError: 源不存在或复制失败
        """
        try:
            if Path(src).is_dir():
                if dest.exists():
                    shutil.rmtree(dest)
                shutil.copytree(src, dest)
                return 0

            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dest)
            return dest.stat().st_size
        except Exception as e:
            raise DownloadError(
                "复制文件失败", context={"error": str(e), "src": src}
            ) from e
