import logging

from odoo import api, fields, models
from odoo.exceptions import ValidationError

from ..fields import PgVector

_logger = logging.getLogger(__name__)


class LLMKnowledgeChunkEmbedding(models.Model):
    _name = "llm.knowledge.chunk.embedding"
    _description = "Vector Embedding for Knowledge Chunks"

    chunk_id = fields.Many2one(
        "llm.knowledge.chunk",
        string="Chunk",
        required=True,
        ondelete="cascade",
        index=True,
    )
    # Related field to get collections from chunk's resource
    collection_ids = fields.Many2many(
        "llm.knowledge.collection",
        string="Collections",
        related="chunk_id.collection_ids",
        store=False,
        readonly=True,
    )
    embedding_model_id = fields.Many2one(
        "llm.model",
        string="Embedding Model",
        domain="[('model_use', '=', 'embedding')]",
        required=True,
        ondelete="restrict",
        index=True,
    )
    embedding = PgVector(
        string="Vector Embedding",
        help="Vector embedding for similarity search",
    )

    resource_id = fields.Many2one(
        related="chunk_id.resource_id",
        store=True,
        readonly=True,
        index=True,
    )

    display_name = fields.Char(
        compute="_compute_display_name", string="Display Name"
    )

    @api.depends("chunk_id.name", "embedding_model_id.name")
    def _compute_display_name(self):
        """Compute display name for better readability"""
        for record in self:
            chunk_name = record.chunk_id.name if record.chunk_id else "Chunk"
            model_name = (
                record.embedding_model_id.name if record.embedding_model_id else "Model"
            )
            record.display_name = f"{chunk_name} [{model_name}]"

    @api.constrains("chunk_id", "embedding_model_id")
    def _check_unique_chunk_embedding_model(self):
        """Ensure a chunk can only have one embedding per embedding model"""
        for record in self:
            if record.chunk_id and record.embedding_model_id:
                # Check for duplicate embeddings
                duplicates = self.search(
                    [
                        ("chunk_id", "=", record.chunk_id.id),
                        ("embedding_model_id", "=", record.embedding_model_id.id),
                        ("id", "!=", record.id),
                    ],
                    limit=1,
                )
                if duplicates:
                    raise ValidationError(
                        "A chunk can only have one embedding per embedding model"
                    )

    @api.model_create_multi
    def create(self, vals_list):
        """Override create to handle special cases"""
        for vals in vals_list:
            # If embedding_model_id not provided, try to get from collection
            if not vals.get("embedding_model_id") and vals.get("chunk_id"):
                chunk = self.env["llm.knowledge.chunk"].browse(vals["chunk_id"])
                # Get first collection's embedding model
                if chunk.collection_ids and chunk.collection_ids[0].embedding_model_id:
                    vals["embedding_model_id"] = chunk.collection_ids[
                        0
                    ].embedding_model_id.id

        return super().create(vals_list)
