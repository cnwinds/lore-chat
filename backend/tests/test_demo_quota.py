import pytest

from app.demo.quota import DemoQuota, DemoQuotaExceeded


def test_allows_within_session_limit():
    q = DemoQuota(per_session=2)
    q.acquire("s1", "1.1.1.1"); q.release()
    q.acquire("s1", "1.1.1.1"); q.release()


def test_blocks_over_session_limit():
    q = DemoQuota(per_session=1)
    q.acquire("s1", "1.1.1.1"); q.release()
    with pytest.raises(DemoQuotaExceeded) as e:
        q.acquire("s1", "1.1.1.1")
    assert e.value.code == "demo_quota_exceeded"


def test_session_limit_is_per_session():
    q = DemoQuota(per_session=1)
    q.acquire("s1", "1.1.1.1"); q.release()
    q.acquire("s2", "1.1.1.1"); q.release()


def test_blocks_over_ip_hourly_limit():
    q = DemoQuota(per_session=100, per_ip_hourly=1)
    q.acquire("s1", "1.1.1.1"); q.release()
    with pytest.raises(DemoQuotaExceeded) as e:
        q.acquire("s2", "1.1.1.1")
    assert e.value.code == "demo_quota_exceeded"


def test_blocks_over_daily_total():
    q = DemoQuota(per_session=100, per_ip_hourly=100, daily_total=1)
    q.acquire("s1", "1.1.1.1"); q.release()
    with pytest.raises(DemoQuotaExceeded):
        q.acquire("s2", "2.2.2.2")


def test_quota_message_includes_deploy_cta():
    q = DemoQuota(per_session=1)
    q.acquire("s1", "1.1.1.1")
    q.release()
    with pytest.raises(DemoQuotaExceeded) as e:
        q.acquire("s1", "1.1.1.1")
    assert "部署你自己的 Lore" in e.value.message


def test_blocks_over_concurrency_without_release():
    q = DemoQuota(per_session=100, per_ip_hourly=100, max_concurrent=1)
    q.acquire("s1", "1.1.1.1")
    with pytest.raises(DemoQuotaExceeded) as e:
        q.acquire("s2", "2.2.2.2")
    assert e.value.code == "demo_busy"
