# Session 2 — crash fix + 5 new features

## 🔴 Crash fix: "search button not working"

Your logs pointed straight at it:
```
File "Tools/db.py", line 386, in get_subs
    ... for w in webs for s in subs.get(w, [])) ...
AttributeError: 'list' object has no attribute 'get'
```

Root cause: `ensure_user()` only added `"subs"` to a user's record if the key
was **missing** — it didn't check the key was the right **type**. At least
one existing user document had `"subs"` stored as a flat list (an older
schema), so `subs.get(...)` crashed immediately. Every tap of a search
result calls this, which is why it looked like "the button doesn't work."

**Fixed:** `ensure_user()` now checks the type, not just presence, and
resets `subs`/`setting` to `{}` if they're ever the wrong shape. Also added
defensive filtering in `get_subs`/`delete_sub`/`get_all_subs` so a stray
malformed entry inside a site's list can't crash things either.

Also found and fixed while in there: the `/start` menu's **"🛠 Bot Settings
(admin)"** button (`adm:home`) had no handler anywhere in the codebase —
another dead button. It now opens the real `/settings` panel.

### About `[ManhwaBot] No plugin loaded from "TG"`
This line is harmless in your logs — not a bug. This bot registers every
handler directly on the already-created `Bot` instance (`@Bot.on_message`),
not through pyrogram's lazy class-level `@Client.on_message` pattern that
its plugin-counter checks for. The handlers *do* get registered correctly
(your own traceback proves it — `ch_handler` ran), the loader's count is
just wrong. Nothing to fix here.

## 🆕 New features

**1. Duplicate-post guard** — before publishing (wizard, auto-fetch, or
force-publish), the bot checks existing posts for a matching title. If
found, you get a warning with the existing post's ID/read count and have to
explicitly tap "Publish Anyway" to proceed.

**2. Inline mode** (`TG/inline.py`) — type `@YourBot <query>` in any chat to
search and share a result card with a "📖 Open in bot" button.
⚠️ **You must turn this on yourself** via @BotFather → your bot → Bot
Settings → Inline Mode. It can't be enabled from the bot's own code.

**3. Backup / Restore** (`TG/backup.py`) — `/backup` exports every table
(users, premium, posts, tokens, config, scheduled posts, auto-publish list)
as one JSON file. `/restore` (reply to that file) imports it back — merge
mode by default (won't clobber newer data), or `/restore overwrite` to
force-replace. Also reachable from `/settings` → 💾 Backup & Restore.

**4. Scheduled posting** — every post preview now has a **🕒 Schedule**
button alongside Confirm & Publish. Accepts `in 2h` / `in 30m` / `in 1d` or
an exact `YYYY-MM-DD HH:MM` (server clock). Stored in the DB (not memory),
so a restart before the scheduled time doesn't lose it. Manage pending ones
with `/scheduled`.

**5. Auto-publish for subscriptions** — every manga's info card now has a
**🔁 Auto-Publish** button next to Post to Channel. Tap it once, and from
then on new chapters get downloaded and posted to the Post Channel
automatically — no manual confirmation needed. Manage the list with
`/autopublish` (also reachable from `/settings`). Runs on the same interval
as subscription checks (⚡ Performance → Update Interval).

## Note on testing

Same caveat as before: no network/bot token in this environment, so I
traced every new code path by hand and the whole project compiles cleanly,
but I could not run it live. Two things worth testing first:
- The duplicate-guard's title match is exact (case/whitespace-insensitive)
  — a slightly different title for the same manga won't be caught.
- Inline mode needs BotFather's Inline Mode toggle turned on, or it won't
  receive any queries at all (Telegram-side requirement, not a bug here).
