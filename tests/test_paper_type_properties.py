"""Property-based tests for the paper type system.

Validates: Requirements 1.1, 1.4, 1.5, 1.6, 1.7, 1.8, 1.9, 1.11, 1.12
"""
import pytest
from hypothesis import given
from hypothesis import settings as h_settings
from hypothesis import strategies as st

from app.services.paper_type_service import (
    REQUIRED_STAGES,
    VALID_PAPER_TYPES,
    get_pipeline_stages,
)


@h_settings(max_examples=200)
@given(paper_type=st.text().filter(lambda x: x not in VALID_PAPER_TYPES))
def test_invalid_paper_type_rejected(paper_type):
    """Property 1: Paper type validation rejects invalid values.

    **Validates: Requirements 1.1, 1.11**
    """
    with pytest.raises(ValueError):
        get_pipeline_stages(paper_type)


@h_settings(max_examples=200)
@given(paper_type=st.sampled_from(VALID_PAPER_TYPES))
def test_pipeline_stages_completeness(paper_type):
    """Property 2: Pipeline stages contain all required stages for each paper type.

    **Validates: Requirements 1.4, 1.5, 1.6, 1.7, 1.8, 1.9**
    """
    stages = get_pipeline_stages(paper_type)
    required = REQUIRED_STAGES[paper_type]
    for req_stage in required:
        assert req_stage in stages


@h_settings(max_examples=200)
@given(paper_type=st.sampled_from(VALID_PAPER_TYPES))
def test_paper_type_roundtrip(paper_type):
    """Property 3: Paper type round-trip preservation.

    Verify that get_pipeline_stages is deterministic (same input → same output).

    **Validates: Requirements 1.12**
    """
    stages1 = get_pipeline_stages(paper_type)
    stages2 = get_pipeline_stages(paper_type)
    assert stages1 == stages2
    assert paper_type in VALID_PAPER_TYPES
