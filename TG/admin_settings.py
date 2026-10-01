"""
Admin bot-wide settings panel — /settings.

Every knob in Tools/config.py's registry (channels, post design, access &
security, performance, progress bar) plus the 3 caption templates, premium
emoji slots, extra admins and force-subscribe channels is editable from here.

/settings was already advertised in the bot's command menu but had no
handler at all — this file is that handler. Every change is written to the
DB via Tools.config.set_value()/set_fsb_list()/etc, which also updates
`bot.Vars` immediately, so nothing needs a restart.
"""
import html

from pyrogram import filters
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from pyrogram.errors import ListenerTimeout as TimeoutError

from bot import Bot, Vars, logger
from Tools.config import (
    CATEGORIES, ITEMS, BY_KEY, coerce, set_value, reset_value, is_overridden,
    extra_admins, set_extra_admins, fsb_list, set_fsb_list, emoji_map, set_emoji_map,
)
from Tools.templates import SLOTS, SLOT_ORDER, TEMPLATES, SAMPLE, render_post
from .storage import retry_on_flood, igrone_error

CANCEL_WORDS = ("/cancel", "cancel")


# --------------------------------------------------------------------------- #
# category / item rendering
# --------------------------------------------------------------------------- #
def _fmt_value(item):
  val = getattr(Vars, item.key, None)
  if item.kind == "bool":
    return "✅ On" if val else "❌ Off"
  if item.kind == "choice":
    for v, label in item.choices:
      if v == val:
        return label
    return str(val)
  if val in (None, ""):
    return "Not set"
  if getattr(item, "secret", False):
    text = str(val)
    return f"•••• {text[-4:]}" if len(text) > 4 else "•••• set"
  text = str(val)
  return text if len(text) <= 28 else text[:25] + "…"


def _root_markup():
  rows = [[InlineKeyboardButton(label, callback_data=f"cfgcat:{key}")] for key, (label, _d) in CATEGORIES.items()]
  rows.append([InlineKeyboardButton("👮 Extra Admins", callback_data="cfgadmins"),
               InlineKeyboardButton("🚧 Force-Sub", callback_data="cfgfsb")])
  rows.append([InlineKeyboardButton("🔁 Auto-Publish List", callback_data="cfgautopub"),
               InlineKeyboardButton("🕒 Scheduled Posts", callback_data="schedlist")])
  rows.append([InlineKeyboardButton("✖️ Close", callback_data="cfgclose")])
  return InlineKeyboardMarkup(rows)


def _root_text():
  return (
    "<b>🛠 Bot Settings</b>\n\n"
    "Saved straight to the database and applied instantly — no restart, "
    "no env vars needed. Pick a category:"
  )


def _cat_items(cat_key):
  return [i for i in ITEMS if i.cat == cat_key]


def _cat_markup(cat_key):
  rows = []
  for item in _cat_items(cat_key):
    row = [InlineKeyboardButton(f"{item.label}: {_fmt_value(item)}", callback_data=f"cfgset:{item.key}")]
    if is_overridden(item.key):
      row.append(InlineKeyboardButton("↩️", callback_data=f"cfgreset:{item.key}"))
    rows.append(row)
  if cat_key == "post":
    rows.append([InlineKeyboardButton(f"🎨 Caption Template  (#{Vars.POST_TEMPLATE} {TEMPLATES[Vars.POST_TEMPLATE][0]})", callback_data="cfgtmpl")])
    rows.append([InlineKeyboardButton("🎭 Premium Emoji Slots", callback_data="cfgemoji")])
  if cat_key == "backup":
    rows.append([InlineKeyboardButton("📦 Backup Now", callback_data="cfgbackupnow")])
    rows.append([InlineKeyboardButton("ℹ️ How to restore", callback_data="cfgbackup")])
  if cat_key == "filestore":
    rows.append([InlineKeyboardButton("🔌 Test Connection", callback_data="cfgfstest")])
    rows.append([InlineKeyboardButton("📖 Setup Guide", callback_data="cfgfsguide")])
  rows.append([InlineKeyboardButton("⇦ Back", callback_data="cfgroot")])
  return InlineKeyboardMarkup(rows)


