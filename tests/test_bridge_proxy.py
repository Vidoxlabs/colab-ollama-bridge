"""Unit and integration tests for src/bridge_proxy.py."""

from __future__ import annotations

import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import pytest

from src.bridge_proxy import ProxyHandler

TEST_API_KEY = "super-secret-bridge-key-12345678"


class MockOllamaHandler(BaseHTTPRequestHandler):
    """Mock Ollama server that records received requests."""

    last_received_headers: dict = {}
    last_received_body: bytes = b""
    last_received_path: str = ""

    def log_message(self, format: str, *args: object) -> None:
        pass

    def do_GET(self) -> None:  # noqa: N802
        MockOllamaHandler.last_received_path = self.path
        MockOllamaHandler.last_received_headers = dict(self.headers)
        if self.path == "/v1/models":
            data = json.dumps({"data": [{"id": "qwen2.5-coder:7b"}]}).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
        else:
            self.send_response(404)
            self.end_headers()

    def do_POST(self) -> None:  # noqa: N802
        MockOllamaHandler.last_received_path = self.path
        MockOllamaHandler.last_received_headers = dict(self.headers)
        content_length = int(self.headers.get("Content-Length", 0))
        MockOllamaHandler.last_received_body = self.rfile.read(content_length)

        if self.path == "/v1/chat/completions":
            if b'"stream": true' in MockOllamaHandler.last_received_body:
                self.send_response(200)
                self.send_header("Content-Type", "text/event-stream")
                self.send_header("Transfer-Encoding", "chunked")
                self.end_headers()
                chunks = [
                    b'data: {"choices":[{"delta":{"content":"Hello"}}]}\n\n',
                    b'data: {"choices":[{"delta":{"content":" world"}}]}\n\n',
                    b"data: [DONE]\n\n",
                ]
                for c in chunks:
                    chunk_hdr = f"{len(c):X}\r\n".encode("latin-1")
                    self.wfile.write(chunk_hdr + c + b"\r\n")
                    self.wfile.flush()
                self.wfile.write(b"0\r\n\r\n")
                self.wfile.flush()
            else:
                data = json.dumps(
                    {
                        "choices": [{"message": {"content": "Response"}}],
                        "usage": {"total_tokens": 10},
                    }
                ).encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)
        elif self.path == "/v1/completions":
            data = json.dumps({"choices": [{"text": "Completion text"}]}).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
        elif self.path == "/v1/embeddings":
            data = json.dumps({"data": [{"embedding": [0.1, 0.2]}]}).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
        else:
            self.send_response(404)
            self.end_headers()


@pytest.fixture(scope="module")
def servers():
    # 1. Start Mock Ollama Server
    ollama_server = ThreadingHTTPServer(("127.0.0.1", 0), MockOllamaHandler)
    ollama_port = ollama_server.server_port
    t_ollama = threading.Thread(target=ollama_server.serve_forever, daemon=True)
    t_ollama.start()

    # 2. Start Proxy Server
    ProxyHandler.api_key = TEST_API_KEY
    ProxyHandler.upstream_host = "127.0.0.1"
    ProxyHandler.upstream_port = ollama_port
    ProxyHandler.enable_embeddings = False
    ProxyHandler.max_body_bytes = 1024 * 1024  # 1 MiB for tests

    proxy_server = ThreadingHTTPServer(("127.0.0.1", 0), ProxyHandler)
    proxy_port = proxy_server.server_port
    t_proxy = threading.Thread(target=proxy_server.serve_forever, daemon=True)
    t_proxy.start()

    time.sleep(0.1)
    yield f"127.0.0.1:{proxy_port}", f"127.0.0.1:{ollama_port}"

    proxy_server.shutdown()
    ollama_server.shutdown()


def test_healthz_unauthenticated(servers):
    proxy_addr, _ = servers
    url = f"http://{proxy_addr}/healthz"
    req = Request(url)
    with urlopen(req) as resp:
        assert resp.status == 200
        data = json.loads(resp.read().decode("utf-8"))
        assert data["status"] == "healthy"


def test_missing_auth_rejected(servers):
    proxy_addr, _ = servers
    url = f"http://{proxy_addr}/v1/models"
    req = Request(url)
    with pytest.raises(HTTPError) as exc_info:
        urlopen(req)
    assert exc_info.value.code == 401
    payload = json.loads(exc_info.value.read().decode("utf-8"))
    assert payload["error"]["code"] == "unauthorized"


