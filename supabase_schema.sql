-- Supabase에서 실행하세요
CREATE TABLE conversations (
    id          BIGSERIAL PRIMARY KEY,
    user_id     TEXT        NOT NULL,
    user_message TEXT       NOT NULL,
    bot_reply   TEXT        NOT NULL,
    created_at  TIMESTAMPTZ DEFAULT NOW()
);

-- 사용자별 대화 조회용 인덱스
CREATE INDEX idx_conversations_user_id ON conversations (user_id);
CREATE INDEX idx_conversations_created_at ON conversations (created_at DESC);