def _cat_text(cat_key):
  label, desc = CATEGORIES[cat_key]
  return f"<b>{label}</b>\n<i>{desc}</i>"


@Bot.on_callback_query(filters.regex("^adm:home$") & filters.user(Vars.ADMINS))
async def settings_from_start_menu_cb(client, query):
  # The /start menu's "🛠 Bot Settings (admin)" button pointed at this
  # callback_data with no handler anywhere in the codebase - another dead
  # button. It lives on a photo message, so open the panel as a fresh
  # message rather than trying to edit_message_text a photo's caption.
  await igrone_error(query.answer)()
  await retry_on_flood(client.send_message)(query.message.chat.id, _root_text(), reply_markup=_root_markup())


@Bot.on_callback_query(filters.regex("^cfgbackup$") & filters.user(Vars.ADMINS))
async def settings_backup_cb(client, query):
  await igrone_error(query.answer)()
  await retry_on_flood(query.edit_message_text)(
    "<b>💾 Backup & Restore</b>\n\n"
    "• <b>/backup</b> — export everything (users, posts, settings, scheduled "
    "posts, auto-publish list) as one JSON file.\n"
    "• <b>/restore</b> — reply to a backup file with this command to import it "
    "(safe merge by default - existing entries are kept; add "
    "<code>overwrite</code> to force-replace them instead).\n\n"
    "Tap below to create one now.",
    reply_markup=InlineKeyboardMarkup([
      [InlineKeyboardButton("📦 Backup Now", callback_data="cfgbackupnow")],
      [InlineKeyboardButton("⇦ Back", callback_data="cfgcat:backup")],
    ]),
  )


@Bot.on_callback_query(filters.regex("^cfgbackupnow$") & filters.user(Vars.ADMINS))
async def settings_backup_now_cb(client, query):
  await igrone_error(query.answer)("📦 Building backup...")
  from .backup import backup_cmd
  await backup_cmd(client, query.message)


@Bot.on_callback_query(filters.regex("^cfgfstest$") & filters.user(Vars.ADMINS))
async def settings_filestore_test_cb(client, query):
  await igrone_error(query.answer)("🔌 Testing...")
  from Tools import filestore_api

  back = InlineKeyboardMarkup([[InlineKeyboardButton("⇦ Back", callback_data="cfgcat:filestore")]])

  if not Vars.FILESTORE_API_URL or not Vars.FILESTORE_API_KEY:
    return await retry_on_flood(query.edit_message_text)(
      "❌ <b>Not configured.</b>\n\nSet API Base URL and API Key first "
      "(tap them above), then test again.",
      reply_markup=back,
    )

  data = await filestore_api.ping()
  if not data:
    return await retry_on_flood(query.edit_message_text)(
      "❌ <b>Connection failed.</b>\n\n"
      "Check the API Base URL is correct and reachable, and that the API "
      "Key hasn't been revoked. Check the bot's logs for the exact error.",
      reply_markup=back,
    )

  from .post import get_dump_channel
  storage = get_dump_channel()
  await retry_on_flood(query.edit_message_text)(
    f"✅ <b>Connected!</b>\n\n"
    f"<b>Bot:</b> @{data.get('bot', '?')}\n"
    f"<b>Key:</b> {data.get('key_label', '?')}\n"
    f"<b>API version:</b> {data.get('version', '?')}\n\n"
    f"Links are built from this bot's storage channel"
    + (f" (<code>{storage}</code>)" if storage else " — <b>not set yet</b>, set the Constant Dump")
    + f". Add that channel to @{data.get('bot', 'that bot')} as a DB channel "
    "so links reference the files in place (no copies).",
    reply_markup=back,
  )


