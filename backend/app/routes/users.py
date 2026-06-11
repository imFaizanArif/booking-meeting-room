from flask import Blueprint, g, jsonify, request

from ..auth import require_admin, require_auth
from ..services.user_service import UserService

users_bp = Blueprint("users", __name__)


@users_bp.get("")
@require_auth
def list_users():
    users = UserService().list_users(search=request.args.get("search"))
    return jsonify({"data": users})


@users_bp.get("/me")
@require_auth
def get_me():
    return jsonify({"data": g.current_user.to_dict()})


@users_bp.put("/me")
@require_auth
def update_me():
    payload = request.get_json(silent=True) or {}
    user = UserService().update_profile(str(g.current_user.id), payload, g.current_user)
    return jsonify({"data": user})


@users_bp.get("/<user_id>")
@require_auth
def get_user(user_id: str):
    return jsonify({"data": UserService().get_user(user_id)})


@users_bp.put("/<user_id>")
@require_admin
def admin_update_user(user_id: str):
    payload = request.get_json(silent=True) or {}
    user = UserService().admin_update_user(user_id, payload, g.current_user)
    return jsonify({"data": user})
