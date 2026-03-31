"""
Regression tests for Claude API overload retry logic.

Root cause: Anthropic returns 529 overloaded_error under load.
Without retry, the query fails immediately with "發生錯誤，請稍後再試".
Fix: exponential backoff retry up to _MAX_RETRIES on APIStatusError(529).
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch, call
from anthropic import APIStatusError

from app.services.rag import _call_claude_with_retry, stream_query_law, _MAX_RETRIES


def _make_overload_error():
    """Build an APIStatusError that mimics the 529 overloaded_error response."""
    mock_response = MagicMock()
    mock_response.status_code = 529
    mock_response.headers = {}
    return APIStatusError(
        message="Overloaded",
        response=mock_response,
        body={"type": "error", "error": {"type": "overloaded_error", "message": "Overloaded"}},
    )


# ---------------------------------------------------------------------------
# _call_claude_with_retry unit tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_retry_succeeds_on_second_attempt():
    """Factory that fails once with 529, then succeeds — should return the value."""
    attempts = []

    async def factory():
        attempts.append(1)
        if len(attempts) == 1:
            raise _make_overload_error()
        return "answer"

    with patch("app.services.rag.asyncio.sleep", new_callable=AsyncMock):
        result = await _call_claude_with_retry(factory)

    assert result == "answer"
    assert len(attempts) == 2


@pytest.mark.asyncio
async def test_retry_exhausted_raises():
    """Factory that always raises 529 — should re-raise after _MAX_RETRIES."""
    async def factory():
        raise _make_overload_error()

    with patch("app.services.rag.asyncio.sleep", new_callable=AsyncMock):
        with pytest.raises(APIStatusError):
            await _call_claude_with_retry(factory)


@pytest.mark.asyncio
async def test_non_529_error_not_retried():
    """A 500 error should NOT be retried — fail immediately."""
    mock_response = MagicMock()
    mock_response.status_code = 500
    mock_response.headers = {}
    error_500 = APIStatusError(
        message="Internal Server Error",
        response=mock_response,
        body={},
    )
    attempts = []

    async def factory():
        attempts.append(1)
        raise error_500

    with patch("app.services.rag.asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
        with pytest.raises(APIStatusError):
            await _call_claude_with_retry(factory)

    assert len(attempts) == 1
    mock_sleep.assert_not_called()


# ---------------------------------------------------------------------------
# stream_query_law retry integration test
# ---------------------------------------------------------------------------

def _make_mock_row(similarity=0.85):
    row = MagicMock()
    row.article_number = "84"
    row.title = "工資"
    row.content = "工資由勞雇雙方議定之。"
    row.law_id = "N0030001"
    row.law_name = "勞動基準法"
    row.similarity = similarity
    return row


def _make_stream_cm(raise_on_enter=False):
    """Build a sync callable that returns an async context manager.
    client.messages.stream(...) is called as a regular function returning a CM.
    """
    cm = MagicMock()
    if raise_on_enter:
        async def _enter(self):
            raise _make_overload_error()
    else:
        async def _enter(self):
            stream_mock = MagicMock()
            async def _text_stream():
                yield "工資由勞雇雙方"
            stream_mock.text_stream = _text_stream()
            return stream_mock
    async def _exit(self, *a):
        pass
    cm.__aenter__ = _enter
    cm.__aexit__ = _exit
    return cm


@pytest.mark.asyncio
async def test_stream_retries_on_overload_then_succeeds(mock_embedder):
    """Stream path: first attempt overloaded, second succeeds — yields tokens."""
    attempt_count = [0]

    def fake_stream_factory(*args, **kwargs):
        attempt_count[0] += 1
        return _make_stream_cm(raise_on_enter=(attempt_count[0] == 1))

    mock_db = AsyncMock()
    rows = [_make_mock_row(0.9)]

    with patch("app.services.rag.get_embedder", return_value=mock_embedder), \
         patch("app.services.rag._hybrid_search", AsyncMock(return_value=rows)), \
         patch("app.services.rag._generate_hypothetical_doc", AsyncMock(return_value="假設法條")), \
         patch("app.services.rag.asyncio.sleep", new_callable=AsyncMock), \
         patch("app.services.rag.AsyncAnthropic") as MockClient:
        MockClient.return_value.messages.stream = fake_stream_factory
        events = []
        async for event in stream_query_law("加班費怎麼算", mock_db, role="employee"):
            events.append(event)

    types = [e["type"] for e in events]
    assert "error" not in types, f"Got error event after retry: {events}"
    assert "token" in types


@pytest.mark.asyncio
async def test_stream_yields_error_after_all_retries_exhausted(mock_embedder):
    """Stream path: all attempts fail with 529 — must yield error event, not crash."""
    def always_overloaded(*args, **kwargs):
        return _make_stream_cm(raise_on_enter=True)

    mock_db = AsyncMock()
    rows = [_make_mock_row(0.9)]

    with patch("app.services.rag.get_embedder", return_value=mock_embedder), \
         patch("app.services.rag._hybrid_search", AsyncMock(return_value=rows)), \
         patch("app.services.rag._generate_hypothetical_doc", AsyncMock(return_value="假設法條")), \
         patch("app.services.rag.asyncio.sleep", new_callable=AsyncMock), \
         patch("app.services.rag.AsyncAnthropic") as MockClient:
        MockClient.return_value.messages.stream = always_overloaded
        events = []
        async for event in stream_query_law("加班費怎麼算", mock_db, role="employee"):
            events.append(event)

    error_events = [e for e in events if e["type"] == "error"]
    assert len(error_events) == 1, f"Expected exactly 1 error event, got: {events}"
