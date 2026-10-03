import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import httpx
import pytest

from repofix.config import Settings
from repofix.providers import LiveProvider, ProviderError, redact


@pytest.mark.parametrize(
    "proxy_url",
    ["file:///tmp/proxy", "http://", "http://user:secret@localhost:1234", "http://localhost?q=x"],
)
def test_invalid_explicit_proxy_is_rejected_before_network(proxy_url):
    with pytest.raises(ProviderError, match="proxy"):
        LiveProvider(Settings(api_key="fake", model="fake", proxy_url=proxy_url))


def test_model_request_uses_explicit_local_proxy():
    observations = []

    class ProxyFixture(BaseHTTPRequestHandler):
        def do_POST(self):
            observations.append((self.path, self.headers.get("Authorization")))
            self.rfile.read(int(self.headers["Content-Length"]))
            response = json.dumps({"choices": [{"message": {"content": "proxy fixture"}}]}).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(response)))
            self.end_headers()
            self.wfile.write(response)

        def log_message(self, *args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), ProxyFixture)
    worker = threading.Thread(target=server.serve_forever, daemon=True)
    worker.start()
    try:
        settings = Settings(
            api_key="fake-test-key",
            model="local-proxy-fixture",
            base_url="http://127.0.0.1:1/v1",
            proxy_url=f"http://127.0.0.1:{server.server_port}",
        )
        reply = LiveProvider(settings).complete([], [], timeout=3)
        assert reply.summary == "proxy fixture"
        assert observations == [("http://127.0.0.1:1/v1/chat/completions", "Bearer fake-test-key")]
        assert "proxy_url" not in repr(settings)
    finally:
        server.shutdown()
        server.server_close()
        worker.join(timeout=3)


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
