from odoo import api, fields, models


class LLMRagasKnowledgeGraphRelationship(models.Model):
    _name = "llm.ragas.knowledge.graph.relationship"
    _description = "Ragas Knowledge Graph Relationship"
    _order = "graph_id, id"

    _unique_relationship_per_graph = models.Constraint(
        "UNIQUE(graph_id, ragas_uuid)",
        "A relationship with this ragas UUID already exists in this graph.",
    )

    graph_id = fields.Many2one(
        "llm.ragas.knowledge.graph", required=True, ondelete="cascade", index=True
    )
    name = fields.Char(compute="_compute_name", store=True)
    ragas_uuid = fields.Char(required=True, index=True)
    relationship_type = fields.Char(
        help="Raw ragas relationship type, e.g. 'cosine_similarity', "
        "'entities_overlap'.",
    )
    source_node_id = fields.Many2one(
        "llm.ragas.knowledge.graph.node", required=True, ondelete="cascade"
    )
    target_node_id = fields.Many2one(
        "llm.ragas.knowledge.graph.node", required=True, ondelete="cascade"
    )
    bidirectional = fields.Boolean()
    properties = fields.Json(
        default=dict,
        help="Raw ragas relationship properties (similarity score, shared "
        "entities, ...).",
    )

    @api.depends("relationship_type", "source_node_id.name", "target_node_id.name")
    def _compute_name(self):
        for rel in self:
            arrow = "<->" if rel.bidirectional else "->"
            rel.name = (
                f"{rel.source_node_id.name} {arrow} {rel.target_node_id.name} "
                f"({rel.relationship_type})"
            )
