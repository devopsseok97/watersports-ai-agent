-- ================================================================
--  서퍼스트 Supabase 전체 스키마
--  Supabase SQL Editor 에서 실행하세요.
-- ================================================================

-- ── 1. 카카오 챗봇 대화 기록 ──────────────────────────────────
CREATE TABLE IF NOT EXISTS conversations (
    id               BIGSERIAL    PRIMARY KEY,
    user_id          TEXT         NOT NULL,
    user_message     TEXT         NOT NULL,
    bot_reply        TEXT         NOT NULL,
    is_booking_intent BOOLEAN     NOT NULL DEFAULT FALSE,
    admin_memo       TEXT         NOT NULL DEFAULT '',
    created_at       TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_conversations_user_id    ON conversations (user_id);
CREATE INDEX IF NOT EXISTS idx_conversations_created_at ON conversations (created_at DESC);
CREATE INDEX IF NOT EXISTS idx_conversations_booking    ON conversations (is_booking_intent, created_at DESC);


-- ── 2. 예약 관리 ─────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS reservations (
    id            BIGSERIAL    PRIMARY KEY,
    slot_date     DATE         NOT NULL,
    program       TEXT         NOT NULL,
    time_slot     TEXT         NOT NULL DEFAULT '',
    customer_name TEXT         NOT NULL DEFAULT '',
    people        INT          NOT NULL DEFAULT 1 CHECK (people >= 1),
    platform      TEXT         NOT NULL DEFAULT '현장',
    memo          TEXT         NOT NULL DEFAULT '',
    amount        BIGINT       NOT NULL DEFAULT 0 CHECK (amount >= 0),
    status        TEXT         NOT NULL DEFAULT '예약'
                               CHECK (status IN ('예약', '입금대기', '노쇼')),
    created_at    TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_reservations_slot_date ON reservations (slot_date);
CREATE INDEX IF NOT EXISTS idx_reservations_status    ON reservations (status);


-- ── 3. 사진 앨범 메타데이터 ────────────────────────────────────
CREATE TABLE IF NOT EXISTS photo_albums (
    id          BIGSERIAL    PRIMARY KEY,
    code        TEXT         NOT NULL UNIQUE,
    memo        TEXT         NOT NULL DEFAULT '',
    photo_count INT          NOT NULL DEFAULT 0 CHECK (photo_count >= 0),
    expires_at  TIMESTAMPTZ  NOT NULL,
    created_at  TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_photo_albums_code       ON photo_albums (code);
CREATE INDEX IF NOT EXISTS idx_photo_albums_created_at ON photo_albums (created_at DESC);


-- ── 4. 기존 DB 마이그레이션 (테이블이 이미 있을 때 아래 구문 실행) ─────────
-- conversations 에 누락된 컬럼 추가
ALTER TABLE conversations ADD COLUMN IF NOT EXISTS is_booking_intent BOOLEAN NOT NULL DEFAULT FALSE;
ALTER TABLE conversations ADD COLUMN IF NOT EXISTS admin_memo        TEXT    NOT NULL DEFAULT '';

-- reservations 에 결제수단 컬럼 추가
ALTER TABLE reservations ADD COLUMN IF NOT EXISTS payment_method TEXT NOT NULL DEFAULT '계좌이체';


-- ================================================================
--  5. RLS (Row Level Security) 활성화 및 정책
--  Supabase SQL Editor 에서 아래 구문 전체 실행
-- ================================================================

-- RLS 활성화
ALTER TABLE conversations  ENABLE ROW LEVEL SECURITY;
ALTER TABLE reservations   ENABLE ROW LEVEL SECURITY;
ALTER TABLE photo_albums   ENABLE ROW LEVEL SECURITY;

-- conversations: service_role(백엔드 서버)만 읽기·쓰기 허용
CREATE POLICY "service_role_only_conversations"
  ON conversations
  FOR ALL
  TO service_role
  USING (true)
  WITH CHECK (true);

-- reservations: service_role(백엔드 서버)만 읽기·쓰기 허용
CREATE POLICY "service_role_only_reservations"
  ON reservations
  FOR ALL
  TO service_role
  USING (true)
  WITH CHECK (true);

-- photo_albums: service_role(백엔드 서버)만 읽기·쓰기 허용
CREATE POLICY "service_role_only_photo_albums"
  ON photo_albums
  FOR ALL
  TO service_role
  USING (true)
  WITH CHECK (true);

-- 오손 랜딩페이지 도입 문의 리드
CREATE TABLE IF NOT EXISTS leads (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    name TEXT NOT NULL,
    phone TEXT NOT NULL,
    business_name TEXT NOT NULL,
    message TEXT NOT NULL DEFAULT '',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

ALTER TABLE leads ENABLE ROW LEVEL SECURITY;

CREATE POLICY "service_role_only_leads" ON leads
    FOR ALL TO service_role USING (true) WITH CHECK (true);
