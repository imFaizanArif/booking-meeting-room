"""Sandboxed prompt templates.

Jinja2 `SandboxedEnvironment` + `StrictUndefined`: variable substitution, conditionals,
loops and a few filters. No attribute access to private names, no imports, no globals
beyond what we pass. Missing variables fail with a clear error listing them.
"""

from __future__ import annotations

import json
from typing import Any

from jinja2 import StrictUndefined, TemplateSyntaxError, UndefinedError, meta
from jinja2.sandbox import ImmutableSandboxedEnvironment

from app.core.enums import ErrorCode
from app.core.errors import AppError

_MAX_OUTPUT = 400_000


class TemplateError(AppError):
    code = ErrorCode.template_error


def _tojson(value: Any, indent: int | None = None) -> str:
    return json.dumps(value, indent=indent, default=str, ensure_ascii=False)


def _env() -> ImmutableSandboxedEnvironment:
    env = ImmutableSandboxedEnvironment(
        undefined=StrictUndefined, autoescape=False, trim_blocks=True, lstrip_blocks=True
    )
    env.filters["tojson"] = _tojson
    env.filters["truncate_chars"] = lambda v, n=500: (str(v)[: int(n)] + "…") if len(str(v)) > int(n) else str(v)
    return env


_ENV = _env()


def referenced_variables(source: str) -> set[str]:
    """Top-level names a template uses (e.g. `my_resume`, `nodes`, `input`)."""
    try:
        return set(meta.find_undeclared_variables(_ENV.parse(source)))
    except TemplateSyntaxError as exc:
        raise TemplateError(
            f"Template syntax error on line {exc.lineno}: {exc.message}", details={"line": exc.lineno}
        ) from exc


def render(source: str, context: dict[str, Any]) -> str:
    missing = sorted(referenced_variables(source) - set(context))
    if missing:
        raise TemplateError(f"Missing template variables: {', '.join(missing)}", details={"missing": missing})
    try:
        out = _ENV.from_string(source).render(**context)
    except UndefinedError as exc:
        raise TemplateError(f"Template references an undefined value: {exc.message}") from exc
    except TemplateSyntaxError as exc:
        raise TemplateError(
            f"Template syntax error on line {exc.lineno}: {exc.message}", details={"line": exc.lineno}
        ) from exc
    except Exception as exc:  # SecurityError, TypeError inside expressions
        raise TemplateError(f"Template failed to render: {exc}") from exc
    if len(out) > _MAX_OUTPUT:
        raise TemplateError("Rendered template is too large", details={"limit": _MAX_OUTPUT})
    return out


def preview(source: str, context: dict[str, Any]) -> tuple[str | None, list[str], str | None]:
    """Render for the UI: (output, unresolved variables, error message)."""
    try:
        names = referenced_variables(source)
    except TemplateError as exc:
        return None, [], exc.message
    missing = sorted(names - set(context))
    if missing:
        filled = {**context, **{m: f"{{{{{m}}}}}" for m in missing}}
        try:
            return _ENV.from_string(source).render(**filled), missing, None
        except Exception as exc:  # noqa: BLE001 - preview reports any rendering error to the author
            return None, missing, str(exc)
    try:
        return render(source, context), [], None
    except TemplateError as exc:
        return None, [], exc.message
