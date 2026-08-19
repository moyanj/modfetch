"""合并指令（$delete/$replace/$remove/$override）与 merge_dicts 纯度测试

merge_dicts 的高级语义：
- 键级指令 $delete / $replace
- 列表项指令 $remove / $override
- 无指令输入行为与旧版完全一致（回归）
- 返回值为全新结构，与入参不共享可变嵌套对象
"""

from pathlib import Path

import pytest

from modfetch.adapters.config import resolve_inheritance
from modfetch.domain.config_models import ModFetchConfig


# ---------------------------------------------------------------------------
# $remove：按身份删除列表项
# ---------------------------------------------------------------------------


def test_remove_single_item():
    result = ModFetchConfig.merge_dicts(
        {"minecraft": {"mods": ["sodium", "iris", "modmenu"]}},
        {"minecraft": {"mods": [{"$remove": "iris"}]}},
    )
    assert result["minecraft"]["mods"] == ["sodium", "modmenu"]


def test_remove_multiple_items_via_list():
    result = ModFetchConfig.merge_dicts(
        {"minecraft": {"mods": ["a", "b", "c", "d"]}},
        {"minecraft": {"mods": [{"$remove": ["b", "d"]}]}},
    )
    assert result["minecraft"]["mods"] == ["a", "c"]


def test_remove_nonexistent_is_noop():
    result = ModFetchConfig.merge_dicts(
        {"minecraft": {"mods": ["sodium"]}},
        {"minecraft": {"mods": [{"$remove": "ghost-mod"}]}},
    )
    assert result["minecraft"]["mods"] == ["sodium"]


def test_remove_matches_dict_entry_by_identity():
    """字符串 remove 目标可以命中 dict 形式的同身份条目"""
    result = ModFetchConfig.merge_dicts(
        {"minecraft": {"mods": [{"id": "sodium", "version": "0.5"}, "iris"]}},
        {"minecraft": {"mods": [{"$remove": "sodium"}]}},
    )
    assert result["minecraft"]["mods"] == ["iris"]


def test_remove_also_filters_same_level_additions():
    """$remove 对同层 overlay 的普通新增项同样生效"""
    result = ModFetchConfig.merge_dicts(
        {"minecraft": {"mods": ["sodium"]}},
        {"minecraft": {"mods": [{"$remove": "iris"}, "iris", "modmenu"]}},
    )
    assert result["minecraft"]["mods"] == ["sodium", "modmenu"]


# ---------------------------------------------------------------------------
# $override：同身份替换（保持原位置），未命中则追加
# ---------------------------------------------------------------------------


def test_override_replaces_in_place():
    """子配置覆盖父配置同身份模组的版本，且保持其在列表中的原位置"""
    result = ModFetchConfig.merge_dicts(
        {"minecraft": {"mods": ["sodium", "iris", "modmenu"]}},
        {
            "minecraft": {
                "mods": [
                    {"$override": {"slug": "iris", "version": "1.8.0"}}
                ]
            }
        },
    )
    assert result["minecraft"]["mods"] == [
        "sodium",
        {"slug": "iris", "version": "1.8.0"},
        "modmenu",
    ]


def test_override_missing_identity_appends():
    """override 的目标在父配置中不存在时，追加到列表末尾"""
    result = ModFetchConfig.merge_dicts(
        {"minecraft": {"mods": ["sodium"]}},
        {
            "minecraft": {
                "mods": [
                    {"$override": {"slug": "iris", "version": "1.8.0"}}
                ]
            }
        },
    )
    assert result["minecraft"]["mods"] == [
        "sodium",
        {"slug": "iris", "version": "1.8.0"},
    ]


def test_override_matches_dict_entry_by_identity():
    """override 命中父配置中 dict 形式的同身份条目"""
    result = ModFetchConfig.merge_dicts(
        {"minecraft": {"mods": [{"id": "sodium", "version": "0.5"}, "iris"]}},
        {"minecraft": {"mods": [{"$override": "sodium"}]}},
    )
    # 用裸字符串替换 dict 条目，保持原位置
    assert result["minecraft"]["mods"] == ["sodium", "iris"]


# ---------------------------------------------------------------------------
# $replace：整体替换键值（列表不再拼接）
# ---------------------------------------------------------------------------


def test_replace_list_wholesale():
    result = ModFetchConfig.merge_dicts(
        {"minecraft": {"mods": ["sodium", "iris", "modmenu"]}},
        {"minecraft": {"mods": {"$replace": ["lithium", "ferritecore"]}}},
    )
    assert result["minecraft"]["mods"] == ["lithium", "ferritecore"]


