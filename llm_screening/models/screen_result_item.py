# -*- coding: utf-8 -*-

from odoo import fields, models

from .screen_result import STATUS_SELECTION


class ScreenResultItem(models.Model):
    _name = 'screen.result.item'
    _description = 'Screening Result Item'
    _order = 'sequence, id'

    result_id = fields.Many2one(
        'screen.result', string='Result',
        required=True, ondelete='cascade', index=True,
    )
    rule_id = fields.Many2one(
        'screen.profile.rule', string='Rule',
        required=True, ondelete='restrict', index=True,
    )

    sequence = fields.Integer(related='rule_id.sequence', store=True)
    rule_name = fields.Char(related='rule_id.name', readonly=True)
    requirement = fields.Text(related='rule_id.requirement', readonly=True)
    is_required = fields.Boolean(related='rule_id.is_required', store=True)

    status = fields.Selection(
        STATUS_SELECTION, string='Status',
    )
    reasoning = fields.Text(string='Reasoning')
    evidence = fields.Text(string='Evidence')

    _unique_rule_per_result = models.Constraint(
        'unique(result_id, rule_id)',
        'A rule can only appear once per screening result.',
    )
