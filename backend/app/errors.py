"""Centralised application errors and Flask error handlers."""

from flask import Flask, jsonify
from pydantic import ValidationError


class AppError(Exception):
    status_code = 400
    code = "bad_request"

    def __init__(self, message: str, status_code: int | None = None, code: str | None = None):
        super().__init__(message)
        self.message = message
        if status_code is not None:
            self.status_code = status_code
        if code is not None:
            self.code = code


class NotFoundError(AppError):
    status_code = 404
    code = "not_found"


class ConflictError(AppError):
    status_code = 409
    code = "conflict"


class UnauthorizedError(AppError):
    status_code = 401
    code = "unauthorized"


class ForbiddenError(AppError):
    status_code = 403
    code = "forbidden"


def register_error_handlers(app: Flask) -> None:
    @app.errorhandler(AppError)
    def handle_app_error(error: AppError):
        return jsonify({"error": {"code": error.code, "message": error.message}}), error.status_code

    @app.errorhandler(ValidationError)
    def handle_validation_error(error: ValidationError):
        details = [
            {"field": ".".join(str(loc) for loc in e["loc"]), "message": e["msg"]}
            for e in error.errors()
        ]
        return (
            jsonify({"error": {"code": "validation_error", "message": "Invalid request payload", "details": details}}),
            422,
        )

    @app.errorhandler(404)
    def handle_404(_):
        return jsonify({"error": {"code": "not_found", "message": "Resource not found"}}), 404

    @app.errorhandler(405)
    def handle_405(_):
        return jsonify({"error": {"code": "method_not_allowed", "message": "Method not allowed"}}), 405

    @app.errorhandler(Exception)
    def handle_unexpected(error: Exception):
        app.logger.exception("Unhandled exception: %s", error)
        return (
            jsonify({"error": {"code": "internal_error", "message": "An unexpected error occurred"}}),
            500,
        )
