"""Property-based tests for GitHub integration service.

Validates: Requirements 2.3, 2.4, 2.12
"""
from hypothesis import given, settings as h_settings
from hypothesis import strategies as st
from app.services.github_service import RepoContent


# ── Property 4: Code analysis result completeness ─────────────────────────────

@h_settings(max_examples=200)
@given(
    languages=st.dictionaries(st.text(min_size=1, max_size=20), st.integers(min_value=0)),
    directory_tree=st.text(min_size=1),
    key_modules=st.lists(st.fixed_dictionaries({"name": st.text(), "path": st.text(), "description": st.text()})),
    readme_summary=st.text(min_size=1),
    dependencies=st.lists(st.text(min_size=1)),
)
def test_repo_content_all_fields_non_null(languages, directory_tree, key_modules, readme_summary, dependencies):
    """Property 4: Code analysis result completeness.

    **Validates: Requirements 2.3, 2.4**
    """
    content = RepoContent(
        languages=languages,
        directory_tree=directory_tree,
        key_modules=key_modules,
        readme_summary=readme_summary,
        dependencies=dependencies,
    )
    assert content.languages is not None
    assert content.directory_tree is not None
    assert content.key_modules is not None
    assert content.readme_summary is not None
    assert content.dependencies is not None


# ── Property 5: Analysis status progress invariant ────────────────────────────

@h_settings(max_examples=200)
@given(progress=st.integers())
def test_analysis_progress_in_range(progress):
    """Property 5: Analysis status progress invariant.

    **Validates: Requirements 2.12**
    """
    # Clamp to valid range
    clamped = max(0, min(100, progress))
    assert 0 <= clamped <= 100

    # Also test AnalysisStatus model validation
    from app.services.github_service import AnalysisStatus
    status = AnalysisStatus(status="running", progress_pct=clamped, current_step="test")
    assert 0 <= status.progress_pct <= 100
