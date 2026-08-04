"""Read-only evidence loading and deterministic lexical retrieval."""

import hashlib
import re
from pathlib import Path

from resume_agent.models import EvidenceChunk, Requirement

SUPPORTED_SUFFIXES = {".md", ".txt"}
TOKEN_PATTERN = re.compile(r"[A-Za-z][A-Za-z0-9_+.#/-]*|[\u4e00-\u9fff]{2,}")


def read_text_file(path: Path) -> str:
    resolved = path.expanduser().resolve()
    if not resolved.is_file():
        raise ValueError(f"Input file does not exist: {path}")
    if resolved.suffix.lower() not in SUPPORTED_SUFFIXES:
        raise ValueError(f"Unsupported input type: {resolved.suffix or '<none>'}")
    return resolved.read_text(encoding="utf-8")


def load_evidence(resume_path: Path, evidence_dir: Path | None) -> list[EvidenceChunk]:
    paths = [resume_path.expanduser().resolve()]
    if evidence_dir is not None:
        root = evidence_dir.expanduser().resolve()
        if not root.is_dir():
            raise ValueError(f"Evidence directory does not exist: {evidence_dir}")
        paths.extend(
            path for path in sorted(root.rglob("*"))
            if path.is_file() and path.suffix.lower() in SUPPORTED_SUFFIXES
        )

    chunks: list[EvidenceChunk] = []
    seen: set[Path] = set()
    for path in paths:
        if path in seen:
            continue
        seen.add(path)
        text = read_text_file(path)
        for index, content in enumerate(split_text(text), start=1):
            digest = hashlib.sha1(f"{path}:{index}:{content}".encode()).hexdigest()[:10]
            chunks.append(EvidenceChunk(id=f"ev-{digest}", source=str(path), content=content))
    return chunks


def split_text(text: str, max_chars: int = 1200) -> list[str]:
    paragraphs = [part.strip() for part in re.split(r"\n\s*\n", text) if part.strip()]
    chunks: list[str] = []
    for paragraph in paragraphs:
        if len(paragraph) <= max_chars:
            chunks.append(paragraph)
            continue
        chunks.extend(
            paragraph[start : start + max_chars]
            for start in range(0, len(paragraph), max_chars)
        )
    return chunks


def tokenize(text: str) -> set[str]:
    return {token.lower() for token in TOKEN_PATTERN.findall(text)}


def search_evidence(
    requirement: Requirement,
    chunks: list[EvidenceChunk],
    limit: int = 4,
) -> list[EvidenceChunk]:
    query_tokens = tokenize(" ".join([requirement.description, *requirement.keywords]))
    ranked: list[tuple[int, EvidenceChunk]] = []
    for chunk in chunks:
        content_tokens = tokenize(chunk.content)
        overlap = len(query_tokens & content_tokens)
        phrase_bonus = sum(
            2 for keyword in requirement.keywords
            if keyword and keyword.lower() in chunk.content.lower()
        )
        score = overlap + phrase_bonus
        if score:
            ranked.append((score, chunk))
    ranked.sort(key=lambda item: (-item[0], item[1].id))
    return [chunk for _, chunk in ranked[:limit]]
