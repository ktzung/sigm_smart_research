"""Shared test fixtures."""
import os
import pytest

# Use a file-based test DB so the app's init_db() and test sessions share the same DB
TEST_DB_PATH = "./test_research_platform.db"
os.environ["DATABASE_URL"] = f"sqlite:///{TEST_DB_PATH}"


@pytest.fixture(autouse=True, scope="session")
def setup_test_db():
    """Create tables once for the test session, clean up after."""
    from app.core.database import init_db, engine, Base
    init_db()
    yield
    Base.metadata.drop_all(engine)
    engine.dispose()
    import time
    time.sleep(0.1)
    if os.path.exists(TEST_DB_PATH):
        try:
            os.remove(TEST_DB_PATH)
        except PermissionError:
            pass  # Windows may hold the file; it's a test artifact, not critical


@pytest.fixture(autouse=True)
def clean_tables():
    """Truncate all tables between tests for isolation."""
    yield
    from app.core.database import SessionLocal, Base, engine
    db = SessionLocal()
    try:
        for table in reversed(Base.metadata.sorted_tables):
            db.execute(table.delete())
        db.commit()
    finally:
        db.close()
