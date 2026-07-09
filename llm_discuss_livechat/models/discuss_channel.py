from odoo import models


class DiscussChannel(models.Model):
    _inherit = "discuss.channel"

    def _llm_discuss_should_trigger(self, assistant, message, msg_vals):
        """Add the Live Chat rule on top of ``llm_discuss``'s base rules:
        any comment message in a livechat session where this assistant is
        the current operator triggers a reply, regardless of
        ``discuss_trigger_mode`` (a Live Chat session only ever has one
        visitor and one operator, so every visitor message is implicitly
        addressed to the operator).
        """
        self.ensure_one()
        bot_partner = assistant.discuss_user_id.partner_id
        if (
            bot_partner
            and self.channel_type == "livechat"
            and self.livechat_operator_id == bot_partner
            and message.author_id != bot_partner
            and msg_vals.get("message_type", "notification") == "comment"
        ):
            return True
        return super()._llm_discuss_should_trigger(assistant, message, msg_vals)
