import os
from typing import Any

from litellm import completion

from .models import Message, Persona, PersonaNote, Todo

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

STEWARD_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "create_todo",
            "description": "Create a pending todo from the user's stated intention.",
            "parameters": {
                "type": "object",
                "properties": {
                    "title": {"type": "string"},
                    "due_time": {"type": ["string", "null"]},
                },
                "required": ["title", "due_time"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "update_todo",
            "description": "Update a pending todo's title or due time by id.",
            "parameters": {
                "type": "object",
                "properties": {
                    "todo_id": {"type": "integer"},
                    "title": {"type": ["string", "null"]},
                    "due_time": {"type": ["string", "null"]},
                },
                "required": ["todo_id", "title", "due_time"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "complete_todo",
            "description": "Mark a pending todo complete and optionally record its result.",
            "parameters": {
                "type": "object",
                "properties": {
                    "todo_id": {"type": "integer"},
                    "result": {"type": ["string", "null"]},
                },
                "required": ["todo_id", "result"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "write_memo",
            "description": "Write an objective long-term memo in first-person steward voice.",
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
            "name": "list_todos",
            "description": "List current pending todos.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
]


def model_name(alias: str) -> str | None:
    return os.getenv(alias) or None


def model_enabled(alias: str) -> bool:
    return bool(model_name(alias))


def format_recent_messages(recent: list[Message], persona_names: dict[int, str]) -> str:
    lines = []
    for message in recent:
        if message.sender == "user":
            who = "用户"
        else:
            who = persona_names.get(message.persona_id or 0, "角色")
        lines.append(f"{who}: {message.content}")
    return "\n".join(lines)


def format_notes(notes: list[PersonaNote]) -> str:
    if not notes:
        return "（空）"
    return "\n".join(f"- id={note.id}: {note.content}" for note in notes)


def format_todos(todos: list[Todo]) -> str:
    if not todos:
        return "（无未完成事项）"
    return "\n".join(
        f"- id={todo.id}: {todo.title}; due_time={todo.due_time or '未定'}"
        for todo in todos
    )


def _tool_call_name(call: Any) -> str:
    return call.function.name if hasattr(call, "function") else call["function"]["name"]


def _tool_call_args(call: Any) -> dict[str, Any]:
    import json

    raw = call.function.arguments if hasattr(call, "function") else call["function"]["arguments"]
    if isinstance(raw, dict):
        return raw
    if not raw:
        return {}
    return json.loads(raw)


def _tool_call_id(call: Any) -> str:
    return call.id if hasattr(call, "id") else call["id"]


def run_persona_agent(
    persona: Persona,
    notes: list[PersonaNote],
    recent: list[Message],
    user_content: str,
    persona_names: dict[int, str],
) -> tuple[str, list[dict[str, Any]]]:
    model = model_name(persona.model)
    if not model:
        return fallback_persona(persona, notes, user_content)

    system = f"""{persona.system_prompt}

当前你的私有记忆本:
{format_notes(notes)}

最近频道消息:
{format_recent_messages(recent, persona_names)}
"""
    messages: list[dict[str, Any]] = [
        {"role": "system", "content": system},
        {
            "role": "user",
            "content": f"用户刚刚说: {user_content}\n请自然回复，并在需要时调用记忆工具。",
        }
    ]
    tool_calls: list[dict[str, Any]] = []
    final_text = ""

    for _ in range(4):
        response = completion(
            model=model,
            messages=messages,
            tools=PERSONA_NOTE_TOOLS,
            max_tokens=800,
        )
        message = response.choices[0].message
        content = message.content or ""
        final_text = content.strip() or final_text
        tool_calls_response = message.tool_calls or []
        messages.append(message.model_dump(exclude_none=True))
        uses = list(tool_calls_response)
        if not uses:
            break
        for use in uses:
            name = _tool_call_name(use)
            args = _tool_call_args(use)
            tool_calls.append({"name": name, "input": args})
            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": _tool_call_id(use),
                    "content": "ok",
                }
            )

    return final_text or "我听到了。", tool_calls


def run_steward_agent(
    steward: Persona,
    open_todos: list[Todo],
    recent: list[Message],
    user_content: str,
    persona_names: dict[int, str],
) -> list[dict[str, Any]]:
    model = model_name(steward.model)
    if not model:
        return fallback_steward(open_todos, user_content)

    system = f"""{steward.system_prompt}

当前未完成待办:
{format_todos(open_todos)}

最近频道消息:
{format_recent_messages(recent, persona_names)}
"""
    messages: list[dict[str, Any]] = [
        {"role": "system", "content": system},
        {
            "role": "user",
            "content": f"用户刚刚说: {user_content}\n请只在需要时调用工具，不要输出聊天回复。",
        }
    ]
    tool_calls: list[dict[str, Any]] = []

    for _ in range(4):
        response = completion(
            model=model,
            messages=messages,
            tools=STEWARD_TOOLS,
            max_tokens=600,
        )
        message = response.choices[0].message
        messages.append(message.model_dump(exclude_none=True))
        uses = list(message.tool_calls or [])
        if not uses:
            break
        for use in uses:
            name = _tool_call_name(use)
            args = _tool_call_args(use)
            if name == "list_todos":
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": _tool_call_id(use),
                        "content": format_todos(open_todos),
                    }
                )
            else:
                tool_calls.append({"name": name, "input": args})
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": _tool_call_id(use),
                        "content": "ok",
                    }
                )

    return tool_calls


def fallback_persona(
    persona: Persona,
    notes: list[PersonaNote],
    user_content: str,
) -> tuple[str, list[dict[str, Any]]]:
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
            return "可以啊兄弟，跑 PB 这事儿值得吹一晚上。", calls
        if "两点" in user_content and any("健身" in n.content for n in notes) is False:
            calls.append({"name": "add_note", "input": {"content": "哥们下午两点要去健身"}})
            return "下午两点开练是吧，别到点又说先躺五分钟。", calls
        if "健身" in user_content:
            return "行啊，准备去健身了？别光嘴上燃，去了才算。", calls
        return f"懂你意思，{user_content} 这事儿咱慢慢捋。", calls

    if "研究设计" in user_content or "怎么改" in user_content:
        return "建议先明确研究问题，再检查变量定义、样本选择与识别策略是否一致。", calls
    return "我建议先把问题表述得更精确，再决定下一步方法。", calls


def fallback_steward(open_todos: list[Todo], user_content: str) -> list[dict[str, Any]]:
    text = user_content.lower().replace(" ", "")
    calls: list[dict[str, Any]] = []
    gym = next((todo for todo in open_todos if "健身" in todo.title), None)

    if "跑了pb" in text or "跑了PB" in user_content:
        if gym:
            calls.append(
                {
                    "name": "complete_todo",
                    "input": {"todo_id": gym.id, "result": "跑了 PB"},
                }
            )
        calls.append(
            {
                "name": "write_memo",
                "input": {"content": "我记录到用户今日完成健身，并跑出个人最佳。"},
            }
        )
        return calls

    if "两点" in user_content:
        if gym:
            calls.append(
                {
                    "name": "update_todo",
                    "input": {"todo_id": gym.id, "title": "健身", "due_time": "下午两点"},
                }
            )
        else:
            calls.append(
                {
                    "name": "create_todo",
                    "input": {"title": "健身", "due_time": "下午两点"},
                }
            )
        return calls

    if "健身" in user_content:
        calls.append(
            {
                "name": "create_todo",
                "input": {"title": "健身", "due_time": None},
            }
        )

    return calls
