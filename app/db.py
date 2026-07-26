"""Engine and session helpers."""
from contextlib import contextmanager

from sqlmodel import Session, SQLModel, create_engine

from app import config
from app import models  # noqa: F401  (import registers tables)

connect_args = {"check_same_thread": False} if config.DATABASE_URL.startswith("sqlite") else {}
engine = create_engine(config.DATABASE_URL, connect_args=connect_args)


def create_tables() -> None:
    SQLModel.metadata.create_all(engine)


@contextmanager
def session_scope():
    session = Session(engine)
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def get_session():
    """FastAPI dependency."""
    with Session(engine) as session:
        yield session
