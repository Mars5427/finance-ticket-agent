from __future__ import annotations

import math
import re
from dataclasses import dataclass
from time import perf_counter
from typing import Any

from app.rag.documents import KnowledgeChunk, load_knowledge_base


TOKEN_PATTERN = re.compile(r"[\w]+|[\u4e00-\u9fff]{2,}")


@dataclass(frozen=True)
class RetrievalResult:
    source: str
    heading: str
    snippet: str
    score: float
    chunk_id: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "source": self.source,
            "heading": self.heading,
            "snippet": self.snippet,
            "score": self.score,
            "chunk_id": self.chunk_id,
        }


def retrieve_evidence(
    query: str,
    sources: list[str] | None = None,
    top_k: int = 3,
    min_score: float = 0.18,
    chunks: list[KnowledgeChunk] | None = None,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    started = perf_counter()
    all_chunks = chunks if chunks is not None else load_knowledge_base()
    scoped_chunks = [chunk for chunk in all_chunks if not sources or chunk.source in sources]
    query_tokens = tokenize(query)
    scored: list[RetrievalResult] = []

    for chunk in scoped_chunks:
        score = score_chunk(query_tokens, chunk)
        if score >= min_score:
            scored.append(
                RetrievalResult(
                    source=chunk.source,
                    heading=chunk.heading,
                    snippet=make_snippet(chunk.content),
                    score=round(score, 4),
                    chunk_id=chunk.chunk_id,
                )
            )

    scored.sort(key=lambda item: item.score, reverse=True)
    results = [item.as_dict() for item in scored[:top_k]]
    meta = {
        "query": query,
        "matched_sources": sorted({item["source"] for item in results}),
        "snippets": [item["snippet"] for item in results],
        "scores": [item["score"] for item in results],
        "elapsed_ms": int((perf_counter() - started) * 1000),
        "no_evidence_reason": None if results else "knowledge base did not contain a strong enough matching chunk",
    }
    return results, meta


def tokenize(text: str) -> set[str]:
    normalized = text.lower()
    tokens = set(TOKEN_PATTERN.findall(normalized))
    chinese_text = "".join(re.findall(r"[\u4e00-\u9fff]+", normalized))
    for index in range(max(len(chinese_text) - 1, 0)):
        tokens.add(chinese_text[index : index + 2])
    return {token for token in tokens if len(token) >= 2 and token not in STOP_WORDS}


def score_chunk(query_tokens: set[str], chunk: KnowledgeChunk) -> float:
    if not query_tokens:
        return 0.0
    content_tokens = tokenize(f"{chunk.heading} {chunk.content}")
    if not content_tokens:
        return 0.0
    overlap = query_tokens & content_tokens
    if not overlap:
        return 0.0
    recall = len(overlap) / len(query_tokens)
    precision = len(overlap) / math.sqrt(len(content_tokens))
    heading_bonus = 0.15 if query_tokens & tokenize(chunk.heading) else 0.0
    source_bonus = source_match_bonus(query_tokens, chunk.source)
    return recall * 0.7 + precision * 0.2 + heading_bonus + source_bonus


def source_match_bonus(query_tokens: set[str], source: str) -> float:
    source_tokens = tokenize(source.replace("-", " ").replace(".md", ""))
    return 0.1 if query_tokens & source_tokens else 0.0


def make_snippet(content: str, max_length: int = 160) -> str:
    if len(content) <= max_length:
        return content
    return f"{content[:max_length].rstrip()}..."


STOP_WORDS = {
    "the",
    "and",
    "or",
    "for",
    "with",
    "from",
    "this",
    "that",
    "what",
    "how",
    "can",
    "need",
    "needs",
    "是否",
    "什么",
    "怎么",
    "帮我",
}
