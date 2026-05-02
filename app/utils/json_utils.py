"""Shared JSON extraction utilities for LLM responses."""
import json
import re
import logging

logger = logging.getLogger(__name__)


def extract_json(raw: str, expected_type: type = dict) -> dict | list:
    """
    Robustly extract JSON from LLM response.
    Handles: markdown fences, extra text before/after, wrapped objects.

    Args:
        raw: Raw LLM response string
        expected_type: dict or list — what type to expect

    Returns:
        Parsed JSON object
    """
    if not raw:
        return expected_type()

    # Strip markdown code fences
    cleaned = re.sub(r"```(?:json|python)?\s*", "", raw).strip().rstrip("`").strip()

    # Try direct parse
    try:
        data = json.loads(cleaned)
        if isinstance(data, expected_type):
            return data
        # Handle wrapped responses like {"queries": [...]} when expecting list
        if expected_type == list and isinstance(data, dict):
            for key in ("queries", "bundles", "gaps", "results", "items", "data"):
                if key in data and isinstance(data[key], list):
                    return data[key]
        return data
    except json.JSONDecodeError:
        pass

    # Try to find JSON in the text
    if expected_type == list:
        match = re.search(r'\[[\s\S]*\]', cleaned)
    else:
        match = re.search(r'\{[\s\S]*\}', cleaned)

    if match:
        try:
            data = json.loads(match.group())
            return data
        except json.JSONDecodeError:
            pass

    logger.warning("Could not extract JSON from LLM response (first 200 chars): %s", raw[:200])
    return expected_type()
