import base64
from pathlib import Path

from ..models import Message

UPLOAD_ROOT = Path(__file__).resolve().parent.parent.parent / "uploads"


def message_media_label(message: Message) -> str:
    if (message.message_type or "text") != "image":
        return ""
    name = message.file_name or "图片"
    return f"[图片: {name}]"


def message_text_with_media(message: Message) -> str:
    media = message_media_label(message)
    if media and message.content:
        return f"{media} {message.content}"
    return media or message.content


def image_message_to_data_url(message: Message) -> str | None:
    if (message.message_type or "text") != "image" or not message.media_url:
        return None
    relative = message.media_url.removeprefix("/uploads/").replace("/", "\\")
    path = (UPLOAD_ROOT / relative).resolve()
    try:
        path.relative_to(UPLOAD_ROOT.resolve())
    except ValueError:
        return None
    if not path.exists() or not path.is_file():
        return None
    mime = message.mime_type or "image/png"
    data = base64.b64encode(path.read_bytes()).decode("ascii")
    return f"data:{mime};base64,{data}"
