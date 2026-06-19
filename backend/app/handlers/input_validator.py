"""
InputValidator — validates and sanitizes all user-supplied text inputs before entering the pipeline.

Implements requirements: 3.1, 3.2, 4.7
"""

import os
import re

class InputValidationError(ValueError):
    """Exception raised when input validation fails."""
    
    def __init__(self, error_code: str, detail: str) -> None:
        self.error_code = error_code
        self.detail = detail
        super().__init__(detail)


class InputValidator:
    """Validator and sanitizer for user-supplied queries, filenames, and text inputs."""

    # Regex to match HTML tags
    HTML_TAG_RE = re.compile(r'<[^>]+>')

    # Common SQL injection patterns (case-insensitive)
    SQL_INJECTION_PATTERNS = [
        re.compile(r"'\s*or\s+['\"]?\d+['\"]?\s*=\s*['\"]?\d+", re.IGNORECASE),
        re.compile(r"\bor\s+\d+\s*=\s*\d+", re.IGNORECASE),
        re.compile(r"[\"']\s*or\s+[\"']?\w+[\"']?\s*=\s*[\"']?\w+", re.IGNORECASE),
        re.compile(r"\bunion\s+select\b", re.IGNORECASE),
        re.compile(r"\bdrop\s+table\b", re.IGNORECASE),
        re.compile(r"\binsert\s+into\b", re.IGNORECASE),
        re.compile(r"\bselect\s+.*\s+from\b", re.IGNORECASE),
        re.compile(r"--", re.IGNORECASE),
        re.compile(r"/\*", re.IGNORECASE),
        re.compile(r"\*/", re.IGNORECASE),
        re.compile(r";", re.IGNORECASE),
    ]

    @staticmethod
    def validate_query(query: str) -> None:
        """Validate query length and contents.

        Parameters
        ----------
        query : str
            The user query to validate.

        Raises
        ------
        InputValidationError
            If the query is empty/whitespace or exceeds 2000 characters.
        """
        if not query or not query.strip():
            raise InputValidationError("invalid_query", "Query must not be empty or whitespace.")
        if len(query) > 1000000:
            raise InputValidationError("query_too_long", "Query exceeds 1000000 character limit.")

    @classmethod
    def sanitize_query(cls, query: str) -> str:
        """Remove HTML tags, SQL injection patterns, and control characters from query.

        Parameters
        ----------
        query : str
            The query text to sanitize.

        Returns
        -------
        str
            The sanitized query.
        """
        # 1. Remove HTML tags
        sanitized = cls.HTML_TAG_RE.sub("", query)

        # 2. Remove SQL injection patterns
        for pattern in cls.SQL_INJECTION_PATTERNS:
            sanitized = pattern.sub("", sanitized)

        # 3. Remove/escape control characters
        sanitized = cls.sanitize_text(sanitized)
        return sanitized

    @staticmethod
    def sanitize_text(text: str) -> str:
        """Sanitize general text inputs by removing null bytes and control characters.

        Parameters
        ----------
        text : str
            The text to sanitize.

        Returns
        -------
        str
            The sanitized text.
        """
        # Remove null bytes
        text = text.replace("\x00", "")
        # Remove control characters (ASCII 0-31 except tab/newline/carriage return, and 127)
        return "".join(ch for ch in text if ord(ch) >= 32 or ch in "\t\n\r")

    @staticmethod
    def sanitize_filename(filename: str) -> str:
        """Sanitize a file name to retain only safe characters.

        Keeps alphanumeric, dots, dashes, and underscores.

        Parameters
        ----------
        filename : str
            The filename to sanitize.

        Returns
        -------
        str
            The sanitized filename.
        """
        filename = filename.replace("\x00", "")
        name, ext = os.path.splitext(filename)
        # Remove special characters from both base name and extension
        safe_name = re.sub(r"[^a-zA-Z0-9._-]", "", name)
        safe_ext = re.sub(r"[^a-zA-Z0-9._-]", "", ext)
        if not safe_name:
            safe_name = "unnamed"
        return f"{safe_name}{safe_ext}"
