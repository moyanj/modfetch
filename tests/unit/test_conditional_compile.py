"""条件编译（feature/only_version）在计划生成层面的组合测试

锁定契约: mods / resourcepacks / shaderpacks / extra_urls 四类条目
在 PlanBuild 生成计划时统一经 should_include 过滤:
    - only_version: 版本命中才包含（列表命中其一即可）
    - feature: 声明的功能标签全部启用才包含（AND）
    - 两类条件组合亦为 AND；字符串条目无条件, 始终包含

背景: should_include 曾对对象条目过滤完全失效（isinstance 分支不命中），
导致带 feature 的条目被无条件下构建。本套用例在完整计划链路验证
条件编译真实生效，防止回归。谓词本身的真值表见 test_version_matcher.py。
"""

import pytest

from modfetch.application.plan_build import PlanBuild
from modfetch.domain.config_models import ModFetchConfig


async def _plan_names(
    stub_catalog, make_config_dict, mc: dict, active=None, **config_kw
) -> set:
    """构造配置并生成计划，返回制品项目名集合

    active: 传给 execute 的 features（None 时回落 config.features）；
    config_kw: 其余顶层配置键（如 features=["x"] 设置配置默认值）。
    """
    config = ModFetchConfig.from_dict(
        make_config_dict(minecraft=mc, **config_kw)
    )
    plan, _ = await PlanBuild(catalog=stub_catalog).execute(
        config, features=active
    )
    return {a.project_name for a in plan.artifacts}


class TestFeatureGate:
    async def test_enabled_included_disabled_excluded(
        self, stub_catalog, make_config_dict
    ):
        """feature 启用 → 包含；未启用 → 跳过，无条件条目保留"""
        stub_catalog.add_project("sodium", "sodium")
        stub_catalog.add_project("iris", "iris")
        mc = {
            "mods": ["sodium", {"id": "iris", "feature": "graphics"}],
        }

        assert await _plan_names(
            stub_catalog, make_config_dict, mc, active=["graphics"]
        ) == {"sodium", "iris"}
        assert await _plan_names(
            stub_catalog, make_config_dict, mc, active=[]
        ) == {"sodium"}

    async def test_multi_feature_all_required(
        self, stub_catalog, make_config_dict
    ):
        """多 feature 全部启用才包含（AND 语义）"""
        stub_catalog.add_project("sodium", "sodium")
        stub_catalog.add_project("iris", "iris")
        mc = {
            "mods": [
                "sodium",
                {"id": "iris", "feature": ["graphics", "shaders"]},
            ],
        }

        assert await _plan_names(
            stub_catalog, make_config_dict, mc, active=["graphics"]
        ) == {"sodium"}
        assert await _plan_names(
            stub_catalog,
            make_config_dict,
            mc,
            active=["graphics", "shaders"],
        ) == {"sodium", "iris"}


class TestOnlyVersionGate:
    async def test_match_mismatch_and_list(
        self, stub_catalog, make_config_dict
    ):
        """版本命中（含列表命中其一）→ 包含；不命中 → 排除"""
        stub_catalog.add_project("sodium", "sodium")
        stub_catalog.add_project("extra-mod", "extra-mod")

        for only_version, expected in [
            ("1.21.1", {"sodium", "extra-mod"}),          # 命中
            ("1.20.4", {"sodium"}),                        # 不命中
            (["1.20.4", "1.21.1"], {"sodium", "extra-mod"}),  # 列表命中其一
        ]:
            mc = {
                "mods": [
                    "sodium",
                    {"id": "extra-mod", "only_version": only_version},
                ],
            }
            assert await _plan_names(
                stub_catalog, make_config_dict, mc
            ) == expected


class TestCombinedConditions:
    async def test_feature_and_only_version_are_and(
        self, stub_catalog, make_config_dict
    ):
        """feature + only_version 任一不满足即排除"""
        stub_catalog.add_project("sodium", "sodium")
        stub_catalog.add_project("iris", "iris")

        def mc(only_version: str) -> dict:
            return {
                "mods": [
                    "sodium",
                    {
                        "id": "iris",
                        "feature": "graphics",
                        "only_version": only_version,
                    },
                ],
            }

        # feature 未启用 → 排除
        assert await _plan_names(
            stub_catalog, make_config_dict, mc("1.21.1"), active=[]
        ) == {"sodium"}
        # feature 启用 + 版本命中 → 包含
        assert await _plan_names(
            stub_catalog,
            make_config_dict,
            mc("1.21.1"),
            active=["graphics"],
        ) == {"sodium", "iris"}
        # feature 启用但版本不命中 → 排除
        assert await _plan_names(
            stub_catalog,
            make_config_dict,
            mc("1.20.4"),
            active=["graphics"],
        ) == {"sodium"}

    async def test_unconditional_entries_always_included(
        self, stub_catalog, make_config_dict
    ):
        """纯字符串条目与无条件对象条目 → 始终包含"""
        stub_catalog.add_project("sodium", "sodium")
        stub_catalog.add_project("modmenu", "modmenu")
        mc = {"mods": ["sodium", {"id": "modmenu"}]}

        assert await _plan_names(
            stub_catalog, make_config_dict, mc, active=[]
        ) == {"sodium", "modmenu"}

    async def test_features_fallback_to_config(
        self, stub_catalog, make_config_dict
    ):
        """execute 未传 features → 回落 config.features"""
        stub_catalog.add_project("sodium", "sodium")
        stub_catalog.add_project("iris", "iris")
        mc = {"mods": ["sodium", {"id": "iris", "feature": "graphics"}]}

        # 不传 active，config.features 生效
        assert await _plan_names(
            stub_catalog, make_config_dict, mc, features=["graphics"]
        ) == {"sodium", "iris"}


class TestAllCategories:
    """条件编译对资源包/光影包/extra_url 三类条目一致生效"""

    @pytest.mark.parametrize(
        "key,entry,expected_name",
        [
            ("resourcepacks", {"id": "faithful", "feature": "f"}, "faithful"),
            (
                "shaderpacks",
                {"id": "complementary", "feature": "f"},
                "complementary",
            ),
            (
                "extra_urls",
                {"url": "https://example.com/custom.jar", "feature": "f"},
                "custom.jar",
            ),
        ],
    )
    async def test_feature_gate_per_category(
        self,
        stub_catalog,
        make_config_dict,
        key: str,
        entry: dict,
        expected_name: str,
    ):
        stub_catalog.add_project("sodium", "sodium")
        if "id" in entry:
            stub_catalog.add_project(entry["id"], entry["id"])
        mc = {"mods": ["sodium"], key: [entry]}

        assert await _plan_names(
            stub_catalog, make_config_dict, mc, active=[]
        ) == {"sodium"}
        assert await _plan_names(
            stub_catalog, make_config_dict, mc, active=["f"]
        ) == {"sodium", expected_name}
