import pytest
from unittest.mock import MagicMock


@pytest.fixture
def mock_embedder(monkeypatch):
    """Returns a fixed 1024-dim vector for any input — avoids loading bge-m3 in tests."""
    mock = MagicMock()
    mock.get_text_embedding.return_value = [0.1] * 1024
    mock.get_text_embedding_batch.return_value = [[0.1] * 1024]
    return mock
