{
    "name": "LLM Tool Web Search",
    "version": "19.0.1.0.0",
    "category": "Productivity/Tools",
    "author": "Apexive Solutions LLC",
    "website": "https://github.com/apexive/odoo-llm",
    "summary": "Web search and page content fetching tools for AI assistants",
    "description": """
        Provides web search and page fetching capabilities for LLM assistants.
        Enables AI to search the internet and extract readable content from web pages.
    """,
    "depends": ["llm_tool"],
    "external_dependencies": {
        "python": ["requests", "markitdown"],
    },
    "data": [
        "data/llm_tool_data.xml",
    ],
    "images": [
        "static/description/banner.jpeg",
    ],
    "installable": True,
    "application": False,
    "auto_install": False,
    "license": "LGPL-3",
}
