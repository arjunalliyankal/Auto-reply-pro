from langchain_huggingface import HuggingFaceEmbeddings
from config.settings import settings

EMBED_MODEL = settings.embed_model


def get_embedder() -> HuggingFaceEmbeddings:
    """Returns a HuggingFace sentence-transformers embedder."""
    return HuggingFaceEmbeddings(model_name=EMBED_MODEL)
