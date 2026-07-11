import os

# app.config가 요구하는 필수 env를 더미로 채움 (실제 .env보다 우선)
os.environ.setdefault("ANTHROPIC_API_KEY", "test")
os.environ.setdefault("SUPABASE_URL", "http://localhost")
os.environ.setdefault("SUPABASE_KEY", "test")
os.environ.setdefault("KMA_API_KEY", "test")
os.environ.setdefault("SLACK_WEBHOOK_URL", "http://localhost/slack")
