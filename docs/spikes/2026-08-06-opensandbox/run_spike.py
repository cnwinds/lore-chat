#!/usr/bin/env python3
"""OpenSandbox spike: short cmd, streamed long cmd, workspace PVC persistence."""

from __future__ import annotations

import asyncio
import os
import subprocess
import sys
import time
from dataclasses import dataclass, field
from datetime import timedelta


VOLUME_NAME = os.environ.get("SPIKE_VOLUME", "lorechat-opensandbox-workspace")
DOMAIN = os.environ.get("OPENSANDBOX_DOMAIN", "127.0.0.1:18090")
IMAGE = os.environ.get("SANDBOX_IMAGE", "python:3.12-slim")
MARKER = "lorechat-spike-marker-v1"


@dataclass
class SpikeReport:
    steps: list[str] = field(default_factory=list)
    ok: bool = True
    errors: list[str] = field(default_factory=list)

    def log(self, msg: str) -> None:
        print(msg, flush=True)
        self.steps.append(msg)

    def fail(self, msg: str) -> None:
        self.ok = False
        self.errors.append(msg)
        self.log(f"FAIL: {msg}")


def ensure_volume() -> None:
    subprocess.run(
        ["docker", "volume", "create", VOLUME_NAME],
        check=True,
        capture_output=True,
        text=True,
    )


def write_notes(report: SpikeReport, extra: dict[str, str]) -> None:
    path = os.path.join(os.path.dirname(__file__), "NOTES.md")
    lines = [
        "# Spike NOTES",
        "",
        f"- time: {time.strftime('%Y-%m-%d %H:%M:%S %z')}",
        f"- domain: `{DOMAIN}`",
        f"- image: `{IMAGE}`",
        f"- volume: `{VOLUME_NAME}`",
        f"- result: **{'PASS' if report.ok else 'FAIL'}**",
        "",
        "## Steps",
        "",
    ]
    for s in report.steps:
        lines.append(f"- {s}")
    if report.errors:
        lines.extend(["", "## Errors", ""])
        for e in report.errors:
            lines.append(f"- {e}")
    lines.extend(["", "## Observations", ""])
    for k, v in extra.items():
        lines.append(f"- **{k}**: {v}")
    lines.append("")
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    print(f"\nWrote {path}", flush=True)


def _stdout_text(execution) -> str:
    logs = getattr(execution, "logs", None)
    if logs is not None and getattr(logs, "stdout", None):
        return "\n".join(getattr(x, "text", str(x)) for x in logs.stdout)
    return str(execution)


async def create_sandbox(report: SpikeReport):
    from opensandbox import Sandbox
    from opensandbox.config import ConnectionConfig
    from opensandbox.models.sandboxes import PVC, Volume

    config = ConnectionConfig(domain=DOMAIN, protocol="http")
    report.log(f"create sandbox image={IMAGE} volume={VOLUME_NAME} -> /workspace")
    sandbox = await Sandbox.create(
        IMAGE,
        connection_config=config,
        timeout=timedelta(minutes=60),
        ready_timeout=timedelta(minutes=3),
        volumes=[
            Volume(
                name="workspace",
                pvc=PVC(claim_name=VOLUME_NAME),
                mount_path="/workspace",
                read_only=False,
            )
        ],
    )
    sid = getattr(sandbox, "id", None) or getattr(sandbox, "sandbox_id", None)
    report.log(f"sandbox id={sid}")
    return sandbox


async def run_short(sandbox, report: SpikeReport) -> None:
    report.log("short sync: echo hello")
    execution = await sandbox.commands.run("echo hello-from-opensandbox")
    joined = _stdout_text(execution)
    report.log(f"short stdout: {joined!r}")
    if "hello-from-opensandbox" not in joined:
        report.fail("short command missing expected stdout")


