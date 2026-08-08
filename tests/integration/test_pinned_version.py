"""slug@version 版本固定语法端到端测试

锁定契约（参考 commit 8aa1cb1，适配新六边形架构）:
    - 配置解析: "sodium@0.6.0" → ModEntry(id="sodium", version="0.6.0")，
      字典形式 { slug = "sodium", version = "0.6.0" } 等价
    - 解析链路: ModEntry.version → ModResolver → catalog.get_version
      (specific_version=...) 透传
    - 固定版本未命中时**不降级**到最新版本（关键回归点: 曾静默降级）
    - to_dict 序列化保留 version 字段
"""

import pytest

from modfetch.adapters.modrinth import ModrinthClient
from modfetch.application.mod_resolver import ModResolver
from modfetch.application.plan_build import PlanBuild
from modfetch.domain.config_models import ModEntry, ModFetchConfig

pytestmark = pytest.mark.usefixtures("mock_modrinth")


def _make_config(mods: list):
    return ModFetchConfig.from_dict(
        {
            "minecraft": {
                "version": ["1.21.1"],
                "mod_loader": "fabric",
                "mods": mods,
            }
        }
    )


class TestAtSyntaxParsing:
    """解析基线见 test_config_parse.py；此处仅锁定 pinned 专属边界"""

    def test_only_first_at_is_split(self):
        """版本号中含 @ 时仅按第一个 @ 拆分（版本串不二次拆分）"""
        config = _make_config(["sodium@1.0.0-beta@2"])
        pinned = config.minecraft.mods[0]
        assert isinstance(pinned, ModEntry)
        assert pinned.id == "sodium"
        assert pinned.version == "1.0.0-beta@2"

    def test_to_dict_round_trip_preserves_version(self):
        """to_dict 序列化后 version 字段不丢失"""
        config = _make_config(["sodium@0.6.0"])
        serialized = config.to_dict()
        entry = serialized["minecraft"]["mods"][0]
        assert entry == {"id": "sodium", "version": "0.6.0"}


class TestPinnedVersionResolution:
    async def test_resolver_forwards_pinned_version_to_catalog(self, monkeypatch):
        """ModEntry.version 经 ModResolver 透传给 get_version(specific_version)"""
        calls: list[tuple] = []
        original = ModrinthClient.get_version

        async def spy(self, project_id, mc_version, loader, specific_version=None):
            calls.append((project_id, mc_version, loader, specific_version))
            return await original(
                self, project_id, mc_version, loader, specific_version
            )

        monkeypatch.setattr(ModrinthClient, "get_version", spy)

        config = _make_config(["sodium@0.6.0"])
        resolver = ModResolver(ModrinthClient())
        result = await resolver.resolve(config.minecraft.mods[0], "1.21.1", "fabric")

        assert result is not None
        # 透传的是解析出的 ModEntry.version，而非 None
        assert calls and calls[0][3] == "0.6.0"
        assert result[1].version == "0.6.0"

    async def test_unpinned_resolver_passes_none(self, monkeypatch):
        """无固定版本的纯字符串 → specific_version=None（走最新版本逻辑）"""
        calls: list[tuple] = []
        original = ModrinthClient.get_version

        async def spy(self, project_id, mc_version, loader, specific_version=None):
            calls.append((project_id, mc_version, loader, specific_version))
            return await original(
                self, project_id, mc_version, loader, specific_version
            )

        monkeypatch.setattr(ModrinthClient, "get_version", spy)

        resolver = ModResolver(ModrinthClient())
        result = await resolver.resolve("sodium", "1.21.1", "fabric")

        assert result is not None
        assert calls and calls[0][3] is None

    async def test_plan_resolves_pinned_version(self):
        """完整计划: 'sodium@0.6.0' 命中固定版本并进入制品"""
        config = _make_config(["sodium@0.6.0"])
        plan_build = PlanBuild(catalog=ModrinthClient())
        plan, _ = await plan_build.execute(config)

        # sodium + fabric-api 依赖
        assert len(plan.artifacts) == 2
        sodium_artifacts = [
            a for a in plan.artifacts if a.project_id == "AAAA0001"
        ]
        assert len(sodium_artifacts) == 1
        # 固定版本体现在物化文件名中（fixture 文件名含版本号）
        assert "0.6.0" in sodium_artifacts[0].filename

    async def test_pinned_version_missing_does_not_degrade(self):
        """固定版本未命中 → 条目被跳过，而非静默降级到最新版本"""
        config = _make_config(["sodium@9.9.9"])
        plan_build = PlanBuild(catalog=ModrinthClient())
        plan, report = await plan_build.execute(config)

        # 关键断言: 没有制品（未回退到最新 0.6.0）
        assert len(plan.artifacts) == 0

        # 条目记入 skipped 报告
        skipped = [
            item
            for per_target in report.skipped_by_target.values()
            for item in per_target
        ]
        assert skipped, "固定版本未命中时条目应被记录为跳过"
        joined = " ".join(skipped)
        assert "sodium" in joined
        assert "9.9.9" in joined
