"""DependencyGraphResolver（无状态版）单元测试

与旧 DependencyResolver 的行为差异锁定:
- missing: 缺失依赖结构化记录而非静默跳过
- cycles: 循环依赖结构化诊断
- 并发安全: 实例无可变状态，多协程交叉调用不互相污染
"""

import asyncio

import pytest

from modfetch.application.dependency_resolver import DependencyGraphResolver


def _graph_catalog(catalog):
    """root -> [A, B], A -> [B]"""
    catalog.add_project("A", "mod-a", dependencies=[
        {"project_id": "B", "dependency_type": "required"},
    ])
    catalog.add_project("B", "mod-b")
    catalog.add_project("ROOT", "root", dependencies=[
        {"project_id": "A", "dependency_type": "required"},
        {"project_id": "B", "dependency_type": "required"},
    ])
    return catalog.versions["ROOT"][0]


class TestGraphBasics:
    async def test_dedup_and_order(self, stub_catalog):
        root = _graph_catalog(stub_catalog)
        resolver = DependencyGraphResolver(stub_catalog)

        graph = await resolver.resolve(root, "1.21.1", "fabric")

        ids = [p.id for p, _, _ in graph.nodes]
        assert sorted(ids) == ["A", "B"]
        assert graph.missing == []
        assert graph.cycles == []

    async def test_missing_recorded(self, stub_catalog):
        """项目不存在 → missing；版本不存在 → missing"""
        stub_catalog.add_project("ROOT", "root", dependencies=[
            {"project_id": "GHOST", "dependency_type": "required"},
        ])
        resolver = DependencyGraphResolver(stub_catalog)

        graph = await resolver.resolve(
            stub_catalog.versions["ROOT"][0], "1.21.1", "fabric"
        )
        assert graph.nodes == []
        assert graph.missing == ["GHOST"]

    async def test_cycle_diagnosed(self, stub_catalog):
        """A -> B -> A 循环: 产生 cycles 诊断且递归终止"""
        stub_catalog.add_project("A", "mod-a", dependencies=[
            {"project_id": "B", "dependency_type": "required"},
        ])
        stub_catalog.add_project("B", "mod-b", dependencies=[
            {"project_id": "A", "dependency_type": "required"},
        ])
        resolver = DependencyGraphResolver(stub_catalog)

        graph = await resolver.resolve(
            stub_catalog.versions["A"][0], "1.21.1", "fabric"
        )
        ids = [p.id for p, _, _ in graph.nodes]
        # B 与 A 各解析一次；A 的依赖 B 在解析路径上再次出现 → 循环诊断
        assert ids == ["B", "A"]
        assert len(graph.cycles) == 1
        assert graph.cycles[0][-1] == "B"
        assert graph.cycles[0][:-1] == ["B", "A"]

    async def test_graph_is_iterable_and_sized(self, stub_catalog):
        """兼容旧的迭代/长度用法"""
        root = _graph_catalog(stub_catalog)
        resolver = DependencyGraphResolver(stub_catalog)
        graph = await resolver.resolve(root, "1.21.1", "fabric")

        assert len(graph) == 2
        for project, version, file_info in graph:
            assert project.id in ("A", "B")


class TestConcurrencySafety:
    async def test_concurrent_resolves_isolated(self, stub_catalog):
        """并发 resolve 不共享状态（旧实现的并发缺陷回归测试）"""
        stub_catalog.add_project("A", "mod-a")
        stub_catalog.add_project("B", "mod-b")
        stub_catalog.add_project("R1", "root-1", dependencies=[
            {"project_id": "A", "dependency_type": "required"},
        ])
        stub_catalog.add_project("R2", "root-2", dependencies=[
            {"project_id": "B", "dependency_type": "required"},
        ])
        resolver = DependencyGraphResolver(stub_catalog)

        r1, r2 = await asyncio.gather(
            resolver.resolve(stub_catalog.versions["R1"][0], "1.21.1", "fabric"),
            resolver.resolve(stub_catalog.versions["R2"][0], "1.21.1", "fabric"),
        )

        assert [p.id for p, _, _ in r1.nodes] == ["A"]
        assert [p.id for p, _, _ in r2.nodes] == ["B"]
