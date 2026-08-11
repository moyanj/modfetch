"""
Lock 文件服务

lock 文件是配置的「解析结果快照」：将 PlanBuild 的产出（BuildPlan）
序列化到 JSON 文件，搭配配置指纹实现可复现构建。

lock 文件格式（JSON）::

    {
      "lock_version": 1,
      "config_fingerprint": "sha256:...",
      "config_path": "mods.toml",
      "features": ["performance"],
      "generated_at": "2026-08-11T12:00:00+00:00",
      "plan": { ... BuildPlan.to_dict() ... }
    }

文件路径约定：配置文件同目录，文件名 = 配置文件名去后缀 + ".lock.json"
（如 mods.toml → mods.lock.json）。lock 文件是「配置的解析快照」，
放在配置旁边便于版本控制与多配置共存；不放入 download_dir（那是构建
产物目录）。
"""

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

from loguru import logger

from modfetch.domain.build_plan import BuildPlan
from modfetch.domain.config_models import ModFetchConfig
from modfetch.domain.errors import LockError

#: lock 文件格式版本（不兼容时递增）
LOCK_VERSION = 1


@dataclass(frozen=True)
class LockFile:
    """lock 文件的内存表示"""

    lock_version: int  #: lock 格式版本
    config_fingerprint: str  #: 配置指纹（sha256:<hex>）
    config_path: str  #: 源配置文件路径（记录用）
    features: Tuple[str, ...]  #: 构建时 features（已覆盖后的值）
    generated_at: str  #: 生成时间（UTC ISO8601）
    plan: BuildPlan  #: 锁定的构建计划

    def to_dict(self) -> Dict[str, Any]:
        """序列化为可 JSON 的 dict"""
        return {
            "lock_version": self.lock_version,
            "config_fingerprint": self.config_fingerprint,
            "config_path": self.config_path,
            "features": list(self.features),
            "generated_at": self.generated_at,
            "plan": self.plan.to_dict(),
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "LockFile":
        """从 dict 反序列化（用于读取 lock 文件）

        Raises:
            LockError: plan 字段缺失或反序列化失败
        """
        try:
            plan = BuildPlan.from_dict(d["plan"])
        except (KeyError, ValueError, TypeError) as e:
            raise LockError(f"lock 文件计划反序列化失败: {e}") from e
        return cls(
            lock_version=d.get("lock_version", 1),
            config_fingerprint=d["config_fingerprint"],
            config_path=d.get("config_path", ""),
            features=tuple(d.get("features", [])),
            generated_at=d.get("generated_at", ""),
            plan=plan,
        )


def compute_fingerprint(config: ModFetchConfig) -> str:
    """计算配置指纹

    基于 config.to_dict() 的规范化 JSON 哈希。features 字段在
    to_dict() 中已包含（被 CLI -f 覆盖后的值），因此指纹自动
    反映 features 的影响——配置文件或 features 变了指纹就变。

    Returns:
        "sha256:<hex>" 格式的指纹字符串
    """
    canonical = json.dumps(
        config.to_dict(), sort_keys=True, ensure_ascii=False
    )
    digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    return f"sha256:{digest}"


def write_lock(
    lock_path: Path,
    plan: BuildPlan,
    config: ModFetchConfig,
    config_path: str,
) -> str:
    """将 BuildPlan + 配置指纹写入 lock 文件

    Args:
        lock_path: lock 文件目标路径
        plan: 构建计划
        config: 当前配置（features 已覆盖）
        config_path: 配置文件原始路径（记录用）

    Returns:
        写入的绝对路径字符串
    """
    lock = LockFile(
        lock_version=LOCK_VERSION,
        config_fingerprint=compute_fingerprint(config),
        config_path=str(config_path),
        features=tuple(config.features),
        generated_at=datetime.now(timezone.utc).isoformat(),
        plan=plan,
    )
    target = Path(lock_path).expanduser().resolve()
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        json.dumps(lock.to_dict(), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return str(target)


def read_lock(lock_path: Path) -> LockFile:
    """读取 lock 文件并反序列化

    Raises:
        LockError: 文件不存在、JSON 解析失败、版本不兼容
    """
    path = Path(lock_path)
    if not path.exists():
        raise LockError(f"lock 文件不存在: {path}（请先运行 modfetch lock）")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        raise LockError(f"lock 文件 JSON 解析失败: {e}") from e
    if data.get("lock_version", 1) != LOCK_VERSION:
        raise LockError(
            f"lock 文件版本不兼容: 期望 {LOCK_VERSION}, "
            f"实际 {data.get('lock_version')}"
        )
    return LockFile.from_dict(data)


def check_fingerprint(lock: LockFile, config: ModFetchConfig) -> bool:
    """检查 lock 文件的指纹是否与当前配置匹配"""
    current = compute_fingerprint(config)
    return lock.config_fingerprint == current


@dataclass(frozen=True)
class LockDiff:
    """lock 文件差异摘要（update 命令输出用）"""

    added: Tuple[str, ...]  #: 新增的 project_id
    removed: Tuple[str, ...]  #: 移除的 project_id
    changed: Tuple[Tuple[str, str, str], ...]  #: (project_id, 旧url, 新url)


def diff_locks(old: LockFile, new: LockFile) -> LockDiff:
    """对比两个 lock 文件的差异

    按制品的 project_id 做集合差，并对共有的 project_id 比对 url
    变化（url 变了视为版本变更）。
    """
    old_artifacts: Dict[str, str] = {}  # project_id -> url
    new_artifacts: Dict[str, str] = {}
    for a in old.plan.artifacts:
        old_artifacts[a.project_id] = a.url
    for a in new.plan.artifacts:
        new_artifacts[a.project_id] = a.url

    old_ids = set(old_artifacts)
    new_ids = set(new_artifacts)
    added = tuple(sorted(new_ids - old_ids))
    removed = tuple(sorted(old_ids - new_ids))
    changed = tuple(
        sorted(
            (pid, old_artifacts[pid], new_artifacts[pid])
            for pid in (old_ids & new_ids)
            if old_artifacts[pid] != new_artifacts[pid]
        )
    )
    return LockDiff(added=added, removed=removed, changed=changed)
