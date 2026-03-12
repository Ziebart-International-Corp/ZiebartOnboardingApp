"""SQLAlchemy engine and session for data_api (no Flask)."""
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base
from sqlalchemy import MetaData, Table
from data_api.config import DATABASE_URI

engine = create_engine(
    DATABASE_URI,
    pool_pre_ping=True,
    pool_recycle=3600,
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def get_table(name):
    """Reflect existing table by name."""
    metadata = MetaData()
    return Table(name, metadata, autoload_with=engine)
