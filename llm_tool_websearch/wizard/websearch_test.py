# -*- coding: utf-8 -*-
import json

from odoo import models, fields, api


class WebsearchTest(models.TransientModel):
    _name = 'llm.websearch.test'
    _description = 'Web Search Test'

    brave_api_key = fields.Char(string='Brave Search API Key')
    brave_proxy = fields.Char(
        string='Brave Search Proxy',
        help='Optional HTTP/HTTPS proxy URL used when calling the Brave Search API '
             '(e.g. http://user:pass@host:port). Leave empty for no proxy.',
    )
    brightdata_api_key = fields.Char(string='BrightData API Key')
    brightdata_zone = fields.Char(string='BrightData Zone', default='web_unlocker1')
    query = fields.Char(string='Query')
    result = fields.Html(string='Result', readonly=True)

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        params = self.env['ir.config_parameter'].sudo()
        res['brave_api_key'] = params.get_param('llm_tool_websearch.brave_api_key', '')
        res['brave_proxy'] = params.get_param('llm_tool_websearch.brave_proxy', '')
        res['brightdata_api_key'] = params.get_param('llm_tool_websearch.brightdata_api_key', '')
        res['brightdata_zone'] = params.get_param('llm_tool_websearch.brightdata_zone', 'web_unlocker1')
        return res

    def _save_keys(self):
        params = self.env['ir.config_parameter'].sudo()
        params.set_param('llm_tool_websearch.brave_api_key', self.brave_api_key or '')
        params.set_param('llm_tool_websearch.brave_proxy', self.brave_proxy or '')
        params.set_param('llm_tool_websearch.brightdata_api_key', self.brightdata_api_key or '')
        params.set_param('llm_tool_websearch.brightdata_zone', self.brightdata_zone or 'web_unlocker1')

    def _build_research_meta_query(self, query):
        """Build the meta-query for odoo_operator → web_researcher delegation.

        Used by both action_research (sync) and action_research_async (async)
        so the two test paths exercise an identical pipeline:

            odoo_operator → invoke_assistant tool → web_researcher
        """
        return (
            "Use the web_researcher assistant to research the following topic. "
            "Call the invoke_assistant tool with assistant_code=\"web_researcher\" "
            "and pass the topic below verbatim as the query. "
            "When it returns, summarize its findings as your final answer.\n\n"
            f"Topic: {query}"
        )

    def action_research(self):
        """Synchronous research via the same pipeline as action_research_async.

        Calls llm.assistant.invoke_assistant on odoo_operator (default
        new_cursor=True for isolation). Blocks the request until the entire
        chain — odoo_operator → invoke_assistant tool → web_researcher —
        completes.
        """
        self.ensure_one()
        self._save_keys()
        meta_query = self._build_research_meta_query(self.query or '')
        res = self.env['llm.assistant'].invoke_assistant(
            'odoo_operator', meta_query,
        )
        if res.get('error'):
            self.result = f'<p><b>Error:</b> {res["error"]}</p>'
        else:
            self.result = res.get('result') or 'No result.'

    def action_research_async(self):
        """Enqueue the same pipeline as action_research but via queue_job:

            queue_job
              → llm.assistant.invoke_assistant(..., new_cursor=False)
                  (runs on the job cursor, no isolation)
                  → odoo_operator assistant
                      → invoke_assistant tool
                          → web_researcher (with web_search + web_fetch)

        Going through odoo_operator with new_cursor=False keeps the job's
        all-or-nothing semantics intact: if the job fails, queue_job retries
        the entire pipeline cleanly without orphan sub-thread data.
        """
        self.ensure_one()
        self._save_keys()
        meta_query = self._build_research_meta_query(self.query or '')
        job = self.env['llm.assistant'].with_delay().invoke_assistant(
            'odoo_operator', meta_query, new_cursor=False,
        )
        self.result = (
            f'<p>Async research enqueued.</p>'
            f'<p><b>Queue job UUID:</b> {job.uuid}</p>'
            f'<p>Pipeline: <code>queue_job → odoo_operator '
            f'→ invoke_assistant → web_researcher</code></p>'
            f'<p>Watch progress in <i>Queue Jobs</i> menu. '
            f'When done, two threads will exist: the odoo_operator outer '
            f'thread and the web_researcher sub-thread. Find them via '
            f'<i>LLM &gt; Threads</i>.</p>'
        )

    def action_search(self):
        self.ensure_one()
        self._save_keys()
        tool = self.env['llm.tool'].search([('implementation', '=', 'web_search')], limit=1)
        if not tool:
            self.result = 'Error: web_search tool not found'
            return
        res = tool.web_search_execute(query=self.query or '')
        self.result = '<pre>%s</pre>' % json.dumps(res, indent=2, ensure_ascii=False)

    def action_fetch(self):
        self.ensure_one()
        self._save_keys()
        tool = self.env['llm.tool'].search([('implementation', '=', 'web_fetch')], limit=1)
        if not tool:
            self.result = 'Error: web_fetch tool not found'
            return
        urls = [u.strip() for u in (self.query or '').splitlines() if u.strip()]
        if not urls:
            self.result = 'Error: No URLs provided'
            return
        res = tool.web_fetch_execute(urls=urls)
        self.result = '<pre>%s</pre>' % json.dumps(res, indent=2, ensure_ascii=False)