def test_replace_dict_skips_recursive_merge():
    """$replace 对 dict 值跳过递归合并，整体替换"""
    result = ModFetchConfig.merge_dicts(
        {"output": {"download_dir": "./a", "format": ["mrpack"]}},
        {"output": {"$replace": {"download_dir": "./b"}}},
    )
    assert result["output"] == {"download_dir": "./b"}


def test_replace_key_absent_in_base():
    result = ModFetchConfig.merge_dicts(
        {},
        {"minecraft": {"mods": {"$replace": ["sodium"]}}},
    )
    assert result["minecraft"]["mods"] == ["sodium"]


# ---------------------------------------------------------------------------
# $delete：删除继承的键
# ---------------------------------------------------------------------------


def test_delete_scalar_key():
    result = ModFetchConfig.merge_dicts(
        {"metadata": {"name": "Base", "version": "1.0"}},
        {"metadata": {"version": {"$delete": True}}},
    )
    assert result["metadata"] == {"name": "Base"}


def test_delete_dict_key():
    result = ModFetchConfig.merge_dicts(
        {"output": {"download_dir": "./a"}, "metadata": {"name": "x"}},
        {"output": {"$delete": True}},
    )
    assert "output" not in result
    assert result["metadata"] == {"name": "x"}


def test_delete_nonexistent_key_is_noop():
    result = ModFetchConfig.merge_dicts(
        {"metadata": {"name": "Base"}},
        {"metadata": {"ghost": {"$delete": True}}},
    )
    assert result["metadata"] == {"name": "Base"}


# ---------------------------------------------------------------------------
# 指令校验：混用 / 未知指令 / 位置错误
# ---------------------------------------------------------------------------


def test_directive_mixed_with_other_keys_raises():
    with pytest.raises(ValueError, match="独占"):
        ModFetchConfig.merge_dicts(
            {"minecraft": {"mods": ["sodium"]}},
            {"minecraft": {"mods": [{"$remove": "sodium", "note": "x"}]}},
        )


def test_unknown_directive_raises():
    with pytest.raises(ValueError, match="未知的合并指令"):
        ModFetchConfig.merge_dicts(
            {"minecraft": {"mods": ["sodium"]}},
            {"minecraft": {"mods": [{"$remov": "sodium"}]}},
        )


def test_list_directive_at_key_position_raises():
    with pytest.raises(ValueError, match="列表元素"):
        ModFetchConfig.merge_dicts(
            {"minecraft": {"mods": ["sodium"]}},
            {"minecraft": {"mods": {"$remove": "sodium"}}},
        )


def test_key_directive_in_list_item_raises():
    with pytest.raises(ValueError, match="键的值"):
        ModFetchConfig.merge_dicts(
            {"minecraft": {"mods": ["sodium"]}},
            {"minecraft": {"mods": [{"$delete": True}]}},
        )


# ---------------------------------------------------------------------------
# 纯度：返回值为全新结构，与入参不共享可变对象
# ---------------------------------------------------------------------------


def test_merge_result_shares_no_mutable_state_with_inputs():
    base = {"minecraft": {"mods": ["sodium"], "version": ["1.21.1"]}}
    overlay = {"metadata": {"name": "Child"}, "minecraft": {"mods": ["iris"]}}

    result = ModFetchConfig.merge_dicts(base, overlay)

    # 修改返回值的深层结构，入参不受影响
    result["minecraft"]["mods"].append("mutated")
    result["minecraft"]["version"].append("mutated")
    result["metadata"]["name"] = "mutated"

    assert base["minecraft"]["mods"] == ["sodium"]
    assert base["minecraft"]["version"] == ["1.21.1"]
    assert "metadata" not in base
    assert overlay["metadata"]["name"] == "Child"
    assert overlay["minecraft"]["mods"] == ["iris"]


def test_merge_result_list_items_are_copies():
    """列表中的 dict 项也是深拷贝，修改结果不影响入参"""
    base = {"minecraft": {"mods": [{"id": "sodium", "version": "0.5"}]}}
    result = ModFetchConfig.merge_dicts(base, {"minecraft": {"mods": ["iris"]}})

    result["minecraft"]["mods"][0]["version"] = "mutated"
    assert base["minecraft"]["mods"][0]["version"] == "0.5"


# ---------------------------------------------------------------------------
# 回归：无指令输入行为与旧版一致
# ---------------------------------------------------------------------------


def test_regression_scalar_override_and_dict_recursion():
    result = ModFetchConfig.merge_dicts(
        {"minecraft": {"version": ["1.20.4"], "mod_loader": "forge"}},
        {"minecraft": {"mod_loader": "fabric"}},
    )
    # dict 递归合并 + 标量覆盖 + 未触及键保留
    assert result["minecraft"] == {
        "version": ["1.20.4"],
        "mod_loader": "fabric",
    }


