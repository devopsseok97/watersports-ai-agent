from fastapi import FastAPI
from app.routers import kakao, health, admin

app = FastAPI(title="WaterSports AI Agent", version="0.1.0")

app.include_router(health.router)
app.include_router(kakao.router, prefix="/kakao")
app.include_router(admin.router, prefix="/admin")