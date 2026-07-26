"""Cost tracking for OCR API calls.

Tracks per-page and per-document costs across all cloud services used
in the OCR pipeline. Produces a summary at the end of processing.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone


@dataclass
class ApiCall:
    """Record of a single API call."""

    service: str  # "textract", "rekognition", "bedrock"
    operation: str  # "detect_document_text", "analyze_document", etc.
    page: int
    cost_usd: float
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    tokens_in: int = 0
    tokens_out: int = 0
    metadata: dict = field(default_factory=dict)


# Pricing as of 2026-07 (us-east-1)
PRICING = {
    "textract": {
        "detect_document_text": 0.0015,  # per page
        "analyze_document": 0.015,  # per page (tables/forms)
    },
    "rekognition": {
        "detect_text": 0.001,  # per image
    },
    "bedrock": {
        # Claude 3.5 Sonnet vision
        "claude_sonnet_input": 0.003 / 1000,  # per input token
        "claude_sonnet_output": 0.015 / 1000,  # per output token
        # Titan/Nova vision
        "nova_lite_input": 0.00006 / 1000,  # per input token
        "nova_lite_output": 0.00025 / 1000,  # per output token
    },
}


class CostTracker:
    """Tracks API costs across an OCR pipeline run."""

    def __init__(self) -> None:
        self.calls: list[ApiCall] = []

    def record(
        self,
        service: str,
        operation: str,
        page: int,
        tokens_in: int = 0,
        tokens_out: int = 0,
        **metadata: object,
    ) -> float:
        """Record an API call and return its cost."""
        cost = self._compute_cost(service, operation, tokens_in, tokens_out)
        self.calls.append(
            ApiCall(
                service=service,
                operation=operation,
                page=page,
                cost_usd=cost,
                tokens_in=tokens_in,
                tokens_out=tokens_out,
                metadata=dict(metadata),
            )
        )
        return cost

    def _compute_cost(
        self, service: str, operation: str, tokens_in: int, tokens_out: int
    ) -> float:
        """Compute cost for a single API call."""
        if service == "textract":
            return PRICING["textract"].get(operation, 0.0)
        elif service == "rekognition":
            return PRICING["rekognition"].get(operation, 0.0)
        elif service == "bedrock":
            if "claude" in operation or "sonnet" in operation:
                return (
                    tokens_in * PRICING["bedrock"]["claude_sonnet_input"]
                    + tokens_out * PRICING["bedrock"]["claude_sonnet_output"]
                )
            elif "nova" in operation or "titan" in operation:
                return (
                    tokens_in * PRICING["bedrock"]["nova_lite_input"]
                    + tokens_out * PRICING["bedrock"]["nova_lite_output"]
                )
        return 0.0

    @property
    def total_cost(self) -> float:
        """Total cost across all calls."""
        return sum(c.cost_usd for c in self.calls)

    @property
    def total_pages(self) -> int:
        """Number of unique pages processed."""
        return len(set(c.page for c in self.calls))

    def summary(self) -> str:
        """Generate a human-readable cost summary."""
        lines = []
        lines.append("## OCR Pipeline Cost Summary")
        lines.append("")
        lines.append("| Metric | Value |")
        lines.append("|--------|-------|")
        lines.append(f"| Total Cost | **${self.total_cost:.4f}** |")
        lines.append(f"| Pages Processed | {self.total_pages} |")
        lines.append(f"| API Calls | {len(self.calls)} |")
        lines.append(
            f"| Cost per Page | ${self.total_cost / self.total_pages:.4f} |"
            if self.total_pages > 0
            else "| Cost per Page | N/A |"
        )
        lines.append("")

        # Breakdown by service
        services: dict[str, float] = {}
        for call in self.calls:
            services[call.service] = services.get(call.service, 0.0) + call.cost_usd

        lines.append("| Service | Cost | Calls |")
        lines.append("|---------|------|-------|")
        for svc, cost in sorted(services.items()):
            count = sum(1 for c in self.calls if c.service == svc)
            lines.append(f"| {svc} | ${cost:.4f} | {count} |")

        return "\n".join(lines)
