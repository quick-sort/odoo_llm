# LLM Discuss — Design Document

Status: implemented (v19.0.1.0.0)
Related module: `llm_discuss_livechat` (optional, adds Live Chat operator support)

## 1. Problem

`odoo_llm` (`llm`, `llm_thread`, `llm_assistant`, ...) implements a full LLM
assistant stack, but it is **not connected to Odoo's Discuss app**. Assistants
live in their own `llm.thread` conversation records, rendered by a dedicated
client action — a parallel chat UI, not the Discuss channels employees and
Live Chat visitors actually use.

This module makes an `llm.assistant` behave like an **internal bot**: a real
`res.users` account that other users can chat with (1:1 "direct message") or
`@mention` inside any `discuss.channel`, and that replies automatically using
the assistant's configured provider/model/prompt/tools.

## 2. Prior art in Odoo core

Odoo core already ships exactly this pattern for OdooBot, in `mail_bot`:

- OdooBot *is* `base.partner_root`, a real `res.partner`/`res.users`.
- `discuss.channel` (in `mail_bot/models/discuss_channel.py`) overrides
  `_message_post_after_hook(message, msg_vals)` and calls
  `self.env["mail.bot"]._apply_logic(self, msg_vals)`.
- `mail.bot._apply_logic()` decides whether to answer, computes a reply body,
  and calls `channel.sudo().message_post(author_id=odoobot_id, ...)`.

`llm_discuss` reuses this exact hook point (`_message_post_after_hook`) and
architecture, swapping the hand-written FAQ logic in `mail.bot` for a call
into `llm.assistant.invoke()`.

## 3. Design goals / non-goals

Goals:
- Any `llm.assistant` can be turned into a Discuss bot with one click, no
  code changes.
- No blocking of the HTTP request that posted the triggering message — LLM
  calls can take several seconds, they must not stall `message_post`.
- No changes required to `llm`, `llm_thread`, or `llm_assistant` — this is a
  pure additive bridge module.
- No hard dependency on `im_livechat` — Live Chat support is an optional
  companion module (`llm_discuss_livechat`), since many installs use Discuss
  without Live Chat.

Non-goals (left for future iterations, see §8):
- Streaming the assistant's reply token-by-token into the channel.
- Multi-turn context: the current implementation feeds the *triggering
  message's body* as the query; it does not replay channel history into the
  LLM call. `llm.assistant.invoke()` already opens a dedicated `llm.thread`
  per invocation, so *the assistant's own reasoning* can still use tools /
  memory as configured — what's missing is "what did the human say 3 messages
  ago in this Discuss channel", which is a reasonable v2 feature.
- Access control nuances for portal/public users chatting with the bot (see
  §7).

## 4. Architecture

```
res.users (bot account) ──partner_id──> res.partner ──channel_member──> discuss.channel
        ▲                                     │
        │ discuss_user_id (M2O)               │ message_post(..., author_id=bot_partner)
        │                                     ▼
   llm.assistant  ───────────────────────────────────┐
        │ discuss_enabled, discuss_trigger_mode       │
        │                                              │
        │ invoke(query, thread_vals, new_cursor=False) │
        ▼                                              │
   llm.thread (sub-conversation, res_model=discuss.channel) │
        │                                              │
        └──── mail.message (llm_role) ─────────────────┘
                    (read back by the queue job as `result_html`)
```

Message flow, end to end:

1. A message is posted on a `discuss.channel` (comment from a real user, or
   from the frontend controllers `/mail/message/post`, `/discuss/channel/*`).
2. `mail.thread.message_post()` creates the `mail.message`, then calls
   `discuss.channel._message_post_after_hook(message, msg_vals)`
   (`addons/mail/models/mail_thread.py`).
3. `llm_discuss` overrides that hook. It asks every `discuss_enabled`
   assistant, through `discuss.channel._llm_discuss_should_trigger()`,
   whether it should react to this message (see §5 — trigger rules).
4. For each match, it creates an `llm.discuss.reply.queue` row (assistant,
   channel, source message) and calls `ir.cron._trigger()` to wake the
   processing cron **immediately**, without waiting for its normal polling
   interval. This is the same "wake a cron on demand" idiom Odoo itself uses
   (`ir.cron._trigger`), avoiding a hard dependency on `queue_job`.
5. The cron method `llm.discuss.reply.queue._cron_process_pending()` picks up
   pending rows and, **for each row separately**, calls
   `assistant.invoke(query, thread_vals={"model": "discuss.channel",
   "res_id": channel.id}, new_cursor=False)`. `new_cursor=False` is
   intentional: the cron job already owns its own transaction/cursor, and
   `invoke()` composes with that instead of opening a second one.
6. On success, it posts the result back with
   `channel.sudo().message_post(author_id=bot_partner.id, body=result_html,
   message_type="comment", subtype_xmlid="mail.mt_comment")` — this is a
   perfectly ordinary Discuss message, so it goes through the normal
   `mail.message` → `bus.bus` → websocket pipeline and simply appears in the
   channel like a message from any other user.
