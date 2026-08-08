"""BuildPlan 序列化测试

锁定契约: BuildPlan.to_dict() 返回纯 dict（枚举已转 value、嵌套对象
递归展开），可直接 json.dumps 序列化；to_json() 产出合法 JSON；
to_file() 落盘并创建父目录。

计划生成链路（BuildApplicationService.plan）的集成验证见
integration/test_build_service.py。
"""

import json

from modfetch.domain.build_plan import (
    ArtifactCategory,
    BuildPlan,
    BuildTarget,
    OutputSpec,
    ResolvedArtifact,
)
from modfetch.domain.config_models import ModLoader

TARGET = BuildTarget("1.21.1", ModLoader.FABRIC)


def _artifact(name: str = "sodium") -> ResolvedArtifact:
    """构造最小制品"""
    return ResolvedArtifact(
        project_id="AAAA0001",
        project_name=name,
        category=ArtifactCategory.mods(),
        filename=f"{name}.jar",
        url="https://example.com/sodium.jar",
        hashes={"sha1": "0" * 40},
        destination=f"mods/{name}.jar",
        target=TARGET,
    )


def _plan() -> BuildPlan:
    return BuildPlan(
        targets=(TARGET,),
        artifacts=(_artifact(),),
        outputs=(OutputSpec(format="mrpack", target=TARGET, output_name="pack"),),
        metadata={"name": "TestPack", "version": "1.0.0"},
    )


class TestDictShape:
    def test_enums_converted_to_values(self):
        """ModLoader / ArtifactCategory 序列化为 value 字符串"""
        assert BuildTarget("1.21.1", ModLoader.NEOFORGE).to_dict() == {
            "minecraft_version": "1.21.1",
            "loader": "neoforge",
            "dir_name": "1.21.1-neoforge",
        }
        assert ArtifactCategory.shaderpacks().to_dict() == "shaderpacks"

    def test_artifact_full_dict_shape(self):
        """制品 dict 含全部字段与嵌套对象展开"""
        d = _artifact().to_dict()

        assert d["project_name"] == "sodium"
        assert d["category"] == "mods"
        assert d["target"] == TARGET.to_dict()
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


class TestToFile:
    def test_writes_json_and_creates_parents(self, tmp_path):
        """to_file 写入 JSON 并自动创建父目录, 返回绝对路径"""
        plan = _plan()
        out = tmp_path / "nested" / "sub" / "plan.json"

        written = plan.to_file(out)

        assert written == str(out.resolve())
        assert out.resolve().exists()
        # 内容为合法 JSON 且与 to_json 一致
        assert json.loads(out.read_text(encoding="utf-8")) == json.loads(
            plan.to_json()
        )

    def test_overwrites_existing(self, tmp_path):
        """to_file 覆盖已存在的目标文件"""
        plan = _plan()
        out = tmp_path / "plan.json"
        out.write_text("stale", encoding="utf-8")

        plan.to_file(out)

        assert json.loads(out.read_text(encoding="utf-8"))["metadata"][
            "name"
        ] == "TestPack"
