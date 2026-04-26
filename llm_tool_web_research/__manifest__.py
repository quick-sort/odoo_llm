{
    "name": "LLM Tool Web Research",
    "version": "19.0.1.0.0",
    "category": "Productivity/Tools",
    "summary": "Web research tool that uses a sub-assistant to search and summarize web content",
    "depends": ["llm_tool_websearch", "llm_assistant"],
    "data": [
        "security/ir.model.access.csv",
        "data/llm_web_research_data.xml",
        "wizard/websearch_test_views.xml",
    ],
    "installable": True,
    "application": False,
    "auto_install": False,
    "license": "LGPL-3",
}
