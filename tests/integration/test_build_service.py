"""BuildApplicationService 端到端测试（新架构主路径）"""

import json
import zipfile
from pathlib import Path

import pytest

from modfetch.application.build_layout import normalize_slug
from modfetch.application.build_service import BuildApplicationService
from modfetch.composition import create_build_service
from modfetch.domain.config_models import ModFetchConfig
from modfetch.domain.events import BuildEvent

pytestmark = pytest.mark.usefixtures("mock_modrinth")


class CollectingSink:
    """收集全部事件的 EventSink"""

    def __init__(self):
        self.events: list[BuildEvent] = []

    async def publish(self, event: BuildEvent) -> None:
        self.events.append(event)

    async def close(self) -> None:
        pass

    @property
    def types(self) -> list[str]:
        return [e.event_type.value for e in self.events]


async def _run(
    config_dict: dict, sink: CollectingSink, service=None
):
    config = ModFetchConfig.from_dict(config_dict)
    service = service or create_build_service(event_sink=sink)
    result = await service.execute(config, job_id="test-job")
    return result, Path(config.output.download_dir)


def _mrpack_path(root: Path, *, slug: str = "testpack",
                 version: str = "1.0.0", mc: str = "1.21.1",
                 loader: str = "fabric", mode: str = "") -> Path:
    """按新布局构造期望的 mrpack 路径"""
    base = f"{slug}-{version}-mc{mc}-{loader}"
    if mode:
        base += f"-{mode}"
    return root / "dist" / f"{base}.mrpack"


