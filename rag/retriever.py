from langchain_community.vectorstores import FAISS
from rag.vector_store import retrieve as _retrieve
from config.settings import settings


def get_context(query: str, db: FAISS, k: int = None) -> list[str]:
    """
    High-level retriever: returns top-k context chunks for a query.

    Args:
        query: Incoming message text.
        db: Loaded FAISS vector store.
        k: Number of chunks to retrieve (defaults to settings.top_k_chunks).

    Returns:
        List of relevant text chunks.
    """
    if k is None:
        k = settings.top_k_chunks
    return _retrieve(query, db, k=k)
