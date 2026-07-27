# Phase 4 Requirements Specification

## ICD Writer — Search, RAG, and Continuous Model Evaluation

**Document Version:** 1.0
**Date:** 2026-07-27
**Status:** Draft for Review

---

## Context

The ICD Writer pipeline now includes a working search infrastructure:
- OpenSearch with hybrid search (BM25 + kNN + Reciprocal Rank Fusion)
- 4 chunking strategies (paragraph, section, sliding window, fixed words)
- Titan V2 and Cohere English v3 embeddings (1024 dimensions)
- An evaluation harness scoring all (model × chunk × mode) combinations
- A model registry that probes AWS Bedrock for new/deprecated models
- 3 indexed NASA ICDs (LVC, HSI Spectrometer, TSAFE) — 1,054 chunks total
- Ground truth: 13 evaluation queries across 5 categories
- **Current best: 92.3% Recall@10** (Titan V2 + sliding window + hybrid)

This document specifies three features that build on this foundation, ordered by implementation priority.

---

## Feature 1: RAG (Retrieval-Augmented Generation) over ICD Corpus

### 1.1 Problem Statement

**What pain does this solve?**

Engineers, program managers, and new team members regularly need answers from Interface Control Documents but face barriers:
- ICDs are long (15–200+ pages), dense, and full of jargon
- Finding a specific requirement requires knowing which document and section to look in
- Cross-document questions ("Does the thermal limit in the Spectrometer ICD conflict with the spacecraft bus spec?") require reading multiple documents simultaneously
- New team members spend days reading ICDs when they need a single answer now

Without RAG, users must either:
1. Read entire documents manually
2. Use keyword search and interpret raw text chunks themselves
3. Ask a senior engineer (creating a bottleneck)

**Who benefits?**
- **New team members** who need to learn interfaces quickly without reading 200 pages
- **Systems engineers** integrating hardware/software across multiple ICDs
- **Program managers** who need quick answers for reviews and schedule decisions
- **ICD authors** verifying that their document doesn't conflict with related ICDs
- **Quality engineers** checking requirement completeness

### 1.2 User Stories

**US-1.1 (New Team Member):** As a newly assigned engineer, I want to ask "What are the power requirements for the spectrometer interface?" and get a clear answer with the specific section and page cited, so I can understand the interface without reading the entire ICD.

**US-1.2 (Systems Engineer):** As a systems engineer doing integration, I want to ask "What thermal constraints apply to equipment mounted on the spacecraft bus?" and get an answer that pulls from ALL relevant ICDs in the corpus, with each source identified, so I can see the full picture across interfaces.

**US-1.3 (Program Manager):** As a program manager preparing for a design review, I want to ask "What requirements are still TBD in the LVC ICD?" and get a summarized list with owners and section references, so I can assess schedule risk without reading the document myself.

**US-1.4 (ICD Author):** As an ICD author, I want to ask "Does the 50-watt power limit in section 3.1 conflict with any other document?" and get an answer that identifies potential conflicts with cited sources, so I can resolve issues before formal review.

**US-1.5 (Quality Engineer):** As a quality engineer, I want to ask "Show me all 'shall' statements related to thermal design" and get every contractually binding requirement across all indexed documents, with confidence indicators for completeness, so I can verify requirement coverage.

**US-1.6 (Any User):** As a non-expert user, I want the system to explain technical terms in the answer (e.g., "TBD means 'To Be Determined' — this requirement is not yet finalized") when I ask a question using plain language, so I don't need prior ICD expertise to understand the response.

**US-1.7 (Systems Engineer):** As a systems engineer, I want to ask follow-up questions that reference previous answers ("What about the cold case?") without restating the full context, so the interaction feels conversational rather than one-shot.

### 1.3 Adversarial Questions & Answers

**Q1: What happens when the LLM hallucinates a requirement that doesn't exist in any document?**

A: Every claim in the generated answer is grounded in retrieved chunks. The system:
1. Retrieves top-K chunks via the existing hybrid search
2. Passes ONLY those chunks as context to the LLM (no parametric knowledge encouraged)
3. The prompt explicitly instructs: "Only answer based on the provided context. If the context doesn't contain the answer, say so."
4. Every statement in the answer includes an inline citation: `[HSI_SYS_015G, §3.3, p7]`
5. A post-generation verification step checks that each citation maps to actual retrieved text
6. Citations that fail verification are flagged: "⚠️ Could not verify this claim against source documents"

