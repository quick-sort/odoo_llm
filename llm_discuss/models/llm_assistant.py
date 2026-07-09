import logging

from odoo import api, fields, models

_logger = logging.getLogger(__name__)


class LlmAssistant(models.Model):
    _inherit = "llm.assistant"

    discuss_user_id = fields.Many2one(
        "res.users",
        string="Discuss Bot User",
        readonly=True,
        copy=False,
        help="Internal technical user representing this assistant inside "
        "Discuss / Live Chat. Created via the 'Create Bot User' button. "
        "Add this user to a chat/channel to let the assistant participate "
        "in it.",
    )
    discuss_enabled = fields.Boolean(
        string="Enable in Discuss",
        help="When enabled, this assistant automatically replies to "
        "messages in Discuss according to the Reply Trigger below. "
        "Requires a Bot User.",
    )
    discuss_trigger_mode = fields.Selection(
        [
            ("both", "Direct chat or @mention"),
            ("direct_chat", "Only in direct 1:1 chat"),
            ("mention", "Only when @mentioned"),
        ],
        string="Reply Trigger",
        default="both",
        required=True,
        help="Direct chat: the assistant replies to every message in its "
        "1:1 conversation with a user. @mention: the assistant only "
        "replies when explicitly mentioned in a (multi-user) channel.",
    )

    def action_create_discuss_user(self):
        """Create the technical res.users representing this assistant.

        Idempotent: does nothing for assistants that already have one.
        """
        for assistant in self:
            if assistant.discuss_user_id:
                continue
            login = f"llm-bot-{assistant.code or assistant.id}@bot.internal"
            user = (
                self.env["res.users"]
                .sudo()
                .with_context(no_reset_password=True)
                .create(
                    {
                        "name": assistant.name,
                        "login": login,
                        "share": False,
                        "active": True,
                        "groups_id": [(6, 0, [self.env.ref("base.group_user").id])],
                    }
                )
            )
            assistant.discuss_user_id = user.id
            _logger.info(
                "llm_discuss: created bot user %s (login=%s) for assistant %s",
                user.id, login, assistant.id,
            )
        return True

    def _discuss_bot_partner(self):
        self.ensure_one()
        return self.discuss_user_id.partner_id

    @api.model
    def _llm_discuss_dispatch(self, channel, message, msg_vals):
        """Entry point called from ``discuss.channel._message_post_after_hook``.

        Finds every Discuss-enabled assistant that should react to
        ``message`` posted on ``channel``, and enqueues an async reply job
        (``llm.discuss.reply.queue``) for each of them.
        """
        assistants = self.sudo().search(
            [
                ("discuss_enabled", "=", True),
                ("discuss_user_id", "!=", False),
            ]
        )
        if not assistants:
            return
        queue = self.env["llm.discuss.reply.queue"].sudo()
        triggered = False
        for assistant in assistants:
            try:
                should_trigger = channel._llm_discuss_should_trigger(assistant, message, msg_vals)
            except Exception:
                _logger.exception(
                    "llm_discuss: error evaluating trigger for assistant %s on channel %s",
                    assistant.id, channel.id,
                )
                continue
            if should_trigger:
                queue.create(
                    {
                        "assistant_id": assistant.id,
                        "channel_id": channel.id,
                        "message_id": message.id,
                    }
                )
                triggered = True
        if triggered:
            cron = self.env.ref("llm_discuss.ir_cron_process_reply_queue", raise_if_not_found=False)
            if cron:
                cron.sudo()._trigger()
