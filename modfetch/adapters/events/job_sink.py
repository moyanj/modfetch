"""
作业事件接收器

将统一 BuildEvent 翻译为 WebSocket 事件流（保持现有前端契约的事件名），
并维护计数器生成 stats_update 快照。

字段统一（消除旧字段漂移）:
- total（不再混用 total_mods/total）
- completed（不再混用 downloaded/completed）
- bytes_downloaded / size / loader / error.code 均来自真实数据
"""

from typing import Awaitable, Callable, Dict, Optional

from modfetch.domain.events import BuildEvent, EventType

#: 事件广播回调 — 接收 {"event": str, "data": dict} 并推送给所有订阅者
EventBroadcaster = Callable[[Dict], Awaitable[None]]


class JobEventSink:
    """Web 作业状态事件接收器（实现 EventSink）"""

    def __init__(
        self,
        broadcaster: EventBroadcaster,
        job_id: str,
        config_summary: Optional[Dict] = None,
    ):
        self._broadcaster = broadcaster
        self._job_id = job_id
        self._config_summary = config_summary
        self._sequence = 0

        # 统计计数器（从事件中累积真实数据）
        self._total = 0
        self._completed = 0
        self._failed = 0
        self._bytes_downloaded = 0

    async def publish(self, event: BuildEvent) -> None:
        self._sequence += 1
        et = event.event_type
        data = event.payload

        if et == EventType.BUILD_STARTED:
            payload: Dict = {"job_id": self._job_id}
            if self._config_summary is not None:
                payload["config_summary"] = self._config_summary
            await self._emit("job_started", payload)

        elif et == EventType.CONFIG_VALIDATED:
            await self._emit("phase_change", {"phase": "resolve"})

        elif et == EventType.PLAN_CREATED:
            self._total = int(data.get("artifacts", 0))
            await self._emit_stats()

        elif et == EventType.RESOLVE_STARTED:
            await self._emit(
                "resolve_start",
                {
                    "mod_slug": data.get("mod_slug", ""),
                    "mc_version": data.get("mc_version", ""),
                    "loader": data.get("loader", ""),
                },
            )

        elif et == EventType.RESOLVE_COMPLETED:
            await self._emit(
                "resolve_complete",
                {
                    "mod_slug": data.get("mod_slug", ""),
                    "title": data.get("title", ""),
                    "version": data.get("version", ""),
                    "dependencies": data.get("dependencies", 0),
                },
            )

        elif et == EventType.RESOLVE_FAILED:
            await self._emit(
                "resolve_failed", {"mod_slug": data.get("mod_slug", "")}
            )

        elif et == EventType.DOWNLOAD_STARTED:
            await self._emit(
                "download_start",
                {"filename": data.get("filename", ""), "size": 0},
            )

        elif et == EventType.DOWNLOAD_PROGRESS:
            downloaded = int(data.get("bytes_downloaded", 0))
            total = int(data.get("bytes_total", 0))
            await self._emit(
                "download_progress",
                {
                    "filename": data.get("filename", ""),
                    "percent": (downloaded / total * 100) if total > 0 else 0.0,
                    "bytes_downloaded": downloaded,
                    "bytes_total": total,
                },
            )

        elif et == EventType.DOWNLOAD_COMPLETED:
            self._completed += 1
            self._bytes_downloaded += int(data.get("size", 0))
            await self._emit(
                "download_complete",
                {
                    "filename": data.get("filename", ""),
                    "size": data.get("size", 0),
                },
            )
            await self._emit_stats()

        elif et == EventType.DOWNLOAD_FAILED:
            self._failed += 1
            await self._emit(
                "download_failed",
                {
                    "filename": data.get("filename", ""),
                    "error": {
                        "code": "E300",
                        "message": data.get("error", ""),
                    },
                },
            )
            await self._emit_stats()

        elif et == EventType.PACKAGE_STARTED:
            await self._emit("phase_change", {"phase": "package"})
            await self._emit(
                "package_start",
                {
                    "format": data.get("format", ""),
                    "target": data.get("target", ""),
                },
            )

        elif et == EventType.PACKAGE_COMPLETED:
            path = data.get("path", "")
            filename = path.rsplit("/", 1)[-1] if path else ""
            await self._emit(
                "package_complete",
                {
                    "filename": filename,
                    "path": path,
                    "size": data.get("size", 0),
                    "format": data.get("format", ""),
                },
            )

        elif et == EventType.PACKAGE_FAILED:
            await self._emit(
                "package_failed",
                {
                    "format": data.get("format", ""),
                    "target": data.get("target", ""),
                    "error": data.get("error", ""),
                },
            )

        elif et == EventType.BUILD_COMPLETED:
            outputs = data.get("outputs", [])
            await self._emit(
                "job_complete",
                {
                    "results": [
                        self._output_to_result(o) for o in outputs
                    ],
                    "stats": data.get("stats", {}),
                },
            )

        elif et == EventType.BUILD_FAILED:
            error = data.get("error")
            errors = data.get("errors")
            if error:
                await self._emit("job_failed", {"error": error})
            else:
                # 汇总错误列表为单一 job_failed（取首个错误的 code）
                first = errors[0] if errors else {}
                await self._emit(
                    "job_failed",
                    {
                        "error": {
                            "code": first.get("code", "E500"),
                            "message": first.get("message", "构建失败"),
                        },
                        "errors": errors or [],
                    },
                )

    async def close(self) -> None:
        pass

    # -- 内部 ---------------------------------------------------------------

    @staticmethod
    def _output_to_result(output: dict) -> dict:
        """统一输出 → JobResultItem 兼容格式"""
        path = output.get("path", "")
        filename = path.rsplit("/", 1)[-1] if path else ""
        target = output.get("target", "")
        # target 形如 "1.21.1-fabric"
        mc_version, _, loader = target.rpartition("-")
        return {
            "filename": filename,
            "path": path,
            "size": output.get("size", 0),
            "format": output.get("format", ""),
            "mc_version": mc_version,
            "loader": loader,
        }

    async def _emit(self, name: str, data: dict) -> None:
        await self._broadcaster(
            {
                "event": name,
                "data": {
                    "job_id": self._job_id,
                    "sequence": self._sequence,
                    **data,
                },
            }
        )

    async def _emit_stats(self) -> None:
        """广播统计快照（字段统一: total/completed/failed/bytes_downloaded）"""
        await self._emit(
            "stats_update",
            {
                "total": self._total,
                "completed": self._completed,
                "failed": self._failed,
                "skipped": 0,
                "bytes_downloaded": self._bytes_downloaded,
            },
        )
