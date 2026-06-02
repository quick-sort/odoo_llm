{
    "name": "LLM Tool MCP Client",
    "version": "19.0.1.0.0",
    "category": "Technical",
    "summary": "Connect LLM assistants to external MCP services as tools",
    "description": """
        Allows Odoo LLM assistants to call tools provided by external MCP servers.

        - Manage external MCP server connections (HTTP/streamable-http transport)
        - Import remote tools as llm.tool records (static snapshot approach)
        - Sync/refresh tools from remote servers on demand
        - Execute tools via direct HTTP JSON-RPC requests
    """,
    "author": "Apexive Solutions LLC",
    "website": "https://github.com/apexive/odoo-llm",
    "license": "LGPL-3",
    "depends": ["llm_tool"],
    "external_dependencies": {
        "python": ["requests"],
    },
    "data": [
        "security/ir.model.access.csv",
        "views/llm_mcp_client_views.xml",
        "views/llm_tool_views.xml",
        "views/llm_menu_views.xml",
    ],
    "auto_install": False,
    "application": False,
    "installable": True,
}
