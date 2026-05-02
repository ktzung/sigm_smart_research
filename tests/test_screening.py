"""Tests for rule-based screening logic (no LLM calls)."""
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.core.database import Base
from app.models.topic import Topic
from app.models.paper import Paper
from app.services.screening import _rule_based_prefilter


@pytest.fixture
def db():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()


def test_exclude_old_paper():
    paper = Paper(title="Old Paper", year=2010, abstract="Some abstract text here that is long enough.")
    exclude, reason = _rule_based_prefilter(paper)
    assert exclude is True
    assert "2010" in reason


def test_exclude_missing_abstract():
    paper = Paper(title="No Abstract", year=2022, abstract=None)
    exclude, reason = _rule_based_prefilter(paper)
    assert exclude is True


def test_exclude_short_abstract():
    paper = Paper(title="Short Abstract", year=2022, abstract="Too short.")
    exclude, reason = _rule_based_prefilter(paper)
    assert exclude is True


def test_pass_valid_paper():
    paper = Paper(
        title="Valid Paper",
        year=2023,
        abstract="This is a sufficiently long abstract about federated learning and concept drift in distributed systems.",
    )
    exclude, reason = _rule_based_prefilter(paper)
    assert exclude is False
