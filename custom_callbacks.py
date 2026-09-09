"""
LiteLLM Proxy 友好错误回调：把上游晦涩的报错翻译成可读的中文提示。

原理：请求失败时 async_post_call_failure_hook 拿到原始异常，识别出
「余额不足 / Key 无效 / 限流 / 模型不存在 / 上下文超限 / 超时 / 上游不可达」等
常见模式，改写成「模型名 + 原因 + 上游 + 建议」抛回客户端；
未识别的错误一律原样透传，不影响排查。

挂载方式：docker-compose.yml 把本文件映射到 /app/custom_callbacks.py，
config.yaml 的 litellm_settings.callbacks 引用 custom_callbacks.FriendlyErrorHandler。
"""

from typing import Any, Optional

from fastapi import HTTPException
from litellm.integrations.custom_logger import CustomLogger

# 识别规则：(HTTP 状态码, 中文原因, 建议操作, 关键词元组)。
# 关键词对「异常类名 + 异常 message」整体小写后做子串匹配，顺序敏感——
# 余额类必须放最前：第三方代理常用 403/401 携带 INSUFFICIENT_BALANCE，
# 放在鉴权规则后面会被误判成 Key 无效。
_RULES = [
    (
        402,
        "上游账户余额不足",
        "请到上游平台充值，或临时改用其它模型组。",
        (
            "insufficient_balance",
            "insufficient account balance",
            "insufficient_quota",
            "exceeded your current quota",
            "arrearage",
            "余额不足",
        ),
    ),
    (
        403,
        "上游 API Key 无效或无权限",
        "请检查 .env 里对应的 XXX_API_KEY 是否填对，改完执行 npm run env:apply。",
        (
            "authenticationerror",
            "permissiondeniederror",
            "invalid_api_key",
            "incorrect api key",
            "invalid x-api-key",
            "api key not valid",
            "authentication_error",
            "unauthorized",
        ),
    ),
    (
        404,
        "模型不存在或未在网关注册",
        "请对照 config.yaml 的 model_list 检查模型名拼写。",
        (
            "notfounderror",
            "model_not_found",
            "model not found",
            "does not exist",
            "no such model",
        ),
    ),
    (
        429,
        "上游限流（rate limit）",
        "请稍后重试，或给该模型组配置 fallback。",
        (
            "ratelimiterror",
            "rate limit",
            "rate_limit_error",
            "too many requests",
        ),
    ),
    (
        400,
        "上下文长度超限",
        "请精简对话内容（清空历史 / 缩小输入）后重试。",
        (
            "contextwindowexceedederror",
            "context length exceeded",
            "maximum context length",
        ),
    ),
    (
        504,
        "上游超时",
        "可重试；频繁出现的话在 config.yaml 调大 timeout。",
        ("timeout", "timed out", "request timed out"),
    ),
    (
        502,
        "上游服务不可用或连接失败",
        "可重试；持续出现说明该上游故障，请改用其它模型组。",
        (
            "apiconnectionerror",
            "connection error",
            "connection refused",
            "service unavailable",
            "bad gateway",
            "internalservererror",
            "server_error",
            "overloaded",
        ),
    ),
]

# 模型名前缀 → 上游提示，与 config.yaml 的 model_list 保持同步（增删模型时同步这里）。
_PROVIDER_HINTS = [
    ("gpt-5", "GaogeAI 代理（GAOGEAII_API_KEY）"),
    ("gpt-image", "GaogeAI 代理（GAOGEAII_API_KEY）"),
    ("gpt-4o", "OpenAI（OPENAI_API_KEY）"),
    ("claude", "Anthropic（ANTHROPIC_API_KEY）"),
    ("deepseek", "DeepSeek（DEEPSEEK_API_KEY）"),
    ("gemini", "Gemini（GEMINI_API_KEY）"),
    ("minimax", "MiniMax（MINIMAX_API_KEY）"),
    ("glm", "智谱（ZHIPU_API_KEY）"),
    ("qwen", "DashScope（DASHSCOPE_API_KEY）"),
    ("gpt-", "OpenAI（OPENAI_API_KEY）"),
]


def _provider_hint(model: str) -> str:
    lowered = model.lower()
    for prefix, hint in _PROVIDER_HINTS:
        if lowered.startswith(prefix):
            return hint
    return "未知上游"


def _compact(text: str) -> str:
    return " ".join(text.split())


class FriendlyErrorHandler(CustomLogger):
    """仅在请求失败时介入；成功的请求零开销。"""

    async def async_post_call_failure_hook(self, *args: Any, **kwargs: Any):
        # 兼容不同版本 LiteLLM 的签名：
        #   新版 (user_api_key_dict, request_data, original_exception)
        #   旧版 (request_data, original_exception)
        request_data = kwargs.get("request_data") or {}
        original_exception: Optional[Exception] = kwargs.get("original_exception")
        for value in args:
            if isinstance(value, Exception) and original_exception is None:
                original_exception = value
            elif isinstance(value, dict) and not request_data:
                request_data = value
        if original_exception is None or isinstance(original_exception, HTTPException):
            return

        haystack = "{} {} {}".format(
            type(original_exception).__name__,
            getattr(original_exception, "message", "") or "",
            original_exception,
        ).lower()

        for status_code, reason, advice, patterns in _RULES:
            if any(pattern in haystack for pattern in patterns):
                model = str(request_data.get("model") or "未知模型")
                # 保留一小段原始报错便于排查；压掉换行避免客户端日志错乱。
                origin = _compact(str(original_exception))[:160]
                raise HTTPException(
                    status_code=status_code,
                    detail=(
                        f"【{model}】{reason}。上游：{_provider_hint(model)}。"
                        f"{advice} 原始错误：{origin}"
                    ),
                )
        # 未识别：不抛出，走 LiteLLM 默认错误处理，保持原有报错形态


