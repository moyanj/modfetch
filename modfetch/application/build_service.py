"""
BuildApplicationService — 统一构建入口

CLI 与 Web 共用同一编排:
  validate_local → validate_remote → PlanBuild → ExecuteBuild → BuildResult

只依赖 domain 与 ports，不依赖 click/fastapi。
"""

from typing import Optional

from modfetch.application.config_service import ConfigService
from modfetch.application.execute_build import BuildOptions, ExecuteBuild
from modfetch.application.plan_build import PlanBuild
from modfetch.application.validation import format_validation_issues
from modfetch.domain.build_plan import BuildResult
from modfetch.domain.config_models import ModFetchConfig
from modfetch.domain.errors import ConfigValidationError
from modfetch.domain.events import BuildEvent, EventType
from modfetch.ports.event_sink import EventSink


class BuildApplicationService:
    """统一构建入口"""

    def __init__(
        self,
        config_service: ConfigService,
        plan_build: PlanBuild,
        execute_build: ExecuteBuild,
        event_sink: EventSink,
    ):
        self._config_service = config_service
        self._plan_build = plan_build
        self._execute_build = execute_build
        self._event_sink = event_sink

    async def execute(
        self,
        config: ModFetchConfig,
        job_id: str,
        options: Optional[BuildOptions] = None,
        event_sink: Optional[EventSink] = None,
        skip_remote_validation: bool = False,
    ) -> BuildResult:
        sink = event_sink or self._event_sink
        options = options or BuildOptions(
            download_dir=config.output.download_dir,
            max_concurrent=config.max_concurrent,
        )

        await self._publish(sink, job_id, EventType.BUILD_STARTED)

        # 1. 本地校验
        self._config_service.validate_local(config)
        await self._publish(sink, job_id, EventType.CONFIG_VALIDATED)

        # 2. 远程校验
        if not skip_remote_validation:
            report = await self._config_service.validate_remote(
                config, self._plan_build.catalog
            )
            if not report.is_valid:
                message = format_validation_issues(report.issues)
                await self._publish(
                    sink, job_id, EventType.BUILD_FAILED,
                    {"error": {"code": "E102", "message": message}},
                )
                raise ConfigValidationError(message)

        # 3. 生成构建计划
        plan, _report = await self._plan_build.execute(config, config.features)
        await self._publish(
            sink, job_id, EventType.PLAN_CREATED,
            {
                "targets": len(plan.targets),
                "artifacts": len(plan.artifacts),
                "outputs": len(plan.outputs),
            },
        )

        # 4. 执行（下载 + 打包）
        result = await self._execute_build.execute(
            plan, job_id, sink, options
        )

        # 5. 结果事件
        if result.errors:
            await self._publish(
                sink, job_id, EventType.BUILD_FAILED,
                {
                    "errors": [
                        {
                            "code": e.code,
                            "message": e.message,
                            "target": e.target.dir_name,
                            "phase": e.phase,
                        }
                        for e in result.errors
                    ]
                },
            )
        else:
            await self._publish(
                sink, job_id, EventType.BUILD_COMPLETED,
                {
                    "outputs": [
                        {
                            "path": o.path,
                            "format": o.format,
                            "size": o.size,
                            "target": o.target.dir_name,
                        }
                        for o in result.outputs
                    ],
                    "stats": {
                        "total": result.stats.total_artifacts,
                        "downloaded": result.stats.downloaded,
                        "skipped": result.stats.skipped,
                        "failed": result.stats.failed,
                        "bytes_downloaded": result.stats.bytes_downloaded,
                    },
                },
            )

        return result

    @staticmethod
    async def _publish(
        sink: EventSink, job_id: str, event_type: EventType, payload: dict = None
    ) -> None:
        await sink.publish(
            BuildEvent(
                job_id=job_id, event_type=event_type, payload=payload or {}
            )
        )