@Bot.on_callback_query(filters.regex("^cfgfsguide$") & filters.user(Vars.ADMINS))
async def settings_filestore_guide_cb(client, query):
  await igrone_error(query.answer)()
  await retry_on_flood(query.edit_message_text)(
    "<b>📖 File Store Bot setup</b>\n\n"
    "1. In the File Store Bot, run its API-key command (e.g. <code>/newapikey</code>) "
    "to get a bearer token.\n"
    "2. Add <b>API Base URL</b> and <b>API Key</b> above.\n"
    "3. Set this bot's <b>Storage (Constant Dump)</b> channel (Channels) — every file "
    "is stored there once.\n"
    "4. In the File Store Bot, add <b>that same channel</b> as a DB channel "
    "(<code>/adddb</code>). Links then point at the files where they already are — "
    "nothing is copied or stored twice. (If you skip this, the API copies each file "
    "into its own channel instead, which works but duplicates storage; the bot must "
    "then be an admin of the storage channel.)\n"
    "5. Tap <b>🔌 Test Connection</b>, then turn on <b>Use File Store Bot</b>.\n\n"
    "Every new post (manual, Post to Channel, Auto-Publish, scheduled) then gets its "
    "\"Read Now\" link generated automatically. A post's files are written to storage "
    "as one uninterrupted run so a single batch link covers them; if a post's files "
    "ever aren't contiguous (e.g. it reuses chapters stored earlier), the link is built "
    "from an exact copy instead. If a link can't be generated at all, the post still "
    "publishes and just uses this bot's own delivery.",
    reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⇦ Back", callback_data="cfgcat:filestore")]]),
  )


@Bot.on_callback_query(filters.regex("^cfgautopub$") & filters.user(Vars.ADMINS))
async def settings_autopub_cb(client, query):
  await igrone_error(query.answer)()
  from .post import _autopublish_list_view
  text, markup = _autopublish_list_view()
  rows = markup.inline_keyboard if markup else []
  rows = list(rows) + [[InlineKeyboardButton("⇦ Back", callback_data="cfgroot")]]
  await retry_on_flood(query.edit_message_text)(text, reply_markup=InlineKeyboardMarkup(rows))


@Bot.on_message(filters.command("settings") & filters.user(Vars.ADMINS))
async def settings_cmd(client, message):
  await retry_on_flood(message.reply_text)(_root_text(), quote=True, reply_markup=_root_markup())


@Bot.on_callback_query(filters.regex("^cfgroot$") & filters.user(Vars.ADMINS))
async def settings_root_cb(client, query):
  await igrone_error(query.answer)()
  await retry_on_flood(query.edit_message_text)(_root_text(), reply_markup=_root_markup())


@Bot.on_callback_query(filters.regex("^cfgclose$") & filters.user(Vars.ADMINS))
async def settings_close_cb(client, query):
  await igrone_error(query.answer)()
  await igrone_error(query.message.delete)()


@Bot.on_callback_query(filters.regex("^cfgcat:") & filters.user(Vars.ADMINS))
async def settings_cat_cb(client, query):
  cat_key = query.data.split(":", 1)[1]
  if cat_key not in CATEGORIES:
    return await retry_on_flood(query.answer)("Unknown category.", show_alert=True)
  await igrone_error(query.answer)()
  await retry_on_flood(query.edit_message_text)(_cat_text(cat_key), reply_markup=_cat_markup(cat_key))


@Bot.on_callback_query(filters.regex("^cfgreset:") & filters.user(Vars.ADMINS))
async def settings_reset_cb(client, query):
  key = query.data.split(":", 1)[1]
  item = BY_KEY.get(key)
  if not item:
    return await retry_on_flood(query.answer)("Unknown setting.", show_alert=True)
  reset_value(key)
  await igrone_error(query.answer)(f"↩️ {item.label} reset to default.")
  await retry_on_flood(query.edit_message_text)(_cat_text(item.cat), reply_markup=_cat_markup(item.cat))


