"""条件编译（feature/only_version）在计划生成层面的组合测试

锁定契约: mods / resourcepacks / shaderpacks / extra_urls 四类条目
在 PlanBuild 生成计划时统一经 _should_include 过滤:
    - only_version: 版本命中才包含
    - feature: 声明的功能标签全部启用才包含（启用条件语义）
    - 组合条件为 AND——任一不满足即排除
    - 字符串条目无条件, 始终包含

背景: should_include 曾对对象条目过滤完全失效（dict 分支不命中），
导致带 feature 的条目被无条件下构建。本套用例在完整计划链路验证
条件编译真实生效，防止回归。
"""

import pytest

from modfetch.application.plan_build import PlanBuild
from modfetch.domain.config_models import ModFetchConfig


def _project_names(plan) -> set:
    """收集计划中全部制品的项目名（slug）"""
    return {a.project_name for a in plan.artifacts}


class TestFeatureFiltering:
    async def test_feature_enabled_included(self, stub_catalog, make_config_dict):
        """feature 启用 → 模组进入计划"""
        stub_catalog.add_project("sodium", "sodium")
        stub_catalog.add_project("iris", "iris")

        config = ModFetchConfig.from_dict(
            make_config_dict(
                minecraft={
                    "version": ["1.21.1"],
                    "mod_loader": "fabric",
                    "mods": [
                        "sodium",
                        {"id": "iris", "feature": "graphics"},
                    ],
                }
            )
        )

        plan, _ = await PlanBuild(catalog=stub_catalog).execute(
            config, features=["graphics"]
        )
        assert _project_names(plan) == {"sodium", "iris"}

    async def test_feature_not_enabled_excluded(self, stub_catalog, make_config_dict):
        """feature 未启用 → 条件模组被跳过, 无条件模组保留"""
        stub_catalog.add_project("sodium", "sodium")
        stub_catalog.add_project("iris", "iris")

        config = ModFetchConfig.from_dict(
            make_config_dict(
                minecraft={
                    "version": ["1.21.1"],
                    "mod_loader": "fabric",
                    "mods": [
                        "sodium",
                        {"id": "iris", "feature": "graphics"},
                    ],
                }
            )
        )

        plan, _ = await PlanBuild(catalog=stub_catalog).execute(config, features=[])
        assert _project_names(plan) == {"sodium"}

    async def test_feature_multi_all_required(self, stub_catalog, make_config_dict):
        """多 feature 全部启用才包含（AND）"""
        stub_catalog.add_project("sodium", "sodium")
        stub_catalog.add_project("iris", "iris")

        config = ModFetchConfig.from_dict(
            make_config_dict(
                minecraft={
                    "version": ["1.21.1"],
                    "mod_loader": "fabric",
                    "mods": [
                        "sodium",
                        {"id": "iris", "feature": ["graphics", "shaders"]},
                    ],
                }
            )
        )

        # 只启用 graphics → iris 不满足全部 → 排除
        plan, _ = await PlanBuild(catalog=stub_catalog).execute(
            config, features=["graphics"]
        )
        assert _project_names(plan) == {"sodium"}

        # 两个都启用 → 包含
        plan, _ = await PlanBuild(catalog=stub_catalog).execute(
            config, features=["graphics", "shaders"]
        )
        assert _project_names(plan) == {"sodium", "iris"}


class TestOnlyVersionFiltering:
    async def test_only_version_match_included(self, stub_catalog, make_config_dict):
        """only_version 命中 → 包含"""
        stub_catalog.add_project("sodium", "sodium")
        stub_catalog.add_project("extra-mod", "extra-mod")

        config = ModFetchConfig.from_dict(
            make_config_dict(
                minecraft={
                    "version": ["1.21.1"],
                    "mod_loader": "fabric",
                    "mods": [
                        "sodium",
                        {"id": "extra-mod", "only_version": "1.21.1"},
                    ],
                }
            )
        )

        plan, _ = await PlanBuild(catalog=stub_catalog).execute(config)
        assert _project_names(plan) == {"sodium", "extra-mod"}

    async def test_only_version_mismatch_excluded(self, stub_catalog, make_config_dict):
        """only_version 不命中 → 排除"""
        stub_catalog.add_project("sodium", "sodium")
        stub_catalog.add_project("extra-mod", "extra-mod")

        config = ModFetchConfig.from_dict(
            make_config_dict(
                minecraft={
                    "version": ["1.21.1"],
                    "mod_loader": "fabric",
                    "mods": [
                        "sodium",
                        {"id": "extra-mod", "only_version": "1.20.4"},
                    ],
                }
            )
        )

        plan, _ = await PlanBuild(catalog=stub_catalog).execute(config)
        assert _project_names(plan) == {"sodium"}

    async def test_only_version_multi_list(self, stub_catalog, make_config_dict):
        """only_version 支持列表, 命中其一即包含"""
        stub_catalog.add_project("sodium", "sodium")
        stub_catalog.add_project("extra-mod", "extra-mod")

        config = ModFetchConfig.from_dict(
            make_config_dict(
                minecraft={
                    "version": ["1.21.1"],
                    "mod_loader": "fabric",
                    "mods": [
                        "sodium",
                        {"id": "extra-mod", "only_version": ["1.20.4", "1.21.1"]},
                    ],
                }
            )
        )

        plan, _ = await PlanBuild(catalog=stub_catalog).execute(config)
        assert _project_names(plan) == {"sodium", "extra-mod"}


