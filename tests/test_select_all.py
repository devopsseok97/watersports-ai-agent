import pytest

from app.services import db


class _Query:
    def __init__(self, store, columns):
        self.store = store
        self.columns = columns
        self.lo = 0
        self.hi = None

    def select(self, columns):
        self.columns = columns
        return self

    def order(self, col):
        return self

    def range(self, lo, hi):
        self.lo, self.hi = lo, hi
        return self

    async def execute(self):
        page = self.store.rows[self.lo:self.hi + 1]
        # PostgREST의 Max rows 상한을 흉내낸다 — 초과분은 오류 없이 잘려서 온다.
        page = page[:self.store.max_rows]
        self.store.pages.append(len(page))
        return type("Res", (), {"data": page})()


class _Client:
    def __init__(self, rows, max_rows):
        self.rows = rows
        self.max_rows = max_rows
        self.pages: list[int] = []

    def table(self, name):
        return _Query(self, name)


@pytest.fixture
def install(monkeypatch):
    def _install(total, max_rows):
        client = _Client([{"id": i} for i in range(total)], max_rows)

        async def fake_get_supabase():
            return client

        monkeypatch.setattr(db, "get_supabase", fake_get_supabase)
        return client

    return _install


@pytest.mark.anyio
async def test_reads_past_the_row_cap(install):
    """상한이 페이지 크기와 같아도 전량을 읽어야 한다 (매출 누락 방지)."""
    install(total=2500, max_rows=db.SELECT_ALL_PAGE)

    rows = await db.select_all("reservations", "id")

    assert len(rows) == 2500
    assert [r["id"] for r in rows] == list(range(2500))


@pytest.mark.anyio
async def test_single_page_makes_one_request(install):
    client = install(total=301, max_rows=db.SELECT_ALL_PAGE)

    rows = await db.select_all("reservations", "id")

    assert len(rows) == 301
    assert client.pages == [301]


@pytest.mark.anyio
async def test_empty_table(install):
    install(total=0, max_rows=db.SELECT_ALL_PAGE)
    assert await db.select_all("reservations", "id") == []
