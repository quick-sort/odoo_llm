# -*- coding: utf-8 -*-
import json

from odoo import models, fields, api


class WebsearchTest(models.TransientModel):
    _name = 'llm.websearch.test'
    _description = 'Web Search Test'

    brave_api_key = fields.Char(string='Brave Search API Key')
    brightdata_api_key = fields.Char(string='BrightData API Key')
    brightdata_zone = fields.Char(string='BrightData Zone', default='web_unlocker1')
    query = fields.Char(string='Query')
    result = fields.Html(string='Result', readonly=True)

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        params = self.env['ir.config_parameter'].sudo()
        res['brave_api_key'] = params.get_param('llm_tool_websearch.brave_api_key', '')
        res['brightdata_api_key'] = params.get_param('llm_tool_websearch.brightdata_api_key', '')
        res['brightdata_zone'] = params.get_param('llm_tool_websearch.brightdata_zone', 'web_unlocker1')
        return res

    def _save_keys(self):
        params = self.env['ir.config_parameter'].sudo()
        params.set_param('llm_tool_websearch.brave_api_key', self.brave_api_key or '')
        params.set_param('llm_tool_websearch.brightdata_api_key', self.brightdata_api_key or '')
        params.set_param('llm_tool_websearch.brightdata_zone', self.brightdata_zone or 'web_unlocker1')

    def action_research(self):
        self.ensure_one()
        self._save_keys()
        tool = self.env['llm.tool'].search([('implementation', '=', 'web_research')], limit=1)
        if not tool:
            self.result = 'Error: web_research tool not found.'
            return
        res = tool.web_research_execute(query=self.query or '')
        self.result = res.get('result', 'No result.')

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
