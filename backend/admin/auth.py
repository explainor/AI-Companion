import bcrypt
from sqlmodel import Session
from starlette.requests import Request
from starlette.responses import Response
from starlette_admin.auth import AdminUser, AuthProvider
from starlette_admin.exceptions import FormValidationError

from ..core.config import get_setting
from ..db import engine


class AdminAuthProvider(AuthProvider):
    async def login(
        self,
        username: str,
        password: str,
        remember_me: bool,
        request: Request,
        response: Response,
    ) -> Response:
        with Session(engine) as session:
            expected_username = get_setting(session, "admin.username", "admin") or "admin"
            password_hash = get_setting(session, "admin.password_hash", "") or ""
        if username != expected_username or not _check_password(password, password_hash):
            raise FormValidationError({"username": "Invalid username or password"})
        request.session["admin_logged_in"] = True
        request.session["admin_username"] = expected_username
        return response

    async def is_authenticated(self, request: Request) -> bool:
        return bool(request.session.get("admin_logged_in"))

    def get_admin_user(self, request: Request) -> AdminUser | None:
        if not request.session.get("admin_logged_in"):
            return None
        return AdminUser(username=str(request.session.get("admin_username") or "admin"))

    async def logout(self, request: Request, response: Response) -> Response:
        request.session.pop("admin_logged_in", None)
        request.session.pop("admin_username", None)
        return response


def _check_password(password: str, password_hash: str) -> bool:
    if not password or not password_hash:
        return False
    try:
        return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))
    except ValueError:
        return False
