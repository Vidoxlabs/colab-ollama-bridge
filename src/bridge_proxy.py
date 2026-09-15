#!/usr/bin/env python3
"""Colab Ollama Bridge - Loopback Authentication and Route Proxy.

Binds to 127.0.0.1:11435 and securely proxies allowlisted OpenAI-compatible
inference routes to Ollama on 127.0.0.1:11434.
"""

from __future__ import annotations

import contextlib
import hmac
import http.client
import json
import logging
import os
import posixpath
import sys
import time
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import ClassVar

DEFAULT_BRIDGE_BIND = "127.0.0.1:11435"
DEFAULT_OLLAMA_BIND = "127.0.0.1:11434"
DEFAULT_MAX_BODY_BYTES = 8 * 1024 * 1024  # 8 MiB
CONNECT_TIMEOUT = 10.0
READ_TIMEOUT = 300.0

HOP_BY_HOP_HEADERS = {
    "connection",
    "keep-alive",
    "proxy-authenticate",
    "proxy-authorization",
    "te",
    "trailers",
    "transfer-encoding",
    "upgrade",
}

# Configure sanitized logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] [bridge_proxy] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    stream=sys.stderr,
)
logger = logging.getLogger("bridge_proxy")


def load_api_key() -> str:
    """Load BRIDGE_API_KEY from environment or file."""
    key_file = os.environ.get("BRIDGE_API_KEY_FILE")
    if key_file and os.path.isfile(key_file):
        try:
            with open(key_file, encoding="utf-8") as f:
                key = f.read().strip()
                if key:
                    return key
        except Exception:
            logger.error("Failed to read BRIDGE_API_KEY_FILE")
            sys.exit(1)

    key = os.environ.get("BRIDGE_API_KEY", "").strip()
    if not key:
        logger.error("BRIDGE_API_KEY is missing or empty")
        sys.exit(1)
    if len(key) < 16:
        logger.error("BRIDGE_API_KEY is too short (minimum 16 characters required)")
        sys.exit(1)
    if any(c.isspace() for c in key):
        logger.error("BRIDGE_API_KEY must not contain whitespace")
        sys.exit(1)
    return key


def parse_host_port(address: str, default_port: int) -> tuple[str, int]:
    """Parse host:port address string."""
    if ":" in address:
        host, port_str = address.rsplit(":", 1)
        return host.strip(), int(port_str.strip())
    return address.strip(), default_port