If ALL claims fail verification, the answer is replaced with: "I found related content but cannot confidently answer this question. Here are the most relevant passages: [shows raw chunks]"

**Q2: How do you handle questions that require information from multiple documents?**

A: The search already retrieves across all indexed documents. The RAG prompt includes context chunks from multiple sources, and the LLM is instructed to synthesize across them. The answer format explicitly attributes each fact:

```
The thermal limits differ between documents:
- Spectrometer non-operating: -60°C to +61°C [HSI_SYS_015G, §3.3, p7]
- Spacecraft bus allowable: -40°C to +70°C [LVC ICD, §4.2, p12]

⚠️ Note: The spectrometer's cold limit (-60°C) exceeds the bus allowable (-40°C).
This may require a waiver or thermal isolation.
```

When a potential conflict is detected, it's flagged explicitly.

**Q3: What about questions the documents simply don't answer?**

A: The system must gracefully handle "no answer" cases:
- "Based on the indexed documents, I could not find information about [X]."
- "The closest relevant content is: [shows top-3 chunks with scores]"
- "This question might be answered in: [suggests document types or sections to check]"

A confidence score (Low / Medium / High) accompanies every answer, based on:
- Retrieval score of top chunks (high similarity = high confidence)
- Number of chunks that contribute to the answer (multiple sources = higher confidence)
- Whether the answer uses definitive language from the source ("shall" = high) vs. inference

**Q4: If a user asks about a superseded revision, how does the system handle versioning?**

A: Each indexed document carries revision metadata (version, date, supersedes). The system:
1. Default behavior: answers from the LATEST revision of each document
2. If a query mentions a specific revision ("in Rev C of the HSI ICD"), retrieves from that version
3. If content has changed between revisions, the answer notes: "This requirement was modified in Rev G (current). Previous value in Rev F was: [X]"
4. Users can pin their session to a specific document set/revision for consistency

**Q5: How do you prevent the system from giving contractually binding answers that misinterpret "shall" vs. "will" vs. "should"?**

A: The RAG system is explicitly NOT a contractual interpretation tool. Safeguards:
1. A disclaimer accompanies every answer: "This is an AI-assisted summary. Verify contractual requirements against the source document."
2. When quoting "shall" statements, the system preserves exact wording: it quotes rather than paraphrases.
3. The prompt instructs the LLM: "When a requirement uses 'shall', preserve that exact word. Do not change 'shall' to 'will' or 'should'. Quote requirements verbatim."
4. The answer distinguishes between mandatory ("shall"), intentional ("will"), and advisory ("should") language when relevant.

**Q6: What about performance — will users wait 30 seconds for an answer?**

A: Target latency breakdown:
- Retrieval (search): 50-150ms (already measured in eval)
- Embedding the query: 100-200ms
- LLM generation (Bedrock): 2-5 seconds for typical answer
- **Total target: < 6 seconds for standard queries**

Mitigations for slow cases:
- Stream the LLM response (show text as it generates)
- Show retrieved chunks immediately while generation proceeds
- Cache embedding for repeated/similar queries

**Q7: How much does each query cost?**

A: Estimated per-query cost:
- Query embedding (Titan V2): ~$0.00001 (13 tokens × $0.0001/1K)
- LLM generation (Claude Sonnet on Bedrock): ~$0.005-0.015 depending on context length
- **Total: ~$0.01-0.02 per query**

At 100 queries/day: ~$1-2/day. At 1000 queries/day: ~$10-20/day. Cost tracking is built in (extending the existing CostTracker pattern from OCR pipeline).

### 1.4 ICD-Specific Considerations

**Shall/will/must language:** ICDs use precise contractual language. "Shall" indicates a binding requirement, "will" indicates a statement of fact or intent, "should" is advisory. The RAG system must NEVER change these modal verbs. Answers quote requirements verbatim and note the obligation level.

**Interface ownership:** Every ICD interface has two parties (provider and user). When answering questions about responsibility, the system must identify WHICH party a requirement applies to: "The spacecraft (provider) shall supply 28V ± 0.5V" vs. "The spectrometer (user) shall not draw more than 2.5A."

**Cross-reference integrity:** ICDs heavily reference other sections and documents ("per Section 4.2.1" or "per Document ABC-001"). The RAG system resolves these references when possible, pulling the referenced content into the answer context.

