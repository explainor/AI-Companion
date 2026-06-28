import bcrypt
from starlette.requests import Request
from starlette_admin.contrib.sqlmodel import ModelView
from starlette_admin.fields import BooleanField, IntegerField, PasswordField, StringField, TextAreaField

from ..models import Persona, Setting

SETTINGS_WHITELIST = {
    "personas.max_extra_owned",
    "presence.max_segments_group",
    "presence.max_segments_dm",
    "presence.cooldown_seconds",
    "presence.interjection_probability",
    "admin.username",
    "admin.password_hash",
}


class EntertainmentPersonaView(ModelView):
    label = "娱乐 AI 管理"
    name = "娱乐 AI"
    icon = "fa fa-theater-masks"
    fields = [
        IntegerField("id", read_only=True),
        StringField("name", required=True),
        TextAreaField("system_prompt", required=True),
        StringField("model"),
        StringField("model_override"),
        BooleanField("is_system", read_only=True),
        StringField("kind", read_only=True),
    ]
    exclude_fields_from_create = ["id", "is_system", "kind"]
    exclude_fields_from_edit = ["id", "is_system", "kind"]

    def __init__(self):
        super().__init__(Persona, label=self.label, name=self.name)

    def get_list_query(self, request: Request):
        return super().get_list_query(request).where(Persona.kind == "entertainment")

    def get_count_query(self, request: Request):
        return super().get_count_query(request).where(Persona.kind == "entertainment")

    def before_create(self, request: Request, data: dict, obj: Persona) -> None:
        obj.kind = "entertainment"
        obj.creator_user_id = None
        obj.is_system = 0

    def before_edit(self, request: Request, data: dict, obj: Persona) -> None:
        obj.kind = "entertainment"
        obj.is_system = 0

    def before_delete(self, request: Request, obj: Persona) -> None:
        if obj.kind != "entertainment":
            raise ValueError("Only entertainment AI can be deleted here")


class SettingsView(ModelView):
    label = "系统配置"
    name = "系统配置"
    icon = "fa fa-sliders"
    fields = [
        StringField("key", read_only=True),
        PasswordField("value", required=True),
    ]
    exclude_fields_from_create = ["key"]

    def __init__(self):
        super().__init__(Setting, label=self.label, name=self.name)

    def can_create(self, request: Request) -> bool:
        return False

    def can_delete(self, request: Request) -> bool:
        return False

    def get_list_query(self, request: Request):
        return super().get_list_query(request).where(Setting.key.in_(SETTINGS_WHITELIST))

    def get_count_query(self, request: Request):
        return super().get_count_query(request).where(Setting.key.in_(SETTINGS_WHITELIST))

    def before_edit(self, request: Request, data: dict, obj: Setting) -> None:
        if obj.key not in SETTINGS_WHITELIST:
            raise ValueError("This setting is not editable in admin")
        if obj.key == "admin.password_hash":
            value = str(obj.value or "")
            if value and not value.startswith("$2"):
                obj.value = bcrypt.hashpw(value.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")