class ProxyHandler(BaseHTTPRequestHandler):
    """HTTP request handler enforcing bearer authentication and route allowlisting."""

    protocol_version = "HTTP/1.1"

    # Injected by server
    api_key: ClassVar[str] = ""
    upstream_host: ClassVar[str] = "127.0.0.1"
    upstream_port: ClassVar[int] = 11434
    enable_embeddings: ClassVar[bool] = False
    max_body_bytes: ClassVar[int] = DEFAULT_MAX_BODY_BYTES

    def log_message(self, format: str, *args: object) -> None:
        """Suppress default BaseHTTPRequestHandler logging to avoid secret leakage."""

    def _send_json_error(self, status_code: int, error_code: str, message: str) -> None:
        """Send a sanitized JSON error payload."""
        payload = json.dumps(
            {
                "error": {
                    "message": message,
                    "type": "invalid_request_error" if status_code < 500 else "api_error",
                    "code": error_code,
                }
            }
        ).encode("utf-8")
        self.send_response(status_code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("Connection", "close")
        self.end_headers()
        self.wfile.write(payload)

    def _normalize_path(self, raw_path: str) -> tuple[str, str] | None:
        """Normalize raw request path, returning (normalized_path, query_string).

        Returns None if the path is invalid, malformed, or traverses outside root.
        """
        try:
            parsed = urllib.parse.urlsplit(raw_path)
        except Exception:
            return None

        path_part = parsed.path
        if not path_part:
            return None

        unquoted = urllib.parse.unquote(path_part)
        if not unquoted.startswith("/"):
            return None

        # Collapse redundant slashes and resolve . and ..
        normalized = posixpath.normpath(unquoted)
        while normalized.startswith("//"):
            normalized = normalized[1:]

        if unquoted.endswith("/") and normalized != "/":
            normalized = normalized + "/"

        if not normalized.startswith("/"):
            return None

        return normalized, parsed.query

    def _validate_auth(self) -> bool:
        """Validate Authorization: Bearer token using constant-time comparison."""
        auth_header = self.headers.get("Authorization", "").strip()
        if not auth_header.startswith("Bearer "):
            return False
        token = auth_header[7:].strip()
        return hmac.compare_digest(token, self.api_key)

    def _is_route_allowed(self, method: str, clean_path: str) -> bool:
        """Check if request matches allowlisted OpenAI-compatible routes."""
        if method == "GET" and clean_path == "/healthz":
            return True
        if method == "GET" and clean_path == "/v1/models":
            return True
        if method == "POST" and clean_path == "/v1/chat/completions":
            return True
        if method == "POST" and clean_path == "/v1/completions":
            return True
        if method == "POST" and clean_path == "/v1/embeddings":
            return self.enable_embeddings
        return False

    def do_GET(self) -> None:  # noqa: N802
        start_time = time.monotonic()
        norm = self._normalize_path(self.path)
        if norm is None:
            self._send_json_error(400, "bad_request", "Invalid Request Path")
            return
        clean_path, query = norm

        # 1. Check route allowlist
        if not self._is_route_allowed("GET", clean_path):
            self._send_json_error(404, "not_found", "Not Found")
            duration_ms = int((time.monotonic() - start_time) * 1000)
            logger.info("GET %s 404 %dms", clean_path, duration_ms)
            return

        # 2. Check authentication
        if not self._validate_auth():
            self._send_json_error(401, "unauthorized", "Unauthorized")
            duration_ms = int((time.monotonic() - start_time) * 1000)
            logger.info("GET %s 401 %dms", clean_path, duration_ms)
            return

        # 3. Authenticated local health check
        if clean_path == "/healthz":
            payload = json.dumps({"status": "healthy"}).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("Connection", "close")
            self.end_headers()
            self.wfile.write(payload)
            duration_ms = int((time.monotonic() - start_time) * 1000)
            logger.info("GET %s 200 %dms", clean_path, duration_ms)
            return

        # 4. Proxy to upstream
        upstream_path = clean_path + (f"?{query}" if query else "")
        self._proxy_request("GET", upstream_path, clean_path, body=None, start_time=start_time)

    def do_POST(self) -> None:  # noqa: N802
        start_time = time.monotonic()
        norm = self._normalize_path(self.path)
        if norm is None:
            self._send_json_error(400, "bad_request", "Invalid Request Path")
            return
        clean_path, query = norm

        # 1. Check route allowlist
        if not self._is_route_allowed("POST", clean_path):
            self._send_json_error(404, "not_found", "Not Found")
            duration_ms = int((time.monotonic() - start_time) * 1000)
            logger.info("POST %s 404 %dms", clean_path, duration_ms)
            return

        # 2. Check authentication
        if not self._validate_auth():
            self._send_json_error(401, "unauthorized", "Unauthorized")
            duration_ms = int((time.monotonic() - start_time) * 1000)
            logger.info("POST %s 401 %dms", clean_path, duration_ms)
            return

        # 3. Read body with size limits
        content_length_str = self.headers.get("Content-Length")
        if content_length_str:
            try:
                content_length = int(content_length_str)
            except ValueError:
                self._send_json_error(400, "bad_request", "Invalid Content-Length")
                return
            if content_length > self.max_body_bytes:
                with contextlib.suppress(Exception):
                    self.rfile.read(min(content_length, 2 * 1024 * 1024))
                self._send_json_error(413, "payload_too_large", "Payload Too Large")
                duration_ms = int((time.monotonic() - start_time) * 1000)
                logger.info("POST %s 413 %dms", clean_path, duration_ms)
                return
            body = self.rfile.read(content_length)
        else:
            body = b""

        # 4. Proxy to upstream
        upstream_path = clean_path + (f"?{query}" if query else "")
        self._proxy_request("POST", upstream_path, clean_path, body=body, start_time=start_time)

    def _proxy_request(
        self,
        method: str,
        upstream_path: str,
        clean_path: str,
        body: bytes | None,
        start_time: float,
    ) -> None:
        """Forward request to upstream Ollama and stream back response."""
        # Collect Connection header tokens to strip
        custom_connection_hops: set[str] = set()
        raw_connection = self.headers.get("Connection", "")
        if raw_connection:
            for token in raw_connection.split(","):
                token_clean = token.strip().lower()
                if token_clean:
                    custom_connection_hops.add(token_clean)

        # Filter headers: strip hop-by-hop, connection tokens, client Authorization, and Cloudflare Access headers
        forward_headers: dict[str, str] = {}
        for header, value in self.headers.items():
            lower_header = header.lower()
            if (
                lower_header in HOP_BY_HOP_HEADERS
                or lower_header in custom_connection_hops
                or lower_header == "authorization"
                or lower_header.startswith("cf-access-")
            ):
                continue
            forward_headers[header] = value

        conn: http.client.HTTPConnection | None = None
        try:
            conn = http.client.HTTPConnection(
                self.upstream_host,
                self.upstream_port,
                timeout=READ_TIMEOUT,
            )
            conn.request(method, upstream_path, body=body, headers=forward_headers)
            upstream_resp = conn.getresponse()

            # Prepare client response headers
            status_code = upstream_resp.status
            self.send_response(status_code)
            self.send_header("Cache-Control", "no-store")

            content_length = upstream_resp.getheader("Content-Length")
            is_chunked = False

            for header, value in upstream_resp.getheaders():
                lower_header = header.lower()
                if lower_header in HOP_BY_HOP_HEADERS or lower_header == "cache-control":
                    continue
                self.send_header(header, value)

            # If no Content-Length is given, use chunked transfer encoding for streaming
            if content_length is None:
                is_chunked = True
                self.send_header("Transfer-Encoding", "chunked")

            self.end_headers()

            # Stream response body to client
            if is_chunked:
                while True:
                    chunk = upstream_resp.read(4096)
                    if not chunk:
                        break
                    chunk_header = f"{len(chunk):X}\r\n".encode("latin-1")
                    self.wfile.write(chunk_header + chunk + b"\r\n")
                    self.wfile.flush()
                # Write terminal chunk
                self.wfile.write(b"0\r\n\r\n")
                self.wfile.flush()
            else:
                bytes_left = int(content_length)
                while bytes_left > 0:
                    read_len = min(bytes_left, 65536)
                    chunk = upstream_resp.read(read_len)
                    if not chunk:
                        break
                    self.wfile.write(chunk)
                    bytes_left -= len(chunk)
                self.wfile.flush()

            duration_ms = int((time.monotonic() - start_time) * 1000)
            logger.info("%s %s %d %dms", method, clean_path, status_code, duration_ms)

        except (BrokenPipeError, ConnectionResetError):
            duration_ms = int((time.monotonic() - start_time) * 1000)
            logger.info("Client disconnected on %s %s (%dms)", method, clean_path, duration_ms)
        except (TimeoutError, http.client.RemoteDisconnected):
            duration_ms = int((time.monotonic() - start_time) * 1000)
            logger.error("Upstream timeout on %s %s (%dms)", method, clean_path, duration_ms)
            self._send_json_error(504, "gateway_timeout", "Upstream Gateway Timeout")
        except Exception:
            duration_ms = int((time.monotonic() - start_time) * 1000)
            logger.error(
                "Upstream connection failure on %s %s (%dms)", method, clean_path, duration_ms
            )
            self._send_json_error(502, "bad_gateway", "Upstream Connection Failed")
        finally:
            if conn:
                with contextlib.suppress(Exception):
                    conn.close()


def run_server(
    bind_address: str = DEFAULT_BRIDGE_BIND,
    ollama_address: str = DEFAULT_OLLAMA_BIND,
    api_key: str | None = None,
    enable_embeddings: bool = False,
    max_body_bytes: int = DEFAULT_MAX_BODY_BYTES,
) -> None:
    """Initialize and run the proxy server."""
    if not api_key:
        api_key = load_api_key()

    host, port = parse_host_port(bind_address, 11435)
    upstream_host, upstream_port = parse_host_port(ollama_address, 11434)

    ProxyHandler.api_key = api_key
    ProxyHandler.upstream_host = upstream_host
    ProxyHandler.upstream_port = upstream_port
    ProxyHandler.enable_embeddings = enable_embeddings
    ProxyHandler.max_body_bytes = max_body_bytes

    server = ThreadingHTTPServer((host, port), ProxyHandler)
    logger.info(
        "Bridge proxy listening on %s:%d (upstream: %s:%d)",
        host,
        port,
        upstream_host,
        upstream_port,
    )

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        logger.info("Bridge proxy shutting down cleanly")
    finally:
        server.server_close()


if __name__ == "__main__":
    bind_addr = os.environ.get("BRIDGE_BIND", DEFAULT_BRIDGE_BIND)
    ollama_addr = os.environ.get("OLLAMA_BIND", DEFAULT_OLLAMA_BIND)
    embeds = os.environ.get("ENABLE_EMBEDDINGS", "false").lower() in ("true", "1", "yes")

    run_server(bind_address=bind_addr, ollama_address=ollama_addr, enable_embeddings=embeds)
