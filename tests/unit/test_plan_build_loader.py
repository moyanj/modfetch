"""PlanBuild 资源包/光影包 loader 语义回归测试

锁定契约:
    - 模组条目按 target 的 mod_loader(fabric/forge 等)查询版本
    - 资源包/光影包条目以空 loader 查询版本,跳过 Modrinth 的
      loaders 过滤(资源包跨加载器通用,与 remote 校验 validation.py
      空 loader 约定保持一致)

背景: 曾因资源包解析时误传 mod 的 loader(fabric)导致 Modrinth
按 loaders=["fabric"] 过滤返回空, 资源包被静默跳过而构建不报错。
"""

import pytest

from modfetch.application.plan_build import PlanBuild
from modfetch.domain.config_models import ModFetchConfig


class TestPackLoaderSemantics:
    async def test_resourcepack_uses_empty_loader_mod_keeps_loader(
        self, stub_catalog, make_config_dict
    ):
        """资源包传空 loader; 模组仍传 fabric loader"""
        # 注入 mod 与 resourcepack 两类条目到 stub
        stub_catalog.add_project("sodium", "sodium")
        stub_catalog.add_project("faithful", "faithful")

        config = ModFetchConfig.from_dict(
            make_config_dict(
                minecraft={
                    "version": ["1.21.1"],
                    "mod_loader": "fabric",
                    "mods": ["sodium"],
                    "resourcepacks": ["faithful"],
                }
            )
        )

        plan_build = PlanBuild(catalog=stub_catalog)
        plan, _ = await plan_build.execute(config)

        # 两份制品: sodium(mod) + faithful(resourcepack)
        assert len(plan.artifacts) == 2

        # 收集 get_version 调用, 断言 loader 语义
        calls = [c for c in stub_catalog.calls if c.startswith("get_version:")]
        assert len(calls) == 2
        # stub 中 project_id == mod 标识, 直接依此区分
        by_project = {c.split(":")[1]: c for c in calls}
        assert "sodium" in by_project
        assert "faithful" in by_project
        # mod 携带 loader; resourcepack 空 loader
        assert by_project["sodium"].endswith("1.21.1:fabric")
        assert by_project["faithful"].endswith("1.21.1:")

    async def test_shaderpack_uses_empty_loader(self, stub_catalog, make_config_dict):
        """光影包同样以空 loader 查询版本"""
        stub_catalog.add_project("complementary", "complementary")

        config = ModFetchConfig.from_dict(
            make_config_dict(
                minecraft={
                    "version": ["1.21.1"],
                    "mod_loader": "forge",
                    "mods": [],
                    "shaderpacks": ["complementary"],
                }
            )
        )

        plan_build = PlanBuild(catalog=stub_catalog)
        plan, _ = await plan_build.execute(config)

        assert len(plan.artifacts) == 1
        shader_calls = [
            c for c in stub_catalog.calls if c.startswith("get_version:complementary")
        ]
        assert shader_calls and shader_calls[0].endswith("1.21.1:")