@Bot.on_callback_query(filters.regex("^cfgset:") & filters.user(Vars.ADMINS))
async def settings_item_cb(client, query):
  key = query.data.split(":", 1)[1]
  item = BY_KEY.get(key)
  if not item:
    return await retry_on_flood(query.answer)("Unknown setting.", show_alert=True)

  if item.kind == "bool":
    set_value(key, not bool(getattr(Vars, key)))
    await igrone_error(query.answer)(f"{item.label}: {_fmt_value(item)}")
    return await retry_on_flood(query.edit_message_text)(_cat_text(item.cat), reply_markup=_cat_markup(item.cat))

  if item.kind == "choice":
    rows = [[InlineKeyboardButton(f"{'✅ ' if v == getattr(Vars, key) else ''}{label}", callback_data=f"cfgchoice:{key}:{v}")]
            for v, label in item.choices]
    rows.append([InlineKeyboardButton("⇦ Back", callback_data=f"cfgcat:{item.cat}")])
    await igrone_error(query.answer)()
    return await retry_on_flood(query.edit_message_text)(
      f"<b>{item.label}</b>\n<i>{item.help}</i>", reply_markup=InlineKeyboardMarkup(rows)
    )

  hint = ""
  if item.kind == "int":
    hint = f" — a whole number, {item.lo}–{item.hi}"
  elif item.kind == "channel":
    hint = " — forward a message from the channel, or send its @username / numeric id"
  elif item.hi:
    hint = f" — max {item.hi} characters, send <code>-</code> to clear"

  await igrone_error(query.answer)()
  await retry_on_flood(query.edit_message_text)(
    f"<b>📐 {item.label}</b>{hint}\n\n<i>{item.help}</i>\n\n"
    f"Current: <code>{html.escape(_fmt_value(item))}</code>\n\n"
    "Send the new value, or /cancel."
  )
  try:
    reply = await client.listen(user_id=query.from_user.id, timeout=120)
  except TimeoutError:
    return await igrone_error(query.message.edit_text)(_cat_text(item.cat), reply_markup=_cat_markup(item.cat))

  raw = reply.text.strip() if reply.text else None
  if item.kind == "channel" and reply.forward_from_chat:
    raw = reply.forward_from_chat.id
  await igrone_error(reply.delete)()

  if raw is None or (isinstance(raw, str) and raw.lower() in CANCEL_WORDS):
    return await retry_on_flood(query.message.edit_text)(_cat_text(item.cat), reply_markup=_cat_markup(item.cat))

  value, error = coerce(item, raw)
  if error:
    await igrone_error(client.send_message)(query.from_user.id, f"❌ {error}")
    return await retry_on_flood(query.message.edit_text)(_cat_text(item.cat), reply_markup=_cat_markup(item.cat))

  set_value(key, value)
  await retry_on_flood(query.message.edit_text)(_cat_text(item.cat), reply_markup=_cat_markup(item.cat))


@Bot.on_callback_query(filters.regex("^cfgchoice:") & filters.user(Vars.ADMINS))
async def settings_choice_cb(client, query):
  _, key, value = query.data.split(":", 2)
  item = BY_KEY.get(key)
  if not item:
    return await retry_on_flood(query.answer)("Unknown setting.", show_alert=True)
  set_value(key, value)
  await igrone_error(query.answer)(f"✅ {item.label} set.")
  await retry_on_flood(query.edit_message_text)(_cat_text(item.cat), reply_markup=_cat_markup(item.cat))


# --------------------------------------------------------------------------- #
# 🎨 caption templates — live preview against a sample manga, tap to apply
# --------------------------------------------------------------------------- #
def _tmpl_markup():
  rows = [
    [InlineKeyboardButton(f"{'✅ ' if n == Vars.POST_TEMPLATE else ''}{n}. {name}", callback_data=f"cfgtmplset:{n}")]
    for n, (name, _fn) in TEMPLATES.items()
  ]
  rows.append([InlineKeyboardButton("🎭 Premium Emoji Slots", callback_data="cfgemoji")])
  rows.append([InlineKeyboardButton("⇦ Back", callback_data="cfgcat:post")])
  return InlineKeyboardMarkup(rows)