def test_regression_list_concat_dedup_keeps_first_occurrence_order():
    result = ModFetchConfig.merge_dicts(
        {"minecraft": {"mods": ["a", "b"]}},
        {"minecraft": {"mods": ["b", "c", "a"]}},
    )
    assert result["minecraft"]["mods"] == ["a", "b", "c"]


def test_regression_string_and_dict_same_identity_dedup():
    """str 与含 id/slug 的 dict 视为同身份：父配置优先，子配置去重丢弃"""
    result = ModFetchConfig.merge_dicts(
        {"minecraft": {"mods": ["sodium"]}},
        {"minecraft": {"mods": [{"id": "sodium", "version": "1.7"}]}},
    )
    assert result["minecraft"]["mods"] == ["sodium"]


def test_regression_from_key_always_skipped():
    """overlay 的 from 不参与合并；base 的 from 作为数据原样保留"""
    result = ModFetchConfig.merge_dicts(
        {"from": [{"url": "file://./a.toml"}]},
        {"from": [{"url": "file://./b.toml"}], "metadata": {"name": "x"}},
    )
    assert result == {
        "from": [{"url": "file://./a.toml"}],
        "metadata": {"name": "x"},
    }


def test_identity_type_prefix_avoids_cross_type_dedup():
    """int 1 与 str "1" 身份不同，不再互相去重"""
    result = ModFetchConfig.merge_dicts(
        {"minecraft": {"version": [1]}},
        {"minecraft": {"version": ["1"]}},
    )
    assert result["minecraft"]["version"] == [1, "1"]


# ---------------------------------------------------------------------------
# resolve_inheritance 端到端：指令生效与无继承时报错
# ---------------------------------------------------------------------------


async def test_inheritance_directives_end_to_end(tmp_path: Path):
    """经 file:// 父配置：$remove 删除继承模组，$override 覆盖版本"""
    base = tmp_path / "base.toml"
    base.write_text(
        "[minecraft]\n"
        'mods = ["sodium", "iris", "modmenu"]\n',
        encoding="utf-8",
    )
    child = {
        "from": [{"url": base.as_uri(), "format": "toml"}],
        "minecraft": {
            "mods": [
                {"$remove": "iris"},
                {"$override": {"slug": "sodium", "version": "0.6.0"}},
            ]
        },
    }

    merged = await resolve_inheritance(child)

    assert merged["minecraft"]["mods"] == [
        {"slug": "sodium", "version": "0.6.0"},
        "modmenu",
    ]


async def test_directive_without_inheritance_raises(tmp_path: Path):
    """配置无 from 却含合并指令 → ValueError（防误写被静默吞没）"""
    config = {
        "minecraft": {"mods": [{"$remove": "sodium"}]},
    }

    with pytest.raises(ValueError, match="合并指令仅在通过 from 继承配置时有效"):
        await resolve_inheritance(config)


async def test_directive_in_parent_without_own_from_raises(tmp_path: Path):
    """父配置自身无 from 却含指令 → 指令无从生效，应报错而非泄漏"""
    parent = tmp_path / "parent.toml"
    parent.write_text(
        "[minecraft]\n"
        'mods = [{ "$remove" = "sodium" }]\n',
        encoding="utf-8",
    )
    child = {"from": [{"url": parent.as_uri(), "format": "toml"}]}

    with pytest.raises(ValueError, match="合并指令仅在通过 from 继承配置时有效"):
        await resolve_inheritance(child)


async def test_directive_applies_per_level_in_chain(tmp_path: Path):
    """指令按继承链逐层生效：中间层的 $remove 只影响其与上一层的合并"""
    grandparent = tmp_path / "grandparent.toml"
    grandparent.write_text(
        "[minecraft]\n"
        'mods = ["sodium", "iris", "modmenu"]\n',
        encoding="utf-8",
    )
    parent = tmp_path / "parent.toml"
    parent.write_text(
        f'from = [{{ url = "{grandparent.as_uri()}", format = "toml" }}]\n'
        "[minecraft]\n"
        'mods = [{ "$remove" = "iris" }]\n',
        encoding="utf-8",
    )
    child = {
        "from": [{"url": parent.as_uri(), "format": "toml"}],
        "minecraft": {"mods": ["fabric-api"]},
    }

    merged = await resolve_inheritance(child)

    # 中间层删掉 iris 后，子配置在剩余基础上继续拼接
    assert merged["minecraft"]["mods"] == ["sodium", "modmenu", "fabric-api"]
