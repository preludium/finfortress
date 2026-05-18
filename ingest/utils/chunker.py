from __future__ import annotations

from typing import List

from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter

_DEFAULT_SPLITTER = RecursiveCharacterTextSplitter(
    chunk_size=512,
    chunk_overlap=64,
    separators=["\n\n", "\n", ". ", " "],
)

_LEGAL_SPLITTER = RecursiveCharacterTextSplitter(
    chunk_size=1024,
    chunk_overlap=128,
    separators=["\n\n", "\n", ". ", " "],
)


def chunk_documents(docs: List[Document]) -> List[Document]:
    """Split documents into chunks. Legal text uses larger chunk size."""
    result: List[Document] = []
    for doc in docs:
        splitter = (
            _LEGAL_SPLITTER
            if doc.metadata.get("content_type") == "legal_text"
            else _DEFAULT_SPLITTER
        )
        chunks = splitter.split_documents([doc])
        total = len(chunks)
        for i, chunk in enumerate(chunks):
            chunk.metadata["chunk_index"] = i
            chunk.metadata["chunk_total"] = total
        result.extend(chunks)
    return result
