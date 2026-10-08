"""Guideline evidence retrieval (ChromaDB) and finding explanations.

This layer never decides anything. The deterministic rules produce each finding's outcome and
severity; retrieval only looks up the guideline text that relates to it, and the explainer only
words the result. Both attach the source document, section and page of every passage, and
neither can change a finding.

LangChain is not used: ingestion is a short pure function and retrieval is one Chroma query, so
a framework would add dependencies without adding capability. The embedding function is
injectable. The default is a deterministic hashed bag-of-words embedding, so the index builds
offline and gives reproducible results; swap in a sentence-embedding model for fuzzier matching.
"""

import hashlib
import logging
import re
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Protocol

import chromadb
from chromadb import EmbeddingFunction

from .rulepack import YamlRulePack
from .schemas import Finding, Outcome

logger = logging.getLogger(__name__)

_DIMENSIONS = 512
_WORD = re.compile(r"[a-z0-9]+")
_SECTION = re.compile(r"^(\d{1,2}\.\d{1,2})\s+([A-Z][^\n]{2,80})$", re.MULTILINE)


class HashingEmbedding(EmbeddingFunction):
    """Deterministic, offline embedding: hashed word counts, L2-normalised."""

    def __init__(self) -> None:
        pass

    def __call__(self, input: Sequence[str]) -> list[list[float]]:
        vectors = []
        for text in input:
            vec = [0.0] * _DIMENSIONS
            for word in _WORD.findall(text.lower()):
                digest = hashlib.sha256(word.encode()).digest()
                vec[int.from_bytes(digest[:4], "big") % _DIMENSIONS] += 1.0
            norm = sum(v * v for v in vec) ** 0.5 or 1.0
            vectors.append([v / norm for v in vec])
        return vectors

    @staticmethod
    def name() -> str:
        return "hc03-hashing"

    def get_config(self) -> dict:
        return {}

    @staticmethod
    def build_from_config(config: dict) -> "HashingEmbedding":
        return HashingEmbedding()


@dataclass(frozen=True)
class Chunk:
    id: str
    text: str
    document: str  # source document title
    section: str
    page: str | None
    syndrome_code: str | None = None


@dataclass(frozen=True)
class Passage:
    text: str
    document: str
    section: str
    page: str | None
    distance: float

    @property
    def citation(self) -> str:
        page = f", {self.page}" if self.page else ""
        return f"{self.document}, section {self.section}{page}"


def chunks_from_rulepack(pack: YamlRulePack) -> list[Chunk]:
    """One chunk per guideline regimen row, taken from the rule pack's own quotes."""
    chunks = []
    for code in pack.codes():
        syndrome = pack.syndrome(code)
        rows = [syndrome.evidence] + [
            r.evidence for r in (*syndrome.first_line, *syndrome.alternatives)
        ]
        for i, ev in enumerate(rows):
            chunks.append(
                Chunk(
                    id=f"rulepack:{code}:{i}",
                    text=f"{syndrome.name}. {ev.quote or ''}",
                    document=ev.title.split(", section")[0],
                    section=ev.title.split("section ", 1)[-1],
                    page=ev.page,
                    syndrome_code=code,
                )
            )
    return chunks


def chunks_from_pages(pages: Sequence[str], *, document: str, prefix: str) -> list[Chunk]:
    """Split guideline page text into one chunk per numbered section ("5.1 Cystitis").

    `pages` holds the text of each PDF page in order (labelled "pdf p. N", which can differ from
    the printed page number); a section keeps the page it starts on.
    """
    chunks: list[Chunk] = []
    current: dict | None = None

    def close() -> None:
        if current and current["lines"]:
            chunks.append(
                Chunk(
                    id=f"{prefix}:{current['number']}:{len(chunks)}",
                    text="\n".join(current["lines"]).strip(),
                    document=document,
                    section=f"{current['number']} {current['title']}",
                    page=current["page"],
                )
            )

    for page_no, page in enumerate(pages, start=1):
        for line in page.splitlines():
            match = _SECTION.match(line.strip())
            if match and "...." not in line:
                close()
                current = {
                    "number": match.group(1),
                    "title": match.group(2).strip(),
                    "page": f"pdf p. {page_no}",
                    "lines": [],
                }
            elif current is not None and line.strip():
                current["lines"].append(" ".join(line.split()))
    close()
    return chunks


