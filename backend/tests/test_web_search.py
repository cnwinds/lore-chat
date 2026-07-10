import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.config import Settings
from app.engine.web.search import WebSearch, TavilyProvider


@pytest.mark.asyncio
async def test_tavily_provider_parses_results():
    provider = TavilyProvider("test-key")
    mock_data = {"results": [{"title": "A", "url": "https://a.com", "content": "snippet a"}]}
    with patch("app.engine.web.search.httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_resp = MagicMock()
        mock_resp.json.return_value = mock_data
        mock_resp.raise_for_status = MagicMock()
        mock_post.return_value = mock_resp
        results = await provider.search("test", k=3)
    assert len(results) == 1
    assert results[0].title == "A"
    assert results[0].snippet == "snippet a"


def test_web_search_picks_first_configured_provider():
    settings = Settings(serper_api_key="sk-test", tavily_api_key=None, brave_search_api_key=None)
    ws = WebSearch(settings)
    assert ws.provider_name == "serper"


def test_web_search_no_provider():
    settings = Settings(tavily_api_key=None, serper_api_key=None, brave_search_api_key=None)
    ws = WebSearch(settings)
    assert ws.provider is None
