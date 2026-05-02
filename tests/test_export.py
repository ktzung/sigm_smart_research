"""Tests for export module."""
import pytest
from app.services.export import export_markdown


def test_export_markdown_basic():
    bundle = {
        "topic": {"id": 1, "title": "FL Concept Drift", "description": "Test"},
        "papers": [
            {"id": 1, "title": "Paper A", "year": 2023, "venue": "NeurIPS", "url": None,
             "decision": {"label": "direct", "score": 0.9, "reason": "relevant"},
             "extraction": None}
        ],
        "synthesis": None,
        "taxonomy": {"dimensions": {"method": ["centralized", "federated"]}, "paper_mapping": {}, "explanation": "Test taxonomy"},
        "gaps": [{"type": "missing_benchmark", "description": "No real-world benchmarks", "priority": "high", "evidence_ids": [1]}],
        "draft_sections": [{"section": "introduction", "version": 1, "content": "This survey covers..."}],
        "review": {"major_weaknesses": "Coverage is thin", "minor_issues": "Typos", "revision_priorities": "Add more papers", "overall_score": "weak_accept"},
    }
    md = export_markdown(bundle)
    assert "FL Concept Drift" in md
    assert "Paper A" in md
    assert "missing_benchmark" in md
    assert "introduction" in md.lower()
    assert "weak_accept" in md
