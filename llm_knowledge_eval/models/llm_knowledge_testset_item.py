from odoo import api, fields, models


class LLMKnowledgeTestsetItem(models.Model):
    _name = "llm.knowledge.testset.item"
    _description = "RAG Test Case"
    _order = "testset_id, sequence, id"

    testset_id = fields.Many2one(
        "llm.knowledge.testset", required=True, ondelete="cascade", index=True
    )
    sequence = fields.Integer(default=10)
    name = fields.Char(compute="_compute_name", store=True)
    question = fields.Text(required=True)
    reference_answer = fields.Text(string="Reference Answer")
    reference_contexts = fields.Json(
        string="Reference Contexts",
        default=list,
        help="Ground-truth context snippets the reference answer was derived from.",
    )
    query_type = fields.Char(
        string="Query Type",
        help="Free-text label such as single_hop_specific, multi_hop_abstract, "
        "manual, etc. Not restricted to any specific generator tool's vocabulary.",
    )
    source_resource_ids = fields.Many2many(
        "llm.resource",
        string="Source Documents",
        help="Documents this question/answer is derived from, when known.",
    )
    provenance = fields.Json(
        string="Provenance",
        default=dict,
        help="Opaque metadata about how this test case was produced, "
        "e.g. {'tool': 'ragas', 'graph_id': 12}.",
    )
    active = fields.Boolean(
        default=True,
        help="Uncheck to exclude a low-quality generated question from "
        "evaluation runs without deleting it.",
    )

    @api.depends("question")
    def _compute_name(self):
        for item in self:
            question = (item.question or "").strip().replace("\n", " ")
            item.name = (question[:80] + "…") if len(question) > 80 else question