@Bot.on_callback_query(filters.regex("^cfgtmpl$") & filters.user(Vars.ADMINS))
async def settings_tmpl_cb(client, query):
  await igrone_error(query.answer)()
  preview = render_post(SAMPLE, template=Vars.POST_TEMPLATE)
  text = f"<b>🎨 Caption Templates</b>  (currently #{Vars.POST_TEMPLATE})\n\n{preview}"
  await retry_on_flood(query.edit_message_text)(text, reply_markup=_tmpl_markup())


@Bot.on_callback_query(filters.regex("^cfgtmplset:") & filters.user(Vars.ADMINS))
async def settings_tmpl_set_cb(client, query):
  n = int(query.data.split(":", 1)[1])
  if n not in TEMPLATES:
    return await retry_on_flood(query.answer)("Unknown template.", show_alert=True)
  set_value("POST_TEMPLATE", n)
  await igrone_error(query.answer)(f"🎨 {TEMPLATES[n][0]} set as the default template.")
  preview = render_post(SAMPLE, template=n)
  text = f"<b>🎨 Caption Templates</b>  (currently #{n})\n\n{preview}"
  await retry_on_flood(query.edit_message_text)(text, reply_markup=_tmpl_markup())


# --------------------------------------------------------------------------- #
# 🎭 premium emoji slots — map each slot to a custom-emoji id
# --------------------------------------------------------------------------- #
def _emoji_markup():
  m = emoji_map()
  rows = []
  for slot in SLOT_ORDER:
    label, fallback = SLOTS[slot]
    mark = "🎭" if slot in m else fallback
    rows.append([InlineKeyboardButton(f"{mark} {label}", callback_data=f"cfgemojiset:{slot}")])
    if slot in m:
      rows[-1].append(InlineKeyboardButton("↩️", callback_data=f"cfgemojidel:{slot}"))
  rows.append([InlineKeyboardButton("⇦ Back", callback_data="cfgtmpl")])
  return InlineKeyboardMarkup(rows)


@Bot.on_callback_query(filters.regex("^cfgemoji$") & filters.user(Vars.ADMINS))
async def settings_emoji_cb(client, query):
  await igrone_error(query.answer)()
  text = (
    "<b>🎭 Premium Emoji Slots</b>\n\n"
    "Tap a slot, then send a message containing the custom (Telegram Premium) "
    "emoji you want for it. Unmapped slots just use the plain emoji shown — "
    "posts always work even without Premium.\n\n"
    f"Premium emoji are currently <b>{'ON' if Vars.POST_PREMIUM_EMOJI else 'OFF'}</b> "
    "(toggle in 🎨 Post Design)."
  )
  await retry_on_flood(query.edit_message_text)(text, reply_markup=_emoji_markup())


@Bot.on_callback_query(filters.regex("^cfgemojidel:") & filters.user(Vars.ADMINS))
async def settings_emoji_del_cb(client, query):
  slot = query.data.split(":", 1)[1]
  m = emoji_map()
  m.pop(slot, None)
  set_emoji_map(m)
  await igrone_error(query.answer)(f"↩️ {SLOTS[slot][0]} reset to the plain emoji.")
  await retry_on_flood(query.edit_message_text)(query.message.text, reply_markup=_emoji_markup())


