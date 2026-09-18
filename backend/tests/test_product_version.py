from pathlib import Path

from app.product_version import format_display, resolve


def test_release_channel_is_plain_version():
    assert (
        format_display(
            version="0.2.10",
            revision="abc1234",
            commits_ahead=0,
            channel="release",
            dirty=False,
        )
        == "0.2.10"
    )


def test_development_display_is_pep440_local():
    assert (
        format_display(
            version="0.2.10",
            revision="217f1c8",
            commits_ahead=12,
            channel="development",
            dirty=False,
        )
        == "0.2.10+12.g217f1c8"
    )


def test_dirty_development_display_suffix():
    assert (
        format_display(
            version="0.2.10",
            revision="217f1c8",
            commits_ahead=0,
            channel="development",
            dirty=True,
        )
        == "0.2.10+g217f1c8.dirty"
    )


def test_resolve_prefers_env_over_files(tmp_path):
    (tmp_path / "VERSION").write_text("9.9.9\n", encoding="utf-8")
    info = resolve(
        environ={
            "LORECHAT_VERSION": "0.2.10",
            "LORECHAT_REVISION": "deadbee",
            "LORECHAT_COMMITS_AHEAD": "3",
            "LORECHAT_CHANNEL": "development",
        },
        repo_root=tmp_path,
    )
    assert info.version == "0.2.10"
    assert info.channel == "development"
    assert info.display == "0.2.10+3.gdeadbee"
    assert info.revision == "deadbee"


def test_env_release_stays_release():
    info = resolve(
        environ={
            "LORECHAT_VERSION": "0.2.10",
            "LORECHAT_REVISION": "abc1234",
            "LORECHAT_COMMITS_AHEAD": "0",
            "LORECHAT_CHANNEL": "release",
        },
        repo_root=Path("/nonexistent"),
    )
    assert info.channel == "release"
    assert info.display == "0.2.10"


def test_placeholder_env_falls_through_to_version_file(tmp_path):
    (tmp_path / "VERSION").write_text("0.2.10\n", encoding="utf-8")
    info = resolve(
        environ={"LORECHAT_VERSION": "0.0.0", "LORECHAT_CHANNEL": "release"},
        repo_root=tmp_path,
    )
    assert info.version == "0.2.10"
    assert info.channel == "development"


def test_empty_env_does_not_override_version_file(tmp_path):
    (tmp_path / "VERSION").write_text("0.2.10\n", encoding="utf-8")
    info = resolve(
        environ={
            "LORECHAT_VERSION": "",
            "LORECHAT_REVISION": "",
            "LORECHAT_COMMITS_AHEAD": "",
            "LORECHAT_CHANNEL": "",
        },
        repo_root=tmp_path,
    )
    assert info.version == "0.2.10"
    assert info.channel == "development"
    assert info.display == "0.2.10"


def test_env_release_with_ahead_is_development():
    info = resolve(
        environ={
            "LORECHAT_VERSION": "0.2.10",
            "LORECHAT_REVISION": "abc1234",
            "LORECHAT_COMMITS_AHEAD": "4",
            "LORECHAT_CHANNEL": "release",
        },
        repo_root=Path("/nonexistent"),
    )
    assert info.channel == "development"
    assert info.display == "0.2.10+4.gabc1234"


def test_version_file_without_git_is_development(tmp_path):
    (tmp_path / "VERSION").write_text("0.2.10\n", encoding="utf-8")
    info = resolve(environ={}, repo_root=tmp_path)
    assert info.version == "0.2.10"
    assert info.channel == "development"
    assert info.display == "0.2.10"
    assert info.revision == ""
