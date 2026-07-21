{
    "name": "LLM Ragas",
    "summary": "Ragas-powered knowledge graph construction, test set generation "
    "and RAG evaluation for llm_knowledge / llm_knowledge_eval",
    "description": """
        Implements RAG test set generation and evaluation using the ragas
        library, reusing Odoo's existing llm.provider / llm.model configuration
        (API keys, base URLs, native SDK clients) wherever possible instead of
        creating standalone clients.

        The knowledge graph ragas builds while generating questions is fully
        structured into Odoo models (nodes/relationships), not an opaque
        pickle/JSON blob, and can be reused across multiple test set
        generations without recomputing extraction/embedding.

        Generated test cases and evaluation results are written into the
        tool-agnostic models provided by llm_knowledge_eval, so this module
        can be swapped for a different generator/evaluator later without
        affecting anything built on top of llm_knowledge_eval.
    """,
    "category": "Technical",
    "version": "19.0.1.0.0",
    "depends": ["llm_knowledge_eval"],
    "external_dependencies": {
        # Only ragas is imported directly. It pulls in langchain-core/
        # langchain-community itself, but this module never imports
        # langchain (or a raw openai client) directly - all LLM/embedding
        # traffic goes through Odoo's llm.provider/llm.model.
        "python": ["ragas"],
    },
    "author": "Apexive Solutions LLC",
    "website": "https://github.com/apexive/odoo-llm",
    "data": [
        "security/ir.model.access.csv",
        "data/llm_knowledge_eval_metric_data.xml",
        "views/llm_ragas_knowledge_graph_views.xml",
        "views/llm_knowledge_testset_views.xml",
        "views/llm_knowledge_eval_run_views.xml",
        "views/menu.xml",
    ],
    "license": "LGPL-3",
    "installable": True,
    "application": False,
    "auto_install": False,
}