@Bot.on_callback_query(filters.regex("^cfgemojiset:") & filters.user(Vars.ADMINS))
async def settings_emoji_set_cb(client, query):
  slot = query.data.split(":", 1)[1]
  if slot not in SLOTS:
    return await retry_on_flood(query.answer)("Unknown slot.", show_alert=True)

  await igrone_error(query.answer)()
  await retry_on_flood(query.edit_message_text)(
    f"<b>🎭 {SLOTS[slot][0]} emoji</b>\n\n"
    "Send a message containing the custom (premium) emoji for this slot "
    "(just tap it from your emoji panel), or /cancel."
  )
  try:
    reply = await client.listen(user_id=query.from_user.id, timeout=120)
  except TimeoutError:
    return await igrone_error(query.message.edit_text)(
      f"🎭 {SLOTS[slot][0]} — timed out.", reply_markup=_emoji_markup()
    )

  text = reply.text or reply.caption
  if text and text.strip().lower() in CANCEL_WORDS:
    await igrone_error(reply.delete)()
    return await retry_on_flood(query.message.edit_text)(
      f"🎭 {SLOTS[slot][0]} — cancelled.", reply_markup=_emoji_markup()
    )

  emoji_id = None
  for entity in (reply.entities or reply.caption_entities or []):
    if "CUSTOM_EMOJI" in str(entity.type) and getattr(entity, "custom_emoji_id", None):
      emoji_id = entity.custom_emoji_id
      break
  await igrone_error(reply.delete)()

  if not emoji_id:
    await igrone_error(client.send_message)(
      query.from_user.id,
      "❌ That message didn't contain a custom (premium) emoji. "
      "Regular unicode emoji can't be mapped — try again from /settings."
    )
    return await retry_on_flood(query.message.edit_text)(
      f"🎭 {SLOTS[slot][0]} — no custom emoji found.", reply_markup=_emoji_markup()
    )

  m = emoji_map()
  m[slot] = str(emoji_id)
  set_emoji_map(m)
  await retry_on_flood(query.message.edit_text)(
    f"✅ {SLOTS[slot][0]} emoji saved.", reply_markup=_emoji_markup()
  )


# --------------------------------------------------------------------------- #
# 👮 extra admins
# --------------------------------------------------------------------------- #
def _admins_markup():
  rows = [[InlineKeyboardButton(f"❌ {uid}", callback_data=f"cfgadmindel:{uid}")] for uid in extra_admins()]
  rows.append([InlineKeyboardButton("➕ Add admin", callback_data="cfgadminadd")])
  rows.append([InlineKeyboardButton("⇦ Back", callback_data="cfgroot")])
  return InlineKeyboardMarkup(rows)


def _admins_text():
  ids = extra_admins()
  body = "\n".join(f"• <code>{i}</code>" for i in ids) if ids else "<i>None added from the bot yet.</i>"
  return (
    "<b>👮 Extra Admins</b>\n\n"
    "In addition to the <code>ADMINS</code> env var and the owner. "
    f"Tap ❌ to remove one.\n\n{body}"
  )


@Bot.on_callback_query(filters.regex("^cfgadmins$") & filters.user(Vars.ADMINS))
async def settings_admins_cb(client, query):
  await igrone_error(query.answer)()
  await retry_on_flood(query.edit_message_text)(_admins_text(), reply_markup=_admins_markup())


@Bot.on_callback_query(filters.regex("^cfgadmindel:") & filters.user(Vars.ADMINS))
async def settings_admin_del_cb(client, query):
  uid = int(query.data.split(":", 1)[1])
  set_extra_admins([i for i in extra_admins() if i != uid])
  await igrone_error(query.answer)(f"❌ Removed {uid}.")
  await retry_on_flood(query.edit_message_text)(_admins_text(), reply_markup=_admins_markup())


@Bot.on_callback_query(filters.regex("^cfgadminadd$") & filters.user(Vars.ADMINS))
async def settings_admin_add_cb(client, query):
  await igrone_error(query.answer)()
  await retry_on_flood(query.edit_message_text)(
    "<b>➕ Add admin</b>\n\nSend the user's numeric Telegram ID, or forward a message from them, or /cancel."
  )
  try:
    reply = await client.listen(user_id=query.from_user.id, timeout=120)
  except TimeoutError:
    return await igrone_error(query.message.edit_text)(_admins_text(), reply_markup=_admins_markup())

  uid = None
  if reply.forward_from:
    uid = reply.forward_from.id
  elif reply.text and reply.text.strip().lstrip("-").isdigit():
    uid = int(reply.text.strip())
  await igrone_error(reply.delete)()

  if not uid:
    await igrone_error(client.send_message)(query.from_user.id, "❌ Send a numeric user id, or forward a message from them.")
    return await retry_on_flood(query.message.edit_text)(_admins_text(), reply_markup=_admins_markup())

  ids = extra_admins()
  if uid not in ids:
    ids.append(uid)
    set_extra_admins(ids)
  await retry_on_flood(query.message.edit_text)(_admins_text(), reply_markup=_admins_markup())


