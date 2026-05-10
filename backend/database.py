import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.ext.declarative import declarative_base

# =========================
# DATABASE CONFIG (POSTGRES)
# =========================

DATABASE_URL = os.getenv("DATABASE_URL")

# Safety check (helps debugging on Render)
if not DATABASE_URL:
    raise ValueError("DATABASE_URL is not set in environment variables")

# =========================
# CREATE ENGINE
# =========================

engine = create_engine(
    DATABASE_URL,
    pool_pre_ping=True
)

# =========================
# SESSION SETUP
# =========================

SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine
)

# =========================
# BASE MODEL
# =========================

Base = declarative_base()

# =========================
# DB DEPENDENCY
# =========================

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()