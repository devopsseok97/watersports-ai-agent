from pydantic import BaseModel
from typing import Optional


class KakaoUser(BaseModel):
    id: str


class KakaoUserRequest(BaseModel):
    utterance: str
    user: KakaoUser
    # 콜백 블록이 활성화된 경우에만 카카오가 채워 보냄. 없으면 동기 응답.
    callbackUrl: Optional[str] = None


class KakaoBot(BaseModel):
    id: str
    name: str


class KakaoIntent(BaseModel):
    id: str
    name: str


class KakaoWebhookRequest(BaseModel):
    """카카오 오픈빌더 웹훅 요청 스키마"""
    userRequest: KakaoUserRequest
    bot: KakaoBot
    intent: Optional[KakaoIntent] = None


class KakaoSimpleText(BaseModel):
    text: str


class KakaoOutputItem(BaseModel):
    simpleText: KakaoSimpleText


class KakaoTemplate(BaseModel):
    outputs: list[KakaoOutputItem]


class KakaoWebhookResponse(BaseModel):
    """카카오 오픈빌더 웹훅 응답 스키마"""
    version: str = "2.0"
    template: KakaoTemplate

    @classmethod
    def from_text(cls, text: str) -> "KakaoWebhookResponse":
        return cls(
            template=KakaoTemplate(
                outputs=[KakaoOutputItem(simpleText=KakaoSimpleText(text=text))]
            )
        )
