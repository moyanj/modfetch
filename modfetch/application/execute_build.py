"""
ExecuteBuild 用例

按 BuildPlan 执行下载与打包:
- 下载经 DownloaderPort（队列编排由 DownloadExecutor 承担）
- 打包经 PackagerPort；单 target 打包失败记为 BuildError 并继续其他 target
- 下载失败记为 BuildError（phase="download"），不再静默
- 全生命周期事件经 EventSink 发布
"""

import os
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional

from loguru import logger

from modfetch.adapters.download.executor import DownloadExecutor
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


@dataclass(frozen=True)
class BuildOptions:
    """构建执行选项"""

    download_dir: str = "downloads"
    max_concurrent: int = 5


class ExecuteBuild:
    """下载 + 打包执行用例"""

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
        options = options or BuildOptions()
        workspace = Path(options.download_dir)
        workspace.mkdir(parents=True, exist_ok=True)

        outputs: List[OutputArtifact] = []
        errors: List[BuildError] = []
        total_downloaded = 0
        total_skipped = 0
        total_failed = 0
        total_bytes = 0

        for target in plan.targets:
            # -- 下载 --
            report = await self._download_target(
                plan, target, workspace, job_id, event_sink
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

            # -- 打包 --
            for spec in plan.outputs_for(target):
                await self._publish(
                    event_sink, job_id, EventType.PACKAGE_STARTED,
                    {"format": spec.format, "target": target.dir_name},
                )
                try:
                    artifact = await self._packager.package(
                        plan, spec, target, workspace
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

        result = BuildResult(
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
        return result

    # -- 下载 ----------------------------------------------------------------

    async def _download_target(
        self,
        plan: BuildPlan,
        target: BuildTarget,
        workspace: Path,
        job_id: str,
        event_sink: EventSink,
    ):
        """下载单个 target 的全部制品"""
        needs_download = self._needs_download(plan, target)
        version_dir = workspace / target.dir_name
        version_dir.mkdir(parents=True, exist_ok=True)

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
            max_concurrent=self._max_concurrent,
            progress=on_progress,
            on_task_event=on_task_event,
        )

        for artifact in plan.artifacts_for(target):
            if artifact.origin == "catalog" and not needs_download:
                logger.info(f"'{artifact.project_name}' 已记录引用 (跳过下载)")
                continue
            await executor.submit(self._make_task(artifact, version_dir))
            await self._publish(
                event_sink, job_id, EventType.DOWNLOAD_STARTED,
                {"filename": artifact.filename, "target": target.dir_name},
            )

        return await executor.run()

    @staticmethod
    def _needs_download(plan: BuildPlan, target: BuildTarget) -> bool:
        """是否存在需要真实文件的输出（zip 或 mrpack download 模式）"""
        return any(
            spec.format == "zip"
            or (spec.format == "mrpack" and spec.mrpack_mode == "download")
            for spec in plan.outputs_for(target)
        )

    @staticmethod
    def _make_task(
        artifact: ResolvedArtifact, version_dir: Path
    ) -> DownloadTask:
        dest_dir = version_dir / os.path.dirname(artifact.destination)
        return DownloadTask(
            url=artifact.url,
            filename=artifact.filename,
            destination=str(dest_dir),
            expected_sha1=artifact.hashes.get("sha1"),
        )

    @staticmethod
    async def _publish(
        sink: EventSink, job_id: str, event_type: EventType, payload: dict
    ) -> None:
        await sink.publish(
            BuildEvent(job_id=job_id, event_type=event_type, payload=payload)
        )
