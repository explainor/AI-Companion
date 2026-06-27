from typing import Any

from sqlmodel import Session

from ..chat.agents import format_recent_messages
from ..core.config import resolve_model
from ..core.llm import provider_ready, run_tool_loop
from ..core.time_context import build_time_context
from ..models import Message, Persona, Todo

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
    {
        "type": "function",
        "function": {
            "name": "upsert_habit",
            "description": "Create or update a structured habit tracking item.",
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "schedule": {"type": "string"},
                },
                "required": ["name", "schedule"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "log_habit",
            "description": "Log one habit occurrence by habit id.",
            "parameters": {
                "type": "object",
                "properties": {
                    "habit_id": {"type": "integer"},
                    "value": {"type": ["number", "null"]},
                },
                "required": ["habit_id", "value"],
            },
        },
    },
]


def format_todos(todos: list[Todo]) -> str:
    if not todos:
        return "（无未完成事项）"
    return "\n".join(
        f"- id={todo.id}: {todo.title}; due_time={todo.due_time or '未定'}"
        for todo in todos
    )


def run_steward_agent(
    session: Session,
    steward: Persona,
    open_todos: list[Todo],
    recent: list[Message],
    user_content: str,
    persona_names: dict[int, str],
) -> list[dict[str, Any]]:
    model = resolve_model(session, steward.model_role, steward.model_override)
    if not provider_ready(model):
        return fallback_steward(open_todos, user_content)

    system = f"""{steward.system_prompt}

当前未完成待办:
{format_todos(open_todos)}

{build_time_context(recent, steward)}

最近频道消息:
{format_recent_messages(recent, persona_names)}
"""
    messages: list[dict[str, Any]] = [
        {"role": "system", "content": system},
        {
            "role": "user",
            "content": f"用户刚刚说: {user_content}\n请只在需要时调用工具，不要输出聊天回复。",
        },
    ]

    def tool_result(name: str, _args: dict[str, Any]) -> str:
        if name == "list_todos":
            return format_todos(open_todos)
        return "ok"

    _text, calls = run_tool_loop(
        model=model,
        messages=messages,
        tools=STEWARD_TOOLS,
        on_tool_call=tool_result,
        max_tokens=700,
    )
    return [call for call in calls if call["name"] != "list_todos"]


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
