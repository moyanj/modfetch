"""
ExecuteBuild 用例

按 BuildPlan 执行下载、物化与打包（新布局）:
- 下载经 DownloaderPort 写入全局内容寻址缓存（build/cache/）
- 物化作独立阶段：清空重建 target 工作区，将缓存文件硬链接（或复制）
  到 build/<mc>-<loader>/<destination>
- 打包经 PackagerPort（显式 source_dir/output_path）；产物写入 dist/（原子）
- 单 target 内全程持 per-target 互斥锁，防止并发 job 竞争同一工作区/dist
- 失败均记为 BuildError（phase 区分），不再静默
- 全生命周期事件经 EventSink 发布
"""

import asyncio
import os
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional

from loguru import logger

from modfetch.adapters.download.executor import DownloadExecutor
from modfetch.application.build_layout import (
    BuildLayout,
    LayoutError,
    probe_hardlink_support,
)
from modfetch.domain.build_plan import (
    BuildError,
    BuildPlan,
    BuildResult,
    BuildStats,
    BuildTarget,
    OutputArtifact,
    ResolvedArtifact,
)
from modfetch.domain.events import BuildEvent, EventType
from modfetch.ports.downloader import DownloadTask, DownloaderPort
from modfetch.ports.event_sink import EventSink
from modfetch.ports.packager import PackagerPort

#: 物化策略："link"（硬链接，默认）/ "copy"（复制，显式开关）
LinkMode = str

#: 跨 job 实例共享的 per-target 互斥锁表（进程内单事件循环）
#: key = target.dir_name，防止多个并发构建清空重建同一工作区
_TARGET_LOCKS: Dict[str, asyncio.Lock] = {}


def _target_lock(key: str) -> asyncio.Lock:
    """获取某 target 的进程内互斥锁（惰性创建，进程生命周期内复用）"""
    lock = _TARGET_LOCKS.get(key)
    if lock is None:
        lock = asyncio.Lock()
        _TARGET_LOCKS[key] = lock
    return lock


@dataclass(frozen=True)
class BuildOptions:
    """构建执行选项

    layout: 目录布局计算（cache/工作区/dist）
    max_concurrent: 下载并发上限
    link_mode: 物化策略 "link"（硬链接，默认）/ "copy"（复制）
    """

    layout: Optional[BuildLayout] = None
    max_concurrent: int = 5
    link_mode: LinkMode = "link"


