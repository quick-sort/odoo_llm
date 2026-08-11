import json
import logging
import re

import requests

from odoo import _, api, fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

MCP_PROTOCOL_VERSION = "2025-06-18"


class LLMMcpClient(models.Model):
    _name = "llm.mcp.client"
    _description = "External MCP Service Client"
    _inherit = ["mail.thread"]

    name = fields.Char(required=True, tracking=True)
    url = fields.Char(
        string="Endpoint URL",
        required=True,
        tracking=True,
        help="MCP server HTTP endpoint (streamable-http transport), e.g. http://localhost:3000/mcp",
    )
    api_key = fields.Char(
        string="API Key",
        help="Bearer token for authentication (leave empty if not required)",
    )
    active = fields.Boolean(default=True)
    status = fields.Selection(
        [
            ("not_tested", "Not Tested"),
            ("connected", "Connected"),
            ("error", "Error"),
        ],
        default="not_tested",
        readonly=True,
        tracking=True,
    )
    last_sync = fields.Datetime(string="Last Synced", readonly=True)
    tool_ids = fields.One2many(
        "llm.tool",
        "mcp_client_id",
        string="Tools",
    )
    tool_count = fields.Integer(
        string="Tools",
        compute="_compute_tool_count",
    )

    def _compute_tool_count(self):
        counts = self.env["llm.tool"].read_group(
            [("mcp_client_id", "in", self.ids)],
            ["mcp_client_id"],
            ["mcp_client_id"],
        )
        mapping = {r["mcp_client_id"][0]: r["mcp_client_id_count"] for r in counts}
        for rec in self:
            rec.tool_count = mapping.get(rec.id, 0)

    # ------------------------------------------------------------------
    # HTTP helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _decode_body(resp):
        """Decode the response body as UTF-8 unless the server declares a charset.

        ``text/event-stream`` responses carry no charset, and requests then falls
        back to ISO-8859-1 for ``text/*``, which mangles non-ASCII payloads. JSON
        and SSE both default to UTF-8, so decode explicitly.
        """
        if "charset=" in resp.headers.get("Content-Type", "").lower():
            return resp.text
        return resp.content.decode("utf-8", errors="replace")

    @staticmethod
    def _iter_sse_payloads(body):
        """Yield the ``data`` payload of every event in an SSE body.

        Split only on real SSE line terminators (CRLF / CR / LF). ``splitlines()``
        must not be used: it also breaks on U+0085, U+000B, U+2028 and friends,
        which occur legitimately inside JSON text and would truncate the payload.
        Multiple ``data`` lines belonging to one event are joined with newlines,
        per the SSE specification.
        """
        data_lines = []
        for line in re.split(r"\r\n|\r|\n", body):
            if not line:
                if data_lines:
                    yield "\n".join(data_lines)
                    data_lines = []
                continue
            if line.startswith(":"):
                continue  # comment / keep-alive
            field, _sep, value = line.partition(":")
            if field == "data":
                data_lines.append(value[1:] if value.startswith(" ") else value)
        if data_lines:
            yield "\n".join(data_lines)

    def _parse_response_json(self, resp, request_id=None):
        """Parse JSON from a response that may be plain JSON or SSE format.

        MCP servers using streamable-http may return responses as SSE events:
            event: message\\r\\ndata: {...}\\r\\n\\r\\n
        """
        body = self._decode_body(resp)
        if "text/event-stream" not in resp.headers.get("Content-Type", ""):
            return json.loads(body)

        fallback = None
        last_error = None
        for payload in self._iter_sse_payloads(body):
            if not payload.strip():
                continue
            try:
                data = json.loads(payload)
            except ValueError as e:
                last_error = e
                continue
            if not isinstance(data, dict):
                continue
            # Skip server-initiated notifications / progress events and keep
            # looking for the response matching our request.
            if request_id is not None and data.get("id") not in (None, request_id):
                continue
            if "result" in data or "error" in data:
                return data
            if fallback is None:
                fallback = data
        if fallback is not None:
            return fallback
        if last_error is not None:
            raise last_error
        return {}

    def _get_headers(self, session_id=None):
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
        }
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        if session_id:
            headers["Mcp-Session-Id"] = session_id
        return headers

    def _initialize_session(self):
        """Perform MCP handshake and return the session ID."""
        self.ensure_one()
        try:
            resp = requests.post(
                self.url,
                json={
                    "jsonrpc": "2.0",
                    "method": "initialize",
                    "id": 1,
                    "params": {
                        "protocolVersion": MCP_PROTOCOL_VERSION,
                        "capabilities": {},
                        "clientInfo": {"name": "odoo-llm-tool-mcp", "version": "1.0.0"},
                    },
                },
                headers=self._get_headers(),
                timeout=15,
            )
            resp.raise_for_status()
        except requests.RequestException as e:
            raise UserError(_("MCP connection failed: %(msg)s", msg=str(e)))

        # Session ID comes from the response header; body may be plain JSON or SSE
        session_id = resp.headers.get("Mcp-Session-Id")
        try:
            data = self._parse_response_json(resp, request_id=1)
        except ValueError as e:
            _logger.warning(
                "MCP initialize: unparseable response body (%s): %r",
                e,
                self._decode_body(resp)[:500],
            )
        else:
            if "error" in data:
                raise UserError(
                    _("MCP initialize error: %(msg)s", msg=data["error"].get("message", str(data["error"])))
                )

        # Send initialized notification (fire-and-forget, no response expected)
        try:
            requests.post(
                self.url,
                json={"jsonrpc": "2.0", "method": "notifications/initialized"},
                headers=self._get_headers(session_id),
                timeout=10,
            )
        except requests.RequestException:
            pass  # Notification failure is non-fatal

        return session_id

    def _jsonrpc(self, method, params, session_id, request_id=2):
        """Send a JSON-RPC request and return the result dict."""
        self.ensure_one()
        try:
            resp = requests.post(
                self.url,
                json={"jsonrpc": "2.0", "method": method, "id": request_id, "params": params},
                headers=self._get_headers(session_id),
                timeout=60,
            )
            resp.raise_for_status()
        except requests.RequestException as e:
            raise UserError(_("MCP request failed (%(method)s): %(msg)s", method=method, msg=str(e)))

        try:
            data = self._parse_response_json(resp, request_id=request_id)
        except ValueError as e:
            body = self._decode_body(resp)
            _logger.error("MCP %s: unparseable response (%s): %r", method, e, body[:500])
            raise UserError(
                _("MCP server returned unparseable response for %(method)s: %(body)s", method=method, body=body[:200])
            )
        if "error" in data:
            raise UserError(
                _("MCP error (%(method)s): %(msg)s", method=method, msg=data["error"].get("message", str(data["error"])))
            )
        return data.get("result", {})

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def list_tools(self):
        """Fetch the current tool list from the remote MCP server."""
        self.ensure_one()
        session_id = self._initialize_session()
        result = self._jsonrpc("tools/list", {}, session_id)
        return result.get("tools", [])

    def call_tool(self, tool_name, arguments):
        """Execute a tool on the remote MCP server and return the result."""
        self.ensure_one()
        session_id = self._initialize_session()
        result = self._jsonrpc(
            "tools/call",
            {"name": tool_name, "arguments": arguments or {}},
            session_id,
        )

        # MCP tools/call returns {content: [...], isError: bool}
        content = result.get("content", [])
        if result.get("isError"):
            error_text = " ".join(
                c.get("text", "") for c in content if c.get("type") == "text"
            )
            raise UserError(_("MCP tool %(name)s returned error: %(msg)s", name=tool_name, msg=error_text))

        # Flatten text content; preserve non-text items as-is
        texts = [c["text"] for c in content if c.get("type") == "text"]
        if texts:
            return {"result": "\n".join(texts)}
        return {"result": content}

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------

    def action_sync_tools(self):
        """Sync remote MCP tools into llm.tool records (create / update / deactivate)."""
        self.ensure_one()
        Tool = self.env["llm.tool"]

        try:
            remote_tools = self.list_tools()
            self.sudo().write({"status": "connected"})
        except UserError:
            self.sudo().write({"status": "error"})
            raise

        remote_names = {t["name"] for t in remote_tools}
        created = updated = 0

        for remote in remote_tools:
            tool_name = remote["name"]
            description = remote.get("description") or tool_name
            input_schema = json.dumps(remote.get("inputSchema") or {})

            existing = Tool.search(
                [("mcp_client_id", "=", self.id), ("mcp_tool_name", "=", tool_name)],
                limit=1,
            )

            if existing:
                existing.write({
                    "name": tool_name,
                    "description": description,
                    "input_schema": input_schema,
                    "active": True,
                })
                updated += 1
            else:
                Tool.create({
                    "name": tool_name,
                    "description": description,
                    "implementation": "mcp_tool",
                    "mcp_client_id": self.id,
                    "mcp_tool_name": tool_name,
                    "input_schema": input_schema,
                    "read_only_hint": False,
                    "destructive_hint": True,
                    "open_world_hint": True,
                })
                created += 1

        # Deactivate tools that no longer exist on the remote server
        obsolete = Tool.with_context(active_test=False).search([
            ("mcp_client_id", "=", self.id),
            ("mcp_tool_name", "not in", list(remote_names)),
            ("active", "=", True),
        ])
        obsolete.write({"active": False})

        self.sudo().write({"last_sync": fields.Datetime.now()})

        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": _("Sync Complete"),
                "message": _(
                    "Created: %(c)d  |  Updated: %(u)d  |  Deactivated: %(d)d",
                    c=created,
                    u=updated,
                    d=len(obsolete),
                ),
                "sticky": False,
                "type": "success",
            },
        }

    def action_view_tools(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("Tools – %(name)s", name=self.name),
            "res_model": "llm.tool",
            "view_mode": "list,form",
            "domain": [("mcp_client_id", "=", self.id)],
            "context": {
                "default_mcp_client_id": self.id,
                "default_implementation": "mcp_tool",
            },
        }