def test_invalid_auth_rejected(servers):
    proxy_addr, _ = servers
    url = f"http://{proxy_addr}/v1/models"
    req = Request(url, headers={"Authorization": "Bearer wrong-key-value-12345678"})
    with pytest.raises(HTTPError) as exc_info:
        urlopen(req)
    assert exc_info.value.code == 401


def test_valid_auth_models(servers):
    proxy_addr, _ = servers
    url = f"http://{proxy_addr}/v1/models"
    req = Request(url, headers={"Authorization": f"Bearer {TEST_API_KEY}"})
    with urlopen(req) as resp:
        assert resp.status == 200
        data = json.loads(resp.read().decode("utf-8"))
        assert data["data"][0]["id"] == "qwen2.5-coder:7b"

    # Verify Authorization header was stripped before hitting upstream
    assert "Authorization" not in MockOllamaHandler.last_received_headers
    assert "authorization" not in MockOllamaHandler.last_received_headers


def test_chat_completions_json(servers):
    proxy_addr, _ = servers
    url = f"http://{proxy_addr}/v1/chat/completions"
    body = json.dumps(
        {"model": "qwen2.5-coder:7b", "messages": [{"role": "user", "content": "Hi"}]}
    ).encode("utf-8")
    req = Request(
        url,
        data=body,
        headers={"Authorization": f"Bearer {TEST_API_KEY}", "Content-Type": "application/json"},
    )
    with urlopen(req) as resp:
        assert resp.status == 200
        data = json.loads(resp.read().decode("utf-8"))
        assert "choices" in data


def test_chat_completions_streaming(servers):
    proxy_addr, _ = servers
    url = f"http://{proxy_addr}/v1/chat/completions"
    body = json.dumps(
        {
            "model": "qwen2.5-coder:7b",
            "messages": [{"role": "user", "content": "Hi"}],
            "stream": True,
        }
    ).encode("utf-8")
    req = Request(
        url,
        data=body,
        headers={"Authorization": f"Bearer {TEST_API_KEY}", "Content-Type": "application/json"},
    )
    with urlopen(req) as resp:
        assert resp.status == 200
        content = resp.read().decode("utf-8")
        assert "data: [DONE]" in content
        assert "Hello" in content


def test_native_ollama_routes_blocked(servers):
    proxy_addr, _ = servers
    # Ollama admin / native routes must return 404
    for route in ["/api/tags", "/api/pull", "/api/generate", "/api/version"]:
        url = f"http://{proxy_addr}{route}"
        req = Request(url, headers={"Authorization": f"Bearer {TEST_API_KEY}"})
        with pytest.raises(HTTPError) as exc_info:
            urlopen(req)
        assert exc_info.value.code == 404


def test_embeddings_disabled_by_default(servers):
    proxy_addr, _ = servers
    url = f"http://{proxy_addr}/v1/embeddings"
    body = json.dumps({"input": "test text"}).encode("utf-8")
    req = Request(
        url,
        data=body,
        headers={"Authorization": f"Bearer {TEST_API_KEY}", "Content-Type": "application/json"},
    )
    with pytest.raises(HTTPError) as exc_info:
        urlopen(req)
    assert exc_info.value.code == 404


def test_embeddings_enabled_when_flag_set(servers):
    ProxyHandler.enable_embeddings = True
    proxy_addr, _ = servers
    url = f"http://{proxy_addr}/v1/embeddings"
    body = json.dumps({"input": "test text"}).encode("utf-8")
    req = Request(
        url,
        data=body,
        headers={"Authorization": f"Bearer {TEST_API_KEY}", "Content-Type": "application/json"},
    )
    with urlopen(req) as resp:
        assert resp.status == 200
    ProxyHandler.enable_embeddings = False


def test_payload_too_large(servers):
    proxy_addr, _ = servers
    url = f"http://{proxy_addr}/v1/chat/completions"
    old_max = ProxyHandler.max_body_bytes
    ProxyHandler.max_body_bytes = 500  # Set low limit for testing
    try:
        large_body = b"x" * 1500  # Exceeds limit
        req = Request(
            url,
            data=large_body,
            headers={"Authorization": f"Bearer {TEST_API_KEY}", "Content-Type": "application/json"},
        )
        with pytest.raises(HTTPError) as exc_info:
            urlopen(req)
        assert exc_info.value.code == 413
    finally:
        ProxyHandler.max_body_bytes = old_max
