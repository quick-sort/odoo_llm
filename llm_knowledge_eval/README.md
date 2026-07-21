# LLM Knowledge Evaluation

Tool-agnostic data model for RAG test sets, evaluation runs and results.

**Module Type:** 📦 Infrastructure (RAG Evaluation)

## Why a separate module?

This module deliberately has **no dependency on any specific test-generation or
scoring tool** (ragas, or anything else). It only defines:

- `llm.knowledge.testset` / `llm.knowledge.testset.item` — question / reference
  answer pairs used to evaluate a knowledge collection.
- `llm.knowledge.eval.metric` — a registry of metric definitions (name, code,
  free-text `implementation` tag such as `"ragas"`).
- `llm.knowledge.eval.run` / `llm.knowledge.eval.result` — a single evaluation
  run of a test set against a collection, and its per-question results
  (including the actual `llm.knowledge.chunk` records that were retrieved).

Any generator/evaluator tool can populate these tables. Today that's
`llm_ragas`. If ragas is replaced or supplemented by another tool later, this
module and everything built on top of it (dashboards, review workflows,
comparisons across collections) keeps working unchanged.

## Key design points

- `llm.knowledge.eval.run.target_collection_id` can differ from
  `llm.knowledge.testset.collection_id`, so the same test set can be used to
  A/B test different chunking/embedding configurations or vector stores.
- `llm.knowledge.eval.result.retrieved_chunk_ids` links to real
  `llm.knowledge.chunk` records (not a text snapshot), so results are
  traceable back to the actual indexed content.
- `llm.knowledge.testset.item.active` lets you review and disable
  low-quality generated questions without losing them.

## Installation

```bash
odoo-bin -d your_db -i llm_knowledge_eval
```

Depends only on `llm_knowledge`. Install `llm_ragas` (or a future alternative)
to actually generate test sets and run evaluations.

## License

LGPL-3
