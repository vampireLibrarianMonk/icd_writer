"""RAG (Retrieval-Augmented Generation) over ICD corpus.

Allows users to ask natural language questions and get synthesized answers
with inline citations back to source documents, sections, and pages.

Key design decisions:
- Answers are ONLY derived from retrieved chunks (no parametric knowledge)
- Every claim cites [Document, Section, Page]
- "Shall" statements are quoted verbatim, never paraphrased
- Confidence indicator based on retrieval scores and coverage
- Graceful "I don't know" when context is insufficient
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass, field
from typing import Any

import boto3

from .config import SearchConfig, TITAN_V2_SLIDING, IndexConfig
from .embeddings import EmbeddingClient
from .indexing import IndexManager
from .retrieval import HybridSearcher, RetrievalMode, SearchHit, SearchResult

logger = logging.getLogger(__name__)


@dataclass
class Citation:
    """A citation linking a claim to source material."""

    document_title: str
    page_number: int
    section_heading: str | None = None
    section_number: str | None = None
    chunk_text: str = ""  # The source text supporting this citation
    score: float = 0.0

    @property
    def label(self) -> str:
        """Human-readable citation label."""
        parts = [self.document_title]
        if self.section_number:
            parts.append(f"§{self.section_number}")
        elif self.section_heading:
            parts.append(self.section_heading)
        parts.append(f"p{self.page_number}")
        return ", ".join(parts)


@dataclass
class RAGAnswer:
    """A RAG-generated answer with citations and metadata."""

    query: str
    answer: str
    citations: list[Citation]
    confidence: str  # "high", "medium", "low"
    # Performance
    retrieval_time_ms: float = 0.0
    generation_time_ms: float = 0.0
    total_time_ms: float = 0.0
    # Cost
    cost_usd: float = 0.0
    tokens_in: int = 0
    tokens_out: int = 0
    # Context
    chunks_retrieved: int = 0
    chunks_used: int = 0
    model_id: str = ""
    # Warnings
    warnings: list[str] = field(default_factory=list)

    def formatted(self) -> str:
        """Format the answer for display."""
        lines = [self.answer, ""]

        if self.warnings:
            for w in self.warnings:
                lines.append(f"⚠️  {w}")
            lines.append("")

        lines.append(f"Confidence: {self.confidence}")
        lines.append(f"Sources ({len(self.citations)}):")
        for i, c in enumerate(self.citations, 1):
            lines.append(f"  [{i}] {c.label}")

        lines.append("")
        lines.append(
            f"({self.total_time_ms:.0f}ms | "
            f"${self.cost_usd:.4f} | "
            f"{self.chunks_used} chunks used)"
        )
        return "\n".join(lines)


# System prompt for RAG generation
RAG_SYSTEM_PROMPT = """You are a technical assistant helping engineers understand NASA Interface Control Documents (ICDs).

RULES:
1. ONLY answer based on the provided context passages. Do not use outside knowledge.
2. If the context does not contain enough information to answer, say "Based on the indexed documents, I could not find sufficient information about [topic]."
3. For every factual claim, cite the source using [N] notation where N is the passage number.
4. When quoting requirements that use "shall", "will", or "should", preserve the EXACT wording. Never paraphrase contractual language.
5. If a value is listed as "TBD" (To Be Determined), note this explicitly: "This value is TBD (not yet determined)."
6. When information comes from multiple documents, attribute each fact to its source.
7. Include units and tolerances exactly as stated (do not round or convert).
8. If asked about something that spans multiple documents, synthesize across all sources.

RESPONSE FORMAT:
- Start with a direct answer to the question
- Support with specific details and citations [N]
- Note any caveats, TBDs, or potential conflicts between documents
- Keep the answer concise but complete

