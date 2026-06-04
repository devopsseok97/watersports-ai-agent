from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    anthropic_api_key: str
    supabase_url: str
    supabase_key: str
    kma_api_key: str
    slack_webhook_url: str
    kakao_secret_key: str = ""
    admin_password: str = ""  # 사장님 대시보드 비밀번호 (미설정 시 인증 없음)

    class Config:
        env_file = ".env"


settings = Settings()