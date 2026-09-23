"""Normalize Responses history before LiteLLM sends Chat Completions requests."""

from __future__ import annotations

from typing import Any

_TARGET = (
    "litellm.responses.litellm_completion_transformation.transformation"
)


def _get(message: Any, key: str, default: Any = None) -> Any:
    if isinstance(message, dict):
        return message.get(key, default)
    return getattr(message, key, default)


def _set(message: Any, key: str, value: Any) -> None:
    if isinstance(message, dict):
        message[key] = value
    else:
        setattr(message, key, value)


def _content_text(content: Any) -> Any:
    if not content:
        return None
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[Any] = []
        for item in content:
            if isinstance(item, dict):
                text = item.get("text")
                if text:
                    parts.append(text)
            else:
                text = getattr(item, "text", None)
                if text:
                    parts.append(text)
        return "\n".join(str(part) for part in parts) or None
    return str(content)


def _merge_content(current: Any, extra: Any) -> Any:
    if not extra:
        return current
    if not current:
        return extra
    if isinstance(current, str) and isinstance(extra, str):
        return f"{current}\n{extra}"
    if isinstance(current, list) and isinstance(extra, list):
        return current + extra
    return f"{current}\n{extra}"


def _has_tool_calls(message: Any) -> bool:
    return bool(_get(message, "tool_calls")) and _get(message, "role") == "assistant"


def _normalize(messages: Any) -> Any:
    if not isinstance(messages, list):
        return messages

    normalized = list(messages)
    # DeepSeek thinking mode requires the reasoning_content field on EVERY
    # assistant turn in the conversation history, not only those that contain
    # tool_calls. Responses -> Chat conversion strips reasoning items, so we
    # inject an empty reasoning_content for any assistant message that lost
    # it during transformation. The upstream accepts "" as "no reasoning".
    for message in normalized:
        if _get(message, "role") == "assistant":
            if _get(message, "reasoning_content") is None:
                _set(message, "reasoning_content", "")

    i = 0
    while i < len(normalized):
        current = normalized[i]
        if not _has_tool_calls(current):
            i += 1
            continue

        # Chat Completions requires the tool result immediately after the
        # assistant tool-call turn. Responses permits assistant items between
        # a function_call and its function_call_output, so fold those items
        # into the preceding assistant turn.
        j = i + 1
        while j < len(normalized):
            next_message = normalized[j]
            role = _get(next_message, "role")
            if role == "tool":
                break
            if role != "assistant" or _has_tool_calls(next_message):
                break
            extra = _get(next_message, "content")
            if extra:
                _set(current, "content", _merge_content(_get(current, "content"), extra))
            normalized.pop(j)

        i += 1

    return normalized


def _install() -> None:
    try:
        module = __import__(_TARGET, fromlist=["LiteLLMCompletionResponsesConfig"])
        config = module.LiteLLMCompletionResponsesConfig
        original = config._transform_response_input_param_to_chat_completion_message
    except Exception:
        return

    if getattr(original, "__responses_history_patch__", False):
        return

    def patched(*args: Any, **kwargs: Any) -> Any:
        return _normalize(original(*args, **kwargs))

    patched.__responses_history_patch__ = True
    config._transform_response_input_param_to_chat_completion_message = staticmethod(patched)


_install()
