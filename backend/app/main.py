from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.db import Base, engine
from app.routers import channels, export, guardrail, pack, pipeline, projects, providers, settings, system
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

for r in (system, channels, projects, pipeline, pack, guardrail, providers, settings, export):
    app.include_router(r.router)
