from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class KnowledgeChunk:
    chunk_id: str
    source: str
    heading: str
    content: str


DEFAULT_KNOWLEDGE_FILES = [
    "reimbursement-policy.md",
    "approval-rules.md",
    "reconciliation-sop.md",
]


def default_knowledge_dir() -> Path:
    return Path(__file__).resolve().parents[3] / "knowledge"


def load_knowledge_base(knowledge_dir: Path | None = None, files: list[str] | None = None) -> list[KnowledgeChunk]:
    root = knowledge_dir or default_knowledge_dir()
    chunks: list[KnowledgeChunk] = []
    for filename in files or DEFAULT_KNOWLEDGE_FILES:
        chunks.extend(load_markdown_chunks(root / filename))
    return chunks


def load_markdown_chunks(path: Path) -> list[KnowledgeChunk]:
    if not path.exists():
        return []

    chunks: list[KnowledgeChunk] = []
    heading = path.stem
    paragraph_lines: list[str] = []
    chunk_index = 1

    def flush() -> None:
        nonlocal paragraph_lines, chunk_index
        content = normalize_content("\n".join(paragraph_lines))
        paragraph_lines = []
        if not content:
            return
        chunks.append(
            KnowledgeChunk(
                chunk_id=f"{path.name}#{chunk_index}",
                source=path.name,
                heading=heading,
                content=content,
            )
        )
        chunk_index += 1

    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line:
            flush()
            continue
        if line.startswith("#"):
            flush()
            heading = line.lstrip("#").strip() or path.stem
            continue
        paragraph_lines.append(line)
    flush()
    return chunks


def normalize_content(text: str) -> str:
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    return " ".join(lines)
