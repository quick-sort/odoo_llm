import logging

from odoo import _, fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class LLMKnowledgeTestset(models.Model):
    _inherit = "llm.knowledge.testset"

    ragas_graph_id = fields.Many2one(
        "llm.ragas.knowledge.graph",
        string="Ragas Knowledge Graph",
        domain="[('collection_id', '=', collection_id), ('state', '=', 'ready')]",
        help="Pre-built, reusable knowledge graph to generate questions from. "
        "Build it once under LLM Ragas > Knowledge Graphs, then reuse it for "
        "as many test sets as needed.",
    )
    ragas_generation_llm_model_id = fields.Many2one(
        "llm.model",
        string="Ragas Question-Generation Model",
        domain="[('model_use', 'in', ('chat', 'completion'))]",
    )
    ragas_test_size = fields.Integer(string="Ragas Test Size", default=20)
    ragas_distribution = fields.Json(
        string="Ragas Query Type Distribution",
        default=lambda self: {
            "single_hop_specific": 0.35,
            "multi_hop_abstract": 0.3,
            "multi_hop_specific": 0.35,
        },
        help="Relative weights (normalized automatically) per ragas query "
        "synthesizer: single_hop_specific, multi_hop_abstract, "
        "multi_hop_specific.",
    )

    def action_generate_with_ragas(self):
        for testset in self:
            testset._generate_with_ragas()
        return True

    def _generate_with_ragas(self):
        self.ensure_one()

        from ragas.testset import TestsetGenerator
        from ragas.testset.synthesizers import (
            MultiHopAbstractQuerySynthesizer,
            MultiHopSpecificQuerySynthesizer,
            SingleHopSpecificQuerySynthesizer,
        )

        from .ragas_adapters import get_ragas_embeddings_for_graph, get_ragas_llm

        if not self.ragas_generation_llm_model_id:
            raise UserError(
                _("Set a question-generation LLM model before generating with ragas.")
            )
        if not self.ragas_graph_id or self.ragas_graph_id.state != "ready":
            raise UserError(
                _(
                    "Build a ready 'Ragas Knowledge Graph' for this test set's "
                    "collection first (LLM Ragas > Knowledge Graphs), then "
                    "select it here."
                )
            )

        llm = get_ragas_llm(self.ragas_generation_llm_model_id)
        embeddings = get_ragas_embeddings_for_graph(
            self.ragas_graph_id.embedding_model_id
        )

        generator = TestsetGenerator(llm=llm, embedding_model=embeddings)
        generator.knowledge_graph = self.ragas_graph_id.to_ragas_knowledge_graph()

        synth_map = {
            "single_hop_specific": SingleHopSpecificQuerySynthesizer,
            "multi_hop_abstract": MultiHopAbstractQuerySynthesizer,
            "multi_hop_specific": MultiHopSpecificQuerySynthesizer,
        }
        distribution = self.ragas_distribution or {}
        total_weight = sum(
            weight
            for key, weight in distribution.items()
            if weight and weight > 0 and key in synth_map
        )
        if not total_weight:
            raise UserError(
                _(
                    "ragas_distribution has no valid, positive weights for the "
                    "known synthesizers: %(keys)s"
                )
                % {"keys": ", ".join(synth_map)}
            )

        query_distribution = [
            (synth_map[key](llm=llm), weight / total_weight)
            for key, weight in distribution.items()
            if weight and weight > 0 and key in synth_map
        ]

        self.write({"state": "generating"})
        try:
            ragas_testset = generator.generate(
                testset_size=self.ragas_test_size,
                query_distribution=query_distribution,
            )
        except Exception:
            self.write({"state": "failed"})
            raise

        item_vals = []
        for sample in ragas_testset.to_list():
            item_vals.append(
                {
                    "testset_id": self.id,
                    "question": sample.get("user_input"),
                    "reference_answer": sample.get("reference"),
                    "reference_contexts": sample.get("reference_contexts") or [],
                    "query_type": sample.get("synthesizer_name"),
                    "provenance": {
                        "tool": "ragas",
                        "graph_id": self.ragas_graph_id.id,
                    },
                }
            )
        if item_vals:
            self.env["llm.knowledge.testset.item"].create(item_vals)

        self.write({"state": "ready", "source": "ragas"})
