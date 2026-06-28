import json
from typing import Any

from sqlmodel import Session

from ..core.config import resolve_model
from ..core.llm import provider_ready, run_tool_loop
from ..core.time_context import build_time_context
from ..models import Message, Persona, PersonaCard, PersonaNote, PersonaState
from .media import image_message_to_data_url, message_text_with_media
from .relationship import relationship_summary

PERSONA_NOTE_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "add_note",
            "description": "Add a private memory note for this persona.",
            "parameters": {
                "type": "object",
                "properties": {"content": {"type": "string"}},
                "required": ["content"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "update_note",
            "description": "Overwrite an existing private memory note by id.",
            "parameters": {
                "type": "object",
                "properties": {
                    "note_id": {"type": "integer"},
                    "content": {"type": "string"},
                },
                "required": ["note_id", "content"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "delete_note",
            "description": "Delete an existing private memory note by id.",
            "parameters": {
                "type": "object",
                "properties": {"note_id": {"type": "integer"}},
                "required": ["note_id"],
            },
        },
    },
]


def format_recent_messages(recent: list[Message], persona_names: dict[int, str]) -> str:
    lines = []
    for message in recent:
        if message.sender == "user":
            who = "用户"
        else:
            who = persona_names.get(message.persona_id or 0, "角色")
        lines.append(f"{who}: {message_text_with_media(message)}")
    return "\n".join(lines)


def format_notes(notes: list[PersonaNote]) -> str:
    if not notes:
        return "（空）"
    return "\n".join(f"- id={note.id}: {note.content}" for note in notes)


def format_persona_card(persona: Persona, card: PersonaCard | None) -> str:
    if not card:
        return "\n".join([persona.system_prompt, "", persona_output_rules()])
    parts = [
        "角色核心设定:",
        card.persona_core.strip() or persona.system_prompt,
        "",
        "说话风格:",
        card.speaking_style.strip() or "自然、稳定地保持角色口吻。",
    ]
    examples = parse_examples(card.example_dialogues)
    if examples:
        parts.extend(["", "风格示例:"])
        parts.extend(f"- {example}" for example in examples[:6])
    if card.world_info:
        parts.extend(["", "共享背景:", card.world_info.strip()])
    parts.extend(["", persona_output_rules()])
    return "\n".join(parts)


def persona_output_rules() -> str:
    return "\n".join(
        [
            "记忆维护规则:",
            "- 新的、值得长期记住的用户事实用 add_note。",
            "- 旧事实发生变化时用 update_note 覆盖旧条目，不要重复保留过期状态。",
            "- 不重要或过期内容用 delete_note。",
            "",
            "对话输出规则:",
            "- 记忆检索、记忆更新、工具调用都是后台动作，绝不能在回复中提到。",
            "- 不要说“我看了记忆”“记忆已更新”“已记录”“不用动”“工具调用完成”等出戏内容。",
            "- 回复只保留角色本人会自然说出口的话。",
            "- 直接生成 JSON 字符串数组，例如 [\"第一条\", \"第二条\"]。",
            "- 默认 1 条；只有自然像聊天追加时才 2-3 条。每条必须是独立 beat，不要把长段按标点机械切碎。",
        ]
    )


def parse_examples(raw: str | None) -> list[str]:
    if not raw:
        return []
    try:
        value = json.loads(raw)
    except json.JSONDecodeError:
        return [line.strip() for line in raw.splitlines() if line.strip()]
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    return []


def run_persona_agent(
    session: Session,
    persona: Persona,
    notes: list[PersonaNote],
    state: PersonaState | None,
    card: PersonaCard | None,
    recent: list[Message],
    user_content: str,
    persona_names: dict[int, str],
) -> tuple[list[str], list[dict[str, Any]]]:
    model = resolve_model(session, persona.model_role, persona.model_override)
    latest_user_message = next(
        (message for message in reversed(recent) if message.author_type == "human"),
        None,
    )
    image_data_url = image_message_to_data_url(latest_user_message) if latest_user_message else None
    if image_data_url:
        model = resolve_model(session, "vision") or model
    if not provider_ready(model):
        return fallback_persona(persona, notes, user_content)

    system = f"""{format_persona_card(persona, card)}

当前检索到的私有记忆:
{format_notes(notes)}

你和用户的关系状态:
{relationship_summary(state)}

{build_time_context(recent, persona)}

最近频道消息:
{format_recent_messages(recent, persona_names)}
"""
    messages: list[dict[str, Any]] = [
        {"role": "system", "content": system},
        {
            "role": "user",
            "content": user_message_content(user_content, image_data_url),
        },
    ]
    try:
        text, calls = run_tool_loop(
            model=model,
            messages=messages,
            tools=PERSONA_NOTE_TOOLS,
            on_tool_call=lambda _name, _args: "ok",
            max_tokens=800,
        )
    except Exception:
        if image_data_url:
            return ["图我收到了，但当前图片模型没接通。", "你先把图里关键内容说一句，我就能接着聊。"], []
        raise
    return parse_reply_segments(text) or ["我听到了。"], calls


def user_message_content(user_content: str, image_data_url: str | None):
    text = (
        f"用户刚刚说: {user_content or '（用户发送了一张图片）'}\n"
        "请自然回复。需要维护记忆时只调用工具，不要在正文里描述记忆或工具动作。"
    )
    if not image_data_url:
        return text
    return [
        {"type": "text", "text": text},
        {"type": "image_url", "image_url": {"url": image_data_url}},
    ]


def fallback_persona(
    persona: Persona,
    notes: list[PersonaNote],
    user_content: str,
) -> tuple[list[str], list[dict[str, Any]]]:
    text = user_content.lower().replace(" ", "")
    calls: list[dict[str, Any]] = []

    if persona.name == "兄弟":
        if "跑了pb" in text or "跑了PB" in user_content:
            existing = next((n for n in notes if "健身" in n.content), None)
            if existing:
                calls.append(
                    {
                        "name": "update_note",
                        "input": {"note_id": existing.id, "content": "兄弟今天跑了 PB"},
                    }
                )
            else:
                calls.append({"name": "add_note", "input": {"content": "兄弟今天跑了 PB"}})
            return ["可以啊兄弟，跑 PB 这事儿值得吹一晚上。"], calls
        if "两点" in user_content and not any("健身" in n.content for n in notes):
            calls.append({"name": "add_note", "input": {"content": "哥们下午两点要去健身"}})
            return ["下午两点开练是吧。", "别到点又说先躺五分钟。"], calls
        if "健身" in user_content:
            return ["行啊，准备去健身了？", "别光嘴上燃，去了才算。"], calls
        return [f"懂你意思，{user_content} 这事儿咱慢慢捋。"], calls

    if "研究设计" in user_content or "怎么改" in user_content:
        return ["建议先明确研究问题。", "再检查变量定义、样本选择与识别策略是否一致。"], calls
    return ["我建议先把问题表述得更精确，再决定下一步方法。"], calls


def parse_reply_segments(raw: str | None) -> list[str]:
    text = (raw or "").strip()
    if not text:
        return []
    try:
        value = json.loads(text)
    except json.JSONDecodeError:
        value = None
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if isinstance(value, dict) and isinstance(value.get("messages"), list):
        return [str(item).strip() for item in value["messages"] if str(item).strip()]
    paragraphs = [part.strip() for part in text.split("\n\n") if part.strip()]
    return paragraphs if paragraphs else [text]
