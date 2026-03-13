# main.py

import logging
import time
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv
from routers import auth, agents, chat, users, schedules
from database import engine, Base, check_db_connection

# import ALL models so SQLAlchemy registers them before create_all()
from models.user import User
from models.agent import Agent
from models.conversation import Conversation
from models.schedule import Schedule

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("🚀 Nexora API starting up...")
    Base.metadata.create_all(bind=engine)
    logger.info("✅ Database tables verified")
    db_ok = check_db_connection()
    if not db_ok:
        logger.critical("❌ Could not connect to database — check DATABASE_URL in .env")
    logger.info("✅ Nexora API is ready to accept requests")
    yield
    logger.info("🛑 Nexora API shutting down...")


app = FastAPI(
    title="Nexora API",
    description="AI Agent Builder Platform — Build and run AI agents automatically",
    version="1.0.0",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def log_requests(request: Request, call_next):
    start_time = time.time()
    response = await call_next(request)
    duration = (time.time() - start_time) * 1000
    logger.info(f"{request.method} {request.url.path} → {response.status_code} ({duration:.1f}ms)")
    return response


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.error(f"Unhandled exception on {request.method} {request.url.path}: {exc}", exc_info=True)
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={"detail": "An internal server error occurred. Our team has been notified."},
    )


app.include_router(auth.router)
app.include_router(agents.router)
app.include_router(chat.router)
app.include_router(users.router)
app.include_router(schedules.router)


@app.get("/", tags=["System"])
def home():
    return {"product": "Nexora", "message": "AI Agent Builder API 🚀", "version": "1.0.0", "status": "running"}


@app.get("/health", tags=["System"])
def health():
    db_ok = check_db_connection()
    return {"status": "healthy" if db_ok else "degraded", "database": "connected" if db_ok else "unreachable", "version": "1.0.0"}