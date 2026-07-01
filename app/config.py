from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    anthropic_api_key: str
    supabase_url: str
    supabase_key: str
    kma_api_key: str
    slack_webhook_url: str
    kakao_secret_key: str = ""
    admin_password: str = ""
    ops_password: str = ""
    naver_client_id: str = ""
    naver_client_secret: str = ""
    self_url: str = "https://web-production-9282c.up.railway.app"

    class Config:
        env_file = ".env"


settings = Settings()