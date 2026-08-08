"""光影加载器关联校验测试

锁定契约: 配置声明 shaderpacks（光影包）时, 对应 Minecraft 版本下
mods 必须包含光影加载器（iris/oculus/optifine 之一），且校验须正确
考虑 feature 条件编译——被 feature 过滤掉的光影包不触发加载器要求。

背景: 光影包（Complementary/BSL 等）必须配合 iris/oculus/optifine
才能生效; oculus 是 iris 的 Forge/NeoForge 移植, 二者等价。
"""

import pytest

from modfetch.application.config_service import ConfigService
from modfetch.domain.config_models import ModFetchConfig
from modfetch.domain.errors import ConfigValidationError


def _validate(mc: dict, features: list[str] | None = None) -> None:
    """构造配置并执行本地校验（含新跨字段校验）"""
    config = ModFetchConfig.from_dict({"minecraft": mc})
    ConfigService().validate_local(config, features=features)


class TestShaderLoaderValidation:
    @pytest.mark.parametrize(
        "loader", ["iris", "oculus", "optifine"]
    )
    def test_shaderpack_with_loader_passes(self, loader: str):
        """shaderpacks + mods 含光影加载器（oculus ≡ iris 的 Forge 移植）→ 通过"""
        _validate(
            {
                "version": ["1.21.1"],
                "mod_loader": "fabric",
                "mods": [loader],
                "shaderpacks": ["complementary-reimagined"],
            }
        )

    def test_shaderpack_missing_loader_raises(self):
        """shaderpacks 存在但 mods 无光影加载器 → ConfigValidationError"""
        with pytest.raises(ConfigValidationError, match="光影加载器"):
            _validate(
                {
                    "version": ["1.21.1"],
                    "mod_loader": "fabric",
                    "mods": ["sodium"],
                    "shaderpacks": ["complementary-reimagined"],
                }
            )

    def test_shaderpack_filtered_by_feature_no_loader_ok(self):
        """光影包带 feature 且未启用 → 不参与构建 → 无加载器也通过"""
        _validate(
            {
                "version": ["1.21.1"],
                "mod_loader": "fabric",
                "mods": ["sodium"],
                "shaderpacks": [
                    {"id": "complementary-reimagined", "feature": "shaders"}
                ],
            }
        )

    def test_shaderpack_feature_enabled_requires_loader(self):
        """光影包 feature 启用（features 传入）→ 仍需加载器"""
        with pytest.raises(ConfigValidationError, match="光影加载器"):
            _validate(
                {
                    "version": ["1.21.1"],
                    "mod_loader": "fabric",
                    "mods": ["sodium"],
                    "shaderpacks": [
                        {"id": "complementary-reimagined", "feature": "shaders"}
                    ],
                },
                features=["shaders"],
            )

    def test_shaderpack_and_loader_same_feature_passes(self):
        """光影包与 iris 均带 feature 且同时启用 → 通过"""
        _validate(
            {
                "version": ["1.21.1"],
                "mod_loader": "fabric",
                "mods": [{"id": "iris", "feature": "shaders"}],
                "shaderpacks": [
                    {"id": "complementary-reimagined", "feature": "shaders"}
                ],
            },
            features=["shaders"],
        )

    def test_loader_filtered_by_feature_raises(self):
        """iris 带 feature 未启用（不算加载器）→ 报错"""
        with pytest.raises(ConfigValidationError, match="光影加载器"):
            _validate(
                {
                    "version": ["1.21.1"],
                    "mod_loader": "fabric",
                    "mods": [{"id": "iris", "feature": "graphics"}],
                    "shaderpacks": ["complementary-reimagined"],
                }
            )

    def test_shaderpack_only_version_scoped(self):
        """only_version 限定: 光影包仅 1.20.4 生效, 该版本需加载器"""
        # 1.20.4 有光影包但 mods 无加载器 → 报错
        with pytest.raises(ConfigValidationError, match="光影加载器"):
            _validate(
                {
                    "version": ["1.21.1", "1.20.4"],
                    "mod_loader": "fabric",
                    "mods": ["sodium"],
                    "shaderpacks": [
                        {
                            "id": "complementary-reimagined",
                            "only_version": "1.20.4",
                        }
                    ],
                }
            )

        # 1.21.1 有光影包, 加载器 only_version 也限定 1.21.1 → 通过
        _validate(
            {
                "version": ["1.21.1", "1.20.4"],
                "mod_loader": "fabric",
                "mods": [{"id": "iris", "only_version": "1.21.1"}],
                "shaderpacks": [
                    {
                        "id": "complementary-reimagined",
                        "only_version": "1.21.1",
                    }
                ],
            }
        )

    def test_no_shaderpack_no_requirement(self):
        """无光影包 → 不要求加载器"""
        _validate(
            {
                "version": ["1.21.1"],
                "mod_loader": "fabric",
                "mods": ["sodium"],
            }
        )
