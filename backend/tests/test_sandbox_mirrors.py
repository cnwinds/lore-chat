"""沙箱软件源切换。"""

from app.engine.sandbox.mirrors import (
    apt_configure_script,
    mirror_env,
    normalize_mirror_region,
)


def test_normalize_mirror_region():
    assert normalize_mirror_region("cn") == "cn"
    assert normalize_mirror_region("global") == "global"
    assert normalize_mirror_region("china") == "cn"
    assert normalize_mirror_region("intl") == "global"
    assert normalize_mirror_region(None) == "cn"


def test_mirror_env_cn_has_aliyun():
    env = mirror_env("cn")
    assert "aliyun" in env["PIP_INDEX_URL"]
    assert "npmmirror" in env["npm_config_registry"]
    assert env["LORECHAT_MIRROR_REGION"] == "cn"


def test_mirror_env_global_official():
    env = mirror_env("global")
    assert "pypi.org" in env["PIP_INDEX_URL"]
    assert "npmjs.org" in env["npm_config_registry"]


def test_apt_scripts_mention_mirrors():
    cn = apt_configure_script("cn")
    assert "mirrors.aliyun.com" in cn
    assert "npmmirror" in cn
    gl = apt_configure_script("global")
    assert "deb.debian.org" in gl
