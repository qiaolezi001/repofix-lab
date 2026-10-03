"""Scripted offline demo and a documented Chat Completions tool adapter."""

import json
import re
from typing import Any
from urllib.parse import urlparse

import httpx

from repofix.config import Settings
from repofix.models import Action, Reply


class ProviderError(RuntimeError):
    pass


def redact(value: Any, secret: str = "") -> Any:
    if isinstance(value, str):
        if secret:
            value = value.replace(secret, "[REDACTED]")
        return re.sub(r"\bsk-[A-Za-z0-9_-]{12,}", "[REDACTED]", value)
    if isinstance(value, list):
        return [redact(item, secret) for item in value]
    if isinstance(value, dict):
        return {key: redact(item, secret) for key, item in value.items()}
    return value


def tool_reply(name: str, arguments: dict[str, Any], index: int, summary: str) -> Reply:
    call_id = f"mock-{index}"
    message = {
        "role": "assistant",
        "content": summary,
        "tool_calls": [
            {
                "id": call_id,
                "type": "function",
                "function": {"name": name, "arguments": json.dumps(arguments)},
            }
        ],
    }
    return Reply(message, [Action(call_id, name, arguments)], summary, {"mock": True})


class MockProvider:
    """A transparent hand-scripted pagination demonstration, never a benchmark solver."""

    def complete(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
        max_tokens: int = 1800,
        timeout: float = 30,
    ) -> Reply:
        if tools and all(tool["function"]["name"] == "apply_patch" for tool in tools):
            if "start = (page - 1) * page_size + 1" in json.dumps(messages):
                return tool_reply(
                    "apply_patch",
                    {
                        "edits": [
                            {
                                "path": "pagination.py",
                                "old": "start = (page - 1) * page_size + 1",
                                "new": "start = (page - 1) * page_size",
                            }
                        ]
                    },
                    0,
                    "MOCK: dedicated fixture patch from provided source; no model accuracy claim.",
                )
            summary = "MOCK baseline has no scripted patch for this repository; real model accuracy remains unmeasured."
            return Reply(
                {"role": "assistant", "content": summary}, summary=summary, usage={"mock": True}
            )
        observations = [m for m in messages if m["role"] == "tool"]
        step = len(observations)
        if step == 0:
            return tool_reply(
                "search_code",
                {"query": "paginate page page_size", "limit": 4},
                step,
                "MOCK: retrieve pagination evidence using the real search tool.",
            )
        if step == 1:
            return tool_reply(
                "read_file",
                {"path": "pagination.py", "start_line": 1, "end_line": 100},
                step,
                "MOCK: inspect the demo source before proposing an edit.",
            )
        content = json.dumps(observations, ensure_ascii=False)
        if step == 2 and "start = (page - 1) * page_size + 1" in content:
            return tool_reply(
                "apply_patch",
                {
                    "edits": [
                        {
                            "path": "pagination.py",
                            "old": "start = (page - 1) * page_size + 1",
                            "new": "start = (page - 1) * page_size",
                        }
                    ]
                },
                step,
                "MOCK: remove the seeded offset in the dedicated demo fixture.",
            )
        if step == 3:
            return tool_reply(
                "run_tests", {}, step, "MOCK: request the complete public test suite in Docker."
            )
        summary = (
            "Scripted mock workflow finished. Inspect real tool evidence and verification status. "
            "This is not evidence of model repair accuracy."
        )
        return Reply(
            {"role": "assistant", "content": summary}, summary=summary, usage={"mock": True}
        )


class LiveProvider:
    def __init__(self, settings: Settings, transport: httpx.BaseTransport | None = None):
        if not settings.api_key or not settings.model:
            raise ProviderError(
                "Configure REPOFIX_API_KEY and REPOFIX_MODEL locally before live mode."
            )
        parsed = urlparse(settings.base_url)
        if parsed.scheme != "https" and not (
            parsed.scheme == "http" and parsed.hostname in {"localhost", "127.0.0.1", "::1"}
        ):
            raise ProviderError("Model endpoint requires HTTPS, except a local development server.")
        if parsed.username or parsed.password or parsed.query or parsed.fragment:
            raise ProviderError(
                "Model endpoint must not contain credentials, queries or fragments."
            )
        if settings.proxy_url:
            proxy = urlparse(settings.proxy_url)
            if (
                proxy.scheme not in {"http", "https"}
                or not proxy.hostname
                or proxy.username
                or proxy.password
                or proxy.query
                or proxy.fragment
            ):
                raise ProviderError(
                    "Explicit model proxy requires an HTTP(S) URL without credentials."
                )
        self.settings = settings
        self.transport = transport

    def complete(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
        max_tokens: int = 1800,
        timeout: float = 30,
    ) -> Reply:
        body: dict[str, Any] = {
            "model": self.settings.model,
            "messages": messages,
            "max_completion_tokens": max_tokens,
        }
        if tools:
            body.update(tools=tools, tool_choice="auto", parallel_tool_calls=False)
        try:
            with httpx.Client(
                transport=self.transport,
                timeout=timeout,
                trust_env=False,
                proxy=self.settings.proxy_url or None,
            ) as client:
                response = client.post(
                    self.settings.base_url + "/chat/completions",
                    json=body,
                    headers={"Authorization": "Bearer " + self.settings.api_key},
                )
            if response.status_code >= 400:
                raise ProviderError(
                    f"Model endpoint returned HTTP {response.status_code}; check protocol/model compatibility."
                )
            data = response.json()
            message = data["choices"][0]["message"]
            actions = []
            for call in message.get("tool_calls") or []:
                args = json.loads(call["function"]["arguments"])
                if not isinstance(args, dict):
                    raise ValueError("Tool arguments must be an object")
                actions.append(Action(call["id"], call["function"]["name"], args))
            if len(actions) > 1:
                raise ValueError("Provider ignored parallel_tool_calls=false; expected one action")
            clean_message = {"role": "assistant", "content": message.get("content") or ""}
            if message.get("tool_calls"):
                clean_message["tool_calls"] = message["tool_calls"]
            usage = data.get("usage") or {}
            if not isinstance(usage, dict):
                usage = {}
            return Reply(clean_message, actions, message.get("content") or "", usage)
        except (httpx.HTTPError, ValueError, KeyError, TypeError, IndexError) as exc:
            raise ProviderError(
                f"Invalid or unavailable model response ({type(exc).__name__})."
            ) from None

    def check(self) -> dict[str, Any]:
        schema = {
            "type": "function",
            "function": {
                "name": "echo",
                "description": "Echo a value.",
                "parameters": {
                    "type": "object",
                    "properties": {"text": {"type": "string"}},
                    "required": ["text"],
                    "additionalProperties": False,
                },
            },
        }
        reply = self.complete(
            [{"role": "user", "content": "Call echo with text repofix-probe."}],
            [schema],
            max_tokens=128,
        )
        if (
            not reply.actions
            or reply.actions[0].name != "echo"
            or reply.actions[0].arguments != {"text": "repofix-probe"}
        ):
            raise ProviderError("Endpoint did not produce a compatible function call.")
        action = reply.actions[0]
        final = self.complete(
            [
                {"role": "user", "content": "Call echo with text repofix-probe."},
                reply.message,
                {"role": "tool", "tool_call_id": action.id, "content": '{"text":"repofix-probe"}'},
            ],
            [],
            max_tokens=128,
        )
        if final.actions or not final.summary:
            raise ProviderError("Endpoint did not accept the tool-result round trip.")
        return {
            "compatible": True,
            "model": self.settings.model,
            "calls": 2,
            "usage": [reply.usage, final.usage],
            "cost_usd": None,
        }
