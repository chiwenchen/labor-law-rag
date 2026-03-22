from app.services.embedder import get_embedder


def test_embedder_returns_1024_dim_vector():
    embedder = get_embedder()
    vector = embedder.get_text_embedding("員工特休假天數規定")
    assert len(vector) == 1024
    assert all(isinstance(v, float) for v in vector)


def test_embedder_is_singleton():
    assert get_embedder() is get_embedder()
