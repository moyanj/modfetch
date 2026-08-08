"""
BuildApplicationService — 统一构建入口

CLI 与 Web 共用同一编排:
  validate_local → validate_remote → PlanBuild → ExecuteBuild → BuildResult

只依赖 domain 与 ports，不依赖 click/fastapi。
"""

import re
from typing import Optional, Tuple, Protocol

from modfetch.application.config_service import ConfigService
from modfetch.application.execute_build import BuildOptions, ExecuteBuild
from modfetch.application.plan_build import PlanBuild
from modfetch.application.validation import format_validation_issues
from modfetch.domain.build_plan import BuildPlan, BuildResult
from modfetch.domain.config_models import ModFetchConfig
from modfetch.domain.errors import ConfigValidationError
from modfetch.domain.events import BuildEvent, EventType
from modfetch.ports.event_sink import EventSink


class _AsyncClosable(Protocol):
    """可异步释放资源的协议（catalog/downloader 等持有 aiohttp session）"""

    async def close(self) -> None: ...


class BuildApplicationService:
    """统一构建入口

    编排完整构建生命周期: 本地校验 → 远程校验 → 计划生成 → 执行 → 结果事件。
    CLI 与 Web 均通过本服务执行构建；错误以 BuildResult.errors 值传递，
    校验失败则直接抛 ConfigValidationError（fail-fast）。
    """

    def __init__(
        self,
        config_service: ConfigService,
        plan_build: PlanBuild,
        execute_build: ExecuteBuild,
        event_sink: EventSink,
        closables: Tuple[_AsyncClosable, ...] = (),
    ):
        self._config_service = config_service
        self._plan_build = plan_build
        self._execute_build = execute_build
        self._event_sink = event_sink
        #: 构建完成后需释放的资源（catalog/downloader 的 aiohttp session）
        self._closables = closables

    async def close(self) -> None:
        """释放底层资源（aiohttp session 等）

        由调用方（CLI/Web）在构建结束后调用，避免连接池与
        session 泄漏；各资源 close 必须可重复安全调用。
        """
        for resource in self._closables:
            await resource.close()
        self._closables = ()

    async def plan(self, config: ModFetchConfig, job_id: str) -> BuildPlan:
        """生成构建计划（不执行下载/打包）

        供 Web 预览、CLI --dry-run 或外部工具消费计划内容；返回的
        BuildPlan 可通过 to_dict()/to_json()/to_file() 序列化输出。
        """
        plan, _report = await self._plan_build.execute(
            config, config.features, event_sink=self._event_sink, job_id=job_id
        )
        return plan

    async def execute(
        self,
        config: ModFetchConfig,
        job_id: str,
        options: Optional[BuildOptions] = None,
        event_sink: Optional[EventSink] = None,
        skip_remote_validation: bool = False,
    ) -> BuildResult:
        """执行一次完整构建

        Args:
            config: 已解析的用户配置（version/loader/模组清单）
            job_id: 构建作业标识（事件关联用，Web 端为作业 id）
            options: 执行选项；省略时按 config.output.download_dir 与
                config.max_concurrent 派生默认值
            event_sink: 本次构建的事件接收器；省略时回退构造注入的实例
            skip_remote_validation: True 时跳过远程校验
                （Web 预览等已校验场景）

        Returns:
            BuildResult: 含 outputs 与 errors；errors 非空表示部分失败，
            调用方据此判定成败（值传递，不抛异常）。
        """
        sink = event_sink or self._event_sink
        # 未显式提供时从配置派生默认下载目录与并发上限
        # （目录布局 BuildLayout 集中计算 cache/工作区/dist 路径）
        options = options or BuildOptions(
            layout=self._build_layout(config),
            max_concurrent=config.max_concurrent,
        )

        await self._publish(sink, job_id, EventType.BUILD_STARTED)

        # 1. 本地校验
        self._config_service.validate_local(config)
        await self._publish(sink, job_id, EventType.CONFIG_VALIDATED)

        # 2. 远程校验（features 已由 CLI -f 覆盖进 config.features）
        if not skip_remote_validation:
            report = await self._config_service.validate_remote(
                config, self._plan_build.catalog, features=config.features
            )
            if not report.is_valid:
                message = format_validation_issues(report.issues)
                # 远程校验失败属不可恢复错误: 先发布失败事件再 fail-fast 抛出
                await self._publish(
                    sink,
                    job_id,
                    EventType.BUILD_FAILED,
                    {"error": {"code": "E102", "message": message}},
                )
                raise ConfigValidationError(message)

        # 3. 生成构建计划
        plan, _report = await self._plan_build.execute(
            config, config.features, event_sink=sink, job_id=job_id
        )
        await self._publish(
            sink,
            job_id,
            EventType.PLAN_CREATED,
            {
                # 计划规模快照（供前端进度展示）
                "targets": len(plan.targets),
                "artifacts": len(plan.artifacts),
                "outputs": len(plan.outputs),
            },
        )

        # 4. 执行（下载 + 打包）
        result = await self._execute_build.execute(plan, job_id, sink, options)

        # 5. 结果事件（有错误按失败收尾，否则按成功收尾；结果以值传递）
        if result.errors:
            await self._publish(
                sink,
                job_id,
                EventType.BUILD_FAILED,
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
                sink,
                job_id,
                EventType.BUILD_COMPLETED,
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
    def _build_layout(config: ModFetchConfig):
        """从配置构造构建目录布局（集中计算 cache/工作区/dist）"""
        from modfetch.application.build_layout import BuildLayout

        return BuildLayout(config.output.download_dir)

    @staticmethod
    async def _publish(
        sink: EventSink,
        job_id: str,
        event_type: EventType,
        payload: Optional[dict] = None,
    ) -> None:
        """发布一条构建事件（payload 缺省时为空对象）"""
        await sink.publish(
            BuildEvent(job_id=job_id, event_type=event_type, payload=payload or {})
        )
