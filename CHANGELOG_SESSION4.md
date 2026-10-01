# Session 4 — real File Store Bot API integration

## What changed

The earlier "File Store Bot" feature was a manual workaround: turn it on,
and every post creation would stop and ask you to separately upload the
same files to the other bot and paste back whatever link it gave you. That
whole step is gone now — replaced with a real integration against the API
docs you uploaded.

**New:** `Tools/filestore_api.py` — a small client for the File Store Bot's
Link Generation API:
- `ping()` — calls `GET /api/v1/ping`, used by the settings panel's Test
  Connection button.
- `create_link(dump_channel_id, message_ids)` — calls the single or batch
  link endpoint (whichever fits) with `source_chat_id` = your Dump Channel
  and the message id(s) of the files already sitting there. Handles the
  429 rate-limit case with one capped retry, and **fails soft everywhere**:
  any error (not configured, network issue, bad response, over the 100-file
  batch limit, whatever) just logs a warning and returns `None` — it never
  raises, so a File Store Bot hiccup can never block a post from
  publishing. It just falls back to this bot's own Dump Channel delivery
  for that one post.

**Wired into every post-creation path** — manual `/newpost`, "📤 Post to
Channel", and 🔁 Auto-Publish all now call this automatically right after
files land in the Dump Channel. (Scheduled posts inherit whichever draft
was already built, so they're covered too.) No manual step, and it works
even in the fully-automated Auto-Publish flow, which the old manual-paste
version couldn't support at all since there's no admin around to ask.

If the feature is on but generation fails for a specific post, you now get
a heads-up in chat (previously this was silent, log-only) telling you to
check the Test Connection button.

## New settings (`/settings` → 🗄 File Store Bot)

- **Use File Store Bot** (on/off) — same as before.
- **API Base URL** — the File Store Bot's API address.
- **API Key** — the bearer token from that bot's `/newapikey` (or
  equivalent) command. **Shown masked** in the settings UI now (only the
  last 4 characters) — added a `secret` flag to the settings system for
  this, since it didn't exist before and a bearer token is exactly the kind
  of thing that shouldn't sit in plaintext on screen.
- **File Store Bot username** — now just an optional reference field (the
  Test Connection button reports the actual connected bot from the API
  itself, so this isn't load-bearing anymore).
- **🔌 Test Connection** — calls `/api/v1/ping` and shows the connected
  bot/key label/API version, or a specific error if it fails. Deliberately
  works even before you've switched "Use File Store Bot" on, so you can
  verify the key works first.
- **📖 Setup Guide** — walks through the whole setup inline in the bot.

## Setup guide (also available at /settings → 🗄 File Store Bot → 📖 Setup Guide)

1. In the **File Store Bot**, run its API-key command (e.g. `/newapikey`)
   to get a bearer token.
2. In **this** bot: `/settings` → 🗄 File Store Bot → set **API Base URL**
   and **API Key**.
3. **Add the File Store Bot as an admin in this bot's Dump Channel.** This
   is the one manual step that can't be automated — read the explanation
   below for why it's needed.
4. Tap **🔌 Test Connection** to confirm the key works and see which bot
   it's talking to.
5. Turn on **Use File Store Bot**.

That's it — every post from then on gets its "Read Now" button generated
automatically.

### Why the File Store Bot needs to be a Dump Channel admin

Per the API docs: a link request runs in "reference" mode (fast, no copy)
only if `source_chat_id` is a channel the File Store Bot *already stores
files in itself*. Your Dump Channel is this bot's own channel, not theirs —
so every request here automatically falls into "copy" mode instead, where
their bot reads the message from your Dump Channel and copies it into their
own storage the first time a link is requested for it. It can only read
that message if it's an admin there. This happens transparently after
that — you don't need to think about it again once it's set up.

## Note on testing

I don't have a real File Store Bot deployment or API key to test this
against in this environment, so I built this directly and carefully against
the docs you provided, and the whole project still compiles cleanly with
these changes. Please run through the 5-step setup above and use **Test
Connection** before turning the feature on for real posts — that button is
exactly there so you can catch a config mistake (wrong URL, bad key, bot
not added as admin) before it affects anything live.
