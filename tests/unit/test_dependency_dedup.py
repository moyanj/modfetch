"""依赖解析去重基线测试

锁定当前 DependencyResolver 行为:
- 同一 resolve() 调用内按 project_id 去重
- 仅处理 required 依赖
- 每次 resolve() 清空内部状态
"""

import pytest

from modfetch.services.dependency_resolver import DependencyResolver


def _build_graph(catalog):
    """构造依赖图: root -> [A, B], A -> [B]（B 被两条路径引用）"""
    catalog.add_project("A", "mod-a", dependencies=[
        {"project_id": "B", "dependency_type": "required"},
        {"project_id": "OPT", "dependency_type": "optional"},
    ])
    catalog.add_project("B", "mod-b")
    catalog.add_project("OPT", "mod-opt")
    root_project = "ROOT"
    catalog.add_project(root_project, "root", dependencies=[
        {"project_id": "A", "dependency_type": "required"},
        {"project_id": "B", "dependency_type": "required"},
    ])
    return catalog.versions[root_project][0]


class TestDedup:
    async def test_dedup_same_version_loader(self, stub_catalog):
        """同一 (version, loader) 内同一 project_id 的依赖只出现一次"""
        root = _build_graph(stub_catalog)
        resolver = DependencyResolver(stub_catalog)

        deps = await resolver.resolve(root, "1.21.1", "fabric")

        ids = [p.id for p, _, _ in deps]
        assert ids.count("B") == 1
        assert sorted(ids) == ["A", "B"]

    async def test_optional_dependencies_ignored(self, stub_catalog):
        """optional 依赖不进入解析结果"""
        root = _build_graph(stub_catalog)
        resolver = DependencyResolver(stub_catalog)

        deps = await resolver.resolve(root, "1.21.1", "fabric")

        assert "OPT" not in [p.id for p, _, _ in deps]
        assert "get_project:OPT" not in stub_catalog.calls

    async def test_missing_dependency_skipped(self, stub_catalog):
        """项目不存在的依赖被静默跳过（当前行为基线）"""
        stub_catalog.add_project("ROOT", "root", dependencies=[
            {"project_id": "GHOST", "dependency_type": "required"},
        ])
        resolver = DependencyResolver(stub_catalog)

        deps = await resolver.resolve(
            stub_catalog.versions["ROOT"][0], "1.21.1", "fabric"
        )
        assert deps == []

    async def test_resolve_resets_state_between_calls(self, stub_catalog):
        """每次 resolve() 清空内部状态（当前行为基线）"""
        root = _build_graph(stub_catalog)
        resolver = DependencyResolver(stub_catalog)

        first = await resolver.resolve(root, "1.21.1", "fabric")
        second = await resolver.resolve(root, "1.21.1", "fabric")

        assert len(first) == len(second) == 2

    async def test_cycle_does_not_recurse_forever(self, stub_catalog):
        """循环依赖 A<->B 不会死循环（去重集合阻断）

        当前行为基线: 根节点 A 不在 _processed 中，会被 B 的反向依赖重新解析一次，
        但每个 project_id 最多出现一次，递归必然终止。
        """
        stub_catalog.add_project("A", "mod-a", dependencies=[
            {"project_id": "B", "dependency_type": "required"},
        ])
        stub_catalog.add_project("B", "mod-b", dependencies=[
            {"project_id": "A", "dependency_type": "required"},
        ])
        resolver = DependencyResolver(stub_catalog)

        deps = await resolver.resolve(
            stub_catalog.versions["A"][0], "1.21.1", "fabric"
        )
        ids = [p.id for p, _, _ in deps]
        assert sorted(ids) == ["A", "B"]
        assert len(ids) == len(set(ids))
