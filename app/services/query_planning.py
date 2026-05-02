import json
import re
import logging
from jinja2 import Environment, FileSystemLoader, select_autoescape
from pathlib import Path
from sqlalchemy.orm import Session
from app.core.llm_router import get_router
from app.models.topic import Topic, QueryPlan, QueryBundle

logger = logging.getLogger(__name__)

_jinja_env = Environment(
    loader=FileSystemLoader(Path(__file__).parent.parent / "prompts"),
    autoescape=select_autoescape([]),
)


def _extract_json(raw: str) -> list:
    """Extract JSON array from LLM response, handling markdown fences and extra text."""
    # Strip markdown code fences
    cleaned = re.sub(r"```(?:json)?\s*", "", raw).strip().rstrip("`").strip()

    # Try direct parse first
    try:
        data = json.loads(cleaned)
        if isinstance(data, list):
            return data
        if isinstance(data, dict) and "queries" in data:
            return data["queries"]
        if isinstance(data, dict) and "bundles" in data:
            return data["bundles"]
    except json.JSONDecodeError:
        pass

    # Try to find JSON array in the text
    match = re.search(r'\[[\s\S]*\]', cleaned)
    if match:
        try:
            data = json.loads(match.group())
            if isinstance(data, list):
                return data
        except json.JSONDecodeError:
            pass

    raise ValueError(f"Could not extract JSON array from LLM response: {raw[:300]}")


def generate_query_plan(topic: Topic, db: Session) -> QueryPlan:
    """Use LLM to generate a structured query plan for the topic."""
    template = _jinja_env.get_template("query_planning.j2")
    user_prompt = template.render(
        topic_title=topic.title,
        topic_description=topic.description or "",
        adjacent_fields=topic.adjacent_fields or [],
        literature_scarce=topic.literature_scarce,
    )

    router = get_router()
    system_prompt = "You are a research librarian. Return ONLY a valid JSON array, no markdown, no explanation."

    # Retry up to 2 times if JSON parsing fails
    last_error = None
    for attempt in range(2):
        raw = router.complete_for_stage("query_plan", system_prompt, user_prompt)
        try:
            bundles_data = _extract_json(raw)
            break
        except ValueError as e:
            logger.warning("Query plan JSON parse attempt %d failed: %s", attempt + 1, e)
            last_error = e
    else:
        logger.error("All query plan parse attempts failed. Last raw: %s", raw[:300])
        raise ValueError(f"LLM returned invalid JSON for query plan: {last_error}")

    plan = QueryPlan(topic_id=topic.id)
    db.add(plan)
    db.flush()

    for item in bundles_data:
        bundle = QueryBundle(
            plan_id=plan.id,
            label=item.get("label", "direct"),
            query_text=item.get("query_text", ""),
            source=item.get("source", "both"),
        )
        db.add(bundle)

    db.commit()
    db.refresh(plan)
    logger.info("Query plan created: %d bundles for topic %d", len(bundles_data), topic.id)
    return plan
