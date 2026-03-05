from __future__ import annotations

from dataclasses import dataclass, field
from langchain_chroma import Chroma
from sentence_transformers import CrossEncoder, SentenceTransformer


BI_ENCODER_MODEL    = "intfloat/multilingual-e5-base"
CROSS_ENCODER_MODEL = "cross-encoder/mmarco-mMiniLMv2-L12-H384-v1"
CHROMA_DIR          = "data/chroma_db"
COLLECTION_NAME     = "protocols"
CANDIDATE_K         = 20  



class _E5Embeddings:
    def __init__(self, model: SentenceTransformer):
        self._model = model

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return self._model.encode(
            [f"passage: {t}" for t in texts], normalize_embeddings=True
        ).tolist()

    def embed_query(self, text: str) -> list[float]:
        return self._model.encode(
            f"query: {text}", normalize_embeddings=True
        ).tolist()



@dataclass
class Retriever:
    chroma_dir:          str = CHROMA_DIR
    collection_name:     str = COLLECTION_NAME
    bi_encoder_model:    str = BI_ENCODER_MODEL
    cross_encoder_model: str = CROSS_ENCODER_MODEL
    candidate_k:         int = CANDIDATE_K

    _vectorstore:    Chroma       | None = field(default=None, init=False, repr=False)
    _cross_encoder:  CrossEncoder | None = field(default=None, init=False, repr=False)

    def _load(self) -> None:
        if self._vectorstore is not None and self._cross_encoder is not None:
            return
        bi_encoder = SentenceTransformer(self.bi_encoder_model)
        embeddings  = _E5Embeddings(bi_encoder)
        self._vectorstore = Chroma(
            persist_directory=self.chroma_dir,
            embedding_function=embeddings,
            collection_name=self.collection_name,
        )
        self._cross_encoder = CrossEncoder(self.cross_encoder_model)

    def search(
        self,
        query:     str,
        k:         int = 5,
        specialty: str | None = None,
    ) -> list[dict]:
        
        self._load()

        where = {"specialty": specialty} if specialty else None
        candidates = self._vectorstore.similarity_search(
            query, k=self.candidate_k, filter=where
        )

        if not candidates:
            return []

        pairs  = [(query, doc.page_content) for doc in candidates]
        scores = self._cross_encoder.predict(pairs)

        ranked = sorted(zip(scores, candidates), key=lambda x: x[0], reverse=True)

        return [
            {
                **doc.metadata,
                "score":        float(score),
                "page_content": doc.page_content,
            }
            for score, doc in ranked[:k]
        ]
