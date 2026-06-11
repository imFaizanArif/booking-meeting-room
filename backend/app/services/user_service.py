from ..errors import ForbiddenError, NotFoundError
from ..extensions import get_supabase_admin
from ..models import Profile
from ..repositories.user_repository import UserRepository
from ..schemas import UserUpdateSchema


class UserService:
    def __init__(self) -> None:
        self.users = UserRepository()

    def list_users(self, search: str | None = None) -> list[dict]:
        return [u.to_dict() for u in self.users.list_all(search=search)]

    def get_user(self, user_id: str) -> dict:
        return self._get_or_404(user_id).to_dict()

    def update_profile(self, user_id: str, payload: dict, current_user: Profile) -> dict:
        """Self-service profile update — privileged fields are stripped."""
        if str(current_user.id) != str(user_id):
            raise ForbiddenError("You can only update your own profile")
        data = UserUpdateSchema(**payload).model_dump(
            exclude_unset=True, exclude={"role", "is_active"}
        )
        user = self.users.update(self._get_or_404(user_id), data)
        return user.to_dict()

    def admin_update_user(self, user_id: str, payload: dict, current_user: Profile) -> dict:
        """Admin update: role assignment and enable/disable."""
        user = self._get_or_404(user_id)
        data = UserUpdateSchema(**payload).model_dump(exclude_unset=True)

        if str(user.id) == str(current_user.id) and data.get("is_active") is False:
            raise ForbiddenError("You cannot disable your own account")
        if str(user.id) == str(current_user.id) and data.get("role") == "employee":
            raise ForbiddenError("You cannot remove your own admin role")

        user = self.users.update(user, data)

        # Keep Supabase Auth in sync when disabling/enabling accounts.
        if "is_active" in data:
            try:
                supabase = get_supabase_admin()
                ban_duration = "876000h" if not data["is_active"] else "none"
                supabase.auth.admin.update_user_by_id(
                    str(user.id), {"ban_duration": ban_duration}
                )
            except Exception:
                # Profile flag remains the source of truth for the API layer.
                pass

        return user.to_dict()

    def _get_or_404(self, user_id: str) -> Profile:
        user = self.users.get_by_id(user_id)
        if user is None:
            raise NotFoundError("User not found")
        return user
