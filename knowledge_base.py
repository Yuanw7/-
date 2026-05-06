"""Knowledge base ingestion and retrieval for safety rules using Zhipu AI."""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Sequence, Tuple

import chromadb
from pydantic import ValidationError
from pypdf import PdfReader
from zhipuai import ZhipuAI

from models import RoomScene, SafetyConstraint


MODEL_EMBEDDING = "embedding-2"
CHROMA_DIR = Path(".chroma")
COLLECTION_NAME = "safety_specs"
DEFAULT_SPECS_DIR = Path("specs")
REQUIRED_REGULATION_KEYWORDS = ("gb50016", "gb50222", "gb50352", "gb50763")


@dataclass
class SafetyConstraintResult:
    """Safety constraint plus provenance grounding for paper generation."""
    constraint: SafetyConstraint
    snippet: str
    page_number: int
    source_file: str
    score: float


def _canonicalize_name(name: str) -> str:
    lowered = name.lower()
    return re.sub(r"[^a-z0-9]+", "", lowered)


def _create_client() -> ZhipuAI:
    api_key = os.getenv("ZHIPUAI_API_KEY")
    if not api_key:
        raise EnvironmentError("ZHIPUAI_API_KEY is not set.")
    return ZhipuAI(api_key=api_key)


def _get_collection():
    client = chromadb.PersistentClient(path=str(CHROMA_DIR))
    return client.get_or_create_collection(name=COLLECTION_NAME, metadata={"hnsw:space": "cosine"})


