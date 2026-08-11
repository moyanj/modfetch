"""
构建目录布局集中计算

将「产物/下载/工作区/缓存」的目录与文件名决策收拢到单一位置，供
PlanBuild（命名）、ExecuteBuild（下载+物化+发布）与 CLI（clean）复用。

布局约定（固定结构，download_dir 为可配置根）::

    <download_dir>/
    ├── build/
    │   ├── cache/
    │   │   ├── sha1/<prefix>/<sha1>          # 有可信哈希 → 内容寻址缓存
    │   │   └── url/<url_digest>[.meta.json] # 无哈希 → URL 摘要回退 + 元数据
    │   └── <mc-version>-<loader>/          # target 打包工作区（硬链接到 cache）
    └── dist/
        ├── <pack-slug>-<ver>-mc<mc>-<loader>[<mode>].<fmt>
        └── ...（唯一扁平交付目录）

职责：
- 所有路径计算（cache/工作区/dist/缓存键）
- 缓存键规则（有 sha1 → sha1 寻址；无 sha1 → URL 摘要 + sidecar 元数据）
- pack-slug 规范化（metadata.name → 安全文件名）
"""

from __future__ import annotations

import hashlib
import re
from pathlib import Path

from modfetch.domain.build_plan import BuildTarget, OutputSpec, ResolvedArtifact

#: sha1 分片深度（保持 2 位，规避 Windows 长路径/单目录文件过多）
_SHA1_SHARD_DEPTH = 2


class LayoutError(Exception):
    """布局错误：pack-slug 非法等"""


def normalize_slug(name: str) -> str:
    """把 metadata.name 规范化为文件系统安全 slug

    规则：小写、连续空白折叠为单个 ``-``、仅保留 ASCII 字母数字
    ``-``/``_``、去掉首尾 ``-``/``_``。

    当 ASCII 白名单剔除后为空（如纯中文包名）时，宽松回退到保留
    Unicode 字母数字（中文/日文等），仅剔除空白与路径危险字符，
    避免曾经的可用包名变为构建失败；仍为空（如纯符号）才抛错。

    Raises:
        LayoutError: 规范化后为空（不可用于路径）
    """
    raw = name.strip().lower()
    slug = re.sub(r"\s+", "-", raw)
    slug = re.sub(r"[^a-z0-9\-_]", "", slug)
    slug = slug.strip("-_")
    if not slug:
        # 宽松回退：保留 Unicode 字母数字（\w），仅去空白与 ASCII 危险字符
        slug = re.sub(r"\s+", "-", raw)
        slug = re.sub(r"[^\w\-]", "", slug, flags=re.UNICODE)
        slug = slug.strip("-_")
    if not slug:
        raise LayoutError(f"包名无法规范化为文件名: {name!r}")
    return slug


