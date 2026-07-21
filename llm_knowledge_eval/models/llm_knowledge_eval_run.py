import logging

from odoo import _, api, fields, models

_logger = logging.getLogger(__name__)


class LLMKnowledgeEvalRun(models.Model):
    _name = "llm.knowledge.eval.run"
    _description = "RAG Evaluation Run"
    _inherit = ["mail.thread"]
    _order = "id desc"

    name = fields.Char(compute="_compute_name", store=True)
    testset_id = fields.Many2one(
        "llm.knowledge.testset", required=True, ondelete="cascade", tracking=True
    )
    target_collection_id = fields.Many2one(
        "llm.knowledge.collection",
        string="Collection Under Test",
        required=True,
        tracking=True,
        help="Knowledge collection being evaluated. Can differ from the test "
        "set's source collection, e.g. to A/B test different chunking or "
        "embedding configurations with the same question set.",
    )
    metric_ids = fields.Many2many("llm.knowledge.eval.metric", string="Metrics")
    top_k = fields.Integer(default=5, string="Top K", tracking=True)
    state = fields.Selection(
        [
            ("draft", "Draft"),
            ("running", "Running"),
            ("done", "Done"),
            ("failed", "Failed"),
        ],
        default="draft",
        required=True,
        tracking=True,
    )
    aggregate_scores = fields.Json(default=dict, readonly=True)
    scores_by_query_type = fields.Json(default=dict, readonly=True)
    error_message = fields.Text(readonly=True)
    result_ids = fields.One2many("llm.knowledge.eval.result", "eval_run_id")
    result_count = fields.Integer(compute="_compute_result_count")
    active = fields.Boolean(default=True)

    @api.depends("testset_id.name", "target_collection_id.name")
    def _compute_name(self):
        for run in self:
            run.name = _("%(testset)s @ %(collection)s") % {
                "testset": run.testset_id.name or _("New Test Set"),
                "collection": run.target_collection_id.name or _("New Collection"),
            }

    @api.depends("result_ids")
    def _compute_result_count(self):
        for run in self:
            run.result_count = len(run.result_ids)

    def action_view_results(self):
        self.ensure_one()
        return {
            "name": _("Evaluation Results"),
            "type": "ir.actions.act_window",
            "res_model": "llm.knowledge.eval.result",
            "view_mode": "list,form",
            "domain": [("eval_run_id", "=", self.id)],
        }
