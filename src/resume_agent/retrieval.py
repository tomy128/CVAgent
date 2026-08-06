"""LangChain-backed semantic retrieval with deterministic hybrid ranking."""

from collections import defaultdict
import hashlib
import math

from langchain_core.documents import Document
from langchain_core.embeddings import Embeddings
from langchain_core.vectorstores import InMemoryVectorStore

from resume_agent.evidence import search_evidence, tokenize
from resume_agent.domain import EvidenceChunk, Requirement, RequirementRetrieval, RetrievalHit


class DeterministicHashEmbeddings(Embeddings):
    """Small offline embedding implementation for demos and deterministic tests."""

    def __init__(self, size: int = 64) -> None:
        self.size = size

    def _embed(self, text: str) -> list[float]:
        vector = [0.0] * self.size
        for token in tokenize(text):
            digest = hashlib.sha256(token.encode()).digest()
            index = int.from_bytes(digest[:4], "big") % self.size
            vector[index] += -1.0 if digest[4] & 1 else 1.0
        norm = math.sqrt(sum(value * value for value in vector)) or 1.0
        return [value / norm for value in vector]

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [self._embed(text) for text in texts]

    def embed_query(self, text: str) -> list[float]:
        return self._embed(text)


class HybridRetriever:
    """Build a per-process vector index and fuse lexical and semantic rankings."""

    def __init__(self, embeddings: Embeddings) -> None:
        self.embeddings = embeddings
        self._store: InMemoryVectorStore | None = None
        self._signature: tuple[str, ...] = ()

    def build(self, chunks: list[EvidenceChunk]) -> None:
        signature = tuple(f"{item.id}:{item.content_hash}" for item in chunks)
        if self._store is not None and signature == self._signature:
            return
        if not chunks:
            raise ValueError("No usable resume or supplemental source content found")
        documents = [
            Document(
                page_content=item.content,
                metadata={
                    "evidence_id": item.id,
                    "source": item.source,
                    "chunk_index": item.chunk_index,
                    "content_hash": item.content_hash,
                    "source_kind": item.source_kind,
                },
            )
            for item in chunks
        ]
        self._store = InMemoryVectorStore.from_documents(documents, self.embeddings)
        self._signature = signature

    def retrieve(
        self,
        requirement: Requirement,
        chunks: list[EvidenceChunk],
        attempt: int = 0,
        retry_context: list[str] | None = None,
    ) -> RequirementRetrieval:
        self.build(chunks)
        limit = 8 if attempt else 4
        query_parts = [requirement.description, *requirement.keywords]
        if retry_context:
            query_parts.extend(retry_context)
        query = " ".join(part.strip() for part in query_parts if part.strip())

        lexical_requirement = requirement.model_copy(update={"description": query})
        lexical = search_evidence(lexical_requirement, chunks, limit)
        assert self._store is not None
        semantic_docs = self._store.similarity_search(query, k=min(limit, len(chunks)))
        semantic_ids = [str(item.metadata["evidence_id"]) for item in semantic_docs]

        scores: dict[str, float] = defaultdict(float)
        ranks: dict[str, dict[str, int]] = defaultdict(dict)
        for rank, chunk in enumerate(lexical, start=1):
            scores[chunk.id] += 2 / (60 + rank)
            ranks[chunk.id]["lexical"] = rank
        for rank, evidence_id in enumerate(semantic_ids, start=1):
            scores[evidence_id] += 1 / (60 + rank)
            ranks[evidence_id]["semantic"] = rank

        ordered = sorted(scores, key=lambda item: (-scores[item], item))
        hits = [
            RetrievalHit(
                evidence_id=evidence_id,
                methods=[method for method in ("lexical", "semantic") if method in ranks[evidence_id]],
                lexical_rank=ranks[evidence_id].get("lexical"),
                semantic_rank=ranks[evidence_id].get("semantic"),
                fused_score=scores[evidence_id],
            )
            for evidence_id in ordered[:limit]
        ]
        return RequirementRetrieval(
            requirement_id=requirement.id,
            query=query,
            attempt=attempt,
            hits=hits,
        )
