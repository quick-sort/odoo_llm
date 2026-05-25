# -*- coding: utf-8 -*-

import logging
from collections import defaultdict

from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError

_logger = logging.getLogger(__name__)


STATUS_SELECTION = [
    ('pass', 'Pass'),
    ('fail', 'Fail'),
    ('needs_info', 'Needs Info'),
    ('not_applicable', 'Not Applicable'),
]


class ScreenResult(models.Model):
    _name = 'screen.result'
    _description = 'Screening Result'
    _order = 'id desc'

    # Generic reference, attachment-style.
    res_model = fields.Char(string='Resource Model', required=True, index=True)
    res_id = fields.Many2oneReference(
        string='Resource ID', model_field='res_model',
        required=True, index=True,
    )

    profile_id = fields.Many2one(
        'screen.profile', string='Profile',
        ondelete='restrict',
        help='Selected screening profile. May be empty when a result is '
             'pre-created and the picking is delegated to the screening '
             'assistant; setting it later auto-spawns one item per rule.',
    )
    material = fields.Text(
        string='Material',
        help='The text material handed to the LLM for evaluation.',
    )

    state = fields.Selection([
        ('draft', 'Draft'),
        ('running', 'Running'),
        ('done', 'Done'),
        ('failed', 'Failed'),
    ], string='State', default='draft', required=True, copy=False)

    item_ids = fields.One2many(
        'screen.result.item', 'result_id',
        string='Items', copy=False,
    )
    overall_status = fields.Selection(
        STATUS_SELECTION, string='Overall Status',
        compute='_compute_overall_status', store=True,
    )
    summary = fields.Text(string='Summary')
    error_message = fields.Text(string='Error Message', readonly=True)

    @api.depends('profile_id.name', 'state', 'overall_status')
    def _compute_display_name(self):
        """Human-friendly label for m2o renderings and breadcrumbs.

        Default is ``screen.result,{id}`` because the model has no ``name``
        field — that bled through to the opportunity form's Screening page.
        Format: ``Screening #{id} · {profile} · {state-or-status}``, with
        each segment dropped when its source is empty.
        """
        state_labels = dict(self._fields['state'].selection)
        status_labels = dict(self._fields['overall_status'].selection)
        for rec in self:
            parts = [f"Screening #{rec.id}" if rec.id else "Screening (new)"]
            if rec.profile_id:
                parts.append(rec.profile_id.name)
            # Prefer the final outcome over the raw lifecycle state once done.
            if rec.overall_status:
                parts.append(status_labels.get(rec.overall_status, rec.overall_status))
            elif rec.state:
                parts.append(state_labels.get(rec.state, rec.state))
            rec.display_name = ' · '.join(parts)

    @api.depends('state', 'item_ids.status', 'item_ids.is_required')
    def _compute_overall_status(self):
        for result in self:
            if result.state != 'done' or not result.item_ids:
                result.overall_status = False
                continue
            statuses = result.item_ids.mapped('status')
            if any(s == 'fail' and req for s, req in zip(
                    result.item_ids.mapped('status'),
                    result.item_ids.mapped('is_required'))):
                result.overall_status = 'fail'
            elif 'needs_info' in statuses:
                result.overall_status = 'needs_info'
            elif all(s == 'not_applicable' for s in statuses):
                result.overall_status = 'not_applicable'
            else:
                result.overall_status = 'pass'

    @api.constrains('res_model')
    def _check_res_model(self):
        for rec in self:
            if rec.res_model and rec.res_model not in self.env:
                raise ValidationError(_("Unknown model: %s") % rec.res_model)

    @api.model_create_multi
    def create(self, vals_list):
        results = super().create(vals_list)
        for result in results:
            result._sync_items_from_profile()
        return results

    def write(self, vals):
        if 'profile_id' in vals:
            for rec in self:
                if (
                    rec.profile_id
                    and vals['profile_id']
                    and rec.profile_id.id != vals['profile_id']
                ):
                    raise UserError(_(
                        "Profile cannot be changed once the screening "
                        "result has one. Delete this result and run "
                        "the screening again instead."
                    ))
        return super().write(vals)

    def _sync_items_from_profile(self):
        """(Re)create empty items for each rule of the profile."""
        self.ensure_one()
        self.item_ids.unlink()
        item_vals = [
            {'result_id': self.id, 'rule_id': rule.id}
            for rule in self.profile_id.rule_ids
        ]
        if item_vals:
            self.env['screen.result.item'].create(item_vals)

    @api.model
    def set_item_outcomes(self, result_id, outcomes):
        """Bulk-set evaluation outcomes for items on a screen.result.

        For each entry, looks up the item on the result by ``rule_id`` and
        writes the supplied ``status`` / ``reasoning`` / ``evidence``. Items
        belonging to rules not listed are left unchanged. Unknown rule ids
        are skipped silently.

        Args:
            result_id (int): target screen.result id
            outcomes (list[dict]): each dict has 'rule_id' (required) and
                optional 'status', 'reasoning', 'evidence'.
        """
        result = self.browse(result_id)
        if not result.exists():
            return
        items_by_rule = {item.rule_id.id: item for item in result.item_ids}
        for outcome in outcomes:
            item = items_by_rule.get(outcome.get('rule_id'))
            if not item:
                continue
            vals = {
                k: outcome[k]
                for k in ('status', 'reasoning', 'evidence')
                if k in outcome
            }
            if vals:
                item.write(vals)

    @api.model
    def _cron_cleanup_orphans(self):
        """Delete results whose source record no longer exists.

        Primary cleanup happens in the source model's unlink (e.g.
        opportunity), this cron is a safety net.
        """
        by_model = defaultdict(list)
        for rec in self.search([]):
            by_model[rec.res_model].append(rec)

        orphans = self.browse()
        for model_name, records in by_model.items():
            Model = self.env.get(model_name)
            if Model is None:
                orphans |= self.browse([r.id for r in records])
                continue
            ids = [r.res_id for r in records]
            existing = set(Model.browse(ids).exists().ids)
            orphans |= self.browse([r.id for r in records if r.res_id not in existing])

        if orphans:
            _logger.info("Cleaning up %d orphan screen.result(s)", len(orphans))
            orphans.unlink()
