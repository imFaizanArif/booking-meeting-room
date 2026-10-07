"""Central redactor for logs, events and audit payloads.

Two mechanisms:
* key-based: values under sensitive key names are masked wherever they appear;
* value-based: every secret decrypted in this process is registered, and any string
  containing it is masked, even under an innocuous key or inside free text.
"""

from __future__ import annotations

import re
import threading
from collections.abc import Mapping
from typing import Any

MASK = "[REDACTED]"
_SENSITIVE_KEY = re.compile(
    r"(pass(word)?|secret|token|api[_-]?key|authorization|cookie|credential|private[_-]?key|session)",
    re.IGNORECASE,
)
# keys that look sensitive but are safe identifiers
_SAFE_KEYS = frozenset(
    {
        "secret_ref",
        "api_key_secret_ref",
        "token_count",
        "input_tokens",
        "output_tokens",
        "total_tokens",
        "max_tokens",
        "is_set",
        "max_tool_calls",
        "token_budget",
        "tokens",
        "session_id_hint",
        "csrf_token_hint",
        "idempotency_key",
    }
)
_MIN_SECRET_LEN = 6


class Redactor:
    def __init__(self) -> None:
        self._values: set[str] = set()
        self._lock = threading.Lock()
        self._pattern: re.Pattern[str] | None = None

    def register(self, value: str | None) -> None:
        if not value or len(value) < _MIN_SECRET_LEN:
            return
        with self._lock:
            if value not in self._values:
                self._values.add(value)
                self._pattern = re.compile("|".join(re.escape(v) for v in sorted(self._values, key=len, reverse=True)))

    def redact_text(self, text: str) -> str:
        pattern = self._pattern
        if pattern is None:
            return text
        return pattern.sub(MASK, text)

    def redact(self, value: Any, *, _key: str | None = None) -> Any:
        if _key is not None and _key not in _SAFE_KEYS and _SENSITIVE_KEY.search(_key):
            return MASK if value not in (None, "", False) else value
        if isinstance(value, str):
            return self.redact_text(value)
        if isinstance(value, Mapping):
            return {k: self.redact(v, _key=str(k)) for k, v in value.items()}
        if isinstance(value, (list, tuple)):
            return [self.redact(v) for v in value]
        return value


redactor = Redactor()