class BuildLayout:
    """构建目录与键路径计算（纯路径，不执行 IO）

    约定:
        - cache: 全局内容寻址缓存（跨所有 target/版本/加载器共享），
          唯一保存真实字节。有可信 sha1 → ``sha1/<2>/<sha1>``；
          无哈希 → ``url/<sha256(url)>`` 并用 sidecar 记录
          url/filename/size/sha1。
        - build/<target>: 打包工作区，目录树保持 Minecraft 整合包布局，
          内部文件硬链接到 cache（不重复占用空间）。
        - dist: 唯一扁平交付目录，最终产物。

    不负责 mkdir / 硬链接 / 原子替换 —— 那些由执行层（ExecuteBuild /
    打包器 / downloader）承担。
    """

    def __init__(self, root: Path | str):
        self._root = Path(root).expanduser().resolve()

    # -- 目录 -------------------------------------------------------------

    @property
    def root(self) -> Path:
        """构建根目录（download_dir）"""
        return self._root

    @property
    def build_dir(self) -> Path:
        """build/：缓存 + 工作区父目录"""
        return self._root / "build"

    @property
    def cache_dir(self) -> Path:
        """build/cache/：全局内容寻址缓存根"""
        return self.build_dir / "cache"

    @property
    def dist_dir(self) -> Path:
        """dist/：唯一扁平交付目录"""
        return self._root / "dist"

    # -- 缓存键 -----------------------------------------------------------

    def cache_path_for(self, artifact: ResolvedArtifact) -> Path:
        """计算某个制品的缓存键路径

        优先有可信内容哈希（sha1）→ 内容寻址；无哈希时回退为
        URL 摘要键（含 .meta.json sidecar 承载 url/filename/size）。
        """
        sha1 = artifact.hashes.get("sha1")
        if sha1:
            return self.sha1_blob(sha1)
        return self.url_blob(artifact.url)

    def cache_parts(self, artifact: ResolvedArtifact) -> tuple[Path, str]:
        """拆出下载任务需要的 (cache 目录, 缓存文件名)

        下载器会把文件写到目录/文件名下；目录为 cache/sha1/<prefix>
        或 cache/url，文件名为 sha1 值或 url-digest。
        """
        cache_path = self.cache_path_for(artifact)
        return cache_path.parent, cache_path.name

    def sha1_blob(self, sha1: str) -> Path:
        """内容寻址 blob 路径：cache/sha1/<前两位>/<sha1>"""
        return Path(self.cache_dir, "sha1", sha1[:_SHA1_SHARD_DEPTH], sha1)

    def url_blob(self, url: str) -> Path:
        """URL 摘要回退 blob：cache/url/<sha256(url)>"""
        digest = hashlib.sha256(url.encode("utf-8")).hexdigest()
        return Path(self.cache_dir, "url", digest)

    def url_meta(self, url: str) -> Path:
        """URL 键的 sidecar 元数据路径（记录 url/filename/size/sha1）"""
        return Path(str(self.url_blob(url)) + ".meta.json")

    # -- 工作区 -----------------------------------------------------------

    def target_build_dir(self, target: BuildTarget) -> Path:
        """target 打包工作区根：build/<mc-version>-<loader>"""
        return self.build_dir / target.dir_name

    def workspace_for(self, target: BuildTarget, destination: str) -> Path:
        """工作区内某制品的最终路径

        ``destination`` 为相对工作区根的路径（如 ``mods/sodium.jar``），
        由 PlanBuild 生成；本方法做目录穿越防御。

        防御覆盖三种逃逸形态：
        - 空/绝对路径（``/etc/passwd``、``C:\\x``）
        - 开头穿越（``../x``）
        - 中间穿越（``mods/../../x``、``mods\\..\\..\\x``）
        """
        if not destination:
            raise LayoutError(f"非法目标相对路径: {destination!r}")
        dest = Path(destination)
        # Path.parts 按平台分隔符切分：含 ".." 分段或绝对路径均拒绝
        # （Windows 上反斜杠也是分隔符，跨平台一致防御）
        if dest.is_absolute() or ".." in dest.parts:
            raise LayoutError(f"非法目标相对路径: {destination!r}")
        return self.target_build_dir(target) / dest

    # -- 产物 -----------------------------------------------------------

    def output_path(self, spec: OutputSpec) -> Path:
        """dist/ 下最终产物路径：{output_name}.{format}"""
        return self.dist_dir / f"{spec.output_name}.{spec.format}"

    def lock_path_for(self, config_path: str | Path) -> Path:
        """配置文件对应的 lock 文件路径

        约定：配置文件同目录，文件名 = 配置文件名去后缀 + ".lock.json"
        （如 mods.toml → mods.lock.json）。

        lock 文件是「配置的解析快照」，放在配置旁边便于版本控制与
        多配置共存；不放入 download_dir（那是构建产物目录）。
        """
        config = Path(config_path).expanduser().resolve()
        return config.parent / f"{config.stem}.lock.json"


def clean_layout(layout: BuildLayout, *, cache: bool = False) -> list[Path]:
    """清理构建目录（显式命令，如 ``modfetch clean [--cache]``）

    默认只清理 target 打包工作区（build/<mc>-<loader>/），保留全局缓存；
    ``cache=True`` 时额外清空 build/cache/（独立显式操作，不自动触发）。

    Returns:
        被清理的目录列表
    """
    import shutil

    removed: list[Path] = []
    if layout.build_dir.exists():
        # 清理全部 target 工作区，但保留 cache（cache 单独由 cache=True 控制）
        for child in layout.build_dir.iterdir():
            if child.name == "cache":
                continue
            if child.is_dir():
                shutil.rmtree(child, ignore_errors=True)
                removed.append(child)
    if cache and layout.cache_dir.exists():
        shutil.rmtree(layout.cache_dir, ignore_errors=True)
        removed.append(layout.cache_dir)
    return removed


def probe_hardlink_support(layout: BuildLayout) -> None:
    """硬链接启动预检（fail-fast）

    在下载任何文件之前验证 cache 与工作区能建立硬链接：
    - 在 cache 目录创建临时文件，硬链接到工作区目录
    - 成功则立即清理；失败抛 LayoutError（文件系统不支持硬链接）
    - 仅 link 模式需要；copy 模式跳过（由调用方判断）

    Raises:
        LayoutError: 文件系统不支持硬链接（EXDEV/EPERM/ENOTSUP 等）
    """
    import os

    cache_dir = layout.cache_dir
    work_dir = layout.build_dir
    cache_dir.mkdir(parents=True, exist_ok=True)
    work_dir.mkdir(parents=True, exist_ok=True)

    probe_src = cache_dir / ".hardlink-probe"
    probe_dst = work_dir / ".hardlink-probe"
    try:
        probe_src.write_bytes(b"probe")
        os.link(probe_src, probe_dst)
    except OSError as e:
        raise LayoutError(
            f"文件系统不支持硬链接（{e}）。"
            "工作区与缓存需位于同一文件系统且支持硬链接，"
            "或使用 --link-mode copy 改为复制。"
        ) from e
    finally:
        probe_src.unlink(missing_ok=True)
        probe_dst.unlink(missing_ok=True)
