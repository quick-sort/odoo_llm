# -*- coding: utf-8 -*-

import logging

from odoo import api, fields, models, _
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class ScreenProfile(models.Model):
    _name = 'screen.profile'
    _description = 'Screening Profile'
    _order = 'name'

    name = fields.Char(string='Name', required=True)
    description = fields.Text(string='Applicability Description')
    active = fields.Boolean(string='Active', default=True)

    rule_ids = fields.One2many(
        'screen.profile.rule', 'profile_id',
        string='Rules', copy=True,
    )
    rule_count = fields.Integer(
        string='Rule Count', compute='_compute_rule_count',
    )

    @api.depends('rule_ids')
    def _compute_rule_count(self):
        for profile in self:
            profile.rule_count = len(profile.rule_ids)

    @api.model
    def run_screening(self, res_model, res_id, content):
        """Entry point for any model to trigger a screening.

        Pre-creates a draft ``screen.result`` (without a profile, no items),
        then hands its id to the ``screening`` assistant. The assistant
        inspects all active profiles, picks the one whose applicability
        description matches ``content``, sets ``profile_id`` on the result
        (which auto-spawns one ``screen.result.item`` per rule via the
        write hook), evaluates each item, and writes outcomes + summary.

        Returns the pre-created ``screen.result`` recordset (callers commonly
        read ``.id`` / ``.overall_status`` / ``.state`` afterwards).
        """
        if not res_model or not res_id:
            raise UserError(_("res_model and res_id are required."))
        if res_model not in self.env:
            raise UserError(_("Unknown model: %s") % res_model)

        result = self.env['screen.result'].create({
            'res_model': res_model,
            'res_id': res_id,
            'material': content or '',
            'state': 'draft',
        })

        query = (
            f"RESULT_ID: {result.id}\n"
            f"Material:\n{content or ''}"
        )

        # new_cursor=False: run the screening assistant on the caller's
        # cursor so the just-created screen.result (still uncommitted) is
        # visible when the assistant inserts screen.result.item rows.
        # All current callers (_job_screen_opportunity queue_job,
        # action_run_screening HTTP button) own the transaction boundary,
        # so all-or-nothing semantics are preserved.
        invocation = self.env['llm.assistant'].invoke_assistant(
            'screening', query, new_cursor=False,
        )

        if invocation.get('error'):
            raise UserError(_(
                "Screening assistant failed: %s"
            ) % invocation['error'])

        _logger.info(
            "Screening assistant ran on screen.result %s for %s(%s) "
            "(assistant thread %s)",
            result.id, res_model, res_id, invocation.get('thread_id'),
        )
        return result
