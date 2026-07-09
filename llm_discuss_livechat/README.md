# LLM Discuss Live Chat

Companion module for [`llm_discuss`](../llm_discuss): lets an assistant act
as a **Live Chat operator**.

**Module Type:** 🔌 Bridge (`llm_discuss` ⇄ `im_livechat`)

## What it does

- Adds a **Live Chat Channels** field on `llm.assistant` (once it has a Bot
  User, from `llm_discuss`): pick which `im_livechat.channel` records this
  assistant operates on.
- Keeps the bot user's operator membership on those channels in sync.
- Adds the Live-Chat-specific auto-reply rule: every visitor message in a
  session where the assistant is the operator gets an answer — no
  `@mention` needed, unlike plain Discuss channels.

## Install

```bash
odoo-bin -d your_db -i llm_discuss_livechat
```

## Design

See [`DESIGN.md`](DESIGN.md), especially the notes on how this interacts
with human operators and with Odoo's native `chatbot.script` framework
(they solve different problems and can coexist).

## License

LGPL-3
