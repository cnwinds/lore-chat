"""progress_log：ANSI / 行覆盖 / 刷屏折叠。"""

from app.engine.chat.progress_log import (
    append_progress_chunk,
    ensure_line_chunk,
    normalize_stream_chunk,
)


def test_strips_ansi_and_applies_cr_overwrite():
    raw = "◐ Downloading 4%\x1b[1G\x1b[J◑ Downloading 5%"
    assert normalize_stream_chunk(raw) == "◑ Downloading 5%"


def test_ensure_line_chunk_skips_newline_on_redraw():
    frame = "\x1b[1G\x1b[J◐ Downloading Chrome 4%"
    out = ensure_line_chunk(frame)
    assert out.startswith("\r") or "Downloading" in out
    assert not out.endswith("\n")


def test_ensure_line_chunk_still_adds_newline_for_plain_line():
    assert ensure_line_chunk("total 12") == "total 12\n"


def test_append_overwrites_spinner_frames():
    log: list[str] = []
    log = append_progress_chunk(log, ensure_line_chunk("◐ Downloading 1%"))
    log = append_progress_chunk(
        log, ensure_line_chunk("\x1b[1G\x1b[J◑ Downloading 2%")
    )
    log = append_progress_chunk(
        log, ensure_line_chunk("\x1b[1G\x1b[J◒ Downloading 3%")
    )
    joined = "".join(log)
    assert "Downloading 3%" in joined
    assert joined.count("Downloading") == 1


def test_collapse_persisted_spam_on_normalize():
    spam = "\n".join(f"Downloading Chrome | {i}% | 1.0s" for i in range(1, 50))
    out = normalize_stream_chunk(spam)
    assert out.count("\n") <= 1
    assert "49%" in out
