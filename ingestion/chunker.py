from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_core.documents import Document


def chunk_documents(
    documents: list[Document],
    chunk_size: int = 500,
    chunk_overlap: int = 50,
) -> list[Document]:
    """
    Splits a list of LangChain Documents into smaller chunks.

    Args:
        documents: Raw loaded documents.
        chunk_size: Number of characters per chunk.
        chunk_overlap: Overlap between consecutive chunks.

    Returns:
        List of chunked Document objects.
    """
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
    )
    return splitter.split_documents(documents)
