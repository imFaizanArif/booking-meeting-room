from flask import Blueprint, g, jsonify, request

from ..auth import require_auth
from ..errors import AppError
from ..services.booking_service import BookingService

bookings_bp = Blueprint("bookings", __name__)


@bookings_bp.get("")
@require_auth
def list_bookings():
    service = BookingService()
    bookings = service.list_bookings(
        room_id=request.args.get("room_id"),
        user_id=request.args.get("user_id"),
        status=request.args.get("status"),
        start_after=request.args.get("start_after"),
        end_before=request.args.get("end_before"),
        search=request.args.get("search"),
    )
    return jsonify({"data": bookings})


@bookings_bp.get("/<booking_id>")
@require_auth
def get_booking(booking_id: str):
    return jsonify({"data": BookingService().get_booking(booking_id)})


@bookings_bp.get("/availability")
@require_auth
def check_availability():
    room_id = request.args.get("room_id")
    start_time = request.args.get("start_time")
    end_time = request.args.get("end_time")
    if not (room_id and start_time and end_time):
        raise AppError("room_id, start_time and end_time query params are required")
    result = BookingService().check_availability(room_id, start_time, end_time)
    return jsonify({"data": result})


@bookings_bp.post("")
@require_auth
def create_booking():
    payload = request.get_json(silent=True) or {}
    booking = BookingService().create_booking(payload, g.current_user)
    return jsonify({"data": booking}), 201


@bookings_bp.put("/<booking_id>")
@require_auth
def update_booking(booking_id: str):
    payload = request.get_json(silent=True) or {}
    booking = BookingService().update_booking(booking_id, payload, g.current_user)
    return jsonify({"data": booking})


@bookings_bp.post("/<booking_id>/cancel")
@require_auth
def cancel_booking(booking_id: str):
    booking = BookingService().cancel_booking(booking_id, g.current_user)
    return jsonify({"data": booking})


@bookings_bp.delete("/<booking_id>")
@require_auth
def delete_booking(booking_id: str):
    BookingService().delete_booking(booking_id, g.current_user)
    return jsonify({"data": {"deleted": True}})
