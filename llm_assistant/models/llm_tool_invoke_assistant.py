# -*- coding: utf-8 -*-
import logging
import time
from typing import Any

from odoo import api, models

_logger = logging.getLogger(__name__)


def _preview(s: str, limit: int = 200) -> str:
    """Truncate a string for log output."""
    if s is None:
        return ""
    return s if len(s) <= limit else s[:limit] + f"...<+{len(s) - limit}c>"

# Maximum nesting depth for invoke_assistant calls. Each invocation increments
# a context counter so an assistant delegating to a chain of sub-assistants
# cannot loop forever (e.g. A -> B -> A -> B ...).
DEFAULT_MAX_DEPTH = 5


class LLMToolInvokeAssistant(models.Model):
    _inherit = "llm.tool"

    @api.model
    def _get_available_implementations(self):
        implementations = super()._get_available_implementations()
        return implementations + [
            ("invoke_assistant", "Invoke Assistant"),
        ]

    def invoke_assistant_execute(
        self,
        assistant_code: str,
        query: str,
    ) -> dict[str, Any]:
        """
        Delegate a sub-task to another assistant identified by its code.

        The sub-assistant runs in an isolated transaction with its own thread,
        message stream, and tool execution lifecycle. Use this to compose
        specialized assistants instead of replicating their tool sequences
        yourself.

        The returned dict carries the sub-assistant's final answer in
        ``result`` (a string), or an ``error`` field if the invocation failed.

        Parameters:
            assistant_code: Unique code of the sub-assistant to invoke
                (e.g. "web_researcher", "statement_updater"). Use the value
                stored in llm.assistant.code.
            query: Natural-language instruction or question to send to the
                sub-assistant as the first user message.
        """
        depth = self.env.context.get("llm_invoke_assistant_depth", 0)
        _logger.info(
            "[invoke_assistant] ENTER depth=%d code=%r query_len=%d preview=%r",
            depth, assistant_code, len(query or ""), _preview(query),
        )

        if depth >= DEFAULT_MAX_DEPTH:
            msg = (
                f"invoke_assistant nesting depth limit reached "
                f"({DEFAULT_MAX_DEPTH}); refusing to call '{assistant_code}'."
            )
            _logger.warning("[invoke_assistant] BLOCKED depth=%d %s", depth, msg)
            return {"error": msg}

        start = time.monotonic()
        res = self.env["llm.assistant"].invoke_assistant(
            assistant_code,
            query,
            parent_context={"llm_invoke_assistant_depth": depth + 1},
        )
        elapsed = time.monotonic() - start

        result_len = len(res["result"]) if res.get("result") else 0
        _logger.info(
            "[invoke_assistant] EXIT  depth=%d code=%r elapsed=%.1fs "
            "thread_id=%s error=%s result_len=%d",
            depth, assistant_code, elapsed,
            res.get("thread_id"), res.get("error"), result_len,
        )
        # Strip ``result_html`` before returning to the calling LLM. The HTML
        # variant exists for programmatic callers binding output to a
        # fields.Html column; an LLM seeing both keys would waste context on
        # duplicate content and may not know which to consume. Keep ``result``
        # (markdown) as the canonical reply for chained-assistant flows.
        return {
            "query": res.get("query"),
            "result": res.get("result"),
            "error": res.get("error"),
            "thread_id": res.get("thread_id"),
        }
