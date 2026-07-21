from odoo import api, fields, models


class LLMRagasKnowledgeGraphNode(models.Model):
    _name = "llm.ragas.knowledge.graph.node"
    _description = "Ragas Knowledge Graph Node"
    _order = "graph_id, id"

    _unique_node_per_graph = models.Constraint(
        "UNIQUE(graph_id, ragas_uuid)",
        "A node with this ragas UUID already exists in this graph.",
    )

    graph_id = fields.Many2one(
        "llm.ragas.knowledge.graph", required=True, ondelete="cascade", index=True
    )
    name = fields.Char(compute="_compute_name", store=True)
    ragas_uuid = fields.Char(
        required=True,
        index=True,
        help="UUID of the corresponding ragas Node object, used to reconstruct "
        "an in-memory KnowledgeGraph for reuse (test set generation).",
    )
    node_type = fields.Char(
        help="Raw ragas NodeType value ('document', 'chunk', ...). Kept as free "
        "text instead of a Selection so future ragas node types don't require "
        "a migration.",
    )
    chunk_id = fields.Many2one(
        "llm.knowledge.chunk", ondelete="set null", index=True
    )
    resource_id = fields.Many2one(
        "llm.resource", ondelete="set null", index=True
    )
    properties = fields.Json(
        default=dict,
        help="Raw ragas node properties (summary, entities, themes, "
        "summary_embedding, ...).",
    )

    @api.depends("node_type", "chunk_id.name", "resource_id.name")
    def _compute_name(self):
        for node in self:
            label = node.chunk_id.name or node.resource_id.name or node.ragas_uuid
            node.name = f"[{node.node_type}] {label}" if node.node_type else label
