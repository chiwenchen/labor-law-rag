import sys
from unittest.mock import MagicMock

# Stub out heavy dependencies before importing scheduler modules
_llama_mock = MagicMock()
sys.modules.setdefault("llama_index", _llama_mock)
sys.modules.setdefault("llama_index.embeddings", _llama_mock)
sys.modules.setdefault("llama_index.embeddings.huggingface", _llama_mock)

import pytest
from unittest.mock import AsyncMock, patch
from app.services.scheduler import run_law_update
from app.services.indexer import IndexResult


@pytest.mark.asyncio
async def test_run_law_update_success_writes_log():
    """Successful update writes a 'success' log entry per law."""
    mock_articles = [MagicMock()]
    mock_result = IndexResult(inserted=5, updated=2, skipped=80)

    mock_session = AsyncMock()
    mock_cm = AsyncMock()
    mock_cm.__aenter__ = AsyncMock(return_value=mock_session)
    mock_cm.__aexit__ = AsyncMock(return_value=False)

    with patch("app.services.scheduler.fetch_law", return_value=mock_articles), \
         patch("app.services.scheduler.upsert_articles", return_value=mock_result), \
         patch("app.services.scheduler.AsyncSessionLocal", return_value=mock_cm):
        await run_law_update()

    # One add() call per law in LAW_REGISTRY (for the log entry)
    assert mock_session.add.called
    # Check the last log entry written has status success
    log = mock_session.add.call_args[0][0]
    assert log.status == "success"
    assert log.articles_changed == 7  # 5 inserted + 2 updated


@pytest.mark.asyncio
async def test_run_law_update_failure_writes_error_log():
    """Failed update writes a 'failed' log entry with error_message."""
    mock_session = AsyncMock()
    mock_cm = AsyncMock()
    mock_cm.__aenter__ = AsyncMock(return_value=mock_session)
    mock_cm.__aexit__ = AsyncMock(return_value=False)

    with patch("app.services.scheduler.fetch_law",
               side_effect=Exception("Connection timeout")), \
         patch("app.services.scheduler.AsyncSessionLocal", return_value=mock_cm):
        await run_law_update()  # Should NOT raise

    assert mock_session.add.called
    log = mock_session.add.call_args[0][0]
    assert log.status == "failed"
    assert "Connection timeout" in log.error_message
