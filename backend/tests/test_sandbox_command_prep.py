"""prepare_streaming_command 单测。"""

from app.engine.sandbox.command_prep import prepare_streaming_command


def test_injects_unbuffer_for_python():
    cmd = "/workspace/TikTokDownloader/venv/bin/python script.py"
    assert prepare_streaming_command(cmd).startswith("PYTHONUNBUFFERED=1 ")


def test_skips_when_already_unbuffered():
    cmd = "PYTHONUNBUFFERED=1 python3 script.py"
    assert prepare_streaming_command(cmd) == cmd


def test_skips_python_u_flag():
    cmd = "python3 -u script.py"
    assert prepare_streaming_command(cmd) == cmd


def test_non_python_unchanged():
    cmd = "echo hello"
    assert prepare_streaming_command(cmd) == cmd