**Units and tolerances:** Requirements specify precise values with tolerances (e.g., "28.0 ± 0.5 VDC at 25°C ± 5°C ambient"). The system preserves exact numerical values and units without rounding or unit conversion unless explicitly asked.

**TBD/TBR items:** When an answer depends on a TBD item, this is flagged: "⚠️ This requirement contains a TBD (not yet determined). The answer may change when resolved."

**Revision awareness:** ICD answers must be traceable to a specific document revision. Every citation includes the document revision identifier.

### 1.5 Acceptance Criteria

1. A user can submit a natural language question via CLI (`search` command with `--rag` flag) or API endpoint and receive a synthesized answer with inline citations.
2. Every factual claim in the answer cites a specific document, section, and page number.
3. Citations are verifiable: clicking/following a citation shows the source text that supports the claim.
4. When retrieved context doesn't contain sufficient information, the system says "I don't have enough information" rather than guessing.
5. Answers that involve "shall" statements quote them verbatim rather than paraphrasing.
6. Multi-document questions produce answers that attribute facts to their respective sources.
7. A confidence indicator (Low/Medium/High) accompanies each answer.
8. A disclaimer reminds users to verify contractual requirements against source documents.
9. Response latency is < 8 seconds for 95% of queries (p95).
10. Per-query cost is tracked and reported.
11. Follow-up questions within a session maintain conversational context.
12. The system handles "What's TBD?" queries by linking to TBD items (integration with Feature 2).

### 1.6 Non-Functional Requirements

- **Latency:** p50 < 4s, p95 < 8s for answer generation
- **Cost:** < $0.02 per query average; monthly cost reported
- **Accuracy:** > 90% of citations are verifiable against source text (measured via eval set)
- **Availability:** Depends on Bedrock LLM availability; graceful degradation to "raw chunks" mode if LLM is unavailable
- **Concurrency:** Support 10 simultaneous queries without degradation
- **Accessibility:** Answers are plain text (screenreader compatible); citations are structured data

### 1.7 Out of Scope

- **Real-time document editing** — RAG reads from the indexed corpus; it doesn't modify documents
- **Contractual interpretation** — the system summarizes and retrieves, not interprets legal obligation
- **Automatic requirement writing** — the system answers questions, not generates new requirements
- **Cross-corpus deconfliction** — flagging conflicts is in scope; resolving them is not
- **Classified document handling** — all documents are assumed unclassified/publicly releasable in this phase
- **Voice interface** — text-only in this phase

### 1.8 Dependencies & Risks

| Dependency | Risk | Mitigation |
|-----------|------|-----------|
| Bedrock LLM availability | Service outages block RAG | Fallback to "raw chunks" mode (search without synthesis) |
| LLM context window | Very long answers may truncate context | Limit to top-K chunks that fit; summarize if needed |
| Prompt engineering | Poor prompts = poor answers | Eval harness with ground-truth Q&A pairs; iterate prompts |
| Citation verification | LLM may cite wrong section numbers | Post-processing maps citations to actual chunk IDs |
| Cost at scale | High query volume = high cost | Rate limiting, caching, cost alerts |
| Model deprecation | Bedrock model used for generation may be deprecated | Same model registry pattern; fallback to alternative model |


---

## Feature 2: TBD Dashboard (Cross-Document)

### 2.1 Problem Statement

**What pain does this solve?**

NASA ICDs contain TBD (To Be Determined) and TBR (To Be Resolved) items that represent unresolved engineering decisions. These are schedule risks — each unresolved TBD blocks downstream design work. Today:

- TBDs are scattered across documents with no centralized view
- The same interface gap often appears as a TBD in BOTH documents (provider ICD and user ICD), but tracked separately with different wording
- Program managers manually scrub documents to compile TBD lists for reviews
- There's no systematic way to know if a TBD resolved in Document A is still open in Document B
- No visibility into TBD aging — a TBD open for 2 years has different urgency than one opened last week

Without this dashboard:
- Design reviews waste time manually counting and categorizing TBDs
- Cross-interface TBD inconsistencies go undetected until integration testing
- Schedule risk from unresolved TBDs is invisible until it's too late
- There's no audit trail of TBD resolution decisions

**Who benefits?**
- **Program managers** who track schedule risk and review readiness
- **Systems engineers** who need to know what interfaces are incomplete
- **ICD authors** who need to resolve their TBDs and verify cross-document consistency
- **Review boards** (PDR, CDR) that require TBD status as gate criteria

