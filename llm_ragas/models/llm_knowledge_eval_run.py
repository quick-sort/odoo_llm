import logging
import time

from odoo import _, fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

# Maps our generic llm.knowledge.eval.metric.code to a class name in
# ragas.metrics.collections.
_RAGAS_METRIC_CLASS_BY_CODE = {
    "faithfulness": "Faithfulness",
    "answer_relevancy": "AnswerRelevancy",
    "context_precision": "ContextPrecision",
    "context_recall": "ContextRecall",
    "context_entities_recall": "ContextEntityRecall",
    "noise_sensitivity": "NoiseSensitivity",
}


def _metric_kwargs(code, question, answer, contexts, reference):
    """Build the keyword arguments a given ragas collections metric expects."""
    if code == "faithfulness":
        return {"user_input": question, "response": answer, "retrieved_contexts": contexts}
    if code == "answer_relevancy":
        return {"user_input": question, "response": answer}
    if code == "context_precision":
        return {"user_input": question, "reference": reference, "retrieved_contexts": contexts}
    if code == "context_recall":
        return {"user_input": question, "retrieved_contexts": contexts, "reference": reference}
    if code == "context_entities_recall":
        return {"reference": reference, "retrieved_contexts": contexts}
    if code == "noise_sensitivity":
        return {
            "user_input": question,
            "response": answer,
            "reference": reference,
            "retrieved_contexts": contexts,
        }
    # Best-effort default for metrics not in the registry above.
    return {
        "user_input": question,
        "response": answer,
        "retrieved_contexts": contexts,
        "reference": reference,
    }