7. Each queue row commits independently (`self.env.cr.commit()`) so one
   failing job (LLM timeout, provider error) can never roll back or block
   the others — mirroring how Odoo's own batch cron jobs are written.

## 5. Trigger rules (`discuss_channel._llm_discuss_should_trigger`)

An assistant is only ever considered if:
- `assistant.discuss_enabled = True`, and
- it has a `discuss_user_id` (bot account created), and
- the triggering message's author is *not* the bot itself (loop guard,
  same check `mail.bot` does against OdooBot), and
- `msg_vals["message_type"] == "comment"` (ignores system/log/notification
  messages, e.g. "X joined the channel").

Given that, `assistant.discuss_trigger_mode` selects:

| Mode | Condition |
|---|---|
| `direct_chat` | `channel.channel_type == "chat"` (1:1 DM) and the bot is a member |
| `mention` | the bot's partner is in `msg_vals["partner_ids"]` (an `@mention`) |
| `both` (default) | either of the above |

`_llm_discuss_should_trigger` is a plain overridable model method — this is
the extension point `llm_discuss_livechat` overrides to add a Live-Chat-only
rule (any message in a livechat session where the bot is the operator),
without `llm_discuss` itself knowing anything about `im_livechat`.

## 6. Why a custom queue model instead of `queue_job` or a raw thread

Three options were considered:

1. **Synchronous call in the HTTP request** — rejected: an LLM call can take
   5-30s; blocking `message_post` would make Discuss feel broken for the
   human participants of the same channel.
2. **OCA `queue_job`** — the natural production choice, but it is an optional
   dependency not guaranteed to be installed, and `odoo_llm` deliberately
   keeps its module graph dependency-light (see `llm_assistant`'s own
   `invoke()` docstring, which already anticipates both `queue_job` and
   plain-cron callers via the `new_cursor` flag).
3. **A tiny queue table + `ir.cron._trigger()`** (chosen) — zero extra
   dependencies, uses only core Odoo primitives, and the per-row `try/except`
   + `cr.commit()` pattern gives the same failure isolation `queue_job` would.
   If a site *does* have `queue_job` installed, swapping
   `Queue.create(...)` + `cron._trigger()` for `assistant.with_delay().invoke(...)`
   is a one-method change (`llm.assistant._llm_discuss_dispatch`), not a
   redesign.

The cron itself still runs every minute as a safety net (in case a
`_trigger()` call is lost, e.g. server restart between create and trigger),
so replies are near-real-time in the common case and eventually-consistent
in the worst case.

## 7. Security notes

- The bot's `res.users` is created with `share=False` and only
  `base.group_user` — an ordinary internal user, deliberately **not** an
  administrator. It only gets whatever access `llm.assistant`'s own ACLs
  already grant plus normal Discuss member rights on channels it is added to.
- `llm.discuss.reply.queue` is only ever created/read via `sudo()` from the
  hook and the cron; direct ACL access is restricted to `llm.group_llm_manager`
  (defined in the `llm` module) so regular users cannot see or tamper with
  pending jobs from the UI/ORM.
- The reply is posted with `channel.sudo().message_post(...)` — required
  because the code path runs from inside a cron job (`env.user` is the cron's
  runner, not the bot), mirroring how `mail.bot` also does
  `channel.sudo().message_post(author_id=odoobot_id, ...)`.
- **Portal/public visitors**: `llm.assistant.is_public` / `allowed_group_ids`
  gate *interactive* use of an assistant (e.g. opening its chat UI). The
  Discuss bridge bypasses that check by design — once an assistant is
  `discuss_enabled` it will answer *any* member of a channel it belongs to,
  including portal users if such a channel includes one. If this is not
  desired, restrict which channels the bot account is added to, or add an
  explicit ACL check in `_llm_discuss_should_trigger` before installing this
  module in a portal-facing deployment.
- No secrets are logged; queue rows only store the assistant/channel/message
  ids, not API keys or raw provider payloads.

## 8. Limitations / future work

- No conversation history is replayed into the assistant call (see §3).
- No streaming — the whole answer appears at once when generation finishes.
- No dedup/backoff if an assistant is added to a very high-traffic channel;
  each qualifying message enqueues one job. For heavy use, point
  `_llm_discuss_dispatch` at `queue_job` instead (see §6).
- `discuss.channel.member` forbids public users
  (`_contrains_no_public_member`), so the bot account can never be a member
  through the public/guest path — only via being explicitly added as an
  internal user, which is the expected setup.

## 9. Module layout

```
llm_discuss/
├── __manifest__.py
├── models/
│   ├── llm_assistant.py        # discuss_user_id, discuss_enabled, dispatch
│   ├── discuss_channel.py      # _message_post_after_hook, trigger rule
│   └── llm_discuss_reply_queue.py
├── data/ir_cron_data.xml       # safety-net cron (1 min)
├── security/ir.model.access.csv
├── views/llm_assistant_views.xml   # "Discuss / Live Chat" tab on the assistant form
└── DESIGN.md                   # this file
```

See `llm_discuss_livechat/DESIGN.md` for the Live Chat operator extension.