### 2.2 User Stories

**US-2.1 (Program Manager):** As a program manager preparing for CDR, I want to see a single dashboard showing ALL unresolved TBDs across all ICDs in the program, sorted by age and criticality, so I can assess review readiness in minutes rather than days of manual scrubbing.

**US-2.2 (Systems Engineer):** As a systems engineer, I want to see when the same TBD appears in multiple documents (e.g., "data rate TBD" in both the sender and receiver ICDs) and whether it's been resolved consistently, so I can catch cross-interface inconsistencies before integration.

**US-2.3 (ICD Author):** As an ICD author, I want to mark a TBD as resolved with a value, rationale, and resolution date, and have that resolution propagated to related TBDs in other documents, so I don't create inconsistencies.

**US-2.4 (Quality Engineer):** As a quality engineer, I want to verify that no "shall" statement depends on an unresolved TBD, because a binding requirement with a TBD value is contractually ambiguous and may indicate an immature design.

**US-2.5 (Program Manager):** As a program manager, I want to filter TBDs by owner (which organization is responsible), target resolution date, and interface area, so I can assign action items and track closure at weekly status meetings.

**US-2.6 (New Team Member):** As a new team member, I want to understand what "TBD" and "TBR" mean in this project's context, see examples, and understand the lifecycle (open → assigned → resolved → verified), so I can contribute to resolving them.

**US-2.7 (Any User):** As any user, I want to export the TBD list to a format suitable for review packages (PDF table or CSV), so I can include it in formal documentation without re-typing.

### 2.3 Adversarial Questions & Answers

**Q1: How do you detect that "data rate TBD" in Document A and "throughput to be determined" in Document B are the SAME unresolved item?**

A: Cross-document TBD correlation uses a multi-signal approach:
1. **Semantic similarity:** Embed the TBD's surrounding context (the paragraph/requirement containing it) and find vectors with high cosine similarity across documents. "Data rate TBD" in a communications section and "throughput to be determined" in a receiver section will have similar embeddings.
2. **Section heading alignment:** TBDs under similar section headings (e.g., "3.2 Data Interface" in both docs) are strong correlation candidates.
3. **Interface party matching:** If Document A is the provider ICD and Document B is the user ICD for the same interface, TBDs in corresponding sections are likely the same item.
4. **Confidence scoring:** Each correlation gets a confidence score (High/Medium/Low). Only High-confidence matches are auto-linked; Medium matches are flagged for human review.

False positives (incorrectly linking unrelated TBDs) are handled by requiring human confirmation for the initial linkage. Once confirmed, the link is persistent.

**Q2: What if a TBD is resolved differently in two documents?**

A: This is an inconsistency — exactly what the dashboard is designed to surface. When detected:
1. The dashboard shows: "⚠️ CONFLICT: TBD-042 resolved as '1.5 Mbps' in Document A but '2.0 Mbps' in Document B"
2. Both resolutions are shown with their dates and rationale
3. The item is flagged as "Requires reconciliation" — it cannot be marked as fully resolved until both documents agree
4. An action item is auto-generated for the interface owners

**Q3: How do you handle TBDs that have been resolved in a newer revision but the older revision is still indexed?**

A: The dashboard shows TBD status PER REVISION:
- "TBD-015: OPEN in Rev C, RESOLVED in Rev G (current) with value '28V ± 0.5V'"
- The default view shows only current-revision status
- A "history" view shows the full lifecycle: when opened, when assigned, when resolved, in which revision
- Only TBDs that are open in the LATEST revision of each document count toward review readiness metrics

**Q4: Who "owns" a TBD when it appears in an interface between two organizations?**

A: ICD TBDs inherently have dual ownership (both parties need the value). The dashboard tracks:
- **Source party:** Which organization's ICD first introduced the TBD
- **Responsible party:** Who is assigned to resolve it (usually the requirements owner)
- **Affected parties:** Who is blocked by this TBD (may be both sides)

Owner assignment is a manual field (set by the user or extracted from document text if explicitly stated). The system suggests ownership based on section context: "This TBD appears in a section describing spacecraft-provided services → likely spacecraft team responsibility."

**Q5: What about TBDs buried in table cells or figure captions?**

A: The existing TBD tracker (`src/tbd_tracker.py`) already extracts TBDs from all content types — paragraph text, table cells, figure captions, headers, and footnotes. Each TBD records its source location (page, y-position, content type). The dashboard inherits this comprehensive extraction.

