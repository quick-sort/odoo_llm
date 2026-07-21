{
    "name": "LLM Knowledge Evaluation",
    "summary": "Tool-agnostic RAG test sets, evaluation runs and metrics for llm_knowledge collections",
    "description": """
        Stores RAG test cases (question / reference answer / reference contexts),
        evaluation runs and per-sample results as first-class Odoo records.

        This module has NO dependency on any specific test-generation or scoring
        tool (such as ragas) - it only defines the data model that such tools
        write into. See llm_ragas for a concrete implementation that uses the
        ragas library to populate these tables.
    """,
    "category": "Technical",
    "version": "19.0.1.0.0",
    "depends": ["llm_knowledge"],
    "author": "Apexive Solutions LLC",
    "website": "https://github.com/apexive/odoo-llm",
    "data": [
        "security/ir.model.access.csv",
        "views/llm_knowledge_testset_views.xml",
        "views/llm_knowledge_eval_run_views.xml",
        "views/llm_knowledge_eval_metric_views.xml",
        "views/menu.xml",
    ],
    "license": "LGPL-3",
    "installable": True,
    "application": False,
    "auto_install": False,
}