def _normalize_text(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def _tokenize(text: str) -> list[str]:
    return re.findall(r"[a-zA-Z0-9_]+", text.lower())


def _chunk_text(text: str, chunk_size: int = 1200, overlap: int = 200) -> list[str]:
    text = _normalize_text(text)
    if not text:
        return []

    if overlap >= chunk_size:
        raise ValueError("overlap must be smaller than chunk_size")

    chunks: list[str] = []
    start = 0
    while start < len(text):
        end = min(len(text), start + chunk_size)
        chunks.append(text[start:end])
        if end == len(text):
            break
        start = end - overlap
    return chunks


def _embed_texts(client: ZhipuAI, texts: Sequence[str], batch_size: int = 20) -> list[list[float]]:
    """Embed texts using Zhipu AI embedding-2 model. Returns list of embedding vectors."""
    embeddings: list[list[float]] = []
    text_list = list(texts)
    # ZhipuAI batch API: max 64 items per call
    for start in range(0, len(text_list), 64):
        chunk = text_list[start:start + 64]
        response = client.embeddings.create(model=MODEL_EMBEDDING, input=chunk)
        embeddings.extend([item.embedding for item in response.data])
    return embeddings


def _build_query_terms(room_scene: RoomScene) -> list[str]:
    terms: list[str] = []
    for item in room_scene.furniture:
        terms.append(item.name)
        terms.append(item.material)
    terms.extend(room_scene.boundary.walls)
    terms.extend(room_scene.boundary.windows)
    terms.extend(room_scene.boundary.doors)
    filtered = [_normalize_text(t) for t in terms if _normalize_text(t)]
    return list(dict.fromkeys(filtered))


def _query_text_from_room_scene(room_scene: RoomScene) -> str:
    query_parts = _build_query_terms(room_scene)
    return "Safety constraints for room with: " + ", ".join(query_parts)


def ingest_specs(specs_folder: str | Path = DEFAULT_SPECS_DIR) -> int:
    """Ingest PDF manuals from /specs into ChromaDB with Zhipu AI embeddings.

    Returns:
        Number of chunks indexed.
    """
    specs_path = Path(specs_folder).expanduser().resolve()
    if not specs_path.exists() or not specs_path.is_dir():
        raise FileNotFoundError(f"Specs folder not found: {specs_path}")

    pdf_paths = sorted(specs_path.glob("*.pdf"))
    if not pdf_paths:
        return 0

    canonical_pdf_names = [_canonicalize_name(path.stem) for path in pdf_paths]
    missing = [
        code
        for code in REQUIRED_REGULATION_KEYWORDS
        if not any(code in name for name in canonical_pdf_names)
    ]
    if missing:
        raise ValueError(
            "Missing required regulation PDFs in /specs. Expected files covering: " + ", ".join(missing)
        )

    genai_client = _create_client()
    collection = _get_collection()

    ids: list[str] = []
    docs: list[str] = []
    metadatas: list[Dict[str, object]] = []

    for pdf_path in pdf_paths:
        reader = PdfReader(str(pdf_path))
        for page_index, page in enumerate(reader.pages):
            page_text = _normalize_text(page.extract_text() or "")
            if not page_text:
                continue
            chunks = _chunk_text(page_text)
            for chunk_index, chunk in enumerate(chunks):
                chunk_id = f"{pdf_path.name}:p{page_index + 1}:c{chunk_index}"
                ids.append(chunk_id)
                docs.append(chunk)
                metadatas.append(
                    {
                        "source_file": pdf_path.name,
                        "page_number": page_index + 1,
                        "chunk_index": chunk_index,
                    }
                )

    if not docs:
        return 0

    embeddings = _embed_texts(genai_client, docs)
    collection.upsert(ids=ids, documents=docs, embeddings=embeddings, metadatas=metadatas)
    return len(docs)


def _keyword_score(text: str, query_terms: Sequence[str]) -> float:
    tokens = _tokenize(text)
    if not tokens:
        return 0.0
    corpus = " ".join(tokens)
    score = 0.0
    for term in query_terms:
        normalized = term.strip().lower()
        if not normalized:
            continue
        if normalized in corpus:
            score += 1.0
    return score


def _safe_constraint_from_snippet(snippet: str, query_terms: Sequence[str]) -> SafetyConstraint:
    terms = ", ".join(query_terms[:6]) if query_terms else "general room elements"
    return SafetyConstraint(
        rule_id=f"retrieved_rule_{abs(hash(snippet)) % 10_000_000}",
        material_requirement=f"Applies to: {terms}",
        minimum_clearance=0.0,
        source_document="ingested safety specifications",
    )


def query_safety_rules(room_scene: RoomScene, top_k: int = 5) -> list[SafetyConstraintResult]:
    """Hybrid (semantic + keyword) search over ingested manuals.

    Returns top-k constraints with snippet + page grounding for paper generation.
    """
    collection = _get_collection()
    query_terms = _build_query_terms(room_scene)
    if not query_terms:
        return []

    query_text = _query_text_from_room_scene(room_scene)
    genai_client = _create_client()
    query_embedding = _embed_texts(genai_client, [query_text])[0]

    # Semantic candidates (ANN over embeddings)
    semantic = collection.query(
        query_embeddings=[query_embedding],
        n_results=max(top_k * 4, 20),
        include=["documents", "metadatas", "distances"],
    )

    # Keyword candidates (lexical overlap over full corpus)
    lexical = collection.get(include=["documents", "metadatas"])

    candidate_scores: dict[Tuple[str, int, int], dict[str, object]] = {}

    semantic_docs = semantic.get("documents", [[]])[0]
    semantic_metas = semantic.get("metadatas", [[]])[0]
    semantic_distances = semantic.get("distances", [[]])[0]

    for doc, meta, distance in zip(semantic_docs, semantic_metas, semantic_distances):
        source_file = str(meta.get("source_file", "unknown.pdf"))
        page_number = int(meta.get("page_number", -1))
        chunk_index = int(meta.get("chunk_index", -1))
        key = (source_file, page_number, chunk_index)
        semantic_score = 1.0 / (1.0 + float(distance))
        lexical_score = _keyword_score(doc or "", query_terms)
        candidate_scores[key] = {
            "snippet": doc or "",
            "source_file": source_file,
            "page_number": page_number,
            "semantic_score": semantic_score,
            "lexical_score": lexical_score,
        }

    lexical_docs = lexical.get("documents") or []
    lexical_metas = lexical.get("metadatas") or []
    for doc, meta in zip(lexical_docs, lexical_metas):
        source_file = str(meta.get("source_file", "unknown.pdf"))
        page_number = int(meta.get("page_number", -1))
        chunk_index = int(meta.get("chunk_index", -1))
        key = (source_file, page_number, chunk_index)
        lexical_score = _keyword_score(doc or "", query_terms)
        if lexical_score <= 0:
            continue
        if key not in candidate_scores:
            candidate_scores[key] = {
                "snippet": doc or "",
                "source_file": source_file,
                "page_number": page_number,
                "semantic_score": 0.0,
                "lexical_score": lexical_score,
            }
        else:
            candidate_scores[key]["lexical_score"] = max(
                float(candidate_scores[key]["lexical_score"]), lexical_score
            )

    ranked = sorted(
        candidate_scores.values(),
        key=lambda item: 0.65 * float(item["semantic_score"]) + 0.35 * float(item["lexical_score"]),
        reverse=True,
    )

    results: list[SafetyConstraintResult] = []
    for item in ranked[:top_k]:
        snippet = str(item["snippet"])
        try:
            constraint = _safe_constraint_from_snippet(snippet, query_terms)
        except ValidationError:
            continue
        results.append(
            SafetyConstraintResult(
                constraint=constraint,
                snippet=snippet,
                page_number=int(item["page_number"]),
                source_file=str(item["source_file"]),
                score=0.65 * float(item["semantic_score"]) + 0.35 * float(item["lexical_score"]),
            )
        )

    return results
