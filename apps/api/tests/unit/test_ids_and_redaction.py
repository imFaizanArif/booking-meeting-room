"""Idempotency keys and the central redactor."""

from __future__ import annotations

import uuid

from app.core.ids import external_idempotency_key, idempotency_key, new_id, slugify
from app.core.redaction import MASK, Redactor


def test_idempotency_key_is_deterministic() -> None:
    execution_id = uuid.UUID("01a1131d-0000-7000-8000-000000000001")
    assert idempotency_key(execution_id, "draft", 2) == f"{execution_id}:draft:2"
    assert idempotency_key(str(execution_id), "draft", 2) == idempotency_key(execution_id, "draft", 2)
    assert idempotency_key(execution_id, "draft", 3) != idempotency_key(execution_id, "draft", 2)
    assert idempotency_key(execution_id, "other", 2) != idempotency_key(execution_id, "draft", 2)
    external = external_idempotency_key(idempotency_key(execution_id, "draft", 2))
    assert external == external_idempotency_key(f"{execution_id}:draft:2")
    assert len(external) == 32 and str(execution_id) not in external


def test_ids_and_slugs() -> None:
    a, b = new_id(), new_id()
    assert a.version == 7 and a != b
    assert slugify("Job Application Assistant!") == "job_application_assistant"
    assert slugify("***") == "item"


def test_registered_values_masked_anywhere() -> None:
    r = Redactor()
    r.register("sk-live-0123456789")
    r.register("abc")  # too short to register safely
    payload = {
        "note": "using sk-live-0123456789 now",
        "nested": {"list": ["x", {"deep": "sk-live-0123456789"}]},
        "tuple": ("sk-live-0123456789",),
        "short": "abc",
        "n": 5,
    }
    assert r.redact(payload) == {
        "note": f"using {MASK} now",
        "nested": {"list": ["x", {"deep": MASK}]},
        "tuple": [MASK],
        "short": "abc",
        "n": 5,
    }
    assert r.redact_text("prefix-sk-live-0123456789-suffix") == f"prefix-{MASK}-suffix"


def test_overlapping_values_prefer_longest() -> None:
    r = Redactor()
    r.register("secret-value")
    r.register("secret-value-extended")
    assert r.redact_text("secret-value-extended!") == f"{MASK}!"


def test_sensitive_key_names_masked() -> None:
    r = Redactor()
    payload = {
        "password": "hunter2",
        "Authorization": "Bearer x",
        "api_key": "k",
        "X-Api-Key": "k",
        "client_secret": "s",
        "refresh_token": "t",
        "cookie": "c",
        "private_key": "p",
        "headers": {"authorization": "Bearer y"},
        "credentials": {"user": "u"},
        "token": "",
        "secret": None,
    }
    out = r.redact(payload)
    for key in (
        "password",
        "Authorization",
        "api_key",
        "X-Api-Key",
        "client_secret",
        "refresh_token",
        "cookie",
        "private_key",
        "credentials",
    ):
        assert out[key] == MASK, key
    assert out["headers"] == {"authorization": MASK}
    assert out["token"] == "" and out["secret"] is None  # nothing to hide


def test_safe_keys_are_kept() -> None:
    r = Redactor()
    payload = {
        "api_key_secret_ref": "secret:123",
        "input_tokens": 10,
        "max_tokens": 5,
        "is_set": True,
        "idempotency_key": "e:n:1",
        "total_tokens": 15,
        "title": "fine",
    }
    assert r.redact(payload) == payload
