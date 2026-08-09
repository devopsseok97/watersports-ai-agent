import pytest

import app.routers.photos as photos


class _Storage:
    """list()가 실패하는 Supabase Storage 스텁."""

    def __init__(self, fail: bool):
        self.fail = fail
        self.removed: list[list[str]] = []

    def from_(self, bucket):
        return self

    async def list(self, path, options=None):
        if self.fail:
            raise RuntimeError("storage unavailable")
        return [{"name": "a.jpg"}]

    async def remove(self, paths):
        self.removed.append(paths)


@pytest.fixture
def env(monkeypatch):
    state = {"deleted": []}

    async def fake_list_expired():
        return [{"code": "AB2C3D"}]

    async def fake_delete_album(code):
        state["deleted"].append(code)

    monkeypatch.setattr(photos.album, "list_expired_albums", fake_list_expired)
    monkeypatch.setattr(photos.album, "delete_album", fake_delete_album)
    return state


def _install_client(monkeypatch, storage):
    class _Client:
        pass

    client = _Client()
    client.storage = storage

    async def fake_get_supabase():
        return client

    monkeypatch.setattr(photos, "get_supabase", fake_get_supabase)


@pytest.mark.anyio
async def test_expired_album_deleted_when_storage_ok(env, monkeypatch):
    storage = _Storage(fail=False)
    _install_client(monkeypatch, storage)

    assert await photos.cleanup_expired_albums() == 1
    assert env["deleted"] == ["AB2C3D"]
    assert storage.removed == [["AB2C3D/a.jpg"]]


@pytest.mark.anyio
async def test_db_record_kept_when_storage_list_fails(env, monkeypatch):
    """파일 목록 조회가 실패했는데 DB 레코드만 지우면 파일이 영구 고아가 된다.

    앨범 코드가 사라지면 Storage의 {code}/ 폴더를 다시 찾을 단서가 없다.
    조회에 실패한 회차는 건드리지 말고 다음 정리 주기에 다시 시도해야 한다.
    """
    storage = _Storage(fail=True)
    _install_client(monkeypatch, storage)

    assert await photos.cleanup_expired_albums() == 0
    assert env["deleted"] == []