# 注意：LiteLLM 的 get_instance_fn 只做 getattr、不会实例化类，
# 这里必须导出模块级实例，config.yaml 引用 custom_callbacks.friendly_error_handler。
friendly_error_handler = FriendlyErrorHandler()


class ToolCallIdPatcher(CustomLogger):
    """修补 LiteLLM 1.97.0 Responses → Chat Completions 翻译 bug。

    两个面：
    1. `async_pre_call_deployment_hook`（若被 LiteLLM 调用）：给缺 `tool_call_id`
       的 `role=tool` 消息按顺序回填前面最近的 `assistant.tool_calls[].id`。
    2. 模块级 monkey-patch（本文件被 import 时执行，见文件末尾）：直接包一层
       `transform_responses_api_request_to_chat_completion_request`，在翻译产物上
       合并「assistant(tool_calls) 后面紧邻的纯 assistant 文字消息」。

    背景：ZCode / Codex 走 Responses API，会发送 `function_call → message
    (output_text) → function_call_output` 这种顺序；LiteLLM 1.97.0 转换时把它
    转成两条独立的 assistant 消息（一条带 tool_calls、一条纯文字），违反 OpenAI
    规范「assistant.tool_calls 必须被 tool 消息紧跟」。DeepSeek 严格校验，直接 400。
    """

    async def async_pre_call_deployment_hook(
        self, kwargs: dict, call_type: Any
    ) -> Optional[dict]:
        messages = kwargs.get("messages")
        if not messages or not isinstance(messages, list):
            return None

        pending: list = []
        for msg in messages:
            if not isinstance(msg, dict):
                continue
            role = msg.get("role")
            if role == "assistant":
                tool_calls = msg.get("tool_calls") or []
                if isinstance(tool_calls, list):
                    for tc in tool_calls:
                        if isinstance(tc, dict) and tc.get("id"):
                            pending.append(tc["id"])
            elif role == "tool":
                # tool 消息缺 tool_call_id 时，按排队顺序回填最近一个
                if not msg.get("tool_call_id") and pending:
                    msg["tool_call_id"] = pending.pop(0)

        return kwargs


tool_call_id_patcher = ToolCallIdPatcher()


def _merge_stray_assistant(messages: list) -> list:
    """把 assistant(tool_calls) 后面紧邻的纯 assistant 消息合并进前者。

    LiteLLM 1.97.0 会把 Responses API 的 `function_call → message → function_call_output`
    转成两条独立 assistant 消息，导致 tool_calls 后不紧跟 tool 消息。
    合并后序列变为 assistant(tool_calls + 合并的 content) → tool(...)，符合 OpenAI 规范。
    对已经合规的序列是 no-op。
    """
    if not isinstance(messages, list):
        return messages
    out: list = []
    i = 0
    while i < len(messages):
        m = messages[i]
        if isinstance(m, dict) and m.get("role") == "assistant" and m.get("tool_calls"):
            j = i + 1
            while j < len(messages):
                nxt = messages[j]
                if not isinstance(nxt, dict) or nxt.get("role") != "assistant" or nxt.get("tool_calls"):
                    break
                nc = nxt.get("content")
                if nc:
                    cur = m.get("content")
                    if not cur:
                        m["content"] = nc
                    elif isinstance(cur, str) and isinstance(nc, str):
                        m["content"] = cur + "\n" + nc
                    elif isinstance(cur, list) and isinstance(nc, list):
                        m["content"] = cur + nc
                j += 1
            out.append(m)
            i = j
            continue
        out.append(m)
        i += 1
    return out


def _patch_litellm_responses_translation() -> bool:
    """Monkey-patch LiteLLM 的 Responses → ChatCompletions 翻译函数。

    返回 True 表示 patch 成功；失败则静默返回 False（LiteLLM 版本升级改了
    函数签名时，本 patch 自动失效，用户需按错误提示重新适配）。
    """
    try:
        from litellm.responses.litellm_completion_transformation.transformation import (
            LiteLLMCompletionResponsesConfig,
        )
    except Exception:
        return False
    orig = getattr(
        LiteLLMCompletionResponsesConfig,
        "transform_responses_api_request_to_chat_completion_request",
        None,
    )
    if orig is None:
        return False

    def patched(*args: Any, **kwargs: Any):
        req = orig(*args, **kwargs)
        if isinstance(req, dict):
            msgs = req.get("messages")
            if isinstance(msgs, list):
                req["messages"] = _merge_stray_assistant(msgs)
        return req

    LiteLLMCompletionResponsesConfig.transform_responses_api_request_to_chat_completion_request = (
        staticmethod(patched)
    )
    return True


# 模块 import 时立即生效；本文件通过 config.yaml 的 callbacks 引用被 LiteLLM 加载。
_patch_litellm_responses_translation()
