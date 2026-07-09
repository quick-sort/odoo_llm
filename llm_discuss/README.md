# LLM Discuss

Turn any `llm.assistant` into an internal Discuss bot.

**Module Type:** 🔌 Bridge (`llm_assistant` ⇄ `mail`/Discuss)

## What it does

- Adds a **Create Bot User** button on `llm.assistant`, which creates a
  dedicated internal `res.users` account for the assistant.
- Add that user to a 1:1 chat or any channel like any other employee.
- Once `discuss_enabled` is checked, the assistant automatically replies:
  - to every message in its direct 1:1 chat, and/or
  - whenever it is `@mentioned` in a channel

  (configurable via the **Reply Trigger** field).
- Replies are generated asynchronously (internal queue + `ir.cron`, woken up
  immediately via `ir.cron._trigger()`), so posting a message never blocks
  waiting on the LLM call.

## Install

```bash
odoo-bin -d your_db -i llm_discuss
```

Requires `llm_assistant` (and therefore `llm`, `llm_thread`, `mail`) to
already be configured with at least one provider/model/assistant.

For Live Chat operator support, also install `llm_discuss_livechat`.

## Design

See [`DESIGN.md`](DESIGN.md) for the full architecture write-up: message
flow, trigger rules, why a custom queue instead of `queue_job`, and security
notes.

## License

LGPL-3