class EvidenceRetriever(Protocol):
    def retrieve(
        self, query: str, *, syndrome_code: str | None = None, k: int = 2
    ) -> list[Passage]: ...


class ChromaEvidenceStore:
    """ChromaDB-backed passage index. In-memory by default; pass `path` to persist."""

    def __init__(
        self,
        name: str = "guidelines",
        *,
        path: str | None = None,
        embedding: EmbeddingFunction | None = None,
    ) -> None:
        client = chromadb.PersistentClient(path=path) if path else chromadb.EphemeralClient()
        self._collection = client.get_or_create_collection(
            name, embedding_function=embedding or HashingEmbedding()
        )

    def add(self, chunks: Sequence[Chunk]) -> None:
        if not chunks:
            return
        self._collection.upsert(
            ids=[c.id for c in chunks],
            documents=[c.text for c in chunks],
            metadatas=[
                {
                    "document": c.document,
                    "section": c.section,
                    "page": c.page or "",
                    "syndrome_code": c.syndrome_code or "",
                }
                for c in chunks
            ],
        )

    def count(self) -> int:
        return self._collection.count()

    def retrieve(
        self, query: str, *, syndrome_code: str | None = None, k: int = 2
    ) -> list[Passage]:
        """Passages most similar to the query, restricted to the syndrome when one is given."""
        if self.count() == 0:
            return []
        where = {"syndrome_code": syndrome_code} if syndrome_code else None
        result = self._collection.query(query_texts=[query], n_results=k, where=where)
        return [
            Passage(
                text=doc,
                document=meta["document"],
                section=meta["section"],
                page=meta["page"] or None,
                distance=dist,
            )
            for doc, meta, dist in zip(
                result["documents"][0], result["metadatas"][0], result["distances"][0], strict=True
            )
        ]


def build_store(pack: YamlRulePack, *, name: str = "guidelines", path: str | None = None):
    """Index the rule pack's guideline rows. Further documents can be added with `add`."""
    store = ChromaEvidenceStore(name, path=path)
    store.add(chunks_from_rulepack(pack))
    return store


class Explainer(Protocol):
    def explain(self, finding: Finding, passages: Sequence[Passage]) -> str: ...


class TemplateExplainer:
    """Deterministic explanation: the rule's message plus the guideline it rests on."""

    def explain(self, finding: Finding, passages: Sequence[Passage]) -> str:
        if finding.outcome is Outcome.PASS:
            lead = finding.message
        elif finding.outcome is Outcome.FLAG:
            lead = f"{finding.message} This is a rule-based flag for pharmacist review."
        else:
            lead = (
                f"{finding.message} The engine could not assess this and has not assumed it "
                "is safe."
            )
        sources = [e.title + (f", {e.page}" if e.page else "") for e in finding.evidence]
        sources += [p.citation for p in passages if p.citation not in sources]
        return f"{lead} Source: {'; '.join(sources)}." if sources else lead


class LlmExplainer:
    """Wording by a language model, constrained to the deterministic result.

    `complete` is any text-in/text-out callable. The model is given the finding and the
    retrieved passages and told to explain, not to judge. Its text is only ever shown as the
    explanation; the finding's outcome and severity come from the rules. If the call fails the
    template explanation is used.
    """

    PROMPT = (
        "You explain a stewardship rule result to a pharmacist in two sentences. The result is "
        "final: do not change it, do not recommend any drug or dose that is not in the "
        "passages, and cite the source given.\nResult: {outcome} ({rule}). {message}\n"
        "Passages:\n{passages}"
    )

    def __init__(self, complete: Callable[[str], str]) -> None:
        self._complete = complete
        self._fallback = TemplateExplainer()

    def explain(self, finding: Finding, passages: Sequence[Passage]) -> str:
        prompt = self.PROMPT.format(
            outcome=finding.outcome.value,
            rule=finding.rule_id,
            message=finding.message,
            passages="\n".join(f"- {p.text} [{p.citation}]" for p in passages) or "- none",
        )
        try:
            text = self._complete(prompt).strip()
        except Exception:
            logger.exception("LLM explanation failed for %s; using template", finding.rule_id)
            return self._fallback.explain(finding, passages)
        return text or self._fallback.explain(finding, passages)