Table-cell TBDs are particularly common in interface parameter tables (e.g., "Data Rate: TBD Mbps"). These are tagged with their column context for richer display: "Parameter: Data Rate, Value: TBD, Unit: Mbps."

**Q6: How does this integrate with the existing TBD tracker?**

A: The existing `src/tbd_tracker.py` module performs per-document extraction. The dashboard extends this with:
1. **Cross-document correlation** (linking related TBDs via semantic search)
2. **Status tracking** (lifecycle state machine: open → assigned → resolved → verified)
3. **Persistence** (TBD states are stored beyond the current session)
4. **Aggregation** (corpus-wide statistics and filtering)

The extraction logic is reused; the dashboard adds the management and visibility layer.

**Q7: What's the difference between TBD and TBR?**

A: Both are tracked but have different semantics:
- **TBD (To Be Determined):** A value or decision that hasn't been made yet. Resolution requires an engineering decision or analysis.
- **TBR (To Be Resolved):** A requirement or statement that needs further refinement, often through negotiation between parties. Resolution often requires agreement/approval.

The dashboard tracks both with appropriate labels. Filter views allow separating TBDs (engineering work) from TBRs (negotiation/approval work) since they may have different owners and different resolution paths.

### 2.4 ICD-Specific Considerations

**TBD lifecycle in NASA programs:** TBDs follow a formal lifecycle aligned with design reviews:
- PDR (Preliminary Design Review): Some TBDs acceptable at this stage
- CDR (Critical Design Review): Most TBDs must be resolved; remaining ones need closure plans
- TRR (Test Readiness Review): Zero TBDs acceptable in test-related requirements

The dashboard should indicate review-gate implications: "12 TBDs remaining — CDR gate requires < 5."

**Interface symmetry:** Every interface has a provider and user. A TBD in the provider document ("output voltage: TBD") should have a corresponding TBD or placeholder in the user document ("input voltage tolerance: TBD"). When only one side has the TBD, the other side may have assumed a value — this is a risk the dashboard should flag.

**Contractual implications:** An ICD with unresolved TBDs in "shall" statements cannot be baselined as a contractual document. The dashboard should distinguish between:
- TBDs in "shall" statements (contractually blocking)
- TBDs in informational sections (non-blocking)
- TBDs in "will" statements (intent, not contractual)

**Numerical TBDs vs. textual TBDs:** "Temperature: TBD °C" (needs a specific number) differs from "The thermal control approach is TBD" (needs a paragraph of description). The dashboard should categorize accordingly — numeric TBDs are often resolved by analysis, while textual TBDs require design decisions.

### 2.5 Acceptance Criteria

1. A CLI command (`python3 -m src.cli tbd-dashboard`) produces a cross-document TBD summary.
2. The dashboard displays all TBD/TBR items from all indexed documents with source document, page, section, and surrounding context.
3. Cross-document correlation identifies related TBDs with confidence scores (High/Medium/Low).
4. Users can set TBD status (open/assigned/resolved/verified), owner, target date, and resolution value.
5. Inconsistent resolutions (same TBD resolved differently in different documents) are flagged as conflicts.
6. TBDs in "shall" statements are distinguished from TBDs in informational text.
7. Filter by: document, owner, status, age, review gate, content type (paragraph/table/figure).
8. Export to CSV and markdown table formats.
9. API endpoint returns TBD data as JSON for frontend dashboard rendering.
10. Statistics: total count, open count, resolution rate, average age, oldest unresolved.
11. When a user resolves a TBD, correlated TBDs in other documents are flagged for review.

### 2.6 Non-Functional Requirements

- **Performance:** Dashboard loads in < 2 seconds for up to 500 TBD items across 50 documents
- **Persistence:** TBD status changes are stored and survive system restart (session journal or database)
- **Audit trail:** Every status change records who, when, what, and why
- **Concurrency:** Multiple users can update TBD status simultaneously without conflicts (last-write-wins with conflict notification)
- **Accessibility:** Dashboard is usable with screen readers; color coding has text alternatives

### 2.7 Out of Scope

- **Automatic TBD resolution** — the system tracks and surfaces TBDs; humans resolve them
- **Document editing** — resolving a TBD in the dashboard doesn't modify the source PDF (that's the editor's job)
- **Notification system** — no email/Slack alerts for TBD status changes in this phase
- **Approval workflows** — no formal sign-off chain; status changes are immediate
- **Historical trending** — no "TBD burn-down chart over time" in this phase (future enhancement)

