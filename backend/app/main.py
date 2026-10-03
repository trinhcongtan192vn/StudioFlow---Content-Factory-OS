from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.asset_vault.migration import migrate_asset_vault_to_global
from app.db import Base, SessionLocal, engine
from app.order_migration import migrate_order_columns
from app.providers.factory import NoProviderConfiguredError
from app.routers import asset_vault, channels, export, guardrail, library, pack, pipeline, projects, providers, render, settings, system, trash, youtube_analytics
from app.seed import run_seed
from app.youtube_migration import migrate_youtube_columns, migrate_youtube_token_to_per_channel

Base.metadata.create_all(bind=engine)
migrate_asset_vault_to_global(engine)  # Kho Tài Nguyên toàn cục (2026-08-27) — xem docstring module
migrate_youtube_columns(engine)  # Chỉ số YouTube (2026-09-12) — xem docstring module
migrate_order_columns(engine)  # Kéo thả sắp xếp Sidebar (2026-09-19) — xem docstring module
with SessionLocal() as _migration_db:
    migrate_youtube_token_to_per_channel(_migration_db)  # Token YouTube riêng theo kênh (2026-09-19) — xem docstring module
run_seed()

app = FastAPI(title="StudioFlow API", version="0.1.0")

# Electron/React chạy trên localhost, không auth (single-user, §03).
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(NoProviderConfiguredError)
async def no_provider_configured_handler(request: Request, exc: NoProviderConfiguredError):
    # Format {"detail": ...} khớp cách frontend/src/api/client.ts đọc lỗi (không dùng
    # format {"error": {code, message}} trong specs/03_api.md — nhất quán với mọi
    # HTTPException khác trong app, xem IMPLEMENTATION_REPORT.md).
    return JSONResponse(status_code=400, content={"detail": str(exc)})


for r in (system, channels, projects, pipeline, pack, guardrail, providers, settings, export, render, trash, library, asset_vault, youtube_analytics):
    app.include_router(r.router)