class LLMKnowledgeEvalRun(models.Model):
    _inherit = "llm.knowledge.eval.run"

    ragas_judge_llm_model_id = fields.Many2one(
        "llm.model",
        string="Ragas Judge LLM",
        domain="[('model_use', 'in', ('chat', 'completion'))]",
        help="Used both to generate the answer being evaluated and, for "
        "LLM-based metrics, to score it.",
    )
    ragas_embedding_model_id = fields.Many2one(
        "llm.model",
        string="Ragas Judge Embedding Model",
        domain="[('model_use', '=', 'embedding')]",
        help="Required only if the 'answer_relevancy' metric is selected.",
    )

    def action_run_with_ragas(self):
        for run in self:
            run._run_with_ragas()
        return True

    def _run_with_ragas(self):
        self.ensure_one()

        import ragas.metrics.collections as ragas_metric_collections

        from .ragas_adapters import get_ragas_embedding_for_metrics, get_ragas_llm

        if not self.ragas_judge_llm_model_id:
            raise UserError(_("Set a judge LLM model before running a ragas evaluation."))
        active_items = self.testset_id.item_ids.filtered("active")
        if not active_items:
            raise UserError(_("The test set has no active test cases."))

        judge_llm = get_ragas_llm(self.ragas_judge_llm_model_id)
        judge_embeddings = None

        scorers = {}
        for metric in self.metric_ids:
            metric_cls_name = _RAGAS_METRIC_CLASS_BY_CODE.get(metric.code)
            metric_cls = getattr(ragas_metric_collections, metric_cls_name, None)
            if metric_cls is None:
                _logger.warning(
                    "No ragas collections metric class found for code '%s' "
                    "(run %s), skipping.",
                    metric.code,
                    self.id,
                )
                continue

            kwargs = {"llm": judge_llm}
            if metric.code == "answer_relevancy":
                if not self.ragas_embedding_model_id:
                    raise UserError(
                        _(
                            "The 'answer_relevancy' metric requires a judge "
                            "embedding model to be set on this run."
                        )
                    )
                if judge_embeddings is None:
                    judge_embeddings = get_ragas_embedding_for_metrics(
                        self.ragas_embedding_model_id
                    )
                kwargs["embeddings"] = judge_embeddings

            scorers[metric.code] = metric_cls(**kwargs)

        if not scorers:
            raise UserError(
                _("None of the selected metrics have a known ragas implementation.")
            )

        self.write({"state": "running", "error_message": False})
        self.result_ids.unlink()

        try:
            result_vals = []
            per_metric_scores = {code: [] for code in scorers}
            per_type_scores = {}

            for item in active_items:
                start = time.monotonic()
                chunks = self._ragas_retrieve_context(item.question)
                answer = self._ragas_generate_answer(item.question, chunks)
                latency_ms = (time.monotonic() - start) * 1000.0

                contexts = [c.content for c in chunks]
                scores = {}
                for code, scorer in scorers.items():
                    kwargs = _metric_kwargs(
                        code, item.question, answer, contexts, item.reference_answer
                    )
                    try:
                        metric_result = scorer.score(**kwargs)
                        scores[code] = float(metric_result.value)
                    except Exception as exc:
                        _logger.warning(
                            "Failed to compute metric '%s' for test case %s: %s",
                            code,
                            item.id,
                            exc,
                        )
                        scores[code] = -1.0

                    if scores[code] >= 0:
                        per_metric_scores[code].append(scores[code])
                        qtype = item.query_type or "unknown"
                        per_type_scores.setdefault(qtype, {}).setdefault(
                            code, []
                        ).append(scores[code])

                result_vals.append(
                    {
                        "eval_run_id": self.id,
                        "testset_item_id": item.id,
                        "generated_answer": answer,
                        "retrieved_chunk_ids": [(6, 0, chunks.ids)],
                        "scores": scores,
                        "latency_ms": latency_ms,
                    }
                )

            if result_vals:
                self.env["llm.knowledge.eval.result"].create(result_vals)

            aggregate_scores = {
                code: (sum(vals) / len(vals) if vals else -1.0)
                for code, vals in per_metric_scores.items()
            }
            scores_by_query_type = {
                qtype: {
                    code: (sum(vals) / len(vals) if vals else -1.0)
                    for code, vals in code_map.items()
                }
                for qtype, code_map in per_type_scores.items()
            }

            self.write(
                {
                    "state": "done",
                    "aggregate_scores": aggregate_scores,
                    "scores_by_query_type": scores_by_query_type,
                }
            )
        except Exception as exc:
            _logger.exception("Ragas evaluation run %s failed", self.id)
            self.write({"state": "failed", "error_message": str(exc)})
            raise

    def _ragas_retrieve_context(self, question):
        """Retrieve context chunks using llm_knowledge's own vector search API
        (llm.knowledge.chunk's overridden ``search()``), so evaluation goes
        through the exact same retrieval path production traffic uses.
        """
        self.ensure_one()
        return self.env["llm.knowledge.chunk"].search(
            [("embedding", "=", question)],
            limit=self.top_k,
            collection_id=self.target_collection_id.id,
        )

    def _ragas_generate_answer(self, question, chunks):
        """Generate the answer being evaluated using the judge LLM and the
        retrieved chunks, reusing ``llm.model.chat()``.

        NOTE: not verified against a live Odoo instance. ``llm.model.chat()``
        expects a ``mail.message`` recordset; this builds one unsaved record
        via ``.new()`` rather than adding a new "raw chat" entry point to the
        base ``llm`` module. If a given provider's message formatting relies
        on persisted-record specifics, this may need to post a real
        (and then cleaned up) message instead.
        """
        self.ensure_one()
        context_text = "\n\n---\n\n".join(c.content for c in chunks)
        prompt = _(
            "Based on the following context, answer the question. If the "
            "answer cannot be found in the context, say so.\n\n"
            "Context:\n%(context)s\n\nQuestion: %(question)s\n\nAnswer:"
        ) % {"context": context_text, "question": question}

        message = self.env["mail.message"].new({"body": prompt, "llm_role": "user"})
        response = self.ragas_judge_llm_model_id.chat(message)
        if isinstance(response, dict):
            return response.get("content", "")
        return str(response)
