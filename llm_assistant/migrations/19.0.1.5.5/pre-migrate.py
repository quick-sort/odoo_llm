# -*- coding: utf-8 -*-
"""Drop the generic_operator assistant and its prompt; merged into odoo_operator.

`generic_operator` was a transitional assistant. Its capabilities (invoke_assistant
tool + meta-orchestration prompt) have been folded into `odoo_operator`, which
now serves as the single general-purpose CRUD + delegation assistant.
"""

import logging

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    if not version:
        return

    # Wipe the assistant row
    cr.execute("DELETE FROM llm_assistant WHERE code = 'generic_operator'")
    deleted_assistants = cr.rowcount

    # Wipe the prompt row by xmlid (covers the case where prompt was reused
    # or moved elsewhere — only the one we created with this xmlid is removed).
    cr.execute(
        """
        DELETE FROM llm_prompt
        WHERE id IN (
            SELECT res_id FROM ir_model_data
            WHERE module = 'llm_assistant'
              AND name = 'llm_prompt_generic_operator'
        )
        """,
    )
    deleted_prompts = cr.rowcount

    # Drop their ir.model.data rows so the un-loaded data file doesn't leave dangling xmlids
    cr.execute(
        """
        DELETE FROM ir_model_data
        WHERE module = 'llm_assistant'
          AND name IN ('llm_assistant_generic_operator', 'llm_prompt_generic_operator')
        """,
    )
    deleted_xmlids = cr.rowcount

    _logger.info(
        "llm_assistant 19.0.1.5.5: dropped %d assistant row(s), %d prompt row(s), "
        "%d ir.model.data entries for the obsolete generic_operator",
        deleted_assistants, deleted_prompts, deleted_xmlids,
    )
