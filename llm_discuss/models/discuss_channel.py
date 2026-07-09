from odoo import models


class DiscussChannel(models.Model):
    _inherit = "discuss.channel"

    def _message_post_after_hook(self, message, msg_vals):
        self.env["llm.assistant"]._llm_discuss_dispatch(self, message, msg_vals)
        return super()._message_post_after_hook(message, msg_vals)

    def _llm_discuss_should_trigger(self, assistant, message, msg_vals):
        """Return whether ``assistant`` should auto-reply to ``message``
        posted on this channel.

        Base rules: direct 1:1 chat with the bot, and/or explicit
        ``@mention``, depending on ``assistant.discuss_trigger_mode``.

        Override this method (see ``llm_discuss_livechat``) to add other
        trigger conditions, e.g. "any message in a Live Chat session where
        this assistant is the operator".
        """
        self.ensure_one()
        bot_partner = assistant.discuss_user_id.partner_id
        if not bot_partner or message.author_id == bot_partner:
            return False
        if msg_vals.get("message_type", "notification") != "comment":
            return False

        is_direct_chat = self.channel_type == "chat" and bot_partner in self.channel_member_ids.partner_id
        is_mentioned = bot_partner.id in (msg_vals.get("partner_ids") or [])

        mode = assistant.discuss_trigger_mode
        if mode == "direct_chat":
            return is_direct_chat
        if mode == "mention":
            return is_mentioned
        return is_direct_chat or is_mentioned