### 2.8 Dependencies & Risks

| Dependency | Risk | Mitigation |
|-----------|------|-----------|
| TBD extraction quality | Missed TBDs = incomplete dashboard | Validate against manual TBD lists from existing reviews |
| Semantic correlation accuracy | False positives link unrelated TBDs | Confidence scoring + human confirmation for non-obvious matches |
| Persistence mechanism | Need to store status outside the session | Use a lightweight JSON/YAML store; migrate to DB if scale demands |
| Cross-document coverage | Only indexed documents appear | Clear messaging: "Showing TBDs from N indexed documents" |
| TBD wording variations | "TBD", "to be determined", "not yet defined", "[TBD]" | Existing TBD tracker handles these patterns; verify coverage |


---

## Feature 3: Benchmark Newly-Discovered Models

### 3.1 Problem Statement

**What pain does this solve?**

The model registry discovered 11 new embedding models on Bedrock. Each represents a potential improvement in retrieval quality — but also a potential increase in cost, different dimension requirements, and different token limits. Today there is no systematic process to:
- Decide which models are worth evaluating
- Evaluate them fairly despite different configurations
- Translate metrics into actionable "switch" or "stay" decisions
- Handle the operational cost of switching (re-indexing the entire corpus)

Without a structured benchmark process:
- New models accumulate in the "unbenchmarked" list indefinitely
- Someone manually adds each model, creates indices, and runs eval — a multi-hour process per model
- There's no cost/benefit framework (is 3% recall improvement worth 5x cost increase?)
- Deprecated models stay in production until they break
- Better retrieval quality (which directly improves RAG answers) is left on the table

**Who benefits?**
- **Pipeline maintainers** who need to know when to upgrade
- **Program managers** who need to understand cost implications
- **All search/RAG users** who benefit from better retrieval quality

### 3.2 User Stories

**US-3.1 (Pipeline Maintainer):** As the engineer maintaining the search pipeline, I want to run a single command that evaluates all unbenchmarked models and produces a ranked comparison table, so I can decide which models to adopt without manually configuring each one.

**US-3.2 (Program Manager):** As a program manager, I want to see a cost/benefit analysis showing recall improvement alongside cost per query and monthly projected cost at our query volume, so I can approve or reject model upgrades based on budget.

**US-3.3 (Systems Engineer):** As a systems engineer, I want the benchmark to handle models with different dimension sizes automatically (512d vs. 1024d vs. 1536d), creating appropriate indices without manual configuration, so I don't need to understand OpenSearch internals.

**US-3.4 (Pipeline Maintainer):** As the pipeline maintainer, I want the system to flag when a currently-used model is deprecated and automatically identify the best available replacement, so I can migrate before the model stops working.

**US-3.5 (Quality Engineer):** As a quality engineer, I want benchmark results broken down by query category (requirements, architecture, metadata, TBD), so I can identify if a model is strong in one area but weak in another.

**US-3.6 (Any Stakeholder):** As any stakeholder, I want a human-readable recommendation ("Switch to Model X because: +5% recall, same cost" or "Stay because: Model Y is only +1% but 8x cost"), so I can decide without being an ML expert.

**US-3.7 (Pipeline Maintainer):** As the pipeline maintainer, I want the benchmark to detect when a model requires different token limits and automatically test with adjusted chunk sizes, so I don't miss optimal configurations due to parameter mismatches.

### 3.3 Adversarial Questions & Answers

**Q1: What if a new model is 5% better on recall but 10x more expensive?**

A: The benchmark computes a cost-effectiveness score:

```
value_score = (recall_new - recall_baseline) / max(0.01, cost_new / cost_baseline)
```

Configurable decision thresholds:
- **Strong upgrade:** recall improvement > 5% AND cost increase < 2x → "Recommend upgrade"
- **Conditional upgrade:** recall improvement > 10% regardless of cost → "Recommend if budget allows" (with monthly cost projection)
- **Not worth it:** recall improvement < 2% with any cost increase → "Stay with current"
- **Cost optimization:** recall within 1% AND cost decrease > 30% → "Recommend for cost savings"

The report always shows raw numbers alongside the recommendation so humans can override.

**Q2: How do you fairly compare a 512-dimension model against a 1024-dimension model?**

