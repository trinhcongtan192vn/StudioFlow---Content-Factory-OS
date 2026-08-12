from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.db import Base, engine
from app.providers.factory import NoProviderConfiguredError
from app.routers import channels, export, guardrail, pack, pipeline, projects, providers, render, settings, system
from app.seed import run_seed

Base.metadata.create_all(bind=engine)
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


for r in (system, channels, projects, pipeline, pack, guardrail, providers, settings, export, render):
    app.include_router(r.router)
