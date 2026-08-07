"""
公共测试 fixtures

- fake_jar: 生成带已知 SHA1 的伪 JAR 文件
- mock_modrinth: 离线 Mock ModrinthClient（项目/版本/加载器元数据）
- make_config_dict: 配置字典工厂
- stub_catalog: 内存版 Catalog 桩（供依赖解析等单元测试使用）
"""

import hashlib
import json
from pathlib import Path
from typing import Any, Dict, List, Optional

import pytest

from modfetch.domain import ProjectInfo, ProjectType, VersionInfo
from modfetch.adapters.modrinth import ModrinthClient

FIXTURES_DIR = Path(__file__).parent / "fixtures"


def _sha1_of(path: Path) -> str:
    return hashlib.sha1(path.read_bytes()).hexdigest()


@pytest.fixture
def fixtures_dir() -> Path:
    return FIXTURES_DIR


@pytest.fixture
def fake_jar(tmp_path: Path) -> Path:
    """生成一个带固定内容的伪 JAR 文件"""
    jar = tmp_path / "fake-mod.jar"
    jar.write_bytes(b"PK\x03\x04 fake jar content for modfetch tests")
    return jar


@pytest.fixture
def fake_jar_b(tmp_path: Path) -> Path:
    """第二个伪 JAR（内容不同，SHA1 不同）"""
    jar = tmp_path / "fake-dep.jar"
    jar.write_bytes(b"PK\x03\x04 fake dependency jar content")
    return jar


class FakeModrinthAPI:
    """离线 Modrinth API 数据集

    项目图谱:
      sodium (AAAA0001) --required--> fabric-api (BBBB0002)
    所有文件 URL 指向本地伪 JAR（file:// 协议），保证完全离线。
    """

    def __init__(self, jar_a: Path, jar_b: Path):
        self.jar_a = jar_a
        self.jar_b = jar_b

        resp_dir = FIXTURES_DIR / "api_responses"
        self.project_sodium = json.loads(
            (resp_dir / "project_sodium.json").read_text()
        )
        self.project_fabric_api = json.loads(
            (resp_dir / "project_fabric_api.json").read_text()
        )
        self.version_sodium = json.loads(
            (resp_dir / "version_sodium_1.21_fabric.json").read_text()
        )

        # 用本地 file:// URL 与真实 SHA1 覆盖 fixture 中的占位值
        self.version_sodium["files"][0]["url"] = jar_a.as_uri()
        self.version_sodium["files"][0]["size"] = jar_a.stat().st_size
        self.version_sodium["files"][0]["hashes"] = {"sha1": _sha1_of(jar_a)}

        self.version_fabric_api = {
            "id": "v0.100.0",
            "name": "Fabric API 0.100.0",
            "version_number": "0.100.0",
            "loaders": ["fabric", "forge"],
            "game_versions": ["1.21.1", "1.20.4"],
            "dependencies": [],
            "files": [
                {
                    "url": jar_b.as_uri(),
                    "filename": "fabric-api-0.100.0.jar",
                    "size": jar_b.stat().st_size,
                    "primary": True,
                    "hashes": {"sha1": _sha1_of(jar_b)},
                }
            ],
        }

        # 多版本/多加载器均可用（mock 不过滤参数）
        self.version_sodium["loaders"] = ["fabric", "forge"]
        self.version_sodium["game_versions"] = ["1.21.1", "1.20.4"]

        self.loader_versions = {
            "fabric": "0.16.5",
            "forge": "52.0.1",
            "neoforge": "21.1.0",
            "quilt": "0.27.0",
        }

    async def handle_request(
        self, endpoint: str, params: Optional[dict] = None
    ) -> Optional[Any]:
        """按 endpoint 分发到对应数据集（slug 与项目 ID 均可寻址）"""
        # 依赖解析通过 project_id 查询，直接访问通过 slug
        aliases = {
            "sodium": ("sodium", self.project_sodium, self.version_sodium),
            "AAAA0001": ("sodium", self.project_sodium, self.version_sodium),
            "fabric-api": (
                "fabric-api", self.project_fabric_api, self.version_fabric_api
            ),
            "BBBB0002": (
                "fabric-api", self.project_fabric_api, self.version_fabric_api
            ),
        }
        for key, (_, project, version) in aliases.items():
            if f"/project/{key}/version" in endpoint:
                return [version]
            if endpoint.endswith(f"/project/{key}"):
                return project
        if endpoint.endswith("/search"):
            resp_dir = FIXTURES_DIR / "api_responses"
            return json.loads((resp_dir / "search_sodium.json").read_text())
        return None