DISCLAIMER (include at end if the answer involves requirements):
"Note: This is an AI-assisted summary. Verify contractual requirements against the source document."
"""


class RAGPipeline:
    """RAG pipeline: retrieve relevant chunks → generate answer with citations."""

    def __init__(self, search_config: SearchConfig | None = None,
                 index_config: IndexConfig | None = None,
                 generation_model: str = "us.amazon.nova-pro-v1:0",
                 region: str = "us-east-1") -> None:
        self.config = search_config or SearchConfig(aws_region=region)
        self.index_config = index_config or TITAN_V2_SLIDING
        self.generation_model = generation_model
        self.region = region

        self._index_manager = IndexManager(self.config)
        self._embed_client = EmbeddingClient(
            self.index_config.embedding_config, region=region
        )
        self._searcher = HybridSearcher(
            self._index_manager.client, self._embed_client, self.index_config
        )
        self._bedrock_runtime = boto3.client("bedrock-runtime", region_name=region)

    def ask(self, query: str, k: int = 8,
            mode: RetrievalMode = RetrievalMode.HYBRID_RRF,
            conversation_history: list[dict[str, str]] | None = None) -> RAGAnswer:
        """Ask a question and get an answer with citations.

        Args:
            query: Natural language question
            k: Number of chunks to retrieve for context
            mode: Retrieval mode
            conversation_history: Previous Q&A pairs for follow-up questions

        Returns:
            RAGAnswer with synthesized answer, citations, and metadata
        """
        total_start = time.perf_counter()

        # Step 1: Retrieve relevant chunks
        retrieval_start = time.perf_counter()
        search_result = self._searcher.search(query, k=k, mode=mode)
        retrieval_ms = (time.perf_counter() - retrieval_start) * 1000

        if not search_result.hits:
            return RAGAnswer(
                query=query,
                answer="I could not find any relevant content in the indexed documents for this query.",
                citations=[],
                confidence="low",
                retrieval_time_ms=retrieval_ms,
                total_time_ms=(time.perf_counter() - total_start) * 1000,
                warnings=["No matching content found in the indexed ICD corpus."],
            )

        # Step 2: Build context from retrieved chunks
        context_passages, citations = self._build_context(search_result.hits)

        # Step 3: Generate answer with LLM
        generation_start = time.perf_counter()
        answer_text, tokens_in, tokens_out = self._generate(
            query, context_passages, conversation_history
        )
        generation_ms = (time.perf_counter() - generation_start) * 1000

        # Step 4: Assess confidence
        confidence = self._assess_confidence(search_result.hits, answer_text)

        # Step 5: Check for warnings
        warnings = self._check_warnings(search_result.hits, answer_text)

        # Cost estimation (Nova Pro pricing)
        cost = self._estimate_cost(tokens_in, tokens_out)

        total_ms = (time.perf_counter() - total_start) * 1000

        return RAGAnswer(
            query=query,
            answer=answer_text,
            citations=citations,
            confidence=confidence,
            retrieval_time_ms=retrieval_ms,
            generation_time_ms=generation_ms,
            total_time_ms=total_ms,
            cost_usd=cost,
            tokens_in=tokens_in,
            tokens_out=tokens_out,
            chunks_retrieved=len(search_result.hits),
            chunks_used=len(context_passages),
            model_id=self.generation_model,
            warnings=warnings,
        )

    def _build_context(self, hits: list[SearchHit]) -> tuple[list[str], list[Citation]]:
        """Build numbered context passages and citation objects."""
        passages = []
        citations = []

        for i, hit in enumerate(hits, 1):
            # Format passage with metadata
            header_parts = [f"[{i}]"]
            header_parts.append(f"Document: {hit.document_title}")
            if hit.section_heading:
                header_parts.append(f"Section: {hit.section_heading}")
            header_parts.append(f"Page: {hit.page_number}")
            header_parts.append(f"Type: {hit.content_type}")

            passage = f"{' | '.join(header_parts)}\n{hit.text}"
            passages.append(passage)

            citations.append(Citation(
                document_title=hit.document_title,
                page_number=hit.page_number,
                section_heading=hit.section_heading,
                section_number=hit.section_number,
                chunk_text=hit.text[:200],
                score=hit.score,
            ))

        return passages, citations

    def _generate(self, query: str, context_passages: list[str],
                  conversation_history: list[dict[str, str]] | None) -> tuple[str, int, int]:
        """Generate answer using Bedrock LLM."""
        # Build the prompt
        context_block = "\n\n".join(context_passages)
        user_message = (
            f"Context passages from ICD documents:\n\n"
            f"{context_block}\n\n"
            f"---\n\n"
            f"Question: {query}"
        )

        # Build messages
        messages = []
        if conversation_history:
            for entry in conversation_history[-3:]:  # Last 3 turns for context
                messages.append({"role": "user", "content": [{"text": entry["query"]}]})
                messages.append({"role": "assistant", "content": [{"text": entry["answer"]}]})
        messages.append({"role": "user", "content": [{"text": user_message}]})

        body = {
            "messages": messages,
            "system": [{"text": RAG_SYSTEM_PROMPT}],
            "inferenceConfig": {
                "maxTokens": 1024,
                "temperature": 0.1,  # Low temp for factual answers
                "topP": 0.9,
            },
        }

        try:
            response = self._bedrock_runtime.invoke_model(
                modelId=self.generation_model,
                body=json.dumps(body),
                contentType="application/json",
                accept="application/json",
            )
            result = json.loads(response["body"].read())

            # Extract text from response
            answer = ""
            if "output" in result and "message" in result["output"]:
                content = result["output"]["message"].get("content", [])
                for block in content:
                    if "text" in block:
                        answer += block["text"]

            # Token usage
            usage = result.get("usage", {})
            tokens_in = usage.get("inputTokens", len(user_message.split()))
            tokens_out = usage.get("outputTokens", len(answer.split()))

            return answer, tokens_in, tokens_out

        except Exception as e:
            logger.error(f"Generation failed: {e}")
            # Fallback: return raw passages
            fallback = (
                "I encountered an error generating a synthesized answer. "
                "Here are the most relevant passages:\n\n"
            )
            for p in context_passages[:3]:
                fallback += f"{p}\n\n"
            return fallback, 0, 0

    def _assess_confidence(self, hits: list[SearchHit], answer: str) -> str:
        """Assess answer confidence based on retrieval quality."""
        if not hits:
            return "low"

        # Factors:
        # 1. Top hit score (higher = better match)
        top_score = hits[0].score
        # 2. Number of hits contributing (more sources = higher confidence)
        contributing = sum(1 for h in hits if h.score > top_score * 0.5)
        # 3. Whether answer says "could not find" or "TBD"
        hedging = any(phrase in answer.lower() for phrase in [
            "could not find", "no information", "unclear", "not specified"
        ])

        if hedging:
            return "low"
        elif top_score > 0.03 and contributing >= 3:
            return "high"
        elif top_score > 0.02 and contributing >= 2:
            return "medium"
        else:
            return "low"

    def _check_warnings(self, hits: list[SearchHit], answer: str) -> list[str]:
        """Check for conditions that warrant warnings."""
        warnings = []

        # Check for TBD in source material
        if any("tbd" in h.text.lower() for h in hits):
            warnings.append(
                "Some source content contains TBD (To Be Determined) items. "
                "The answer may change when these are resolved."
            )

        # Check if answer references "shall" (contractual language)
        if "shall" in answer.lower():
            warnings.append(
                "This answer references contractual requirements ('shall' statements). "
                "Verify against the source document for contractual decisions."
            )

        # Check if multiple documents contribute (potential for conflicts)
        doc_titles = set(h.document_title for h in hits)
        if len(doc_titles) > 1:
            # Not a warning per se, but useful metadata
            pass

        return warnings

    def _estimate_cost(self, tokens_in: int, tokens_out: int) -> float:
        """Estimate cost based on model pricing."""
        # Nova Pro pricing (approximate)
        cost_per_1k_input = 0.0008
        cost_per_1k_output = 0.0032

        cost = (tokens_in / 1000) * cost_per_1k_input
        cost += (tokens_out / 1000) * cost_per_1k_output
        # Add embedding cost
        cost += 0.00001  # ~one query embedding
        return cost