class ExecuteBuild:
    """下载 + 物化 + 打包执行用例

    按 BuildPlan 逐 target 执行: 先并发下载全部制品到全局缓存，
    再物化 target 工作区，最后按输出规格打包。下载/打包失败均记为
    BuildError（phase 区分），不中断其余 target。
    """

    def __init__(
        self,
        downloader: DownloaderPort,
        packager: PackagerPort,
        max_concurrent: int = 5,
    ):
        self._downloader = downloader
        self._packager = packager
        self._max_concurrent = max_concurrent

    async def execute(
        self,
        plan: BuildPlan,
        job_id: str,
        event_sink: EventSink,
        options: Optional[BuildOptions] = None,
    ) -> BuildResult:
        """按计划执行全部 target 的下载、物化与打包

        Args:
            plan: 构建计划（targets/artifacts/outputs）
            job_id: 作业标识（事件关联用）
            event_sink: 生命周期事件接收器
            options: 执行选项；省略时用默认布局（download_dir="downloads"）

        Returns:
            BuildResult: 聚合产物与错误；errors 以值传递，不抛异常。
        """
        options = options or BuildOptions()
        layout = options.layout or BuildLayout("downloads")
        layout.cache_dir.mkdir(parents=True, exist_ok=True)
        layout.dist_dir.mkdir(parents=True, exist_ok=True)
        # 硬链接预检（link 模式）：在下载前验证文件系统支持硬链接
        if options.link_mode == "link":
            try:
                probe_hardlink_support(layout)
            except LayoutError as e:
                logger.error(str(e))
                raise
        logger.debug(
            f"[执行] 布局: cache={layout.cache_dir}, dist={layout.dist_dir}"
            f" (并发={options.max_concurrent}, 物化={options.link_mode})"
        )

        max_concurrent = options.max_concurrent or self._max_concurrent
        outputs: List[OutputArtifact] = []
        errors: List[BuildError] = []
        total_downloaded = 0
        total_skipped = 0
        total_failed = 0
        total_bytes = 0

        for target in plan.targets:
            # per-target 互斥：同 target 并发 job 串行，其他并行
            async with _target_lock(target.dir_name):
                logger.debug(f"[执行] 开始 target {target.dir_name}")

                # -- 1. 下载到全局缓存 --
                report = await self._download_target(
                    plan, target, layout, job_id, event_sink,
                    max_concurrent=max_concurrent,
                )
                logger.debug(
                    f"[执行] target {target.dir_name} 下载报告: "
                    f"完成={report.completed}, 跳过={report.skipped}, "
                    f"失败={report.failed}, 字节={report.bytes_downloaded}"
                )
                total_downloaded += report.completed
                total_skipped += report.skipped
                total_failed += report.failed
                total_bytes += report.bytes_downloaded

                for failure in report.failures:
                    errors.append(
                        BuildError(
                            code=failure.error_code or "E300",
                            message=failure.error or "下载失败",
                            target=target,
                            phase="download",
                            context={"filename": failure.filename},
                        )
                    )

                # -- 2. 物化 target 工作区（下载成功才做）--
                errors.extend(
                    await self._materialize_target(
                        plan, target, layout, options.link_mode
                    )
                )

                # -- 3. 打包 --
                for spec in plan.outputs_for(target):
                    await self._publish(
                        event_sink, job_id, EventType.PACKAGE_STARTED,
                        {"format": spec.format, "target": target.dir_name},
                    )
                    try:
                        artifact = await self._packager.package(
                            plan, spec,
                            source_dir=layout.target_build_dir(target),
                            output_path=layout.output_path(spec),
                        )
                        outputs.append(artifact)
                        await self._publish(
                            event_sink, job_id, EventType.PACKAGE_COMPLETED,
                            {
                                "format": spec.format,
                                "path": artifact.path,
                                "size": artifact.size,
                                "target": target.dir_name,
                            },
                        )
                    except Exception as e:
                        code = getattr(e, "code", "E400")
                        errors.append(
                            BuildError(
                                code=code,
                                message=str(e),
                                target=target,
                                phase="package",
                                context={"format": spec.format},
                            )
                        )
                        await self._publish(
                            event_sink, job_id, EventType.PACKAGE_FAILED,
                            {
                                "format": spec.format,
                                "target": target.dir_name,
                                "error": str(e),
                            },
                        )

        return BuildResult(
            plan=plan,
            outputs=tuple(outputs),
            errors=tuple(errors),
            stats=BuildStats(
                total_artifacts=len(plan.artifacts),
                downloaded=total_downloaded,
                skipped=total_skipped,
                failed=total_failed,
                bytes_downloaded=total_bytes,
            ),
        )

    # -- 下载（写入全局缓存） ---------------------------------------------

    async def _download_target(
        self,
        plan: BuildPlan,
        target: BuildTarget,
        layout: BuildLayout,
        job_id: str,
        event_sink: EventSink,
        max_concurrent: int,
    ):
        """把 target 的全部制品下载到全局缓存（build/cache/）

        缓存键（cache_parts）基于内容 sha1 或 URL 摘要寻址：
        - 需真实文件（zip / mrpack-download）时才下载
        - mrpack reference 模式 catalog 制品不需实体文件，忽略下载

        Args:
            max_concurrent: 本次执行的下载并发上限
                （来自 BuildOptions，缺省回落构造器默认值）
        """
        needs_download = self._needs_download(plan, target)

        async def on_task_event(task, result):
            if result.skipped:
                return
            if result.success:
                await self._publish(
                    event_sink, job_id, EventType.DOWNLOAD_COMPLETED,
                    {
                        "filename": result.filename,
                        "size": result.bytes_downloaded,
                        "target": target.dir_name,
                    },
                )
            else:
                await self._publish(
                    event_sink, job_id, EventType.DOWNLOAD_FAILED,
                    {
                        "filename": result.filename,
                        "error": result.error or "",
                        "target": target.dir_name,
                    },
                )

        async def on_progress(filename, downloaded, total):
            await self._publish(
                event_sink, job_id, EventType.DOWNLOAD_PROGRESS,
                {
                    "filename": filename,
                    "bytes_downloaded": downloaded,
                    "bytes_total": total,
                    "target": target.dir_name,
                },
            )

        executor = DownloadExecutor(
            self._downloader,
            max_concurrent=max_concurrent,
            progress=on_progress,
            on_task_event=on_task_event,
        )

        for artifact in plan.artifacts_for(target):
            if artifact.origin == "catalog" and not needs_download:
                logger.info(f"'{artifact.project_name}' 已记录引用 (跳过下载)")
                continue
            cache_dir, cache_name = layout.cache_parts(artifact)
            task = DownloadTask(
                url=artifact.url,
                filename=cache_name,
                destination=str(cache_dir),
                expected_sha1=artifact.hashes.get("sha1"),
            )
            await executor.submit(task)
            await self._publish(
                event_sink, job_id, EventType.DOWNLOAD_STARTED,
                {"filename": artifact.filename, "target": target.dir_name},
            )

        return await executor.run()

    # -- 物化（缓存 → 工作区） ---------------------------------------------

    async def _materialize_target(
        self,
        plan: BuildPlan,
        target: BuildTarget,
        layout: BuildLayout,
        link_mode: LinkMode,
    ) -> List[BuildError]:
        """清空重建 target 工作区，并从缓存硬链接（或复制）制品

        工作区目录树保持 Minecraft 整合包布局：每个制品的 destination
        （如 mods/sodium.jar）就是工作区内相对路径。

        Returns:
            物化阶段的 BuildError 列表
        """
        errors: List[BuildError] = []
        workdir = layout.target_build_dir(target)

        # 清空重建（缓存不动；崩溃后重建是安全操作）
        if workdir.exists():
            shutil.rmtree(workdir)
        workdir.mkdir(parents=True, exist_ok=True)

        needs_download = self._needs_download(plan, target)
        for artifact in plan.artifacts_for(target):
            if artifact.origin == "catalog" and not needs_download:
                continue
            cache_path = layout.cache_path_for(artifact)
            # 缓存文件缺失（下载失败或缓存被清/损坏）：下载阶段已记为
            # E300 错误，这里直接跳过，不再重复报误导性 E400 物化失败
            if not cache_path.exists():
                logger.warning(
                    f"[物化] 缓存缺失，跳过: {artifact.filename} ({cache_path})"
                )
                continue
            dest = layout.workspace_for(target, artifact.destination)
            dest.parent.mkdir(parents=True, exist_ok=True)
            try:
                if link_mode == "copy":
                    await _copy_artifact(cache_path, dest)
                else:
                    await _link_artifact(cache_path, dest)
                # 无可信哈希的 URL 键制品：物化后写 sidecar 元数据
                # （url/filename/size/sha1），供缓存回退寻址与后续校验
                if not artifact.hashes.get("sha1"):
                    await _write_url_meta(layout, artifact, cache_path)
            except Exception as e:
                errors.append(
                    BuildError(
                        code="E400",
                        message=f"物化失败: {e}",
                        target=target,
                        phase="materialize",
                        context={"filename": artifact.filename},
                    )
                )
        return errors

    @staticmethod
    def _needs_download(plan: BuildPlan, target: BuildTarget) -> bool:
        """是否存在需要真实文件的输出（zip 或 mrpack download 模式）"""
        return any(
            spec.format == "zip"
            or (spec.format == "mrpack" and spec.mrpack_mode == "download")
            for spec in plan.outputs_for(target)
        )

    @staticmethod
    async def _publish(
        sink: EventSink, job_id: str, event_type: EventType, payload: dict
    ) -> None:
        """发布构建生命周期事件"""
        await sink.publish(
            BuildEvent(job_id=job_id, event_type=event_type, payload=payload)
        )


