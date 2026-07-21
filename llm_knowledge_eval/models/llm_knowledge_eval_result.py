from odoo import fields, models


class LLMKnowledgeEvalResult(models.Model):
    _name = "llm.knowledge.eval.result"
    _description = "RAG Evaluation Result"
    _order = "eval_run_id, id"

    eval_run_id = fields.Many2one(
        "llm.knowledge.eval.run", required=True, ondelete="cascade", index=True
    )
    testset_item_id = fields.Many2one(
        "llm.knowledge.testset.item", required=True, ondelete="cascade", index=True
    )
    question = fields.Text(
        related="testset_item_id.question", store=True, readonly=True
    )
    query_type = fields.Char(
        related="testset_item_id.query_type", store=True, readonly=True
    )
    generated_answer = fields.Text()
    retrieved_chunk_ids = fields.Many2many(
        "llm.knowledge.chunk",
        string="Retrieved Chunks",
        help="The actual chunk records returned by the collection's retrieval "
        "for this question, so results are traceable back to real content.",
    )
    scores = fields.Json(default=dict, help="Metric code -> score value.")
    latency_ms = fields.Float(string="Latency (ms)")
