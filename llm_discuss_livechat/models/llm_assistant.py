from odoo import fields, models


class LlmAssistant(models.Model):
    _inherit = "llm.assistant"

    livechat_channel_ids = fields.Many2many(
        "im_livechat.channel",
        "llm_assistant_livechat_channel_rel",
        "assistant_id",
        "livechat_channel_id",
        string="Live Chat Channels",
        help="Live Chat channels this assistant is registered as an "
        "operator on. Requires a Bot User (see the Discuss tab).",
    )

    def write(self, vals):
        res = super().write(vals)
        if "livechat_channel_ids" in vals or "discuss_user_id" in vals:
            self._sync_livechat_operator()
        return res

    @property
    def _livechat_bot_user(self):
        self.ensure_one()
        return self.discuss_user_id

    def _sync_livechat_operator(self):
        """Add this assistant's bot user to the operator list of every
        channel in ``livechat_channel_ids``, and remove it from Live Chat
        channels no longer selected."""
        LivechatChannel = self.env["im_livechat.channel"].sudo()
        for assistant in self:
            bot_user = assistant.discuss_user_id
            if not bot_user:
                continue
            selected = assistant.livechat_channel_ids
            currently_operator_on = LivechatChannel.search([("user_ids", "in", bot_user.id)])
            to_add = selected - currently_operator_on
            to_remove = currently_operator_on - selected
            for channel in to_add:
                channel.write({"user_ids": [(4, bot_user.id)]})
            for channel in to_remove:
                channel.write({"user_ids": [(3, bot_user.id)]})

    def action_create_discuss_user(self):
        res = super().action_create_discuss_user()
        self._sync_livechat_operator()
        return res
