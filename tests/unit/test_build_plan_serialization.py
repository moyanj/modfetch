"""BuildPlan 序列化测试

锁定契约: BuildPlan.to_dict() 返回纯 dict（枚举已转 value、嵌套对象
递归展开），可直接 json.dumps 序列化；to_json() 产出合法 JSON。
"""

import json

from modfetch.application.build_service import BuildApplicationService
from modfetch.domain.build_plan import (
    ArtifactCategory,
    BuildPlan,
    BuildTarget,
    OutputSpec,
    ResolvedArtifact,
)
from modfetch.domain.config_models import ModLoader


def _artifact(name: str = "sodium", category=None, target=None) -> ResolvedArtifact:
    """构造最小制品"""
    return ResolvedArtifact(
        project_id="AAAA0001",
        project_name=name,
        category=category or ArtifactCategory.mods(),
        filename=f"{name}.jar",
        url="https://example.com/sodium.jar",
        hashes={"sha1": "0" * 40},
        destination=f"mods/{name}.jar",
        target=target or BuildTarget("1.21.1", ModLoader.FABRIC),
    )


def _plan() -> BuildPlan:
    target = BuildTarget("1.21.1", ModLoader.FABRIC)
    return BuildPlan(
        targets=(target,),
        artifacts=(_artifact(target=target),),
        outputs=(OutputSpec(format="mrpack", target=target, output_name="pack"),),
        metadata={"name": "TestPack", "version": "1.0.0"},
    )


class TestBuildTargetToDict:
    def test_loader_enum_converted_to_value(self):
        """ModLoader 枚举转 value 字符串"""
        d = BuildTarget("1.21.1", ModLoader.NEOFORGE).to_dict()
        assert d == {
            "minecraft_version": "1.21.1",
            "loader": "neoforge",
            "dir_name": "1.21.1-neoforge",
        }


class TestArtifactCategoryToDict:
    def test_returns_value_string(self):
        """类别序列化为纯字符串"""
        assert ArtifactCategory.shaderpacks().to_dict() == "shaderpacks"


class TestResolvedArtifactToDict:
    def test_full_dict_shape(self):
        """制品 dict 含全部字段与嵌套对象展开"""
        target = BuildTarget("1.21.1", ModLoader.FABRIC)
        d = _artifact(category=ArtifactCategory.mods(), target=target).to_dict()

        assert d["project_name"] == "sodium"
        assert d["category"] == "mods"
        assert d["target"] == target.to_dict()
        assert d["mrpack_entry"] == {
            "path": "mods/sodium.jar",
            "hashes": {"sha1": "0" * 40},
            "env": {"client": "required", "server": "required"},
            "downloads": ["https://example.com/sodium.jar"],
            "fileSize": 0,
        }


class TestBuildPlanToDict:
    def test_json_round_trip(self):
        """to_dict 可被 json.dumps 直接序列化，to_json 可反序列化"""
        plan = _plan()
        payload = json.loads(plan.to_json())

        assert payload["metadata"] == {"name": "TestPack", "version": "1.0.0"}
        assert len(payload["targets"]) == 1
        assert payload["targets"][0]["loader"] == "fabric"
        assert len(payload["artifacts"]) == 1
        assert payload["artifacts"][0]["category"] == "mods"
        assert len(payload["outputs"]) == 1
        assert payload["outputs"][0]["format"] == "mrpack"

    def test_ensure_ascii_false_preserves_chinese(self):
        """to_json 中文不做 \\uXXXX 转义"""
        plan = _plan()
        assert "TestPack" in plan.to_json()

    def test_to_file_writes_json_and_creates_parents(self, tmp_path):
        """to_file 写入 JSON 并自动创建父目录, 返回绝对路径"""
        plan = _plan()
        out = tmp_path / "nested" / "sub" / "plan.json"

        written = plan.to_file(out)

        # 返回绝对路径
        assert written == str(out.resolve())
        assert out.resolve().exists()
        # 内容为合法 JSON 且与 to_json 一致
        assert json.loads(out.read_text(encoding="utf-8")) == json.loads(
            plan.to_json()
        )

    def test_to_file_overwrites_existing(self, tmp_path):
        """to_file 覆盖已存在的目标文件"""
        plan = _plan()
        out = tmp_path / "plan.json"
        out.write_text("stale", encoding="utf-8")

        plan.to_file(out)

        assert json.loads(out.read_text(encoding="utf-8"))["metadata"][
            "name"
        ] == "TestPack"


class TestBuildServicePlanProperty:
    """BuildApplicationService.plan 生成计划并可序列化输出"""

    async def test_plan_generated_and_serializable_to_file(
        self, stub_catalog, make_config_dict, tmp_path
    ):
        """plan() 生成计划, 可 to_dict / to_file 输出到文件"""
        from modfetch.application.build_service import BuildApplicationService
        from modfetch.application.config_service import ConfigService
        from modfetch.application.execute_build import ExecuteBuild
        from modfetch.application.plan_build import PlanBuild
        from modfetch.domain.config_models import ModFetchConfig
        from modfetch.ports.event_sink import EventSink

        stub_catalog.add_project("sodium", "sodium")
        config = ModFetchConfig.from_dict(
            make_config_dict(minecraft={"mods": ["sodium"]})
        )
        config.features = []

        class _NullSink(EventSink):
            async def publish(self, *args, **kwargs):  # type: ignore[no-untyped-def]
                pass

            async def close(self) -> None:  # type: ignore[no-untyped-def]
                pass

        plan_build = PlanBuild(catalog=stub_catalog)
        svc = BuildApplicationService(
            config_service=ConfigService(),
            plan_build=plan_build,
            execute_build=ExecuteBuild.__new__(ExecuteBuild),  # 不触碰真实执行
            event_sink=_NullSink(),
        )

        # plan() 生成计划（不执行下载）
        generated = await svc.plan(config, job_id="test")

        # 序列化闭环: 读内存 + 落盘
        payload = generated.to_dict()
        assert payload["targets"][0]["loader"] == "fabric"
        assert payload["artifacts"][0]["category"] == "mods"

        out = tmp_path / "sub" / "plan.json"
        saved = generated.to_file(out)
        assert saved == str(out.resolve())
        assert json.loads(out.read_text(encoding="utf-8"))["metadata"][
            "name"
        ] == "TestPack"
