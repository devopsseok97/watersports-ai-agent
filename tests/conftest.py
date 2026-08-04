import os

# app.config가 요구하는 필수 env를 더미로 채움 (실제 .env보다 우선)
os.environ.setdefault("ANTHROPIC_API_KEY", "test")
os.environ.setdefault("SUPABASE_URL", "http://localhost")
os.environ.setdefault("SUPABASE_KEY", "test")
os.environ.setdefault("KMA_API_KEY", "test")
os.environ.setdefault("SLACK_WEBHOOK_URL", "http://localhost/slack")

import pytest


@pytest.fixture
def anyio_backend():
    """@pytest.mark.anyio 비동기 테스트를 asyncio로 실행.

    이 fixture가 없으면 anyio 마크가 붙은 async 테스트는 조용히 스킵된다
    (실패가 아니라 스킵이라 CI가 초록불로 보인다). 반드시 필요.
    """
    return "asyncio"
