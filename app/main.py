import sentry_sdk
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.database import init_db
from app.api.routes import router as api_router

from app.config import settings

sentry_sdk.init(
    dsn=settings.sentry_dsn,
    send_default_pii=True,
    traces_sample_rate=0.1,
)

app = FastAPI(title="TrimAURA", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router)


@app.on_event("startup")
def on_startup():
    init_db()


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/sentry-debug")
async def trigger_error():
    division_by_zero = 1 / 0


app.mount("/", StaticFiles(directory="public", html=True), name="public")
