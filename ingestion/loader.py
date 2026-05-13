import json
import pandas as pd
from pathlib import Path
from langchain_community.document_loaders import (
    PyPDFLoader,
    TextLoader,
    UnstructuredWordDocumentLoader,
    CSVLoader,
)

from langchain_core.documents import Document

def load_document(file_path: str) -> list[Document]:
    """
    Dispatches file to the correct loader based on extension.
    Returns a list of LangChain Document objects.
    """
    ext = Path(file_path).suffix.lower()

    if ext == ".pdf":
        return PyPDFLoader(file_path).load()

    elif ext in (".txt", ".md"):
        return TextLoader(file_path, encoding="utf-8").load()

    elif ext == ".docx":
        return UnstructuredWordDocumentLoader(file_path).load()

    elif ext == ".csv":
        return CSVLoader(file_path).load()

    elif ext in (".xlsx", ".xls"):
        df = pd.read_excel(file_path, sheet_name=None)
        docs = []
        for sheet_name, sheet_df in df.items():
            text = f"Sheet: {sheet_name}\n{sheet_df.to_string(index=False)}"
            docs.append(Document(page_content=text, metadata={"sheet": sheet_name, "source": file_path}))
        return docs

    elif ext == ".json":
        with open(file_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        text = json.dumps(data, indent=2)
        return [Document(page_content=text, metadata={"source": file_path})]

    else:
        raise ValueError(f"Unsupported file format: {ext}")
