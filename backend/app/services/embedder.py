from llama_index.embeddings.huggingface import HuggingFaceEmbedding

_embedder: HuggingFaceEmbedding | None = None


def get_embedder() -> HuggingFaceEmbedding:
    global _embedder
    if _embedder is None:
        _embedder = HuggingFaceEmbedding(
            model_name="BAAI/bge-m3",
            embed_batch_size=32,
        )
    return _embedder
