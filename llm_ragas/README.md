# LLM Ragas

Ragas-powered knowledge graph construction, test set generation and RAG
evaluation, wired into `llm_knowledge` and `llm_knowledge_eval`.

**Module Type:** 🔌 Extension (Ragas Implementation)

## What this module does NOT do

It does not define its own test set / evaluation result tables. Generated
questions and evaluation results are written into `llm_knowledge_eval`'s
tool-agnostic models (`llm.knowledge.testset[.item]`,
`llm.knowledge.eval.run/result`). `llm_ragas` only adds:

- `llm.ragas.knowledge.graph` (+ `.node` / `.relationship`) — a structured,
  reusable representation of ragas' `KnowledgeGraph`.
- A handful of fields and buttons on `llm.knowledge.testset` /
  `llm.knowledge.eval.run` (via `_inherit`) to trigger ragas-specific
  generation/evaluation.

If ragas is ever replaced, only this module changes.

## Reusing Odoo's provider configuration

Whenever the `llm.provider` behind a model exposes a native SDK client via
`provider.client` (e.g. `llm_openai`'s `openai.OpenAI(...)`), and ragas has
a factory that can use it directly, this module hands that client straight
to ragas' own `llm_factory()` / `embedding_factory()` — no custom adapter
code, and all traffic still goes through the API key/base URL configured on
the Odoo provider record.

A fallback path (`ragas_adapters.py`) is used for providers without a
ragas-recognized SDK client:

- Embeddings: fully implemented, calls `llm.model.embedding()` directly.
- LLM structured generation: **not implemented yet** (raises
  `NotImplementedError` with a pointer to `ragas_adapters.py`) because
  `llm.provider.chat()` expects an Odoo `mail.message` recordset rather than
  a plain prompt string, and building a robust JSON-schema-constrained
  fallback for arbitrary providers is a separate piece of work. Use an
  OpenAI or Anthropic-compatible provider for `llm_ragas` in the meantime.

Knowledge-graph building is a third, special case: ragas' legacy embedding
interface (`BaseRagasEmbeddings`, required by the graph-building transforms)
has no useful way to accept a pre-built SDK client at all — its own
`embedding_factory()` legacy path silently ignores any `client` argument and
builds a fresh OpenAI client from environment variables instead. So graph
building *always* goes straight through `llm.model.embedding()`
(`_OdooRagasEmbeddingsForGraph`), for every provider, with no SDK-passthrough
fast path to prefer in the first place. No langchain client, no raw openai
client — only `ragas` itself is a Python dependency of this module.

## Knowledge graph reuse

Building a graph (`llm.ragas.knowledge.graph.action_build_graph`) is the
expensive step (LLM calls for summary/entity/theme extraction, embedding
calls for similarity edges). It is a standalone, persisted record that can
be reused across multiple test set generations
(`llm.knowledge.testset.action_generate_with_ragas`) without rebuilding.

Nodes are built directly from `llm.knowledge.chunk` records already produced
by `llm_knowledge`'s indexing pipeline (via ragas'
`default_transforms_for_prechunked`), so ragas' own document splitting step
is skipped entirely.

Note: the embedding computed while building the graph (a summary embedding,
used only to derive `cosine_similarity` relationships between nodes) is a
separate cost from the embeddings already stored in the vector store for
retrieval — it embeds LLM-generated summaries, not the raw chunk content, so
it cannot reuse the vectors already indexed for search.

## Caveats / not yet verified

This module was written against the `ragas` HEAD checked out locally
(`vibrantlabsai/ragas`), by reading its source directly, but has **not**
been run against a live Odoo + ragas + LLM provider environment. In
particular:

- The exact shape of `SingleTurnSample`/testset sample dicts, and the
  `ragas.metrics.collections.*` constructor signatures, should be
  double-checked against the ragas version actually installed.
- `_ragas_generate_answer()` builds an unsaved `mail.message` via `.new(...)`
  to reuse `llm.model.chat()`; this has not been confirmed to work across
  all provider message-formatting implementations.

## License

LGPL-3
