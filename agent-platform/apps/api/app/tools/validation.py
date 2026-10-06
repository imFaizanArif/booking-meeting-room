"""JSON Schema validation of tool arguments with field-level errors."""

from __future__ import annotations

from typing import Any

from jsonschema import Draft202012Validator
from jsonschema.exceptions import SchemaError


def argument_errors(schema: dict[str, Any], arguments: Any) -> list[dict[str, str]]:
    """Return [{"field": "a.b", "message": "..."}]; empty when valid."""
    if not isinstance(arguments, dict):
        return [{"field": "", "message": "Arguments must be a JSON object"}]
    try:
        validator = Draft202012Validator(schema or {"type": "object"})
    except SchemaError as exc:
        return [{"field": "", "message": f"Tool schema is invalid: {exc.message}"}]
    errors = []
    for err in sorted(validator.iter_errors(arguments), key=lambda e: list(e.absolute_path)):
        field = ".".join(str(p) for p in err.absolute_path)
        if err.validator == "required" and isinstance(err.instance, dict):
            missing = [r for r in err.validator_value if r not in err.instance]
            for name in missing:
                errors.append({"field": f"{field}.{name}".strip("."), "message": "This field is required"})
            continue
        errors.append({"field": field, "message": err.message})
    return errors[:50]