async def run_streamed(sandbox, report: SpikeReport) -> None:
    from opensandbox.models.execd import ExecutionHandlers, OutputMessage

    report.log("streamed long: 5 ticks with sleep")
    chunks: list[str] = []

    async def on_stdout(msg: OutputMessage) -> None:
        text = msg.text or ""
        chunks.append(text)
        report.log(f"  event stdout: {text!r}")

    handlers = ExecutionHandlers(on_stdout=on_stdout)
    cmd = "for i in 1 2 3 4 5; do echo SPIKE_TICK_$i; sleep 1; done"
    execution = await sandbox.commands.run(cmd, handlers=handlers)
    joined = "\n".join(chunks) or _stdout_text(execution)
    report.log(f"streamed final: {joined!r} chunks={len(chunks)}")
    if "SPIKE_TICK_" not in joined:
        report.fail("streamed/long command missing SPIKE_TICK_* output")


async def run_background(sandbox, report: SpikeReport) -> None:
    from opensandbox.models.execd import RunCommandOpts

    report.log("background job: sleep 3 + echo, poll logs")
    opts = RunCommandOpts(background=True)
    execution = await sandbox.commands.run(
        "sleep 3; echo SPIKE_BG_DONE",
        opts=opts,
    )
    eid = getattr(execution, "id", None)
    report.log(f"background execution id={eid}")
    if not eid:
        report.fail("background run returned no execution id")
        return

    deadline = time.time() + 30
    saw = ""
    while time.time() < deadline:
        status = await sandbox.commands.get_command_status(eid)
        report.log(f"  status: {status}")
        logs = await sandbox.commands.get_background_command_logs(eid)
        raw = getattr(logs, "output", None) or getattr(logs, "stdout", None) or str(logs)
        if not isinstance(raw, str):
            raw = str(raw)
        if raw and raw != saw:
            report.log(f"  logs: {raw!r}")
            saw = raw
        running = getattr(status, "running", None)
        exit_code = getattr(status, "exit_code", None)
        if running is False or exit_code is not None:
            break
        await asyncio.sleep(0.5)

    if "SPIKE_BG_DONE" not in saw:
        # status object may carry completion without logs shape we guessed
        final = await sandbox.commands.get_background_command_logs(eid)
        saw = str(final)
        report.log(f"  final logs object: {saw!r}")
    if "SPIKE_BG_DONE" not in saw:
        report.fail("background command missing SPIKE_BG_DONE in polled logs")


async def persist_roundtrip(report: SpikeReport) -> None:
    report.log("persistence: write marker, destroy, recreate, read")
    sandbox = await create_sandbox(report)
    try:
        await sandbox.commands.run(
            f"mkdir -p /workspace && echo {MARKER} > /workspace/marker.txt && cat /workspace/marker.txt"
        )
    finally:
        await sandbox.destroy()
        report.log("destroyed first sandbox")

    sandbox2 = await create_sandbox(report)
    try:
        execution = await sandbox2.commands.run("cat /workspace/marker.txt")
        joined = _stdout_text(execution)
        report.log(f"marker after recreate: {joined!r}")
        if MARKER not in joined:
            report.fail("workspace volume did not persist marker across sandbox recreate")
    finally:
        await sandbox2.destroy()
        report.log("destroyed second sandbox")


async def main() -> int:
    report = SpikeReport()
    extra: dict[str, str] = {
        "docker.sock": "only on opensandbox-server container (compose), not on spike client",
        "api_auth": "OPENSANDBOX_INSECURE_SERVER=YES for spike only",
        "host_port": "18090 (8090 taken by lorechat-web)",
    }
    try:
        import opensandbox  # noqa: F401
    except ImportError:
        report.fail("pip install opensandbox first")
        write_notes(report, extra)
        return 1

    try:
        ensure_volume()
        report.log(f"ensured docker volume {VOLUME_NAME}")

        sandbox = await create_sandbox(report)
        try:
            await run_short(sandbox, report)
            await run_streamed(sandbox, report)
            await run_background(sandbox, report)
        finally:
            await sandbox.destroy()
            report.log("destroyed primary sandbox")

        await persist_roundtrip(report)
    except Exception as e:
        report.fail(f"{type(e).__name__}: {e}")
        extra["exception"] = repr(e)

    try:
        import opensandbox as osb
        import inspect
        from opensandbox import Sandbox

        extra["opensandbox_version"] = getattr(osb, "__version__", "unknown")
        extra["Sandbox.create_sig"] = str(inspect.signature(Sandbox.create))
    except Exception as e:
        extra["sdk_probe"] = repr(e)

    write_notes(report, extra)
    return 0 if report.ok else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
