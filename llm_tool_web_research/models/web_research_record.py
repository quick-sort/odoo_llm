# -*- coding: utf-8 -*-
from odoo import models, fields


class WebResearchRecord(models.Model):
    _name = 'web.research.record'
    _description = 'Web Research Record'
    _order = 'create_date desc'

    query = fields.Char(string='Query', required=True, readonly=True)
    result = fields.Html(string='Result', readonly=True)
    thread_id = fields.Many2one('llm.thread', string='LLM Thread', readonly=True, ondelete='set null')
    state = fields.Selection([
        ('running', 'Running'),
        ('done', 'Done'),
        ('error', 'Error'),
    ], string='State', default='running', readonly=True)
    error_message = fields.Text(string='Error', readonly=True)
