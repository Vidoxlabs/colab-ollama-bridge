#!/usr/bin/env python3
"""Colab Ollama Bridge - Process Supervisor.

Supervises Ollama, bridge proxy, and cloudflared processes with strict
PID ownership verification, bounded health checks, and signal handling.
"""

from __future__ import annotations

import contextlib
import json
import logging
import os
import signal
import subprocess
import sys
import time
from pathlib import Path
from typing import Any
from urllib.error import URLError
from urllib.request import Request, urlopen

# Configure sanitized logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] [supervisor] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    stream=sys.stderr,
)
logger = logging.getLogger("supervisor")

DEFAULT_STATE_DIR = "/tmp/bridge_state"
DEFAULT_BRIDGE_BIND = "127.0.0.1:11435"
DEFAULT_OLLAMA_BIND = "127.0.0.1:11434"
MAX_RESTART_ATTEMPTS = 3
INITIAL_BACKOFF_SECONDS = 2.0


class ProcessSupervisor:
    """Supervises owned processes and ensures clean lifecycle management."""

    def __init__(self, state_dir: str = DEFAULT_STATE_DIR) -> None:
        self.state_dir = Path(state_dir)
        self.state_dir.mkdir(parents=True, exist_ok=True)
        self.state_file = self.state_dir / "supervisor_state.json"
        self.owned_processes: dict[str, dict[str, Any]] = {}
        self.running = True
        self._load_state()

        # Register signal handlers
        signal.signal(signal.SIGINT, self._handle_signal)
        signal.signal(signal.SIGTERM, self._handle_signal)

    def _handle_signal(self, signum: int, frame: Any) -> None:
        """Signal handler for graceful shutdown."""
        sig_name = signal.Signals(signum).name
        logger.info("Received signal %s, initiating graceful shutdown", sig_name)
        self.running = False
        self.stop_all()
        sys.exit(0)

    def _load_state(self) -> None:
        """Load state from disk if exists."""
        if self.state_file.exists():
            try:
                with open(self.state_file, encoding="utf-8") as f:
                    self.owned_processes = json.load(f)
            except Exception:
                self.owned_processes = {}

    def _save_state(self) -> None:
        """Save state to disk."""
        try:
            with open(self.state_file, "w", encoding="utf-8") as f:
                json.dump(self.owned_processes, f, indent=2)
        except Exception as e:
            logger.error("Failed to save state: %s", type(e).__name__)

    def register_process(self, name: str, pid: int, cmd_identifier: str) -> None:
        """Register an owned process."""
        self.owned_processes[name] = {
            "pid": pid,
            "cmd_identifier": cmd_identifier,
            "registered_at": time.time(),
        }
        self._save_state()
        logger.info("Registered process [%s] with PID %d", name, pid)

    def verify_pid_ownership(self, name: str) -> bool:
        """Verify that the PID is alive and belongs to the expected command."""
        proc_info = self.owned_processes.get(name)
        if not proc_info:
            return False

        pid = proc_info.get("pid")
        expected_cmd = proc_info.get("cmd_identifier", "")

        if not isinstance(pid, int) or pid <= 0:
            return False

        # 1. Check if PID exists
        try:
            os.kill(pid, 0)
        except OSError:
            return False

        # 2. Check command line identifier to prevent killing recycled PIDs
        try:
            cmdline = ""
            # On Linux /proc/<pid>/cmdline is standard
            proc_cmdline_path = Path(f"/proc/{pid}/cmdline")
            if proc_cmdline_path.exists():
                with open(proc_cmdline_path, "rb") as f:
                    cmdline = f.read().replace(b"\x00", b" ").decode("utf-8", errors="ignore")
            else:
                # Fallback to ps command
                res = subprocess.run(
                    ["ps", "-p", str(pid), "-o", "args="],
                    capture_output=True,
                    text=True,
                    check=False,
                )
                cmdline = res.stdout

            if expected_cmd and expected_cmd in cmdline:
                return True
        except Exception:
            return False

        return False

    def stop_process(self, name: str, timeout: float = 5.0) -> bool:
        """Stop an owned process safely."""
        proc_info = self.owned_processes.get(name)
        if not proc_info:
            return True

        pid = proc_info.get("pid")
        if not isinstance(pid, int):
            self.owned_processes.pop(name, None)
            self._save_state()
            return True

        # Verify identity before sending signals
        if not self.verify_pid_ownership(name):
            logger.info(
                "Process [%s] (PID %d) is already terminated or recycled; unregistering", name, pid
            )
            self.owned_processes.pop(name, None)
            self._save_state()
            return True

        logger.info("Stopping process [%s] (PID %d)", name, pid)
        with contextlib.suppress(OSError):
            os.kill(pid, signal.SIGTERM)

        # Wait for termination
        deadline = time.time() + timeout
        while time.time() < deadline:
            try:
                os.kill(pid, 0)
                time.sleep(0.2)
            except OSError:
                break
        else:
            # Force kill if still running
            logger.warning(
                "Process [%s] (PID %d) did not stop within %ss; sending SIGKILL", name, pid, timeout
            )
            with contextlib.suppress(OSError):
                os.kill(pid, signal.SIGKILL)

        self.owned_processes.pop(name, None)
        self._save_state()
        return True

    def stop_all(self) -> None:
        """Stop all owned processes in reverse order."""
        for name in list(self.owned_processes.keys()):
            self.stop_process(name)

        # Clean up temporary secret files in state directory
        self.cleanup_temp_files()

    def cleanup_temp_files(self) -> None:
        """Purge temporary token files and sensitive state."""
        for token_file in self.state_dir.glob("*.token"):
            with contextlib.suppress(Exception):
                token_file.unlink()
                logger.info("Removed temporary token file: %s", token_file.name)
        for token_file in self.state_dir.glob("*.key"):
            with contextlib.suppress(Exception):
                token_file.unlink()

    def check_health(
        self,
        bridge_bind: str = DEFAULT_BRIDGE_BIND,
        ollama_bind: str = DEFAULT_OLLAMA_BIND,
        api_key: str | None = None,
    ) -> bool:
        """Check health of proxy and upstream Ollama with authenticated health check."""
        # 1. Resolve API key if not provided
        if not api_key:
            api_key = os.environ.get("BRIDGE_API_KEY")
            if not api_key and os.environ.get("BRIDGE_API_KEY_FILE"):
                key_path = Path(os.environ["BRIDGE_API_KEY_FILE"])
                if key_path.is_file():
                    with contextlib.suppress(Exception):
                        api_key = key_path.read_text(encoding="utf-8").strip()
            if not api_key:
                candidate = self.state_dir / "bridge_api.key"
                if candidate.is_file():
                    with contextlib.suppress(Exception):
                        api_key = candidate.read_text(encoding="utf-8").strip()

        # 2. Check bridge proxy
        proxy_url = f"http://{bridge_bind}/healthz"
        proxy_headers = {"User-Agent": "Bridge-Supervisor/1.0"}
        if api_key:
            proxy_headers["Authorization"] = f"Bearer {api_key}"

        try:
            req = Request(proxy_url, headers=proxy_headers)
            with urlopen(req, timeout=3.0) as resp:
                if resp.status != 200:
                    logger.warning("Proxy health check returned HTTP %d", resp.status)
                    return False
        except (URLError, TimeoutError, OSError):
            logger.warning("Proxy health check failed connecting to %s", proxy_url)
            return False

        # 3. Check Ollama
        ollama_url = f"http://{ollama_bind}/"
        try:
            req = Request(ollama_url, headers={"User-Agent": "Bridge-Supervisor/1.0"})
            with urlopen(req, timeout=3.0) as resp:
                if resp.status != 200:
                    logger.warning("Ollama health check returned HTTP %d", resp.status)
                    return False
        except (URLError, TimeoutError, OSError):
            logger.warning("Ollama health check failed connecting to %s", ollama_url)
            return False

        return True

    def supervise_loop(
        self,
        bridge_bind: str = DEFAULT_BRIDGE_BIND,
        ollama_bind: str = DEFAULT_OLLAMA_BIND,
        api_key: str | None = None,
        interval_seconds: float = 10.0,
    ) -> None:
        """Main supervision loop monitoring health."""
        logger.info("Starting supervision loop (interval: %ss)", interval_seconds)
        consecutive_failures = 0

        while self.running:
            is_healthy = self.check_health(bridge_bind, ollama_bind, api_key)
            if is_healthy:
                consecutive_failures = 0
                logger.info("Services healthy (proxy @ %s, ollama @ %s)", bridge_bind, ollama_bind)
            else:
                consecutive_failures += 1
                logger.error(
                    "Health check failed (attempt %d/%d)",
                    consecutive_failures,
                    MAX_RESTART_ATTEMPTS,
                )
                if consecutive_failures >= MAX_RESTART_ATTEMPTS:
                    logger.error("Services failed health checks consistently; shutting down")
                    self.stop_all()
                    sys.exit(1)

            time.sleep(interval_seconds)


if __name__ == "__main__":
    state_directory = os.environ.get("BRIDGE_STATE_DIR", DEFAULT_STATE_DIR)
    bridge_addr = os.environ.get("BRIDGE_BIND", DEFAULT_BRIDGE_BIND)
    ollama_addr = os.environ.get("OLLAMA_BIND", DEFAULT_OLLAMA_BIND)

    supervisor = ProcessSupervisor(state_dir=state_directory)
    if len(sys.argv) > 1 and sys.argv[1] == "stop":
        supervisor.stop_all()
    elif len(sys.argv) > 1 and sys.argv[1] == "check":
        api_k = sys.argv[2] if len(sys.argv) > 2 else None
        healthy = supervisor.check_health(bridge_addr, ollama_addr, api_k)
        sys.exit(0 if healthy else 1)
    elif len(sys.argv) > 4 and sys.argv[1] == "register":
        supervisor.register_process(sys.argv[2], int(sys.argv[3]), sys.argv[4])
        sys.exit(0)
    else:
        supervisor.supervise_loop(bridge_bind=bridge_addr, ollama_bind=ollama_addr)
