"""沙箱代理环境改写。"""

from app.engine.sandbox.opensandbox_runtime import _rewrite_proxy_host_for_sandbox


def test_rewrite_host_docker_internal():
    assert (
        _rewrite_proxy_host_for_sandbox(
            "http://host.docker.internal:7890", "172.17.0.1"
        )
        == "http://172.17.0.1:7890"
    )


def test_rewrite_keeps_other_hosts():
    assert (
        _rewrite_proxy_host_for_sandbox("http://proxy.example:8080", "172.17.0.1")
        == "http://proxy.example:8080"
    )
