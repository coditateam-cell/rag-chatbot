# Feature: rag-chatbot-application, Property 9: Invalid queries are always rejected by the Input Validator
# Feature: rag-chatbot-application, Property 10: Sanitised queries never contain HTML tags or SQL injection patterns
"""
Property-based tests for InputValidator.

Validates: Requirements 3.1, 3.2, 4.7
"""

import pytest
from hypothesis import given, settings, HealthCheck
from hypothesis import strategies as st

from app.handlers.input_validator import InputValidator, InputValidationError


# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

# Strategy for empty or whitespace-only queries
empty_or_whitespace_strategy = st.one_of(
    st.just(""),
    st.text(alphabet=" \t\r\n", min_size=1)
)

# Strategy for too long queries (> 2000 characters)
too_long_query_strategy = st.text(min_size=2001, max_size=3000)

# Strategy for all invalid queries (Property 9)
invalid_query_strategy = st.one_of(
    empty_or_whitespace_strategy,
    too_long_query_strategy
)

# HTML tag injection pattern strategies
html_injections = [
    lambda s: f"<script>{s}</script>",
    lambda s: f"text before <img src='x' onerror='alert(1)'> text after",
    lambda s: f"<div>{s}</div>",
    lambda s: f"<a href='http://evil.com'>{s}</a>",
    lambda s: f"<p>{s}</p>",
]

# SQL injection pattern strategies
sql_injections = [
    lambda s: f"{s} ' OR 1=1",
    lambda s: f"{s} OR 1=1",
    lambda s: f"\" OR \"a\"=\"a",
    lambda s: f"{s}; DROP TABLE documents; --",
    lambda s: f"SELECT * FROM users; {s}",
    lambda s: f"UNION SELECT null, null; {s}",
    lambda s: f"{s} -- comment",
    lambda s: f"{s} /* nested comment */",
]

# Combined strategy for injection inputs
@st.composite
def query_with_html_injection(draw):
    base = draw(st.text(min_size=1, max_size=100))
    template = draw(st.sampled_from(html_injections))
    return template(base)

@st.composite
def query_with_sql_injection(draw):
    base = draw(st.text(min_size=1, max_size=100))
    template = draw(st.sampled_from(sql_injections))
    return template(base)


# ---------------------------------------------------------------------------
# Property Tests
# ---------------------------------------------------------------------------

# Feature: rag-chatbot-application, Property 9: Invalid queries are always rejected by the Input Validator
@given(query=invalid_query_strategy)
@settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow], deadline=None)
def test_p9_invalid_queries_rejected(query: str) -> None:
    """P9: Invalid queries (empty, whitespace, or > 2000 chars) are always rejected.

    Validates: Requirement 3.1
    """
    with pytest.raises(InputValidationError) as exc_info:
        InputValidator.validate_query(query)
    
    error = exc_info.value
    if not query or not query.strip():
        assert error.error_code == "invalid_query"
        assert error.detail == "Query must not be empty or whitespace."
    else:
        assert error.error_code == "query_too_long"
        assert error.detail == "Query exceeds 2000 character limit."


# Feature: rag-chatbot-application, Property 10: Sanitised queries never contain HTML tags or SQL injection patterns
@given(query=st.one_of(query_with_html_injection(), query_with_sql_injection()))
@settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow], deadline=None)
def test_p10_sanitised_queries_safe(query: str) -> None:
    """P10: Sanitised queries never contain HTML tags or SQL injection patterns.

    Validates: Requirements 3.2, 4.7
    """
    sanitized = InputValidator.sanitize_query(query)
    
    # 1. Assert no HTML tags remain
    assert not InputValidator.HTML_TAG_RE.search(sanitized), f"Sanitized query still contains HTML tags: {sanitized}"
    
    # 2. Assert no SQL injection patterns remain
    for pattern in InputValidator.SQL_INJECTION_PATTERNS:
        assert not pattern.search(sanitized), f"Sanitized query still matches SQL pattern: {sanitized}"
        
    # 3. Assert the sanitized query differs from original query (since query is generated to contain injection)
    assert sanitized != query, f"Sanitization did not modify the query containing injection: {query}"


@given(filename=st.text(min_size=1, max_size=100))
@settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow], deadline=None)
def test_sanitize_filename_removes_special_chars(filename: str) -> None:
    """Validate that filename sanitization only retains alphanumeric, dots, dashes, and underscores."""
    sanitized = InputValidator.sanitize_filename(filename)
    # Check that only allowed characters are present
    import re
    assert re.match(r"^[a-zA-Z0-9._-]+$", sanitized), f"Filename contains disallowed characters: {sanitized}"
