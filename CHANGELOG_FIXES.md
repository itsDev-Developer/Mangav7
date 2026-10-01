# What was fixed — read this first

## 🔴 Most important: an auto-updater was silently wiping your bot

`start.sh` ran `update.py` before every boot. That script deleted `.git`,
re-initialized it, and force-reset (`git reset --hard`) your **entire
codebase** to `https://github.com/itsDev-Developer/manwa` — a repo that
belongs to whoever built the original template, not you. Every restart
overwrote every file with that repo's version, with no warning and no way to
opt out from inside the bot.

This is almost certainly why bugs kept resurfacing no matter what got fixed,
and why several fully-built features (progress bars, caption templates, the
settings registry) existed in the code but were never actually wired up —
they'd been added at some point and then silently reverted.

**Fixed:** `update.py` is now disabled by default. It only runs if you
explicitly set `ENABLE_AUTO_UPDATE=true` **and** point `UPSTREAM_REPO` at
your own fork — and even then it only fast-forwards (never force-overwrites
local changes). See the comment at the top of `update.py`.

## 🟢 "Post to Channel" — root cause found and fixed

`TG/post.py`'s `_gather_all_chapters()` called `iter_chapters()` directly on
raw manga data without ever calling `get_chapters()` to actually fetch the
chapter list first. Every site module needs that fetch step — skipping it
meant the function silently returned nothing (or missed everything past the
first page). Fixed to fetch each page properly, matching the logic already
used by the manual chapter-pagination buttons.

## 🟢 Live progress bar while downloading

A full progress-bar system (`Tools/progress.py` — bytes, percent, ETA) already
existed in the code but wasn't connected to two flows:
- **📤 Post to Channel** (`TG/post.py`)
- **📖 Full Page bulk download** (`TG/callback.py`)

Both passed `sts=None`, so nothing displayed until the whole job finished (or
failed). Both now share one live status message + a `BatchState` counter, so
you see per-chapter "downloading page X/Y", bytes and ETA, plus an overall
"chapter i/N" count — the same bar single-chapter downloads already had.

## 🟢 3 caption templates with stylish fonts + premium emoji — wired up

`Tools/templates.py` already contained 3 fully-built designs (**Elegant
Card**, **Neon Frame**, **Kawaii Minimal**) with stylized unicode fonts and
premium (custom) emoji support — but nothing ever called it. Posts were
built by a separate, much plainer caption builder.

Now:
- Every post (manual `/newpost` wizard and auto "📤 Post to Channel") is
  rendered through the real template system.
- Each preview has a **🎨 template switcher** — tap to flip between the 3
  designs and see the exact result before publishing.
- If a channel/bot can't show premium emoji (no Telegram Premium), it
  automatically retries with plain emoji instead of failing the post.

## 🟢 `/settings` — the missing configuration panel, built

The bot's command menu already advertised `/settings`, and a complete
settings *registry* existed (`Tools/config.py`) — but there was no code
file implementing the command at all. Built `TG/admin_settings.py`, covering:

- **📢 Channels** — Post/Dump/Log/Constant-dump channels
- **🎨 Post Design** — button text, footer, synopsis length, stylish fonts
  on/off, premium emoji on/off, blurred poster, **+ the template picker with
  live preview, + premium emoji slot mapping** (tap a slot, send a message
  containing your custom emoji)
- **🔐 Access & Security** — private mode, shortener/token settings,
  force-sub message, **+ extra admins list, + force-subscribe channel list**
- **⚡ Performance** — parallel chapters (workers), download threads, default
  image quality, auto-updates on/off, update interval
- **📊 Progress Bar** — on/off, bar style, refresh interval

Everything saves to the database instantly — no restart needed.

Also fixed: `/postsettings`'s channel setter and the new `/settings` panel
used to write to *different* config keys for the same Post/Dump channel
(`post_channel` vs `POST_CHANNEL`), so they'd silently overwrite each other.
Both now write to the same canonical key.

## 🟡 RAM / CPU

`main.py` unconditionally spawned **20** hardcoded chapter-processing
workers, completely ignoring the `WORKERS` setting (default: 3). Each worker
runs its own download/convert/upload pipeline with its own thread pool, so
this alone was often running several times more concurrent work — and using
several times more RAM/CPU — than intended. Fixed to spawn exactly the
configured number of workers (adjustable live from **⚡ Performance**), via
the `ensure_workers()` mechanism that already existed in `Tools/cworker.py`
but was never called.

Also fixed:
- `Tools/auto.py`'s subscription checker ignored the `AUTO_UPDATES` and
  `UPDATE_INTERVAL` settings (hardcoded to always run every 10 minutes) —
  now respects both.
- `apply_all()` (copies saved settings onto the running bot) was never
  called anywhere — settings changes reverted on every restart. Now called
  at startup in `main.py`.

## 🧹 Cleanup

- `app.py` was a leftover Flask "Hello World" dev server that ran
  automatically on import (no `__main__` guard!) on port 8080. Several
  hosting platforms auto-detect a top-level `app.py` with a Flask `app` and
  will run *that* instead of your actual bot. Neutralized — it's now an
  inert file with an explanation.
- Removed unused dependencies from `requirements.txt`: `flask`, `gunicorn`,
  `PyPDF2`, `cairosvg`, `pytz` — none of them were imported anywhere; the
  bot already has its own lightweight health-check server and builds PDFs
  with `reportlab` directly.

## Note on testing

I don't have network access or Telegram credentials in this environment, so
I read every changed code path end-to-end and confirmed the whole project
compiles cleanly, but I could not run the bot live end-to-end myself. Please
test with your bot token before relying on this in production, especially
the premium-emoji slot mapping (Telegram's custom-emoji entity format can
vary slightly between pyrofork/kurigram versions).
