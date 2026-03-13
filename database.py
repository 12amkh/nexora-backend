# database.py

import os
import logging
from sqlalchemy import create_engine, event
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from sqlalchemy.exc import OperationalError
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

# ── Database URL ────────────────────────────────────────────────────────────────
DATABASE_URL = os.getenv("DATABASE_URL")

if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL is not set in .env — server cannot start without a database.")

# ── Engine ───────────────────────────────────────────────────────────────────────
# pool_size: number of persistent connections kept open (10 is solid for a SaaS)
# max_overflow: extra connections allowed when pool is full (20 = burst capacity)
# pool_timeout: seconds to wait for a free connection before raising an error
# pool_recycle: recycle connections every 30min — prevents stale connection errors
#               especially important with PostgreSQL which drops idle connections
# pool_pre_ping: before using a connection, test it's alive — auto-reconnects if not
#                this is the most important setting for production stability
engine = create_engine(
    DATABASE_URL,
    pool_size=10,
    max_overflow=20,
    pool_timeout=30,
    pool_recycle=1800,
    pool_pre_ping=True,
)

# ── Session Factory ──────────────────────────────────────────────────────────────
# autocommit=False: we control when data is committed — never auto-save
# autoflush=False:  we control when SQLAlchemy syncs changes to DB
SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine,
)

# ── Base ─────────────────────────────────────────────────────────────────────────
Base = declarative_base()


# ── DB Dependency ────────────────────────────────────────────────────────────────
# used in every router via Depends(get_db)
# yields a session, then ALWAYS closes it — even if an exception occurs
# db.rollback() on exception ensures no partial/corrupted writes stay in the DB
def get_db():
    db = SessionLocal()
    try:
        yield db
    except Exception as e:
        db.rollback()  # undo any uncommitted changes if something went wrong
        logger.error(f"Database session error: {e}")
        raise
    finally:
        db.close()  # always release the connection back to the pool


# ── Connection Health Check ──────────────────────────────────────────────────────
# called once at startup from main.py to verify DB is reachable before accepting traffic
# real life: checking the kitchen is open before letting customers into the restaurant
def check_db_connection():
    try:
        with engine.connect() as connection:
            connection.execute(__import__('sqlalchemy').text("SELECT 1"))
        logger.info("✅ Database connection successful")
        return True
    except OperationalError as e:
        logger.critical(f"❌ Database connection failed: {e}")
        return False