# --------------------------------------------------------------------------- #
# 🚧 force-subscribe channels
# --------------------------------------------------------------------------- #
def _fsb_markup():
  rows = [[InlineKeyboardButton(f"❌ {text} → {chat}", callback_data=f"cfgfsbdel:{idx}")]
          for idx, (text, chat) in enumerate(fsb_list())]
  rows.append([InlineKeyboardButton("➕ Add channel", callback_data="cfgfsbadd")])
  rows.append([InlineKeyboardButton("⇦ Back", callback_data="cfgroot")])
  return InlineKeyboardMarkup(rows)


def _fsb_text():
  items = fsb_list()
  body = "\n".join(f"• <b>{html.escape(t)}</b> → <code>{c}</code>" for t, c in items) if items else "<i>None set — force-sub is off.</i>"
  return "<b>🚧 Force-Subscribe Channels</b>\n\nUsers must join all of these before using the bot.\n\n" + body


@Bot.on_callback_query(filters.regex("^cfgfsb$") & filters.user(Vars.ADMINS))
async def settings_fsb_cb(client, query):
  await igrone_error(query.answer)()
  await retry_on_flood(query.edit_message_text)(_fsb_text(), reply_markup=_fsb_markup())


@Bot.on_callback_query(filters.regex("^cfgfsbdel:") & filters.user(Vars.ADMINS))
async def settings_fsb_del_cb(client, query):
  idx = int(query.data.split(":", 1)[1])
  items = fsb_list()
  if 0 <= idx < len(items):
    items.pop(idx)
    set_fsb_list(items)
  await igrone_error(query.answer)("❌ Removed.")
  await retry_on_flood(query.edit_message_text)(_fsb_text(), reply_markup=_fsb_markup())


@Bot.on_callback_query(filters.regex("^cfgfsbadd$") & filters.user(Vars.ADMINS))
async def settings_fsb_add_cb(client, query):
  await igrone_error(query.answer)()
  await retry_on_flood(query.edit_message_text)(
    "<b>➕ Add force-sub channel</b>\n\n"
    "Send the button text and the channel, separated by a colon, e.g.\n"
    "<code>Join Updates: @mychannel</code>\nor forward a message from the channel, or /cancel."
  )
  try:
    reply = await client.listen(user_id=query.from_user.id, timeout=120)
  except TimeoutError:
    return await igrone_error(query.message.edit_text)(_fsb_text(), reply_markup=_fsb_markup())

  text_val, chat_val = None, None
  if reply.forward_from_chat:
    chat_val = reply.forward_from_chat.id
    text_val = reply.forward_from_chat.title or "Join Channel"
  elif reply.text and ":" in reply.text:
    left, right = reply.text.rsplit(":", 1)
    text_val, chat_val = left.strip(), right.strip().lstrip("@")
    if chat_val.lstrip("-").isdigit():
      chat_val = int(chat_val)
  await igrone_error(reply.delete)()

  if not text_val or not chat_val or (reply.text and reply.text.strip().lower() in CANCEL_WORDS):
    if not (reply.text and reply.text.strip().lower() in CANCEL_WORDS):
      await igrone_error(client.send_message)(
        query.from_user.id, "❌ Send it as <code>Text: @channel</code>, or forward a message from the channel."
      )
    return await retry_on_flood(query.message.edit_text)(_fsb_text(), reply_markup=_fsb_markup())

  items = fsb_list()
  items.append([text_val, chat_val])
  set_fsb_list(items)
  await retry_on_flood(query.message.edit_text)(_fsb_text(), reply_markup=_fsb_markup())
