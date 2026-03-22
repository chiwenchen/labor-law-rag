import threading

from llama_index.embeddings.huggingface import HuggingFaceEmbedding

_embedder: HuggingFaceEmbedding | None = None
_lock = threading.Lock()


def get_embedder() -> HuggingFaceEmbedding:
    global _embedder
    if _embedder is None:
        with _lock:
            if _embedder is None:  # double-checked locking
                try:
                    _embedder = HuggingFaceEmbedding(
                        model_name="BAAI/bge-m3",
                        embed_batch_size=32,
                    )
                except Exception as e:
                    raise RuntimeError(f"Failed to initialize embedding model BAAI/bge-m3: {e}") from e
    return _embedder
