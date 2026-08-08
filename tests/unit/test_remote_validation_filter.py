"""远程校验条件过滤测试

锁定契约: 远程校验（ProjectValidationService.validate_config）必须与
计划生成阶段的 VersionMatcher 行为一致——仅通过 only_version/feature
条件过滤的 Minecraft 版本才参与兼容性检查，避免对条件外版本误报
INCOMPATIBLE（如 { slug, only_version = "1.21.4" } 在 1.21.3 构建时
不应被要求判兼容）。

回归背景: 修复前 validate_config 无条件对全部声明版本 × 加载器做
get_version 检查，导致 only_version 限定条目在非目标版本被误报
"项目 X 不兼容: 1.21.3/fabric"。
"""

import pytest

from modfetch.application.config_service import ConfigService
from modfetch.application.validation import ProjectValidationService
from modfetch.domain.config_models import ModFetchConfig
from modfetch.domain.models import ProjectInfo, ProjectType, VersionInfo


class _TrackingCatalog:
    """记录 get_version 调用参数的内存 catalog（离线）"""

    def __init__(self):
        self.calls: list[tuple[str, str, str]] = []
        self.projects: dict[str, ProjectInfo] = {}
        self.versions: dict[str, set[str]] = {}  # project_id → 兼容版本集合

    def add_project(
        self,
        project_id: str,
        slug: str,
        *,
        project_type: str = "mod",
        compatible: list[tuple[str, str]] | None = None,
    ) -> None:
        self.projects[project_id] = ProjectInfo(
            id=project_id,
            name=slug,
            title=slug.title(),
            description=f"stub {slug}",
            project_type=ProjectType(project_type),
            versions=["v1"],
        )

    async def get_project(self, idx: str):
        return self.projects.get(idx)

    async def get_version(
        self, idx: str, mc_version: str, mod_loader: str, specific_version=None
    ):
        self.calls.append((idx, mc_version, mod_loader))
        # 兼容判定：仅当 (mc_version, loader) 声明兼容（值非 False）时返回版本
        compatible = getattr(self, "_compat", None) or {}
        key = (idx, mc_version, mod_loader)
        if compatible.get(key):
            return (
                VersionInfo(
                    id="v1", name="v1", version="1.0",
                    loaders=[mod_loader] if mod_loader else [],
                    game_versions=[mc_version], files=[],
                    dependencies=[],
                ),
                {"filename": "f.jar", "url": "https://x/f.jar",
                 "hashes": {}, "size": 1},
            )
        return None, None

    async def search(self, *args, **kwargs):
        return []

    async def close(self):
        pass


def _config(mc: dict) -> ModFetchConfig:
    return ModFetchConfig.from_dict(
        {"minecraft": {"version": ["1.21.3", "1.21.4"], **mc}}
    )


class TestRemoteValidationFilter:
    async def test_only_version_scoped_mod_skipped(self):
        """only_version="1.21.4" 的 mod 在 1.21.3 不参与兼容性检查"""
        catalog = _run_catalog_with_compat()
        config = _config(
            {
                "mod_loader": "fabric",
                "mods": [
                    {"slug": "modernfix", "only_version": "1.21.4"},
                ],
            }
        )
        result = await ProjectValidationService(catalog).validate_config(config)

        assert result.is_valid, f"不应报不兼容: {result.issues}"
        # 只对 1.21.4 发起 get_version，1.21.3 被过滤
        idxs = [c for c in catalog.calls if c[0] == "modernfix"]
        assert {c[1] for c in idxs} == {"1.21.4"}, f"调用版本错误: {idxs}"

    async def test_mod_without_condition_checks_all_versions(self):
        """无条件 mod → 所有版本都参与兼容性检查（不改变既有行为）"""
        catalog = _run_catalog_with_compat()
        config = _config(
            {
                "mod_loader": "fabric",
                "mods": ["some-other-mod"],
            }
        )
        # 该 mod 不在 catalog 中 → get_project None → NOT_FOUND，而非 INCOMPATIBLE
        result = await ProjectValidationService(catalog).validate_config(config)

        assert not result.is_valid
        assert result.issues[0].code == "NOT_FOUND"

    async def test_feature_gated_mod_skipped_without_feature(self):
        """feature 门控 mod 未启用 feature → 不参与任何版本检查"""
        catalog = _run_catalog_with_compat()
        config = _config(
            {
                "mod_loader": "fabric",
                "mods": [
                    {"slug": "modernfix", "feature": "perf"},
                ],
            }
        )
        # 默认无 features → 条目被过滤，不请求 get_version
        result = await ProjectValidationService(catalog).validate_config(config)
        assert result.is_valid
        assert not any(c[0] == "modernfix" for c in catalog.calls)

    async def test_feature_enabled_checks(self):
        """feature 启用 → 由于 modernfix 在 1.21.3/fabric 不兼容 → 报错"""
        catalog = _run_catalog_with_compat()
        config = _config(
            {
                "mod_loader": "fabric",
                "mods": [{"slug": "modernfix", "feature": "perf"}],
            }
        )
        result = await ProjectValidationService(catalog).validate_config(
            config, features=["perf"]
        )
        assert not result.is_valid
        assert result.issues[0].code == "INCOMPATIBLE"
        # 1.21.3 与 1.21.4 都请求了
        idxs = {c[1] for c in catalog.calls if c[0] == "modernfix"}
        assert idxs == {"1.21.3", "1.21.4"}


def _run_catalog_with_compat() -> _TrackingCatalog:
    catalog = _TrackingCatalog()
    catalog._compat = {  # type: ignore[attr-defined]
        ("modernfix", "1.21.4", "fabric"): True,
        ("modernfix", "1.21.4", ""): True,
        ("modernfix", "1.21.3", "fabric"): False,
        ("modernfix", "1.21.3", ""): False,
    }
    catalog.add_project("modernfix", "modernfix")
    return catalog