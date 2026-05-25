# -*- coding: utf-8 -*-

from odoo import fields, models


class ScreenProfileRule(models.Model):
    _name = 'screen.profile.rule'
    _description = 'Screening Profile Rule'
    _order = 'sequence, id'

    profile_id = fields.Many2one(
        'screen.profile', string='Profile',
        required=True, ondelete='cascade', index=True,
    )
    sequence = fields.Integer(string='Sequence', default=10)
    name = fields.Char(string='Rule Name', required=True)
    requirement = fields.Text(string='Requirement', required=True)
    is_required = fields.Boolean(
        string='Required', default=True,
        help='Hard requirement: any failing required rule fails the overall screening.',
    )
