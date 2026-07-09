import logging
from datetime import timedelta

from odoo import api, fields, models
from odoo.tools import html2plaintext

_logger = logging.getLogger(__name__)

# How many pending jobs a single cron tick processes before yielding back to
# the scheduler. Keeps a single overloaded channel from starving other cron
# jobs on the same worker.
BATCH_SIZE = 50

# How long to keep processed (done/error) rows around, for troubleshooting.
GC_RETENTION_DAYS = 7


class LlmDiscussReplyQueue(models.Model):
    _name = "llm.discuss.reply.queue"
    _description = "Pending LLM Assistant replies to Discuss / Live Chat messages"
    _order = "id"

    assistant_id = fields.Many2one("llm.assistant", required=True, ondelete="cascade", index=True)
    channel_id = fields.Many2one("discuss.channel", required=True, ondelete="cascade", index=True)
    message_id = fields.Many2one(
        "mail.message",
        required=True,
        ondelete="cascade",
        help="The user message that triggered this reply.",
    )
    state = fields.Selection(
        [("pending", "Pending"), ("done", "Done"), ("error", "Error")],
        default="pending",
        required=True,
        index=True,
    )
    error_message = fields.Text()

    @api.model
    def _cron_process_pending(self):
        """Cron entry point: process pending jobs, oldest first.

        Also acts as the safety net if an ``ir.cron._trigger()`` call was
        ever lost (e.g. a server restart between job creation and trigger).
        """
        jobs = self.search([("state", "=", "pending")], order="id", limit=BATCH_SIZE)
        for job in jobs:
            job._process_one()
        self._gc_processed_jobs()

    def _process_one(self):
        """Generate and post the assistant's reply for a single queue row.

        Commits after processing regardless of outcome, so a failure on one
        job never rolls back or blocks the others in the same cron tick.
        """
        self.ensure_one()
        try:
            assistant = self.assistant_id
            message = self.message_id
            channel = self.channel_id
            if not (assistant.discuss_user_id and message.exists() and channel.exists()):
                self.write({"state": "error", "error_message": "assistant/message/channel no longer available"})
                return

            bot_partner = assistant.discuss_user_id.partner_id
            query = html2plaintext(message.body) if message.body else ""

            result = assistant.sudo().invoke(
                query,
                thread_vals={"model": "discuss.channel", "res_id": channel.id},
                new_cursor=False,
            )
            if result.get("error"):
                self.write({"state": "error", "error_message": result["error"]})
                return

            body = result.get("result_html") or result.get("result") or ""
            channel.sudo().message_post(
                author_id=bot_partner.id,
                body=body,
                message_type="comment",
                subtype_xmlid="mail.mt_comment",
            )
            self.write({"state": "done", "error_message": False})
        except Exception as exc:  # noqa: BLE001 - isolate failures per job
            _logger.exception("llm_discuss: failed to process reply queue job %s", self.id)
            self.write({"state": "error", "error_message": str(exc)})
        finally:
            self.env.cr.commit()

    @api.model
    def _gc_processed_jobs(self):
        cutoff = fields.Datetime.now() - timedelta(days=GC_RETENTION_DAYS)
        stale = self.search(
            [("state", "in", ["done", "error"]), ("create_date", "<", cutoff)]
        )
        if stale:
            stale.unlink()
