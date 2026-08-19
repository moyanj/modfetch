"""VersionMatcher.should_include 过滤语义测试

锁定契约（修复后）:
    - 支持 ConditionalEntry 对象（ModEntry/ExtraUrl）、dict 与字符串
    - only_version: 版本命中指定列表才包含
    - only_loader: 加载器命中指定列表才包含（列表命中其一即可）;
      声明 only_loader 但无 loader 上下文（None）时排除（保守）
    - feature: 启用条件语义——条目声明的 feature 全部被启用才包含;
      未声明 feature 的条目始终包含

背景: 历史实现对 dict 采用"全部启用则排除"反向语义, 且对对象条目
(dataclass) 的过滤因 isinstance(entry, dict) 不命中而完全失效。本套
用例锁定修复后的正确行为, 防止回归。
"""

from modfetch.application.version_matcher import VersionMatcher
from modfetch.domain.config_models import ExtraUrl, ModEntry


class TestShouldIncludeObjectEntry:
    def test_mod_entry_only_version_match(self):
        """ModEntry only_version 命中 → 包含"""
        matcher = VersionMatcher()
        entry = ModEntry(id="x", only_version="1.21.1")
        assert matcher.should_include(entry, "1.21.1", [])

    def test_mod_entry_only_version_mismatch(self):
        """ModEntry only_version 未命中 → 排除"""
        matcher = VersionMatcher()
        entry = ModEntry(id="x", only_version="1.20.4")
        assert not matcher.should_include(entry, "1.21.1", [])

    def test_mod_entry_feature_enabled(self):
        """ModEntry feature 全部启用 → 包含"""
        matcher = VersionMatcher()
        entry = ModEntry(id="x", feature=["shaders", "graphics"])
        assert matcher.should_include(entry, "1.21.1", ["shaders", "graphics"])

    def test_mod_entry_feature_partial(self):
        """ModEntry feature 部分启用 → 排除"""
        matcher = VersionMatcher()
        entry = ModEntry(id="x", feature="shaders")
        assert not matcher.should_include(entry, "1.21.1", ["graphics"])

    def test_mod_entry_feature_not_enabled(self):
        """ModEntry feature 未启用 → 排除"""
        matcher = VersionMatcher()
        entry = ModEntry(id="x", feature="shaders")
        assert not matcher.should_include(entry, "1.21.1", [])

    def test_mod_entry_no_conditions_always_included(self):
        """ModEntry 无条件 → 始终包含"""
        matcher = VersionMatcher()
        entry = ModEntry(id="x")
        assert matcher.should_include(entry, "1.21.1", [])

    def test_extra_url_relative_preserved(self):
        """ExtraUrl 无条件 → 包含"""
        matcher = VersionMatcher()
        entry = ExtraUrl(url="https://example.com/x.zip")
        assert matcher.should_include(entry, "1.21.1", [])

    def test_str_entry_always_included(self):
        """字符串条目无条件 → 包含"""
        matcher = VersionMatcher()
        assert matcher.should_include("sodium", "1.21.1", [])


class TestShouldIncludeDict:
    def test_dict_feature_enabled(self):
        """dict feature 启用 → 包含"""
        matcher = VersionMatcher()
        assert matcher.should_include(
            {"id": "x", "feature": "shaders"}, "1.21.1", ["shaders"]
        )

    def test_dict_feature_not_enabled(self):
        """dict feature 未启用 → 排除"""
        matcher = VersionMatcher()
        assert not matcher.should_include(
            {"id": "x", "feature": "shaders"}, "1.21.1", []
        )


class TestOnlyLoaderGate:
    def test_loader_match_included(self):
        """only_loader 命中 → 包含"""
        matcher = VersionMatcher()
        entry = ModEntry(id="x", only_loader="fabric")
        assert matcher.should_include(entry, "1.21.1", [], "fabric")

    def test_loader_mismatch_excluded(self):
        """only_loader 未命中 → 排除"""
        matcher = VersionMatcher()
        entry = ModEntry(id="x", only_loader="fabric")
        assert not matcher.should_include(entry, "1.21.1", [], "forge")

    def test_loader_list_any_match(self):
        """only_loader 列表命中其一 → 包含"""
        matcher = VersionMatcher()
        entry = ModEntry(id="x", only_loader=["fabric", "forge"])
        assert matcher.should_include(entry, "1.21.1", [], "forge")
        assert not matcher.should_include(entry, "1.21.1", [], "neoforge")

    def test_loader_no_context_excluded(self):
        """声明 only_loader 但无 loader 上下文（None）→ 保守排除"""
        matcher = VersionMatcher()
        entry = ModEntry(id="x", only_loader="fabric")
        assert not matcher.should_include(entry, "1.21.1", [])

    def test_loader_case_insensitive(self):
        """加载器匹配大小写不敏感"""
        matcher = VersionMatcher()
        entry = ModEntry(id="x", only_loader="Fabric")
        assert matcher.should_include(entry, "1.21.1", [], "fabric")

    def test_loader_combined_with_version_and_feature(self):
        """only_loader + only_version + feature 同时满足才包含（AND）"""
        matcher = VersionMatcher()
        entry = ModEntry(
            id="x",
            only_version="1.21.1",
            only_loader="fabric",
            feature="graphics",
        )
        assert matcher.should_include(
            entry, "1.21.1", ["graphics"], "fabric"
        )
        assert not matcher.should_include(entry, "1.20.4", ["graphics"], "fabric")
        assert not matcher.should_include(entry, "1.21.1", ["graphics"], "forge")
        assert not matcher.should_include(entry, "1.21.1", [], "fabric")

    def test_dict_only_loader(self):
        """dict 条目 only_loader 同样生效"""
        matcher = VersionMatcher()
        assert matcher.should_include(
            {"id": "x", "only_loader": "forge"}, "1.21.1", [], "forge"
        )
        assert not matcher.should_include(
            {"id": "x", "only_loader": "forge"}, "1.21.1", [], "fabric"
        )

    def test_extra_url_only_loader(self):
        """ExtraUrl 同样支持 only_loader"""
        matcher = VersionMatcher()
        entry = ExtraUrl(url="https://example.com/x.zip", only_loader="fabric")
        assert matcher.should_include(entry, "1.21.1", [], "fabric")
        assert not matcher.should_include(entry, "1.21.1", [], "forge")