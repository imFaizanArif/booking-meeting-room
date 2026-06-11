from flask import Blueprint, jsonify, request

from ..auth import require_admin, require_auth
from ..services.room_service import RoomService

rooms_bp = Blueprint("rooms", __name__)


@rooms_bp.get("")
@require_auth
def list_rooms():
    include_inactive = request.args.get("include_inactive", "false").lower() == "true"
    search = request.args.get("search")
    rooms = RoomService().list_rooms(include_inactive=include_inactive, search=search)
    return jsonify({"data": rooms})


@rooms_bp.get("/<room_id>")
@require_auth
def get_room(room_id: str):
    return jsonify({"data": RoomService().get_room(room_id)})


@rooms_bp.post("")
@require_admin
def create_room():
    payload = request.get_json(silent=True) or {}
    room = RoomService().create_room(payload)
    return jsonify({"data": room}), 201


@rooms_bp.put("/<room_id>")
@require_admin
def update_room(room_id: str):
    payload = request.get_json(silent=True) or {}
    room = RoomService().update_room(room_id, payload)
    return jsonify({"data": room})


@rooms_bp.delete("/<room_id>")
@require_admin
def delete_room(room_id: str):
    RoomService().delete_room(room_id)
    return jsonify({"data": {"deleted": True}})
