"""FileArtifactStore / FileVerifier 单元测试（完全离线）

覆盖 verifier.py 全部静态方法（sha1 计算/校验/存在性/大小/有效性）
与 file_store.py 的 exists/write/verify 分支（safe_path 已在
test_download_adapters.py 覆盖）。
"""

import hashlib

from modfetch.adapters.download.file_store import FileArtifactStore
from modfetch.adapters.download.verifier import FileVerifier


def _sha1(data: bytes) -> str:
    return hashlib.sha1(data).hexdigest()


# -- FileVerifier ------------------------------------------------------------


class TestCalcSha1:
    async def test_existing_file(self, tmp_path):
        f = tmp_path / "a.bin"
        f.write_bytes(b"hello")
        assert await FileVerifier.calc_sha1(str(f)) == _sha1(b"hello")

    async def test_missing_file_returns_none(self, tmp_path):
        assert await FileVerifier.calc_sha1(str(tmp_path / "nope")) is None

    async def test_read_error_returns_none(self, tmp_path):
        """目录路径 → 打开失败（IsADirectoryError）→ None"""
        assert await FileVerifier.calc_sha1(str(tmp_path)) is None


class TestVerifySha1:
    async def test_no_expected_passes(self, tmp_path):
        f = tmp_path / "a.bin"
        f.write_bytes(b"x")
        assert await FileVerifier.verify_sha1(str(f), None) is True
        assert await FileVerifier.verify_sha1(str(f), "") is True

    async def test_match(self, tmp_path):
        f = tmp_path / "a.bin"
        f.write_bytes(b"data")
        assert await FileVerifier.verify_sha1(str(f), _sha1(b"data")) is True

    async def test_mismatch(self, tmp_path):
        f = tmp_path / "a.bin"
        f.write_bytes(b"data")
        assert await FileVerifier.verify_sha1(str(f), "0" * 40) is False

    async def test_unreadable_file_fails(self, tmp_path):
        """文件无法读取（calc 返回 None）→ 校验失败"""
        assert await FileVerifier.verify_sha1(str(tmp_path), _sha1(b"x")) is False


class TestExists:
    def test_existing(self, tmp_path):
        f = tmp_path / "a"
        f.write_bytes(b"x")
        assert FileVerifier.exists(str(f)) is True

    def test_missing(self, tmp_path):
        assert FileVerifier.exists(str(tmp_path / "nope")) is False


class TestGetSize:
    def test_existing_file(self, tmp_path):
        f = tmp_path / "a"
        f.write_bytes(b"12345")
        assert FileVerifier.get_size(str(f)) == 5

    def test_missing_file_returns_zero(self, tmp_path):
        assert FileVerifier.get_size(str(tmp_path / "nope")) == 0

    def test_stat_error_returns_zero(self, tmp_path):
        """损坏的符号链接 → getsize 抛 OSError → 0"""
        link = tmp_path / "broken"
        link.symlink_to(tmp_path / "ghost")
        assert FileVerifier.get_size(str(link)) == 0


class TestIsValid:
    async def test_missing_file_invalid(self, tmp_path):
        assert await FileVerifier.is_valid(str(tmp_path / "nope")) is False

    async def test_exists_without_sha1_valid(self, tmp_path):
        f = tmp_path / "a"
        f.write_bytes(b"data")
        assert await FileVerifier.is_valid(str(f)) is True

    async def test_exists_with_matching_sha1(self, tmp_path):
        f = tmp_path / "a"
        f.write_bytes(b"data")
        assert await FileVerifier.is_valid(str(f), _sha1(b"data")) is True

    async def test_exists_with_wrong_sha1_invalid(self, tmp_path):
        f = tmp_path / "a"
        f.write_bytes(b"data")
        assert await FileVerifier.is_valid(str(f), "0" * 40) is False


# -- FileArtifactStore -------------------------------------------------------


class TestStoreExists:
    async def test_existing(self, tmp_path):
        store = FileArtifactStore()
        f = tmp_path / "a"
        f.write_bytes(b"x")
        assert await store.exists(f) is True

    async def test_missing(self, tmp_path):
        store = FileArtifactStore()
        assert await store.exists(tmp_path / "nope") is False


class TestStoreWrite:
    async def test_writes_stream_and_creates_parent(self, tmp_path):
        store = FileArtifactStore()
        dest = tmp_path / "nested" / "dir" / "a.bin"

        async def source():
            yield b"hello"
            yield b" world"

        written = await store.write(dest, source())
        assert written == 11
        assert dest.read_bytes() == b"hello world"
        assert dest.parent.is_dir()

    async def test_empty_stream(self, tmp_path):
        store = FileArtifactStore()
        dest = tmp_path / "empty.bin"

        async def source():
            if False:  # 空流：不产出任何块
                yield b""

        assert await store.write(dest, source()) == 0
        assert dest.read_bytes() == b""


class TestStoreVerify:
    async def test_missing_file_false(self, tmp_path):
        store = FileArtifactStore()
        assert await store.verify(tmp_path / "nope", {"sha1": "0" * 40}) is False

    async def test_no_hashes_passes(self, tmp_path):
        store = FileArtifactStore()
        f = tmp_path / "a"
        f.write_bytes(b"x")
        assert await store.verify(f, {}) is True
        # 非 sha1 键（如 sha512）不参与校验
        assert await store.verify(f, {"sha512": "abc"}) is True

    async def test_sha1_match(self, tmp_path):
        store = FileArtifactStore()
        f = tmp_path / "a"
        f.write_bytes(b"data")
        assert await store.verify(f, {"sha1": _sha1(b"data")}) is True

    async def test_sha1_mismatch(self, tmp_path):
        store = FileArtifactStore()
        f = tmp_path / "a"
        f.write_bytes(b"data")
        assert await store.verify(f, {"sha1": "0" * 40}) is False