#!/bin/bash
# ════════════════════════════════════════════════════════════
#  서퍼스트 서버 시작 (Mac)  ─ 더블클릭 한 번으로 실행
#  사용법: 이 파일을 watersports-agent 폴더 안에 두고 더블클릭.
#  ※ 처음 한 번만 터미널에서: chmod +x start_server.command
#  이 창(터미널)을 닫거나 Ctrl+C 하면 서버·터널이 같이 종료됩니다.
# ════════════════════════════════════════════════════════════

DOMAIN="darkening-unsalted-harsh.ngrok-free.dev"
PORT=8000

# 1) 이 스크립트가 있는 폴더(=프로젝트 루트)로 이동
cd "$(dirname "$0")" || { echo "❌ 폴더 이동 실패"; read -n1; exit 1; }
echo "📂 작업 폴더: $(pwd)"

# 2) 이전에 떠있던 ngrok / uvicorn 정리 (ERR_NGROK_334 원인 제거)
echo "🧹 이전 프로세스 종료 중..."
pkill -f ngrok 2>/dev/null
pkill -f "uvicorn app.main:app" 2>/dev/null
sleep 2

# 3) 가상환경 있으면 자동 활성화 (venv / .venv 둘 다 대응)
if [ -d "venv" ]; then source venv/bin/activate; echo "🐍 venv 활성화";
elif [ -d ".venv" ]; then source .venv/bin/activate; echo "🐍 .venv 활성화"; fi

# 4) FastAPI 서버 백그라운드 실행 (로그는 uvicorn.log 에 기록)
echo "🚀 FastAPI 시작 (포트 $PORT)..."
uvicorn app.main:app --host 0.0.0.0 --port $PORT --reload > uvicorn.log 2>&1 &
UVICORN_PID=$!
sleep 3

# 서버가 살아있는지 확인
if ! kill -0 $UVICORN_PID 2>/dev/null; then
  echo "❌ FastAPI 실행 실패. uvicorn.log 를 확인하세요:"
  tail -n 20 uvicorn.log
  read -n1 -p "엔터를 누르면 닫힙니다..."
  exit 1
fi
echo "✅ FastAPI 동작 중 (PID $UVICORN_PID) · 로그: uvicorn.log"

# 5) 창 닫힘/Ctrl+C 시 서버·터널 같이 정리
cleanup() {
  echo ""
  echo "🛑 종료 중..."
  kill $UVICORN_PID 2>/dev/null
  pkill -f ngrok 2>/dev/null
  exit 0
}
trap cleanup INT TERM HUP

# 6) ngrok 터널 연결 (이 줄이 포그라운드 — 이 창을 닫으면 전부 종료)
echo "🌐 ngrok 연결: https://$DOMAIN"
echo "────────────────────────────────────────────"
ngrok http --domain="$DOMAIN" $PORT

# ngrok 이 끝나면 서버도 정리
cleanup
