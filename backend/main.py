from pathlib import Path
import asyncio
import os
import secrets
import warnings

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware

from .admin.auth import AdminAuthProvider
from .admin.views import EntertainmentPersonaView, SettingsView
from .api.routes import router
from .core.config import get_setting
from .db import engine, init_db
from .seed import seed_data
from .steward.service import StewardService

app = FastAPI(title="Companion Agent v3")
heartbeat_task: asyncio.Task | None = None

admin_session_secret = os.getenv("ADMIN_SESSION_SECRET")
if not admin_session_secret:
    admin_session_secret = secrets.token_urlsafe(32)
    warnings.warn(
        "ADMIN_SESSION_SECRET is not set; admin sessions will be invalidated on restart.",
        RuntimeWarning,
        stacklevel=2,
    )
app.add_middleware(SessionMiddleware, secret_key=admin_session_secret, same_site="lax")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
async def on_startup() -> None:
    init_db()
    from sqlmodel import Session

    with Session(engine) as session:
        seed_data(session)
    global heartbeat_task
    if heartbeat_task is None:
        heartbeat_task = asyncio.create_task(steward_heartbeat())


async def steward_heartbeat() -> None:
    while True:
        try:
            from sqlmodel import Session

            with Session(engine) as session:
                enabled = get_setting(session, "proactivity.enabled", "false") == "true"
                interval = int(get_setting(session, "proactivity.interval_minutes", "30") or 30)
                if enabled:
                    StewardService(session).proactivity_tick()
            await asyncio.sleep(max(60, interval * 60))
        except asyncio.CancelledError:
            raise
        except Exception:
            await asyncio.sleep(300)


app.include_router(router)


@app.get("/admin", include_in_schema=False)
def admin_redirect():
    return RedirectResponse("/admin/")


from starlette_admin.contrib.sqlmodel import Admin

admin_site = Admin(
    engine,
    title="Companion Admin",
    auth_provider=AdminAuthProvider(),
    base_url="/admin",
)
admin_site.add_view(EntertainmentPersonaView())
admin_site.add_view(SettingsView())
admin_site.mount_to(app)

uploads_dir = Path(__file__).resolve().parent.parent / "uploads"
uploads_dir.mkdir(parents=True, exist_ok=True)
app.mount("/uploads", StaticFiles(directory=uploads_dir), name="uploads")

frontend_dist = Path(__file__).resolve().parent.parent / "frontend" / "dist"
if frontend_dist.exists():
    app.mount("/", StaticFiles(directory=frontend_dist, html=True), name="static")