A: Each model gets its own OpenSearch index with appropriate dimension mapping. Comparison is on retrieval quality metrics (recall, MRR, nDCG) — not on raw vector similarity scores (which are incomparable across dimension spaces). The eval harness already supports this: each `IndexConfig` specifies its own dimensions, and the benchmark creates separate indices per model.

**Q3: What if a model has a shorter max token limit than our current chunking config?**

A: The benchmark auto-adapts:
1. Model registry stores `max_tokens` per model
2. When generating benchmark configs, `max_tokens` is capped to the model's limit
3. If the model's limit (e.g., 512 tokens) is smaller than section chunks (1024 tokens), the benchmark tests with both the model's native limit AND truncation, reporting both
4. The recommendation notes: "Model X requires smaller chunks (512 tokens max) — switching requires re-chunking and re-indexing"

This surfaces operational cost of switching, not just quality difference.

**Q4: How do you handle multimodal models (like Amazon Nova 2) that accept both text and images?**

A: For this phase, multimodal models are benchmarked on text-only embedding quality only. The report notes multimodal capability as a future advantage (diagram search) but does not evaluate image embeddings. Models that ONLY support multimodal input (no pure text mode) are flagged as "incompatible with current pipeline" and skipped.

**Q5: What if benchmarking all 11 models costs hundreds of dollars?**

A: Staged evaluation controls cost:
1. **Stage 1 (filter, ~$0.02 total):** Embed only the 13 ground-truth queries with each model. Eliminate models that error out or produce incompatible outputs.
2. **Stage 2 (subset, ~$1 total):** Index only one document (~100 chunks) with each passing model. Run eval.
3. **Stage 3 (full corpus, top candidates only, ~$1.50):** Only models that beat or match the baseline in Stage 2 get full-corpus evaluation.

Total estimated cost for 11 models: $3-5. A `--budget-cap` flag stops evaluation if cost exceeds a threshold.

**Q6: How do you handle models that aren't yet in the EmbeddingProvider enum?**

A: The benchmark resolves this chicken-and-egg problem:
1. A `DynamicEmbeddingConfig` accepts raw model ID strings (no enum required)
2. The embedding client gains a generic invocation path that works with any Bedrock model conforming to the embedding API contract
3. Only models that pass Stage 1 get promoted to the permanent `EmbeddingProvider` enum
4. No code changes required to TEST a model; code changes only needed to ADOPT one permanently

**Q7: What if a model scores better on our 13 queries but would perform worse on real queries?**

A: This is the fundamental eval harness limitation. Mitigations:
1. The report states confidence intervals based on sample size: "13 queries → ±8% confidence band"
2. Models within the confidence band get "A/B test recommended" rather than "switch immediately"
3. Category breakdown shows if improvement is concentrated (may not generalize) or spread (likely generalizes)
4. A recommendation to expand ground truth accompanies every new model adoption
5. The RAG feature's query log (Feature 1) feeds new ground-truth queries over time, continuously improving eval reliability

### 3.4 ICD-Specific Considerations

**Technical terminology density:** ICD text is dense with domain jargon (TBD, TBR, shall, heritage, bus, payload, waveguide, gimbal). Models trained on general web text may handle these poorly. The benchmark includes queries with heavy technical terminology alongside natural-language paraphrases to test both.

**Numerical precision:** Requirements contain precise values ("28.0 ± 0.5 VDC at 25°C ambient"). Models that treat "28 VDC" and "28.5 VDC" as semantically identical are problematic for precise retrieval. Ground truth includes numerical-precision queries.

**Short vs. long text:** ICD chunks range from single-line requirements ("The system shall weigh no more than 15 kg") to multi-paragraph descriptions. Models perform differently on short vs. long text; the benchmark tests across all chunk strategies to capture this interaction.

**Table content:** Many requirements live in tables. Text extracted from tables has different structure than prose. The benchmark verifies model performance on tabular content.

### 3.5 Acceptance Criteria

1. `python3 -m src.cli search-benchmark` evaluates all unbenchmarked models and produces a comparison report.
2. The benchmark handles different dimension sizes without manual configuration.
3. Chunking parameters are auto-adapted to each model's token limit.
4. Staged evaluation keeps total cost under $10 for up to 15 new models.
5. Output includes a human-readable recommendation with clear justification.
6. Cost-effectiveness analysis: recall improvement per dollar of additional cost.
7. Per-category breakdown provided.
8. Models that fail to produce valid embeddings are excluded with a clear error message.
9. Results are persisted and comparable to previous runs.
10. New models can be tested without code changes to the `EmbeddingProvider` enum.
11. Report includes confidence assessment based on ground-truth sample size.
12. `--dry-run` flag shows which models would be tested and estimated cost without calling APIs.
13. `--budget-cap N` stops evaluation if cumulative cost exceeds N dollars.
14. Deprecated model detection triggers automatic replacement recommendation.

