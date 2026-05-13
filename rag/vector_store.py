from langchain_community.vectorstores import FAISS
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_core.documents import Document
from config.settings import settings

EMBED_MODEL = settings.embed_model
INDEX_PATH = settings.faiss_index_path


def build_index(documents: list[Document]) -> FAISS:
    """Chunk documents and build FAISS index."""
    splitter = RecursiveCharacterTextSplitter(chunk_size=500, chunk_overlap=50)
    chunks = splitter.split_documents(documents)
    embedder = HuggingFaceEmbeddings(model_name=EMBED_MODEL)
    db = FAISS.from_documents(chunks, embedder)
    db.save_local(INDEX_PATH)
    return db


def load_index() -> FAISS:
    """Load persisted FAISS index from disk."""
    embedder = HuggingFaceEmbeddings(model_name=EMBED_MODEL)
    return FAISS.load_local(INDEX_PATH, embedder, allow_dangerous_deserialization=True)


def retrieve(query: str, db: FAISS, k: int = None) -> list[str]:
    """Return top-k relevant text chunks for a query."""
    if k is None:
        k = settings.top_k_chunks
    results = db.similarity_search(query, k=k)
    return [doc.page_content for doc in results]
