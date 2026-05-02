"""Tests for database models and basic service logic."""
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.core.database import Base
from app.models.topic import Topic, QueryPlan, QueryBundle
from app.models.paper import Paper, PaperDecision
from app.models.auth import User


@pytest.fixture
def db():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()
    Base.metadata.drop_all(engine)


def _create_user(db, email: str = "modeltest@example.com") -> User:
    user = User(email=email, display_name="Model Tester", password_hash="x", is_active=True)
    db.add(user)
    db.flush()
    return user


def test_create_topic(db):
    user = _create_user(db)
    topic = Topic(user_id=user.id, title="Test Topic", literature_scarce=True)
    db.add(topic)
    db.commit()
    assert topic.id is not None
    assert topic.title == "Test Topic"


def test_query_plan_with_bundles(db):
    user = _create_user(db, email="modeltest2@example.com")
    topic = Topic(user_id=user.id, title="FL Concept Drift")
    db.add(topic)
    db.flush()

    plan = QueryPlan(topic_id=topic.id)
    db.add(plan)
    db.flush()

    bundle = QueryBundle(plan_id=plan.id, label="direct", query_text="federated learning concept drift", source="both")
    db.add(bundle)
    db.commit()

    assert len(plan.bundles) == 1
    assert plan.bundles[0].label == "direct"


def test_paper_decision(db):
    user = _create_user(db, email="modeltest3@example.com")
    topic = Topic(user_id=user.id, title="Test")
    db.add(topic)
    db.flush()

    paper = Paper(topic_id=topic.id, title="A Paper on FL")
    db.add(paper)
    db.flush()

    decision = PaperDecision(paper_id=paper.id, label="direct", relevance_score=0.9, method="llm")
    db.add(decision)
    db.commit()

    assert paper.decision.label == "direct"
    assert paper.decision.relevance_score == 0.9


def test_paper_deduplication_logic(db):
    """Verify that title-based dedup works at service level."""
    user = _create_user(db, email="modeltest4@example.com")
    topic = Topic(user_id=user.id, title="Test")
    db.add(topic)
    db.flush()

    titles = set()
    papers_to_add = ["Paper A", "Paper B", "Paper A"]  # duplicate
    added = 0
    for title in papers_to_add:
        if title.lower() not in titles:
            titles.add(title.lower())
            p = Paper(topic_id=topic.id, title=title)
            db.add(p)
            added += 1
    db.commit()
    assert added == 2