### 3.6 Non-Functional Requirements

- **Cost:** Total benchmark run for 11 models < $10. Per-model cost logged and reported.
- **Performance:** Full benchmark for one model < 10 minutes. Total for 11 models < 2 hours.
- **Reproducibility:** Same model + corpus + ground truth = same results (within API stochasticity). Full config saved with results.
- **Extensibility:** Adding a new chunking strategy or retrieval mode requires only config change, not benchmark code.
- **Idempotency:** Re-running for an already-benchmarked model uses cached index data unless `--force` is specified.

### 3.7 Out of Scope

- **Automatic model switching** — produces recommendations; humans decide
- **Fine-tuning or training custom models** — evaluates pre-trained models as-is
- **Evaluating generative models (LLMs)** — embedding models only; RAG generation quality is separate
- **Multimodal embedding evaluation** — text-only in this phase
- **Pricing negotiation** — reports costs; procurement decisions are human
- **Automatic ground-truth expansion** — uses existing ground truth; expanding is manual

### 3.8 Dependencies & Risks

| Dependency | Risk | Mitigation |
|-----------|------|-----------|
| Bedrock model access | Some models may require marketplace subscriptions | Stage 1 detects access errors; report notes "request access to benchmark" |
| API stability | New models may have different request/response formats | Generic invocation with validation; non-conforming models skipped |
| Ground truth adequacy | 13 queries may be too few for reliable comparison | Confidence intervals reported; expansion recommended with adoption |
| Cost unpredictability | Undocumented per-token pricing for new models | Budget cap; Stage 1 validates pricing |
| Index storage | 11 new indices × 1,054 chunks | Staged eval; purge intermediate indices after eval |
| Token limit heterogeneity | 256-token models perform poorly with 512-token chunks | Auto-adapted chunking; noted in report |

---

## Cross-Cutting Concerns

### Security and Access Control

All three features must respect document distribution markings:
- RAG never synthesizes answers from documents the user isn't authorized to view
- TBD Dashboard filters items by document access level
- Benchmark results don't expose document content (only aggregate metrics)

### Cost Governance

All features incur AWS costs. Each tracks its own:
- **RAG:** per-query cost (embedding + generation), monthly projection
- **TBD Dashboard:** minimal incremental cost (uses existing indices)
- **Benchmark:** per-run cost with budget caps

A global cost dashboard aggregates all pipeline costs.

### Ground Truth Maintenance

The 13-query ground truth is shared infrastructure for both retrieval eval and RAG answer eval. Maintenance cadence: add 5+ new queries quarterly, sourced from real user questions captured by the RAG query log.

### Feature Integration

The three features are complementary:
1. **RAG uses search** — RAG quality is bounded by retrieval quality. Better models (Feature 3) improve RAG answers (Feature 1).
2. **RAG surfaces TBDs** — When a RAG answer includes TBD content, it links to the TBD Dashboard (Feature 2).
3. **TBD Dashboard uses search** — Cross-document correlation uses vector similarity from the search index.
4. **Benchmark improves all** — Better embeddings improve both RAG retrieval and TBD semantic matching.

---

## Implementation Order

| Priority | Feature | Effort | Rationale |
|----------|---------|--------|-----------|
| 1st | Benchmark New Models | 1-2 days | Identifies the best model for RAG; no dependencies |
| 2nd | RAG over ICD Corpus | 2-3 days | Highest user visibility; uses best model from benchmark |
| 3rd | TBD Dashboard | 2-3 days | Extends existing module; can proceed in parallel with RAG frontend |

Rationale: Benchmark first because it determines which embedding model RAG will use. RAG second because it's the highest-value user feature. TBD Dashboard third because it has lower technical risk and builds on existing extraction.

---

## Approval

| Role | Name | Date | Signature |
|------|------|------|-----------|
| Program Manager | | | |
| Lead Systems Engineer | | | |
| Software Architect | | | |
| Quality Assurance | | | |

---

*End of Requirements Specification*
