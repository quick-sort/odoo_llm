{
    "name": "LLM Tool Web Search",
    "version": "19.0.1.2.0",
    "category": "Productivity/Tools",
    "author": "Apexive Solutions LLC",
    "website": "https://github.com/apexive/odoo-llm",
    "summary": "Web search, fetch, and research tools for AI assistants",
    "description": """
        Provides web search, page fetching, and research capabilities for LLM assistants.
        Enables AI to search the internet, extract readable content from web pages,
        and delegate multi-step research to a specialized web_researcher sub-assistant.
    """,
    "depends": ["llm_tool", "llm_assistant", "queue_job"],
    "external_dependencies": {
        "python": ["requests", "markitdown"],
    },
    "data": [
        "security/ir.model.access.csv",
        "data/llm_tool_data.xml",
        "data/llm_tool_web_research_data.xml",
        "wizard/websearch_test_views.xml",
    ],
    "images": [
        "static/description/banner.jpeg",
    ],
    "installable": True,
    "application": False,
    "auto_install": False,
    "license": "LGPL-3",
    "pre_init_hook": "pre_init_hook",
}
