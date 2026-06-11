from flask import Blueprint, jsonify

from ..auth import require_admin
from ..services.analytics_service import AnalyticsService

analytics_bp = Blueprint("analytics", __name__)


@analytics_bp.get("/dashboard")
@require_admin
def dashboard_stats():
    return jsonify({"data": AnalyticsService().get_dashboard_stats()})
