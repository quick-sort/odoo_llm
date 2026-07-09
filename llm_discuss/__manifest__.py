{
    "name": "LLM Discuss",
    "summary": """
        Turn any LLM Assistant into an internal bot that answers in Discuss
    """,
    "description": """
LLM Discuss
===========
Bridges ``llm_assistant`` with Odoo's Discuss app.

Any ``llm.assistant`` can be promoted to an internal Discuss bot:

- A dedicated technical ``res.users`` account is created for the assistant
  (one click, "Create Bot User").
- Add that user to a 1:1 chat or any channel like any other employee.
- The assistant automatically replies when messaged directly, or when
  ``@mentioned`` in a channel, using its configured provider/model/prompt/tools.
- Replies are generated asynchronously (a lightweight internal queue +
  ``ir.cron``), so posting a message in Discuss never blocks waiting for the
  LLM call.

See ``DESIGN.md`` in this module for the full architecture write-up.

Live Chat support (assigning the bot as a Live Chat operator) is provided by
the companion module ``llm_discuss_livechat``.
    """,
    "category": "Productivity, Discuss",
    "version": "19.0.1.0.0",
    "depends": [
        "base",
        "mail",
        "llm_assistant",
    ],
    "author": "Apexive Solutions LLC",
    "website": "https://github.com/apexive/odoo-llm",
    "data": [
        "security/ir.model.access.csv",
        "data/ir_cron_data.xml",
        "views/llm_assistant_views.xml",
    ],
    "license": "LGPL-3",
    "installable": True,
    "application": False,
    "auto_install": False,
}
