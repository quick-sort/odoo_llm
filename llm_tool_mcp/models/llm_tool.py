import logging

from odoo import _, api, fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class LLMTool(models.Model):
    _inherit = "llm.tool"

    mcp_client_id = fields.Many2one(
        "llm.mcp.client",
        string="MCP Service",
        ondelete="set null",
        help="External MCP server that provides this tool",
    )
    mcp_tool_name = fields.Char(
        string="Remote Tool Name",
        help="Exact tool name as exposed by the MCP server",
    )

    @api.model
    def _get_available_implementations(self):
        return super()._get_available_implementations() + [
            ("mcp_tool", "MCP Tool"),
        ]

    def execute(self, parameters):
        """Route MCP tools to their remote server; delegate everything else upstream."""
        if self.implementation == "mcp_tool":
            self.ensure_one()
            if not self.mcp_client_id:
                raise UserError(
                    _("Tool '%(name)s' has no MCP service configured.", name=self.name)
                )
            remote_name = self.mcp_tool_name or self.name
            return self.mcp_client_id.call_tool(remote_name, parameters)
        return super().execute(parameters)
