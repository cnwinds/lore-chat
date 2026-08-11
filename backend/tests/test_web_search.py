from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from app.config import Settings
from app.engine.web.search import SearchResult, TavilyProvider, WebSearch
from app.engine.web.search_providers import (
    DuplicateSearchProviderError,
    migrate_search_providers,
    parse_search_providers,
    validate_search_providers_unique,
)
from app.engine.web.search_router import (
    NoSearchProviderAvailable,
    resolve_search_candidates,
    select_search_provider,
)
from app.models.cooldown import CooldownStore, ErrorClass


@pytest.mark.asyncio
async def test_tavily_provider_parses_results():
    provider = TavilyProvider("test-key")
    mock_data = {"results": [{"title": "A", "url": "https://a.com", "content": "snippet a"}]}
    with patch(
        "app.engine.web.search_backends.httpx.AsyncClient.post", new_callable=AsyncMock
    ) as mock_post:
        mock_resp = MagicMock()
        mock_resp.json.return_value = mock_data
        mock_resp.raise_for_status = MagicMock()
        mock_post.return_value = mock_resp
        results = await provider.search("test", k=3)
    assert len(results) == 1
    assert results[0].title == "A"
    assert results[0].snippet == "snippet a"


def test_web_search_no_provider(tmp_path):
    settings = Settings(
        kb_path=tmp_path,
        tavily_api_key=None,
        serper_api_key=None,
        brave_search_api_key=None,
        search_providers=[],
    )
    ws = WebSearch(settings, cooldown=CooldownStore(settings.kb_path / '.kb' / 'search_cd.json'))
    assert ws.provider is None


def test_web_search_picks_first_configured_provider(tmp_path):
    settings = Settings(
        kb_path=tmp_path,
        serper_api_key="sk-test",
        tavily_api_key=None,
        brave_search_api_key=None,
        search_providers=None,
    )
    ws = WebSearch(settings, cooldown=CooldownStore(settings.kb_path / '.kb' / 'search_cd.json'))
    assert ws.provider is not None


def test_migrate_from_legacy_keys_and_order():
    data = migrate_search_providers(
        {
            "tavily_api_key": "tv-key",
            "serper_api_key": "sp-key",
            "brave_search_api_key": None,
            "search_provider_order": "serper,tavily,brave",
        }
    )
    entries = parse_search_providers(data["search_providers"])
    assert [e.provider for e in entries] == ["serper", "tavily"]
    assert entries[0].api_key == "sp-key"
    assert data["search_provider_order"] == "serper,tavily"


def test_migrate_honors_explicit_empty_chain():
    data = migrate_search_providers(
        {
            "tavily_api_key": "tv-key",
            "serper_api_key": "sp-key",
            "search_providers": [],
        }
    )
    assert data["search_providers"] == []
    assert data["tavily_api_key"] is None
    assert data["serper_api_key"] is None


def test_validate_duplicate_provider():
    with pytest.raises(DuplicateSearchProviderError, match="duplicate"):
        validate_search_providers_unique(
            [
                {"id": "tavily", "provider": "tavily", "api_key": "a"},
                {"id": "tavily2", "provider": "tavily", "api_key": "b"},
            ]
        )


def test_resolve_instantiates_provider(tmp_path):
    settings = Settings(
        kb_path=tmp_path,
        search_providers=[
            {"id": "tavily", "provider": "tavily", "api_key": "a"},
        ],
    )
    cands = resolve_search_candidates(settings)
    assert len(cands) == 1
    assert cands[0].entry.provider == "tavily"
    assert cands[0].provider is not None


def test_select_skips_cooling(tmp_path):
    settings = Settings(
        kb_path=tmp_path,
        search_providers=[
            {"id": "tavily", "provider": "tavily", "api_key": "a"},
            {"id": "serper", "provider": "serper", "api_key": "b"},
        ],
    )
    store = CooldownStore(tmp_path / "cd.json")
    store.record_failure("tavily", ErrorClass.RATE_LIMIT, error="429")
    sel = select_search_provider(settings, store)
    assert sel.entry.id == "serper"
    assert sel.failover is True
    assert sel.candidate.provider is not None


