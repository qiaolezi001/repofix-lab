import json

import httpx
import pytest

from repofix.config import Settings
from repofix.providers import LiveProvider, ProviderError, redact


def test_live_protocol_tool_roundtrip_without_network():
    requests = []

    def handle(request):
        body = json.loads(request.content)
        requests.append(body)
        assert request.headers["Authorization"] == "Bearer fake-test-key"
        message = {"role": "assistant", "content": "probe complete"}
        if len(requests) == 1:
            message = {
                "role": "assistant",
                "content": None,
                "tool_calls": [
                    {
                        "id": "probe-1",
                        "type": "function",
                        "function": {"name": "echo", "arguments": '{"text":"repofix-probe"}'},
                    }
                ],
            }
            assert body["parallel_tool_calls"] is False
        else:
            assert body["messages"][-1]["tool_call_id"] == "probe-1"
        return httpx.Response(
            200,
            json={
                "choices": [{"message": message}],
                "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
            },
        )

    settings = Settings(api_key="fake-test-key", model="protocol-fixture")
    result = LiveProvider(settings, httpx.MockTransport(handle)).check()
    assert result["compatible"] and result["calls"] == 2
    assert len(requests) == 2


@pytest.mark.parametrize(
    "response",
    [
        {"choices": []},
        {
            "choices": [
                {
                    "message": {
                        "tool_calls": [
                            {"id": "a", "function": {"name": "echo", "arguments": "oops"}}
                        ]
                    }
                }
            ]
        },
    ],
)
def test_malformed_provider_response(response):
    provider = LiveProvider(
        Settings(api_key="fake", model="fake"),
        httpx.MockTransport(lambda request: httpx.Response(200, json=response)),
    )
    with pytest.raises(ProviderError, match="Invalid"):
        provider.complete([], [])


def test_error_body_cannot_leak_credentials():
    provider = LiveProvider(
        Settings(api_key="fake-secret-key", model="fake"),
        httpx.MockTransport(lambda request: httpx.Response(401, text="fake-secret-key")),
    )
    with pytest.raises(ProviderError) as info:
        provider.complete([], [])
    assert "fake-secret-key" not in str(info.value)
    assert redact({"x": "Bearer fake-secret-key"}, "fake-secret-key") == {"x": "Bearer [REDACTED]"}


def test_remote_plain_http_is_rejected():
    with pytest.raises(ProviderError, match="HTTPS"):
        LiveProvider(Settings(api_key="fake", model="fake", base_url="http://example.com/v1"))
