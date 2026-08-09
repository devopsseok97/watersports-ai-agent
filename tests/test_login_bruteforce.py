import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import app.routers.admin as admin
import app.routers.ops as ops
from app.services import ratelimit


@pytest.fixture(autouse=True)
def clean():
    ratelimit.reset()
    yield
    ratelimit.reset()


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr(admin.settings, "admin_password", "correct-horse")
    monkeypatch.setattr(ops.settings, "ops_password", "ops-secret")
    test_app = FastAPI()
    test_app.include_router(admin.router, prefix="/admin")
    test_app.include_router(ops.router, prefix="/ops")
    return TestClient(test_app)


def _try(client, path, password, ip="203.0.113.7"):
    return client.post(
        path,
        data={"password": password},
        headers={"X-Forwarded-For": ip},
        follow_redirects=False,
    )


@pytest.mark.parametrize("path", ["/admin/login", "/ops/login"])
def test_repeated_wrong_password_gets_locked(client, path):
    """비밀번호 하나가 전부인 공개 로그인 폼이라 시도 제한이 없으면 뚫린다.

    관리자 화면에는 예약자 이름·연락처가 그대로 들어 있다.
    """
    for _ in range(ratelimit.MAX_LOGIN_FAILS):
        assert _try(client, path, "wrong").status_code == 401

    assert _try(client, path, "wrong").status_code == 429


@pytest.mark.parametrize(
    "path,password", [("/admin/login", "correct-horse"), ("/ops/login", "ops-secret")]
)
def test_lock_blocks_even_correct_password(client, path, password):
    for _ in range(ratelimit.MAX_LOGIN_FAILS):
        _try(client, path, "wrong")
    assert _try(client, path, password).status_code == 429


@pytest.mark.parametrize(
    "path,password", [("/admin/login", "correct-horse"), ("/ops/login", "ops-secret")]
)
def test_success_clears_failure_count(client, path, password):
    """사장님이 몇 번 틀렸다가 맞히면 기록이 지워져야 한다 (다음 방문에 잠기지 않게)."""
    for _ in range(ratelimit.MAX_LOGIN_FAILS - 1):
        _try(client, path, "wrong")

    assert _try(client, path, password).status_code == 302

    for _ in range(ratelimit.MAX_LOGIN_FAILS - 1):
        assert _try(client, path, "wrong").status_code == 401


def test_admin_lock_does_not_lock_ops(client):
    """한쪽이 공격받아도 다른 쪽 운영 화면까지 잠기면 안 된다."""
    for _ in range(ratelimit.MAX_LOGIN_FAILS + 1):
        _try(client, "/admin/login", "wrong")

    assert _try(client, "/ops/login", "ops-secret").status_code == 302


def test_ip_rotation_hits_global_cap(client):
    """XFF는 위조 가능하므로 IP별 제한만으로는 분산 시도를 못 막는다."""
    for i in range(ratelimit.MAX_LOGIN_FAILS_GLOBAL + 5):
        _try(client, "/admin/login", "wrong", ip=f"198.51.100.{i % 250}.{i}")

    assert _try(client, "/admin/login", "correct-horse",
                ip="203.0.113.99").status_code == 429
