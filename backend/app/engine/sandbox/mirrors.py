"""沙箱软件源：国内 / 国外镜像配置。"""

from __future__ import annotations

from typing import Literal

MirrorRegion = Literal["cn", "global"]

VALID_MIRROR_REGIONS: frozenset[str] = frozenset({"cn", "global"})


def normalize_mirror_region(raw: str | None, *, default: MirrorRegion = "cn") -> MirrorRegion:
    v = (raw or "").strip().lower()
    if v in ("cn", "china", "domestic", "aliyun"):
        return "cn"
    if v in ("global", "intl", "international", "overseas", "default"):
        return "global"
    return default


def mirror_env(region: MirrorRegion) -> dict[str, str]:
    """注入沙箱进程环境（pip / uv / npm）。"""
    if region == "cn":
        return {
            "LORECHAT_MIRROR_REGION": "cn",
            "PIP_INDEX_URL": "https://mirrors.aliyun.com/pypi/simple/",
            "PIP_TRUSTED_HOST": "mirrors.aliyun.com",
            "UV_DEFAULT_INDEX": "https://mirrors.aliyun.com/pypi/simple/",
            "npm_config_registry": "https://registry.npmmirror.com",
        }
    return {
        "LORECHAT_MIRROR_REGION": "global",
        "PIP_INDEX_URL": "https://pypi.org/simple",
        "PIP_TRUSTED_HOST": "pypi.org files.pythonhosted.org",
        "UV_DEFAULT_INDEX": "https://pypi.org/simple",
        "npm_config_registry": "https://registry.npmjs.org",
    }


def apt_configure_script(region: MirrorRegion) -> str:
    """一次性配置 apt 源（debian.sources / sources.list）。幂等。"""
    if region == "cn":
        return r"""
set -e
if [ -f /etc/apt/sources.list.d/debian.sources ]; then
  sed -i 's|http://deb.debian.org|https://mirrors.aliyun.com|g' /etc/apt/sources.list.d/debian.sources
  sed -i 's|https://deb.debian.org|https://mirrors.aliyun.com|g' /etc/apt/sources.list.d/debian.sources
  sed -i 's|http://security.debian.org|https://mirrors.aliyun.com/debian-security|g' /etc/apt/sources.list.d/debian.sources
  sed -i 's|https://security.debian.org|https://mirrors.aliyun.com/debian-security|g' /etc/apt/sources.list.d/debian.sources
fi
if [ -f /etc/apt/sources.list ]; then
  sed -i 's|http://deb.debian.org|https://mirrors.aliyun.com|g' /etc/apt/sources.list
  sed -i 's|https://deb.debian.org|https://mirrors.aliyun.com|g' /etc/apt/sources.list
  sed -i 's|http://security.debian.org|https://mirrors.aliyun.com/debian-security|g' /etc/apt/sources.list
  sed -i 's|https://security.debian.org|https://mirrors.aliyun.com/debian-security|g' /etc/apt/sources.list
fi
mkdir -p /etc/pip
cat > /etc/pip.conf <<'EOF'
[global]
index-url = https://mirrors.aliyun.com/pypi/simple/
trusted-host = mirrors.aliyun.com
EOF
mkdir -p /root
cat > /root/.npmrc <<'EOF'
registry=https://registry.npmmirror.com
EOF
echo "lorechat-mirror=cn"
""".strip()
    return r"""
set -e
if [ -f /etc/apt/sources.list.d/debian.sources ]; then
  sed -i 's|https://mirrors.aliyun.com/debian-security|https://security.debian.org|g' /etc/apt/sources.list.d/debian.sources
  sed -i 's|http://mirrors.aliyun.com/debian-security|http://security.debian.org|g' /etc/apt/sources.list.d/debian.sources
  sed -i 's|https://mirrors.aliyun.com|https://deb.debian.org|g' /etc/apt/sources.list.d/debian.sources
  sed -i 's|http://mirrors.aliyun.com|http://deb.debian.org|g' /etc/apt/sources.list.d/debian.sources
fi
if [ -f /etc/apt/sources.list ]; then
  sed -i 's|https://mirrors.aliyun.com/debian-security|https://security.debian.org|g' /etc/apt/sources.list
  sed -i 's|http://mirrors.aliyun.com/debian-security|http://security.debian.org|g' /etc/apt/sources.list
  sed -i 's|https://mirrors.aliyun.com|https://deb.debian.org|g' /etc/apt/sources.list
  sed -i 's|http://mirrors.aliyun.com|http://deb.debian.org|g' /etc/apt/sources.list
fi
rm -f /etc/pip.conf
rm -f /root/.npmrc
echo "lorechat-mirror=global"
""".strip()