class TestBuildService:
    async def test_full_build_via_service(self, make_config_dict):
        """新架构完整链路: 校验 → 计划 → 下载 → 打包"""
        sink = CollectingSink()
        result, download_dir = await _run(make_config_dict(), sink)

        assert result.success
        assert len(result.outputs) == 1
        assert result.stats.downloaded == 2  # sodium + fabric-api 依赖

        mrpack = _mrpack_path(download_dir)
        assert mrpack.exists()
        with zipfile.ZipFile(mrpack) as zf:
            manifest = json.loads(zf.read("modrinth.index.json"))
            assert manifest["name"] == "TestPack"
            assert manifest["dependencies"]["fabric-loader"] == "0.16.5"

    async def test_event_sequence(self, make_config_dict):
        """事件序列: 以 build_started 开始，build_completed 结束"""
        sink = CollectingSink()
        await _run(make_config_dict(), sink)

        types = sink.types
        assert types[0] == "build_started"
        assert "config_validated" in types
        assert "plan_created" in types
        assert "download_completed" in types
        assert "package_completed" in types
        assert types[-1] == "build_completed"

        # 事件信封契约: to_dict 含 event/data
        for event in sink.events:
            d = event.to_dict()
            assert isinstance(d["event"], str)
            assert isinstance(d["data"], dict)
            assert d["data"]["job_id"] == "test-job"

    async def test_download_failure_structured(self, make_config_dict, tmp_path):
        """下载失败 → BuildResult.errors 含 phase=download 的结构化错误"""
        sink = CollectingSink()
        result, _ = await _run(
            make_config_dict(
                minecraft={
                    "extra_urls": [{"url": "file:///nonexistent/ghost.jar"}]
                }
            ),
            sink,
        )

        assert not result.success
        download_errors = [e for e in result.errors if e.phase == "download"]
        assert len(download_errors) == 1
        assert download_errors[0].code == "E300"
        assert "build_failed" in sink.types

    async def test_multi_target_outputs(self, make_config_dict):
        """多版本×多加载器 → 4 个输出"""
        sink = CollectingSink()
        result, download_dir = await _run(
            make_config_dict(
                minecraft={
                    "version": ["1.21.1", "1.20.4"],
                    "mod_loader": ["fabric", "forge"],
                }
            ),
            sink,
        )

        assert result.success
        assert len(result.outputs) == 4
        assert len(list((download_dir / "dist").glob("*.mrpack"))) == 4

    async def test_reference_mode(self, make_config_dict):
        """REFERENCE 模式: 不下载平台制品，manifest 引用完整"""
        sink = CollectingSink()
        result, download_dir = await _run(
            make_config_dict(output={"mrpack_modes": ["reference"]}), sink
        )

        assert result.success
        mrpack = _mrpack_path(download_dir)
        with zipfile.ZipFile(mrpack) as zf:
            manifest = json.loads(zf.read("modrinth.index.json"))
            paths = {f["path"] for f in manifest["files"]}
            assert "mods/sodium-fabric-0.6.0.jar" in paths
            assert "mods/fabric-api-0.100.0.jar" in paths

    def _make_extra_files(self, tmp_path: Path):
        """创建两个本地 file:// 文件（file 类型 + shaderpack 类型）"""
        datafile = tmp_path / "custom.json"
        datafile.write_text('{"custom": true}', encoding="utf-8")
        shaderfile = tmp_path / "seus.zip"
        shaderfile.write_bytes(b"PK\x03\x04 shader content")
        return datafile, shaderfile

    async def test_extra_url_injected_download_mode(
        self, make_config_dict, tmp_path
    ):
        """DOWNLOAD 模式: extra_url 文件下载并注入 mrpack overrides"""
        datafile, _ = self._make_extra_files(tmp_path)
        sink = CollectingSink()
        result, download_dir = await _run(
            make_config_dict(
                minecraft={
                    "extra_urls": [
                        {
                            "url": datafile.as_uri(),
                            "type": "file",
                            "filename": "custom.json",
                        }
                    ]
                }
            ),
            sink,
        )

        assert result.success
        # extra_url 文件计入下载统计
        assert result.stats.downloaded == 3  # sodium + fabric-api + custom.json
        mrpack = _mrpack_path(download_dir)
        with zipfile.ZipFile(mrpack) as zf:
            # file 类型 → overrides 根目录
            assert "overrides/custom.json" in zf.namelist()
            content = zf.read("overrides/custom.json")
            assert json.loads(content) == {"custom": True}

    async def test_extra_url_injected_reference_mode(
        self, make_config_dict, tmp_path
    ):
        """REFERENCE 模式: extra_url 进入 overrides, catalog 制品仅引用"""
        _, shaderfile = self._make_extra_files(tmp_path)
        sink = CollectingSink()
        result, download_dir = await _run(
            make_config_dict(
                output={"mrpack_modes": ["reference"]},
                minecraft={
                    "extra_urls": [
                        {
                            "url": shaderfile.as_uri(),
                            "type": "shaderpack",
                            "filename": "seus.zip",
                        }
                    ]
                },
            ),
            sink,
        )

        assert result.success
        mrpack = _mrpack_path(download_dir)
        with zipfile.ZipFile(mrpack) as zf:
            manifest = json.loads(zf.read("modrinth.index.json"))
            # catalog 制品写入 manifest.files（引用模式）
            assert any(
                f["path"].startswith("mods/") for f in manifest["files"]
            )
            # shaderpack 类型 extra → overrides/shaderpacks/
            entries = zf.namelist()
            assert "overrides/shaderpacks/seus.zip" in entries

    async def test_extra_url_shaderpack_destination_subdir(
        self, make_config_dict, tmp_path
    ):
        """shaderpack 类型 extra_url 落入 overrides/shaderpacks/ 子目录"""
        _, shaderfile = self._make_extra_files(tmp_path)
        sink = CollectingSink()
        result, download_dir = await _run(
            make_config_dict(
                minecraft={
                    "extra_urls": [
                        {
                            "url": shaderfile.as_uri(),
                            "type": "shaderpack",
                            "filename": "seus.zip",
                        }
                    ]
                }
            ),
            sink,
        )

        assert result.success
        mrpack = _mrpack_path(download_dir)
        with zipfile.ZipFile(mrpack) as zf:
            assert "overrides/shaderpacks/seus.zip" in zf.namelist()