@pytest.fixture
def mock_modrinth(
    monkeypatch: pytest.MonkeyPatch, fake_jar: Path, fake_jar_b: Path
) -> FakeModrinthAPI:
    """离线 Mock ModrinthClient 的所有网络出口"""
    api = FakeModrinthAPI(fake_jar, fake_jar_b)

    async def fake_request(
        self: ModrinthClient, endpoint: str, params: Optional[dict] = None
    ) -> Optional[Any]:
        return await api.handle_request(endpoint, params)

    monkeypatch.setattr(ModrinthClient, "_request", fake_request)

    async def _make_loader_getter(name: str):
        async def getter(self: ModrinthClient, mc_version: str) -> Optional[str]:
            return api.loader_versions.get(name)

        return getter

    # get_loader_version 系列方法直接走 session，逐类替换为离线桩
    for loader in ("fabric", "quilt", "forge"):
        async def getter(
            self: ModrinthClient, mc_version: str, _l: str = loader
        ) -> Optional[str]:
            return api.loader_versions.get(_l)

        monkeypatch.setattr(ModrinthClient, f"get_{loader}_version", getter)

    # CatalogPort 统一入口（阶段3新增）也要离线化
    async def fake_get_loader_version(
        self: ModrinthClient, loader: str, mc_version: str
    ) -> Optional[str]:
        return api.loader_versions.get(loader)

    monkeypatch.setattr(
        ModrinthClient, "get_loader_version",
        fake_get_loader_version, raising=False,
    )

    # session 惰性创建属性也要禁用，避免真实 aiohttp.ClientSession 泄漏
    monkeypatch.setattr(
        ModrinthClient,
        "session",
        property(lambda self: pytest.fail("离线测试不应创建真实 session")),
    )

    return api


@pytest.fixture
def make_config_dict(tmp_path: Path):
    """配置字典工厂，download_dir 指向 pytest 临时目录"""

    def factory(**overrides: Any) -> Dict[str, Any]:
        config: Dict[str, Any] = {
            "minecraft": {
                "version": ["1.21.1"],
                "mod_loader": "fabric",
                "mods": ["sodium"],
            },
            "output": {
                "download_dir": str(tmp_path / "downloads"),
                "format": ["mrpack"],
            },
            "metadata": {"name": "TestPack", "version": "1.0.0"},
        }
        for key, value in overrides.items():
            if isinstance(value, dict) and isinstance(config.get(key), dict):
                config[key].update(value)
            else:
                config[key] = value
        return config

    return factory


class StubCatalog:
    """内存版 Catalog 桩（模拟未来的 CatalogPort）

    供 DependencyResolver 等单元测试使用，避免构造 HTTP 层。
    """

    def __init__(self) -> None:
        self.projects: Dict[str, ProjectInfo] = {}
        self.versions: Dict[str, tuple[VersionInfo, dict]] = {}
        self.calls: List[str] = []

    def add_project(
        self,
        project_id: str,
        slug: str,
        dependencies: Optional[List[Dict[str, str]]] = None,
    ) -> None:
        self.projects[project_id] = ProjectInfo(
            id=project_id,
            name=slug,
            title=slug.title(),
            description=f"stub project {slug}",
            project_type=ProjectType.MOD,
            versions=["v1"],
        )
        version_info = VersionInfo(
            id=f"{project_id}-v1",
            name=f"{slug} 1.0",
            version="1.0",
            loaders=[],
            game_versions=["1.21.1"],
            files=[],
            dependencies=[
                # 构造与 DependencyInfo 同构的轻量对象
                type("Dep", (), dep)()
                for dep in (dependencies or [])
            ],
        )
        file_info = {
            "url": f"file:///stub/{slug}.jar",
            "filename": f"{slug}.jar",
            "size": 1,
            "hashes": {"sha1": "0" * 40},
        }
        self.versions[project_id] = (version_info, file_info)

    async def get_project(self, idx: str) -> Optional[ProjectInfo]:
        self.calls.append(f"get_project:{idx}")
        return self.projects.get(idx)

    async def get_version(
        self,
        idx: str,
        mc_version: str,
        mod_loader: str,
        specific_version: Optional[str] = None,
    ) -> tuple:
        self.calls.append(f"get_version:{idx}:{mc_version}:{mod_loader}")
        return self.versions.get(idx, (None, None))

    async def close(self) -> None:
        pass


@pytest.fixture
def stub_catalog() -> StubCatalog:
    return StubCatalog()
