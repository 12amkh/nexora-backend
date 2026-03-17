# main.py

import os
import logging
import time
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv
from sqlalchemy import inspect, text
from routers import auth, agents, chat, users, schedules, notifications, marketplace
from database import engine, Base, check_db_connection

# import ALL models so SQLAlchemy registers them before create_all()
from models.user import User
from models.agent import Agent
from models.agent_report import AgentReport
from models.conversation import Conversation
from models.schedule import Schedule
from models.agent_memory import AgentMemory
from models.notification import Notification
from models.marketplace_item import MarketplaceItem
from routers import usage_router
from services.usage_service import UsageService 
from routers import admin

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)

# ── Environment Detection ─────────────────────────────────────────────────────────
# Railway sets RAILWAY_ENVIRONMENT automatically
# we use this to switch between dev and production behavior
IS_PRODUCTION = os.getenv("RAILWAY_ENVIRONMENT") is not None
FRONTEND_URL  = os.getenv("FRONTEND_URL", "http://localhost:3000")

logger.info(f"Starting Nexora API — environment={'production' if IS_PRODUCTION else 'development'}")


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("🚀 Nexora API starting up...")
    Base.metadata.create_all(bind=engine)
    inspector = inspect(engine)
    user_columns = {column["name"] for column in inspector.get_columns("users")}
    if "theme" not in user_columns:
        with engine.begin() as connection:
            connection.execute(text("ALTER TABLE users ADD COLUMN theme VARCHAR DEFAULT 'dark'"))
            connection.execute(text("UPDATE users SET theme = 'dark' WHERE theme IS NULL"))
        logger.info("✅ Added missing users.theme column")
    if "theme_family" not in user_columns:
        with engine.begin() as connection:
            connection.execute(text("ALTER TABLE users ADD COLUMN theme_family VARCHAR DEFAULT 'nexora'"))
            connection.execute(text("UPDATE users SET theme_family = 'nexora' WHERE theme_family IS NULL"))
        logger.info("✅ Added missing users.theme_family column")
    report_columns = {column["name"] for column in inspector.get_columns("agent_reports")}
    if "share_id" not in report_columns:
        with engine.begin() as connection:
            connection.execute(text("ALTER TABLE agent_reports ADD COLUMN share_id VARCHAR(36)"))
            connection.execute(text("CREATE UNIQUE INDEX IF NOT EXISTS ix_agent_reports_share_id ON agent_reports (share_id)"))
        logger.info("✅ Added missing agent_reports.share_id column")
    agent_columns = {column["name"] for column in inspector.get_columns("agents")}
    if "is_public" not in agent_columns:
        with engine.begin() as connection:
            connection.execute(text("ALTER TABLE agents ADD COLUMN is_public BOOLEAN DEFAULT FALSE"))
            connection.execute(text("UPDATE agents SET is_public = FALSE WHERE is_public IS NULL"))
        logger.info("✅ Added missing agents.is_public column")
    logger.info("✅ Database tables verified")
    db_ok = check_db_connection()
    if not db_ok:
        logger.critical("❌ Could not connect to database — check DATABASE_URL in environment variables")
    logger.info("✅ Nexora API is ready")
    yield
    logger.info("🛑 Nexora API shutting down...")


app = FastAPI(
    title="Nexora API",
    description="AI Agent Builder Platform",
    version="1.0.0",
    lifespan=lifespan,
    # hide docs in production — prevents exposing your API structure publicly
    docs_url=None if IS_PRODUCTION else "/docs",
    redoc_url=None if IS_PRODUCTION else "/redoc",
)

# ── CORS ──────────────────────────────────────────────────────────────────────────
# development: allow everything (easy local testing)
# production: only allow your actual frontend URL
# this prevents random websites from calling your API on behalf of users
if IS_PRODUCTION:
    allowed_origins = [
        FRONTEND_URL,
        "http://localhost:3000",
        "http://localhost:3001",
        "https://nexora-frontend-pi.vercel.app",
        "https://nexora-frontend-pi.vercel.app/",
    ]
else:
    allowed_origins = ["*"]
    logger.info("CORS open (development mode)")

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Request Logging ───────────────────────────────────────────────────────────────
@app.middleware("http")
async def log_requests(request: Request, call_next):
    start_time = time.time()
    response   = await call_next(request)
    duration   = (time.time() - start_time) * 1000
    logger.info(f"{request.method} {request.url.path} → {response.status_code} ({duration:.1f}ms)")
    return response


# ── Global Error Handler ──────────────────────────────────────────────────────────
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.error(f"Unhandled exception on {request.method} {request.url.path}: {exc}", exc_info=True)
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={"detail": "An internal server error occurred. Our team has been notified."},
    )


# ── Routers ───────────────────────────────────────────────────────────────────────
app.include_router(auth.router)
app.include_router(agents.router)
app.include_router(chat.router)
app.include_router(users.router)
app.include_router(schedules.router)
app.include_router(notifications.router)
app.include_router(marketplace.router)
app.include_router(usage_router.router)
app.include_router(admin.router)


# ── System Endpoints ──────────────────────────────────────────────────────────────
@app.get("/", tags=["System"])
def home():
    return {
        "product": "Nexora",
        "message": "AI Agent Builder API 🚀",
        "version": "1.0.0",
        "status":  "running",
    }


@app.get("/health", tags=["System"])
def health():
    # Railway uses this endpoint to check if the app is alive
    # if this returns non-200, Railway restarts the container
    db_ok = check_db_connection()
    return {
        "status":      "healthy" if db_ok else "degraded",
        "database":    "connected" if db_ok else "unreachable",
        "environment": "production" if IS_PRODUCTION else "development",
        "version":     "1.0.0",
    }
