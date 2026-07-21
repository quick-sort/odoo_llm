from odoo import fields, models


class LLMKnowledgeEvalMetric(models.Model):
    _name = "llm.knowledge.eval.metric"
    _description = "RAG Evaluation Metric Definition"
    _order = "sequence, id"

    _unique_code = models.Constraint(
        "UNIQUE(code)",
        "A metric with this code is already registered.",
    )

    name = fields.Char(required=True)
    code = fields.Char(
        required=True,
        help="Unique technical code used to reference this metric, e.g. "
        "'faithfulness', 'answer_relevancy'.",
    )
    description = fields.Text()
    implementation = fields.Char(
        help="Free-text tag identifying which module knows how to compute this "
        "metric, e.g. 'ragas'. This module does not depend on any implementation.",
    )
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)
