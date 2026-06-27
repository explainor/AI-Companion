import json
import os
from typing import Any, Callable, Optional

from litellm import completion


def provider_ready(model: Optional[str]) -> bool:
    if os.getenv("LLM_FORCE_FALLBACK") == "1":
        return False
    if not model:
        return False
    if model.startswith("ollama/"):
        return True
    env_keys = [
        "OPENAI_API_KEY",
        "DEEPSEEK_API_KEY",
        "ANTHROPIC_API_KEY",
        "OPENROUTER_API_KEY",
        "MOONSHOT_API_KEY",
        "ZHIPUAI_API_KEY",
    ]
    return any(os.getenv(key) for key in env_keys)


def tool_call_name(call: Any) -> str:
    return call.function.name if hasattr(call, "function") else call["function"]["name"]


def tool_call_args(call: Any) -> dict[str, Any]:
    raw = call.function.arguments if hasattr(call, "function") else call["function"]["arguments"]
    if isinstance(raw, dict):
        return raw
    if not raw:
        return {}
    return json.loads(raw)


def tool_call_id(call: Any) -> str:
    return call.id if hasattr(call, "id") else call["id"]


def run_tool_loop(
    model: str,
    messages: list[dict[str, Any]],
    tools: list[dict[str, Any]],
    on_tool_call: Callable[[str, dict[str, Any]], str],
    max_tokens: int,
    max_rounds: int = 4,
) -> tuple[str, list[dict[str, Any]]]:
    final_text = ""
    calls: list[dict[str, Any]] = []
    for _ in range(max_rounds):
        response = completion(
            model=model,
            messages=messages,
            tools=tools,
            max_tokens=max_tokens,
        )
        message = response.choices[0].message
        content = message.content or ""
        final_text = content.strip() or final_text
        messages.append(message.model_dump(exclude_none=True))
        tool_calls = list(message.tool_calls or [])
        if not tool_calls:
            break
        for call in tool_calls:
            name = tool_call_name(call)
            args = tool_call_args(call)
            calls.append({"name": name, "input": args})
            result = on_tool_call(name, args)
            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": tool_call_id(call),
                    "content": result,
                }
            )
    return final_text, calls
