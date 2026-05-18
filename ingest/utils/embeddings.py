from __future__ import annotations

import logging

import numpy as np
from sentence_transformers import SentenceTransformer

log = logging.getLogger(__name__)

EMBED_MODEL = "intfloat/multilingual-e5-large"
EMBED_DIM = 1024


class E5Embeddings:
    """multilingual-e5-large with required passage:/query: prefixes.

    e5 models degrade significantly without these prefixes — do not remove.
    """

    def __init__(self, model_name: str = EMBED_MODEL) -> None:
        log.info("Loading embedding model %s (first run ~2.2 GB download)…", model_name)
        self.model = SentenceTransformer(model_name)

    def embed_documents(self, texts: list[str], batch_size: int = 32) -> np.ndarray:
        prefixed = [f"passage: {t}" for t in texts]
        return self.model.encode(
            prefixed,
            batch_size=batch_size,
            show_progress_bar=False,
            normalize_embeddings=True,
        )

    def embed_query(self, text: str) -> list[float]:
        return self.model.encode(
            f"query: {text}",
            normalize_embeddings=True,
        ).tolist()
