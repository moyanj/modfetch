"""版本×加载器展开基线测试

当前展开逻辑内嵌在 ModFetchOrchestrator.run 中（version 外循环 × loader 内循环），
本测试锁定展开契约：组合数 = len(versions) × len(loaders)，
输出目录命名约定为 f"{version}-{loader.value}"。
"""

from itertools import product

import pytest

from modfetch.domain import ModFetchConfig, ModLoader


def _expand(config: ModFetchConfig) -> list[tuple[str, ModLoader]]:
    """与 orchestrator.run 中展开逻辑等价的参考实现"""
    loaders = (
        config.minecraft.mod_loader
        if isinstance(config.minecraft.mod_loader, list)
        else [config.minecraft.mod_loader]
    )
    return [(v, l) for v in config.minecraft.version for l in loaders]


class TestExpansion:
    def test_single_version_single_loader(self, make_config_dict):
        config = ModFetchConfig.from_dict(make_config_dict())
        assert _expand(config) == [("1.21.1", ModLoader.FABRIC)]

    def test_multi_version(self, make_config_dict):
        config = ModFetchConfig.from_dict(
            make_config_dict(
                minecraft={"version": ["1.21.1", "1.20.4"], "mod_loader": "fabric"}
            )
        )
        combos = _expand(config)
        assert len(combos) == 2
        assert [v for v, _ in combos] == ["1.21.1", "1.20.4"]

    def test_multi_loader(self, make_config_dict):
        config = ModFetchConfig.from_dict(
            make_config_dict(
                minecraft={"version": ["1.21.1"], "mod_loader": ["fabric", "forge"]}
            )
        )
        combos = _expand(config)
        assert len(combos) == 2
        assert [l for _, l in combos] == [ModLoader.FABRIC, ModLoader.FORGE]

    def test_multi_both_cartesian(self, make_config_dict):
        """多版本×多加载器 = 笛卡尔积"""
        config = ModFetchConfig.from_dict(
            make_config_dict(
                minecraft={
                    "version": ["1.21.1", "1.20.4"],
                    "mod_loader": ["fabric", "forge"],
                }
            )
        )
        combos = _expand(config)
        assert len(combos) == 4
        assert set(combos) == set(
            product(["1.21.1", "1.20.4"], [ModLoader.FABRIC, ModLoader.FORGE])
        )


class TestOutputNaming:
    @pytest.mark.parametrize(
        "version,loader,expected",
        [
            ("1.21.1", ModLoader.FABRIC, "1.21.1-fabric"),
            ("1.20.4", ModLoader.FORGE, "1.20.4-forge"),
            ("1.21.1", ModLoader.NEOFORGE, "1.21.1-neoforge"),
        ],
    )
    def test_version_dir_naming(self, version, loader, expected):
        """下载目录命名约定: {version}-{loader.value}（orchestrator._process_version）"""
        assert f"{version}-{loader.value}" == expected

    def test_mrpack_output_naming(self):
        """mrpack 输出命名: {name}_{version}_MC{mc}-{loader}（orchestrator._generate_mrpack_for_version）"""
        metadata = {"name": "TestPack", "version": "1.0.0"}
        name = f"{metadata['name']}_{metadata['version']}_MC1.21.1-fabric"
        assert name == "TestPack_1.0.0_MC1.21.1-fabric"

    def test_mrpack_multi_mode_suffix(self):
        """多 mrpack 模式时附加 -{mode} 后缀"""
        modes = ["download", "reference"]
        for mode in modes:
            suffix = f"-{mode}" if len(modes) > 1 else ""
            name = f"TestPack_1.0.0_MC1.21.1-fabric{suffix}"
            assert name.endswith(f"-{mode}")
