from odoo import fields, models


class LlmMcpTestResult(models.TransientModel):
    _name = "llm.mcp.test.result"
    _description = "MCP Test Result"

    has_key = fields.Boolean(string="Authenticated", readonly=True)
    tool_count = fields.Integer(string="Tools Available", readonly=True)
    tool_list = fields.Text(string="Tools", readonly=True)
