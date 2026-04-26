# -*- coding: utf-8 -*-
import logging
from typing import Any

from odoo import api, models
from odoo.orm.registry import Registry

_logger = logging.getLogger(__name__)


class LLMToolWebResearch(models.Model):
    _inherit = "llm.tool"

    @api.model
    def _get_available_implementations(self):
        implementations = super()._get_available_implementations()
        return implementations + [
            ("web_research", "Web Research"),
        ]

    def web_research_execute(
        self,
        query: str,
    ) -> dict[str, Any]:
        """
        Research a topic on the web and return a comprehensive summary with references.

        This tool delegates to a specialized web research assistant that autonomously
        searches the web, reads relevant pages, and produces a summarized answer.
        Use this instead of calling web_search and web_fetch directly to keep the
        main conversation context clean.

        Parameters:
            query: The research question or topic to investigate.
        """
        # Run in a separate cursor to avoid savepoint conflicts with the outer
        # tool-call transaction.  The nested generate() manages its own
        # savepoints / advisory locks and would otherwise corrupt the caller's
        # savepoint stack.
        db_name = self.env.cr.dbname
        uid = self.env.uid
        context = self.env.context

        with Registry(db_name).cursor() as cr:
            env = api.Environment(cr, uid, context)
            result = self._web_research_in_env(env, query)
            cr.commit()

        return result

    def _web_research_in_env(self, env, query):
        """Execute web research in the given environment (separate cursor)."""
        assistant = env['llm.assistant'].get_assistant_by_code('web_researcher')
        if not assistant:
            return {"error": "Web researcher assistant not found."}

        thread = env['llm.thread'].create({
            'provider_id': assistant.provider_id.id,
            'model_id': assistant.model_id.id,
        })
        thread.set_assistant(assistant.id)

        try:
            for _event in thread.generate(user_message_body=query):
                pass

            message = env['mail.message'].search([
                ('model', '=', 'llm.thread'),
                ('res_id', '=', thread.id),
                ('llm_role', '=', 'assistant'),
            ], order='id desc', limit=1)

            result = str(message.body) if message else "No result."
        except Exception as e:
            result = f"Error: {e}"

        return {"query": query, "result": result}
