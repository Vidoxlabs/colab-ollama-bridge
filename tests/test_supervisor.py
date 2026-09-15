"""Tests for src/supervisor.py process supervision and lifecycle."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

from src.supervisor import ProcessSupervisor


def test_supervisor_registration_and_ownership(tmp_path: Path):
    sup = ProcessSupervisor(state_dir=str(tmp_path))

    # Start dummy process
    proc = subprocess.Popen(["sleep", "10"])
    try:
        sup.register_process("test_sleep", proc.pid, "sleep")
        assert sup.verify_pid_ownership("test_sleep") is True

        # Nonexistent process
        assert sup.verify_pid_ownership("nonexistent") is False
    finally:
        proc.kill()
        proc.wait()


def test_supervisor_stop_process(tmp_path: Path):
    sup = ProcessSupervisor(state_dir=str(tmp_path))
    proc = subprocess.Popen(["sleep", "20"])

    sup.register_process("test_sleep", proc.pid, "sleep")
    stopped = sup.stop_process("test_sleep", timeout=2.0)
    assert stopped is True
    assert proc.poll() is not None


def test_supervisor_cleanup_temp_files(tmp_path: Path):
    sup = ProcessSupervisor(state_dir=str(tmp_path))

    token_file = tmp_path / "test.token"
    token_file.write_text("dummy-token")
    key_file = tmp_path / "test.key"
    key_file.write_text("dummy-key")

    assert token_file.exists()
    assert key_file.exists()

    sup.cleanup_temp_files()

    assert not token_file.exists()
    assert not key_file.exists()


def test_verify_pid_ownership_rejects_recycled_pid(tmp_path: Path):
    sup = ProcessSupervisor(state_dir=str(tmp_path))

    # Register current test process PID with wrong command identifier
    sup.register_process("fake_service", os.getpid(), "totally_different_service_name_12345")
    # Must fail because expected command identifier doesn't match ps output
    assert sup.verify_pid_ownership("fake_service") is False
