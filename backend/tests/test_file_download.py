"""文件下载 MIME / disposition 策略。"""

from app.api.file_download import content_disposition_type, media_type_for_filename


def test_media_type_mp4():
    assert media_type_for_filename("周报.mp4") == "video/mp4"


def test_media_type_png():
    assert media_type_for_filename("shot.png") == "image/png"


def test_media_type_unknown_fallback():
    assert media_type_for_filename("data.bin") == "application/octet-stream"


def test_media_type_shell_is_text_plain():
    assert media_type_for_filename("gen_audio.sh") == "text/plain; charset=utf-8"


def test_inline_by_default_including_octet_stream():
    assert content_disposition_type("video/mp4") == "inline"
    assert content_disposition_type("image/png") == "inline"
    assert content_disposition_type("application/pdf") == "inline"
    assert content_disposition_type("application/octet-stream") == "inline"
    assert content_disposition_type("text/plain; charset=utf-8") == "inline"


def test_force_download_overrides_inline():
    assert (
        content_disposition_type("video/mp4", force_download=True) == "attachment"
    )
    assert (
        content_disposition_type(
            "application/octet-stream", force_download=True
        )
        == "attachment"
    )
