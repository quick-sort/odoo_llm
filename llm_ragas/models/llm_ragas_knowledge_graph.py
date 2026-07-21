import logging

from odoo import _, api, fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class LLMRagasKnowledgeGraph(models.Model):
    _name = "llm.ragas.knowledge.graph"
    _description = "Ragas Knowledge Graph"
    _inherit = ["mail.thread"]
    _order = "id desc"

    name = fields.Char(required=True, tracking=True)
    collection_id = fields.Many2one(
        "llm.knowledge.collection",
        required=True,
        ondelete="cascade",
        tracking=True,
    )
    resource_ids = fields.Many2many(
        "llm.resource",
        string="Documents (optional subset)",
        help="Leave empty to use every resource in the collection.",
    )
    embedding_model_id = fields.Many2one(
        "llm.model",
        string="Graph Embedding Model",
        domain="[('model_use', '=', 'embedding')]",
        required=True,
        tracking=True,
        help="Embedding model used ONLY to build this knowledge graph "
        "(node-summary similarity). Independent from the collection's "
        "retrieval embedding model - this is a separate cost incurred once "
        "per graph build, not reused from the vector store.",
    )
    llm_model_id = fields.Many2one(
        "llm.model",
        string="Graph LLM Model",
        domain="[('model_use', 'in', ('chat', 'completion'))]",
        required=True,
        tracking=True,
        help="LLM used for summary/entity/theme extraction while building "
        "the graph.",
    )
    state = fields.Selection(
        [
            ("draft", "Draft"),
            ("building", "Building"),
            ("ready", "Ready"),
            ("failed", "Failed"),
        ],
        default="draft",
        required=True,
        tracking=True,
    )
    error_message = fields.Text(readonly=True)
    node_ids = fields.One2many("llm.ragas.knowledge.graph.node", "graph_id")
    relationship_ids = fields.One2many(
        "llm.ragas.knowledge.graph.relationship", "graph_id"
    )
    node_count = fields.Integer(compute="_compute_counts", store=True)
    relationship_count = fields.Integer(compute="_compute_counts", store=True)
    active = fields.Boolean(default=True)

    @api.depends("node_ids", "relationship_ids")
    def _compute_counts(self):
        for graph in self:
            graph.node_count = len(graph.node_ids)
            graph.relationship_count = len(graph.relationship_ids)

    def _get_target_chunks(self):
        self.ensure_one()
        resources = self.resource_ids or self.collection_id.resource_ids
        resources = resources.filtered(
            lambda r: r.state in ("chunked", "ready") and r.chunk_ids
        )
        return resources.mapped("chunk_ids").filtered("content")

    def action_build_graph(self):
        for graph in self:
            graph._build_graph()
        return True

    def _build_graph(self):
        self.ensure_one()

        from ragas.run_config import RunConfig
        from ragas.testset.graph import KnowledgeGraph as RagasKnowledgeGraph
        from ragas.testset.graph import Node as RagasNode
        from ragas.testset.graph import NodeType as RagasNodeType
        from ragas.testset.transforms import (
            apply_transforms,
            default_transforms_for_prechunked,
        )

        from .ragas_adapters import get_ragas_embeddings_for_graph, get_ragas_llm

        chunks = self._get_target_chunks()
        if not chunks:
            raise UserError(
                _(
                    "No chunked/ready resources with content were found for "
                    "this graph's collection/resources."
                )
            )

        self.write({"state": "building", "error_message": False})
        # Recreate from scratch: relationships cascade-delete with their nodes.
        self.node_ids.unlink()

        try:
            ragas_nodes = []
            chunk_by_ragas_uuid = {}
            for chunk in chunks:
                node = RagasNode(
                    type=RagasNodeType.CHUNK,
                    properties={
                        "page_content": chunk.content,
                        "document_metadata": {
                            "chunk_id": chunk.id,
                            "resource_id": chunk.resource_id.id,
                            "resource_name": chunk.resource_id.name,
                        },
                    },
                )
                ragas_nodes.append(node)
                chunk_by_ragas_uuid[str(node.id)] = chunk

            kg = RagasKnowledgeGraph(nodes=ragas_nodes)

            llm = get_ragas_llm(self.llm_model_id)
            embeddings = get_ragas_embeddings_for_graph(self.embedding_model_id)
            transforms = default_transforms_for_prechunked(
                llm=llm, embedding_model=embeddings
            )
            apply_transforms(kg, transforms, run_config=RunConfig())

            self._sync_from_ragas_kg(kg, chunk_by_ragas_uuid)
            self.write({"state": "ready"})
        except Exception as exc:
            _logger.exception("Failed to build ragas knowledge graph %s", self.id)
            self.write({"state": "failed", "error_message": str(exc)})
            raise

    def _sync_from_ragas_kg(self, kg, chunk_by_ragas_uuid=None):
        """Persist a ragas ``KnowledgeGraph`` into node/relationship records."""
        self.ensure_one()
        chunk_by_ragas_uuid = chunk_by_ragas_uuid or {}

        node_vals = []
        for node in kg.nodes:
            chunk = chunk_by_ragas_uuid.get(str(node.id))
            node_vals.append(
                {
                    "graph_id": self.id,
                    "ragas_uuid": str(node.id),
                    "node_type": node.type.value,
                    "chunk_id": chunk.id if chunk else False,
                    "resource_id": chunk.resource_id.id if chunk else False,
                    "properties": node.properties,
                }
            )
        node_records = self.env["llm.ragas.knowledge.graph.node"].create(node_vals)
        node_id_by_uuid = {rec.ragas_uuid: rec.id for rec in node_records}

        rel_vals = []
        for rel in kg.relationships:
            source_id = node_id_by_uuid.get(str(rel.source.id))
            target_id = node_id_by_uuid.get(str(rel.target.id))
            if not source_id or not target_id:
                _logger.warning(
                    "Skipping ragas relationship %s: source/target node not "
                    "found among persisted nodes.",
                    rel.id,
                )
                continue
            rel_vals.append(
                {
                    "graph_id": self.id,
                    "ragas_uuid": str(rel.id),
                    "relationship_type": rel.type,
                    "source_node_id": source_id,
                    "target_node_id": target_id,
                    "bidirectional": rel.bidirectional,
                    "properties": rel.properties,
                }
            )
        if rel_vals:
            self.env["llm.ragas.knowledge.graph.relationship"].create(rel_vals)

    def to_ragas_knowledge_graph(self):
        """Rebuild an in-memory ragas ``KnowledgeGraph`` from the persisted
        node/relationship records, so a testset generator can reuse an
        already-built graph without paying the extraction/embedding cost
        again.
        """
        self.ensure_one()
        import uuid as uuid_module

        from ragas.testset.graph import KnowledgeGraph as RagasKnowledgeGraph
        from ragas.testset.graph import Node as RagasNode
        from ragas.testset.graph import NodeType as RagasNodeType
        from ragas.testset.graph import Relationship as RagasRelationship

        nodes_by_odoo_id = {}
        ragas_nodes = []
        for rec in self.node_ids:
            node = RagasNode(
                id=uuid_module.UUID(rec.ragas_uuid),
                type=RagasNodeType(rec.node_type),
                properties=rec.properties or {},
            )
            nodes_by_odoo_id[rec.id] = node
            ragas_nodes.append(node)

        ragas_relationships = []
        for rec in self.relationship_ids:
            ragas_relationships.append(
                RagasRelationship(
                    id=uuid_module.UUID(rec.ragas_uuid),
                    type=rec.relationship_type,
                    source=nodes_by_odoo_id[rec.source_node_id.id],
                    target=nodes_by_odoo_id[rec.target_node_id.id],
                    bidirectional=rec.bidirectional,
                    properties=rec.properties or {},
                )
            )

        return RagasKnowledgeGraph(nodes=ragas_nodes, relationships=ragas_relationships)