class TestCombinedConditions:
    async def test_feature_and_only_version_both_required(
        self, stub_catalog, make_config_dict
    ):
        """feature + only_version 组合为 AND: 任一不满足即排除"""
        stub_catalog.add_project("sodium", "sodium")
        stub_catalog.add_project("iris", "iris")

        config = ModFetchConfig.from_dict(
            make_config_dict(
                minecraft={
                    "version": ["1.21.1"],
                    "mod_loader": "fabric",
                    "mods": [
                        "sodium",
                        {
                            "id": "iris",
                            "feature": "graphics",
                            "only_version": "1.21.1",
                        },
                    ],
                }
            )
        )

        # feature 未启用 → 排除
        plan, _ = await PlanBuild(catalog=stub_catalog).execute(config, features=[])
        assert _project_names(plan) == {"sodium"}

        # feature 启用 + only_version 命中 → 包含
        plan, _ = await PlanBuild(catalog=stub_catalog).execute(
            config, features=["graphics"]
        )
        assert _project_names(plan) == {"sodium", "iris"}

        # feature 启用但 only_version 不命中 → 排除
        config2 = ModFetchConfig.from_dict(
            make_config_dict(
                minecraft={
                    "version": ["1.21.1"],
                    "mod_loader": "fabric",
                    "mods": [
                        "sodium",
                        {
                            "id": "iris",
                            "feature": "graphics",
                            "only_version": "1.20.4",
                        },
                    ],
                }
            )
        )
        plan, _ = await PlanBuild(catalog=stub_catalog).execute(
            config2, features=["graphics"]
        )
        assert _project_names(plan) == {"sodium"}

    async def test_string_entries_always_included(self, stub_catalog, make_config_dict):
        """纯字符串条目无条件 → 始终包含"""
        stub_catalog.add_project("sodium", "sodium")
        stub_catalog.add_project("modmenu", "modmenu")

        config = ModFetchConfig.from_dict(
            make_config_dict(
                minecraft={
                    "version": ["1.21.1"],
                    "mod_loader": "fabric",
                    "mods": ["sodium", "modmenu"],
                }
            )
        )

        plan, _ = await PlanBuild(catalog=stub_catalog).execute(config, features=[])
        assert _project_names(plan) == {"sodium", "modmenu"}


class TestConditionalPackCategories:
    """资源包/光影包/extra_url 三类条目的条件编译"""

    async def test_resourcepack_feature_filtered(
        self, stub_catalog, make_config_dict
    ):
        """资源包 feature 未启用 → 排除"""
        stub_catalog.add_project("sodium", "sodium")
        stub_catalog.add_project("faithful", "faithful")

        config = ModFetchConfig.from_dict(
            make_config_dict(
                minecraft={
                    "version": ["1.21.1"],
                    "mod_loader": "fabric",
                    "mods": ["sodium"],
                    "resourcepacks": [
                        {"id": "faithful", "feature": "faithful-rp"}
                    ],
                }
            )
        )

        plan, _ = await PlanBuild(catalog=stub_catalog).execute(config, features=[])
        assert _project_names(plan) == {"sodium"}

        plan, _ = await PlanBuild(catalog=stub_catalog).execute(
            config, features=["faithful-rp"]
        )
        assert _project_names(plan) == {"sodium", "faithful"}

    async def test_shaderpack_only_version_filtered(
        self, stub_catalog, make_config_dict
    ):
        """光影包 only_version 不命中 → 排除"""
        stub_catalog.add_project("sodium", "sodium")
        stub_catalog.add_project("iris", "iris")
        stub_catalog.add_project("complementary", "complementary")

        config = ModFetchConfig.from_dict(
            make_config_dict(
                minecraft={
                    "version": ["1.21.1"],
                    "mod_loader": "fabric",
                    "mods": ["sodium", "iris"],
                    "shaderpacks": [
                        {
                            "id": "complementary",
                            "only_version": "1.20.4",
                        }
                    ],
                }
            )
        )

        plan, _ = await PlanBuild(catalog=stub_catalog).execute(config)
        assert _project_names(plan) == {"sodium", "iris"}

    async def test_extra_url_feature_filtered(self, stub_catalog, make_config_dict):
        """extra_url feature 未启用 → 排除"""
        config = ModFetchConfig.from_dict(
            make_config_dict(
                minecraft={
                    "version": ["1.21.1"],
                    "mod_loader": "fabric",
                    "mods": ["sodium"],
                    "extra_urls": [
                        {
                            "url": "https://example.com/custom.jar",
                            "feature": "extra",
                        }
                    ],
                }
            )
        )
        stub_catalog.add_project("sodium", "sodium")

        plan, _ = await PlanBuild(catalog=stub_catalog).execute(config, features=[])
        assert _project_names(plan) == {"sodium"}

        plan, _ = await PlanBuild(catalog=stub_catalog).execute(
            config, features=["extra"]
        )
        assert _project_names(plan) == {"sodium", "custom.jar"}


class TestFeaturesFallback:
    async def test_execute_falls_back_to_config_features(
        self, stub_catalog, make_config_dict
    ):
        """execute 未传 features → 回落 config.features"""
        stub_catalog.add_project("sodium", "sodium")
        stub_catalog.add_project("iris", "iris")

        config = ModFetchConfig.from_dict(
            make_config_dict(
                minecraft={
                    "version": ["1.21.1"],
                    "mod_loader": "fabric",
                    "mods": [
                        "sodium",
                        {"id": "iris", "feature": "graphics"},
                    ],
                },
                features=["graphics"],
            )
        )

        plan, _ = await PlanBuild(catalog=stub_catalog).execute(config)
        assert _project_names(plan) == {"sodium", "iris"}