@pytest.mark.asyncio
async def test_search_failover_on_http_error(tmp_path):
    settings = Settings(
        kb_path=tmp_path,
        search_providers=[
            {"id": "tavily", "provider": "tavily", "api_key": "bad"},
            {"id": "serper", "provider": "serper", "api_key": "good"},
        ],
    )
    store = CooldownStore(tmp_path / "cd.json")
    ws = WebSearch(settings, cooldown=store)

    async def fake_search(self, query: str, k: int = 5):
        if self._api_key == "bad":
            raise httpx.HTTPStatusError(
                "rate limit",
                request=MagicMock(),
                response=MagicMock(status_code=429),
            )
        return [SearchResult(title="ok", url="https://x.com", snippet="s")]

    with patch("app.engine.web.search_backends.TavilyProvider.search", fake_search), patch(
        "app.engine.web.search_backends.SerperProvider.search", fake_search
    ):
        results, err = await ws.search("q", k=3)

    assert err is None
    assert len(results) == 1
    assert ws.provider_name == "serper"
    assert not store.is_available("tavily")
    assert store.is_available("serper")


@pytest.mark.asyncio
async def test_search_auth_disables_provider(tmp_path):
    settings = Settings(
        kb_path=tmp_path,
        search_providers=[
            {"id": "tavily", "provider": "tavily", "api_key": "bad"},
            {"id": "serper", "provider": "serper", "api_key": "good"},
        ],
    )
    store = CooldownStore(tmp_path / "cd.json")
    ws = WebSearch(settings, cooldown=store)

    async def fail_auth(self, query: str, k: int = 5):
        raise httpx.HTTPStatusError(
            "Invalid API Key",
            request=MagicMock(),
            response=MagicMock(status_code=401),
        )

    async def ok(self, query: str, k: int = 5):
        return [SearchResult(title="ok", url="https://x.com", snippet="s")]

    with patch("app.engine.web.search_backends.TavilyProvider.search", fail_auth), patch(
        "app.engine.web.search_backends.SerperProvider.search", ok
    ):
        results, err = await ws.search("q")

    assert err is None
    assert store.get("tavily").disabled is True
    with pytest.raises(NoSearchProviderAvailable):
        select_search_provider(settings, store, exclude_ids={"serper"})


def test_clear_cooldown_restores_provider(tmp_path):
    settings = Settings(
        kb_path=tmp_path,
        search_providers=[
            {"id": "tavily", "provider": "tavily", "api_key": "a"},
            {"id": "serper", "provider": "serper", "api_key": "b"},
        ],
    )
    store = CooldownStore(tmp_path / "cd.json")
    store.record_failure("tavily", ErrorClass.AUTH, error="Invalid API Key")
    assert store.get("tavily").disabled is True
    assert select_search_provider(settings, store).entry.id == "serper"

    store.reenable("tavily")
    assert store.is_available("tavily")
    assert select_search_provider(settings, store).entry.id == "tavily"


@pytest.mark.asyncio
async def test_empty_results_not_failure(tmp_path):
    settings = Settings(
        kb_path=tmp_path,
        search_providers=[
            {"id": "tavily", "provider": "tavily", "api_key": "a"},
            {"id": "serper", "provider": "serper", "api_key": "b"},
        ],
    )
    store = CooldownStore(tmp_path / "cd.json")
    ws = WebSearch(settings, cooldown=store)

    async def empty(self, query: str, k: int = 5):
        return []

    with patch("app.engine.web.search_backends.TavilyProvider.search", empty):
        results, err = await ws.search("q")

    assert err is None
    assert results == []
    assert ws.provider_name == "tavily"
    assert store.is_available("tavily")
    assert store.get("tavily").consecutive_failures == 0