async def _link_artifact(src: Path, dest: Path) -> None:
    """把缓存文件硬链接到工作区（os.link 瞬时元数据操作，无阻塞）

    失败抛 LayoutError——不静默复制，共享缓存语义保持严格：
        - EXDEV（跨设备）：cache 与工作区不在同一文件系统
        - EPERM/ENOTSUP：文件系统不支持硬链接（FAT/exFAT/ReFS/SMB）
    """
    try:
        os.link(src, dest)
    except OSError as e:
        raise LayoutError(
            f"硬链接失败: {src} -> {dest} ({e})。"
            "请确保工作区与缓存位于同一文件系统且支持硬链接，"
            "或使用 --link-mode copy 改为复制。"
        ) from e


async def _copy_artifact(src: Path, dest: Path) -> None:
    """把缓存文件复制到工作区（显式 --link-mode copy 时使用）

    copy2 需读取整个文件（可到 GB 级），放入线程池执行，
    避免物化大制品时阻塞事件循环（Web 多 job 并发同进程时尤其关键）。
    """
    await asyncio.to_thread(shutil.copy2, src, dest)


async def _write_url_meta(
    layout: BuildLayout, artifact: ResolvedArtifact, cache_path: Path
) -> None:
    """为无 sha1 的 URL 键制品写 sidecar 元数据

    记录 url/filename/size/实测 sha1，供缓存回退寻址时核对内容
    （防 URL 摘要误命中不同文件）。
    """
    import hashlib
    import json

    # 计算实测 sha1（物化前缓存文件已落盘）
    sha1 = await _compute_sha1(cache_path)
    meta_path = layout.url_meta(artifact.url)
    meta_path.parent.mkdir(parents=True, exist_ok=True)
    tmp = meta_path.with_name(meta_path.name + ".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(
            {
                "url": artifact.url,
                "filename": artifact.filename,
                "size": cache_path.stat().st_size,
                "sha1": sha1,
            },
            f,
            ensure_ascii=False,
        )
    os.replace(tmp, meta_path)


def _sha1_sync(path: Path) -> str:
    """同步计算文件 sha1（供线程池执行，避免阻塞事件循环）"""
    import hashlib

    hasher = hashlib.sha1()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


async def _compute_sha1(path: Path) -> str:
    """计算文件 sha1（异步壳；同步逐块读取放入线程池）"""
    return await asyncio.to_thread(_sha1_sync, path)
