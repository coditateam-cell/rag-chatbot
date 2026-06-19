"""
GuardrailSystem — security layer preventing prompt injection, out-of-scope queries, and too-long queries.

Implements requirements: 4.1, 4.2, 4.3, 4.8, 4.9
"""

import re

class GuardrailViolationError(ValueError):
    """Exception raised when a guardrail rule is violated."""
    
    def __init__(self, error_code: str, detail: str) -> None:
        self.error_code = error_code
        self.detail = detail
        super().__init__(detail)


class GuardrailSystem:
    """Checks queries for prompt injection, out-of-scope topics, and length limits."""

    # Prompt injection patterns (case-insensitive)
    INJECTION_PATTERNS = [
        # Instruction overrides
        r"(?:ignore|forget|disregard|overwrite|bypass|override)\s+(?:all\s+|previous\s+|above\s+|prior\s+|your\s+)*\s*(?:rules|instructions)",
        r"system\s+override",
        r"do\s+anything\s+now",
        r"jailbreak",
        r"developer\s+mode",
        # Role manipulation
        r"you\s+are\s+no\s+longer",
        r"you\s+are\s+now",
        r"act\s+as\s+a",
        r"change\s+role\s+to",
        r"pretend\s+to\s+be",
        r"speak\s+as",
        r"roleplay\s+as",
        r"you\s+must\s+now\s+act",
        # System prompt extraction
        r"print\s+(?:the\s+|your\s+)?system\s+(?:prompt|message|instructions)",
        r"reveal\s+(?:the\s+|your\s+)?system\s+(?:prompt|message|instructions)",
        r"output\s+(?:the\s+|your\s+)?system\s+(?:prompt|message|instructions)",
        r"show\s+(?:the\s+|your\s+)?system\s+(?:prompt|message|instructions)",
        r"reveal\s+(?:instructions|prompt|rules)",
        r"what\s+is\s+(?:the\s+|your\s+)?system\s+(?:prompt|message|instructions)",
        r"what\s+are\s+(?:your\s+)?system\s+(?:prompt|message|instructions|rules)",
        r"tell\s+me\s+(?:your\s+)?rules",
        r"tell\s+me\s+(?:your\s+)?system\s+(?:prompt|message|instructions)"
    ]

    # Out of scope patterns (case-insensitive)
    OUT_OF_SCOPE_PATTERNS = [
        # Unauthorized system operations
        r"\bsudo\b",
        r"\brm\s+-rf\b",
        r"\bformat\s+[a-zA-Z]:",
        r"\bos\.system\b",
        r"\bsubprocess\b",
        r"\beval\(\s*",
        r"\bexec\(\s*",
        # Weather
        r"\bweather\b",
        r"\bforecast\b",
        # Sports
        r"\bfootball\b",
        r"\bbasketball\b",
        r"\bsoccer\b",
        r"\bbaseball\b",
        r"\bsports\s+score\b",
        # Recipes
        r"\brecipe\b",
        r"\bhow\s+to\s+cook\b",
        r"\bcook\s+\w+",
        # Jokes / games / movies
        r"\btell\s+me\s+a\s+joke\b",
        r"\bplay\s+a\s+game\b",
        r"\blatest\s+movie\b",
    ]

    # Pre-compiled regexes
    INJECTION_RE = re.compile("|".join(INJECTION_PATTERNS), re.IGNORECASE)
    OUT_OF_SCOPE_RE = re.compile("|".join(OUT_OF_SCOPE_PATTERNS), re.IGNORECASE)

    @classmethod
    def validate_query(cls, query: str) -> None:
        """Enforce length ceiling, injection check, and scope check.

        Parameters
        ----------
        query : str
            The query text to evaluate.

        Raises
        ------
        GuardrailViolationError
            If the query fails any of the guardrail checks.
        """
        # 1. Length ceiling (Requirement 4.8, 4.9)
        if len(query) > 4000:
            raise GuardrailViolationError("query_too_long", "Query exceeds 4000 character limit.")

        # 2. Prompt injection check (Requirement 4.1, 4.2)
        if cls.INJECTION_RE.search(query):
            raise GuardrailViolationError("security_violation", "Input rejected: security policy violation.")

        # 3. Out-of-scope query check (Requirement 4.3)
        if cls.OUT_OF_SCOPE_RE.search(query):
            raise GuardrailViolationError("out_of_scope", "Query is out of scope for this application.")
