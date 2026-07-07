from pydantic import BaseModel
from typing import Optional


class KakaoUser(BaseModel):
    id: str


class KakaoUserRequest(BaseModel):
    utterance: str
    user: KakaoUser
    callbackUrl: Optional[str] = None  # 오픈빌더 콜백 대기 모드에서 카톡이 전달


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
