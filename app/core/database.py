from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, DeclarativeBase
from app.core.config import settings

_is_sqlite = settings.database_url.startswith("sqlite")

# SQLite doesn't support pool_size/max_overflow — use NullPool for it
if _is_sqlite:
    from sqlalchemy.pool import StaticPool
    engine = create_engine(
        settings.database_url,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        echo=False,
    )
else:
    engine = create_engine(
        settings.database_url,
        pool_size=5,
        max_overflow=10,
        pool_pre_ping=True,
        echo=False,
    )

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    pass


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db():
    """Create all tables. Import every model module so SQLAlchemy registers them."""
    from app.models import topic, paper, pipeline  # noqa: F401
    from app.models import auth, lab, audit, profile, github  # noqa: F401
    Base.metadata.create_all(bind=engine)
