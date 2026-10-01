import asyncio
import os
import platform
import shutil
import time
from io import BytesIO
from os import execl
from sys import executable

import psutil
import pyrogram.errors
from pyrogram import filters
from pyrogram.errors import FloodWait
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from bot import Bot, Vars, admin_only, is_admin, logger, owner_only
from Tools.db import (
  add_premium, ensure_user, get_all_premuim, get_users, premium_user,
  remove_expired_users, remove_premium, uts,
)
from Tools.my_token import verify_token

from .post import deliver_post
from .storage import igrone_error, queue, retry_on_flood, safe_photo_reply

HELP_MSG = """
<b>To download a manga just type the name of the manga you want to keep up to date.</b>

For example:
<code>One Piece</code>

<blockquote expandable><i>Then choose the website you want to use. There you can subscribe, or pick a chapter to download. The chapters are sorted the way the website sorts them.</i></blockquote>

Tap a button below for the full command list.
"""

USER_COMMANDS_MSG = """
<b>👤 User Commands</b>

/start — welcome message and main menu
/help — this help
<code>&lt;manga name&gt;</code> — search and download/subscribe (just type it in DM, no command needed)
/search &lt;manga name&gt; — same search, usable in group chats too
/subs or /subscribes — manage your manga subscriptions
/us, /user_setting or /user_panel — your personal settings (file type, caption, thumbnail, dump chat, compression, password, merge size...)
/my_plan — check your premium status
/queue — see your pending download tasks
/clean_tasks or /clean_queue — clear your pending tasks
"""

ADMIN_COMMANDS_MSG = """
<b>🛠 Admin Commands</b>

<u>Posting</u>
/newpost — create a channel post manually
/postsettings or /pm — set the Post/Dump channels
/settings — full bot settings panel (channels, post design, templates, premium emoji, access, performance, progress bar, auto-backup)
/scheduled — view/cancel scheduled posts
/autopublish — view/remove the Auto-Publish watch list

<u>Data</u>
/backup — export the whole database as JSON
/restore — reply to a backup file to import it (<code>overwrite</code> to force-replace)
/export &lt;file&gt; — send any raw file on disk (debugging)
/import &lt;file&gt; — reply to a file to save it on disk under that name (debugging)

<u>Users &amp; Premium</u>
/info &lt;user_id&gt; — a user's saved settings
/premium or /premium_users — list premium users
/add or /add_premium &lt;user_id&gt; &lt;days&gt; — grant premium
/del or /del_premium &lt;user_id&gt; — revoke premium
/del_expired or /del_expired_premium — clean up expired premium users

<u>Broadcast</u>
/broadcast or /b — message every user
/pbroadcast or /pb — message every premium user
/forward or /fd — forward a message to every user
/pforward or /pfd — forward a message to every premium user

<u>System</u>
/stats — CPU/RAM/disk/network status
/clean or /c — delete leftover work files
/restart — restart the bot
/shell — run a shell command (owner only)
"""


@Bot.on_callback_query(filters.regex("^help_cb$"))
async def help_callback(client, query):
  await igrone_error(query.answer)()
  await retry_on_flood(query.edit_message_caption)(HELP_MSG, reply_markup=_help_markup(query.from_user.id))


@Bot.on_callback_query(filters.regex("^helpcmds$"))
async def help_user_cmds_cb(client, query):
  await igrone_error(query.answer)()
  await retry_on_flood(query.edit_message_caption)(
    USER_COMMANDS_MSG, reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⇦ Back", callback_data="help_cb")]])
  )


@Bot.on_callback_query(filters.regex("^helpadmin$") & filters.user(Vars.ADMINS))
async def help_admin_cmds_cb(client, query):
  await igrone_error(query.answer)()
  await retry_on_flood(query.edit_message_caption)(
    ADMIN_COMMANDS_MSG, reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⇦ Back", callback_data="help_cb")]])
  )


@Bot.on_callback_query(filters.regex("^start_cb$"))
async def back_to_start_callback(client, query):
  await igrone_error(query.answer)()
  await retry_on_flood(query.edit_message_caption)(_start_text(), reply_markup=_start_buttons(query.from_user.id))


def _help_markup(user_id):
  rows = [[InlineKeyboardButton("👤 User Commands", callback_data="helpcmds")]]
  if is_admin(user_id):
    rows.append([InlineKeyboardButton("🛠 Admin Commands", callback_data="helpadmin")])
  rows.append([InlineKeyboardButton("⇦ Back", callback_data="start_cb")])
  return InlineKeyboardMarkup(rows)


@Bot.on_message(filters.command("help"))
async def help_cmd(client, message):
  await safe_photo_reply(message, HELP_MSG, _help_markup(message.from_user.id))


def _start_text():
  ping = time.strftime("%Hh%Mm%Ss", time.gmtime(time.time() - Vars.PING))
  return ("<b><i>👋 Welcome to the best manga/manhwa/manhua PDF bot on Telegram!</i></b>\n\n"
          "<b><i>How to use it?</i></b> Just type the name of the manga you want, "
          "e.g. <code>One Piece</code>, and I'll help you search, read and download it.\n\n"
          f"<b><i>⚡ Uptime:</i></b> <code>{ping}</code>\n\n"
          "<b><i>Tap /help for a full guide.</i></b>")


def _start_buttons(user_id):
  rows = [[InlineKeyboardButton("⚙️ Settings", callback_data="mus"),
           InlineKeyboardButton("❓ Help", callback_data="help_cb")]]
  if is_admin(user_id):
    rows.append([InlineKeyboardButton("🛠 Bot Settings (admin)", callback_data="adm:home")])
  rows.append([InlineKeyboardButton("✖️ Close", callback_data="kclose")])
  return InlineKeyboardMarkup(rows)


@Bot.on_message(filters.command("start"))
async def start(client, message):
  ensure_user(message.from_user.id)
  if len(message.command) > 1:
    param = message.command[1]
    if param != "start":
      # Deep link from the "📖 Read Now" button under a channel post: ?start=get_<post_id>
      if param.startswith("get_"):
        return await deliver_post(client, message, param.removeprefix("get_"))
      # Deep link from an inline-mode result: ?start=isearch_<cache_id>
      if param.startswith("isearch_"):
        return await _run_isearch(client, message, param.removeprefix("isearch_"))
      sts = await message.reply("<i>ㅤProcessing.....</i>")
      return await verify_token(sts, message.from_user.id, param)

  await safe_photo_reply(message, _start_text(), _start_buttons(message.from_user.id))


async def _run_isearch(client, message, sid):
  """Re-run the search that produced an inline-mode result, once the user
  has opened a private chat with the bot (inline results can't deliver
  files directly - see TG/inline.py). `sid` is a short cache id, not the
  raw query text, since Telegram's deep-link parameter only allows
  [A-Za-z0-9_-] and manga titles/queries can contain anything."""
  import random
  from .storage import search_everywhere, check_get_web, searchs, isearch_cache

  query = isearch_cache.get(sid)
  if not query:
    return await retry_on_flood(message.reply_text)(
      "⏰ That search link expired. Please search again.", quote=True
    )

  sts = await retry_on_flood(message.reply_photo)(
    random.choice(Vars.PICS), caption=f"<i>🔎 Searching: <b>{query}</b> ...</i>", quote=True
  )
  try:
    results = await search_everywhere(query)
  except Exception as e:
    logger.exception(e)
    results = []

  results = [r for r in results if query.lower() in (r.get("title") or "").lower()][:10] or results[:10]
  if not results:
    return await igrone_error(sts.edit_caption)(f"❌ No results for <b>{query}</b>.")

  rows = []
  for r in results:
    webs_ = check_get_web(r.get("url", ""))
    if not webs_:
      continue
    c = f"chs|{webs_.sf}{hash(r['url'])}"
    searchs[c] = (webs_, r)
    site_name = type(webs_).__name__.replace("Webs", "")
    rows.append([InlineKeyboardButton(f"{r['title']} [{site_name}]", callback_data=c)])

  if not rows:
    return await igrone_error(sts.edit_caption)(f"❌ No results for <b>{query}</b>.")

  await igrone_error(sts.edit_caption)(
    f"<i>Results for <b>{query}</b>:</i>", reply_markup=InlineKeyboardMarkup(rows)
  )


@Bot.on_message(filters.command("my_plan"))
async def my_plan(client, message):
  plan = await premium_user(message.from_user.id)
  if plan:
    days = round((plan["expiration_timestamp"] - time.time()) / 86400)
    await message.reply(
      f"<i>Your Information:</i>\n\n  <b>- User ID: {message.from_user.id}</b>\n"
      f"  <b>- Username: {message.from_user.username}</b>\n"
      f"  <b>- Days left: {days}</b>\n\n<i>Thanks For Buying It......</i>",
      quote=True,
      reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("▏𝗖𝗟𝗢𝗦𝗘▕", callback_data="kclose")]]))
  else:
    await message.reply("<i> You Have No Plan!! </i>", reply_markup=InlineKeyboardMarkup(
      [[InlineKeyboardButton(" Buy Now ", callback_data="premuim")]]))


@Bot.on_message(filters.command(["clean_tasks", "clean_queue"]))
async def deltask(client, message):
  if queue.get_count(message.from_user.id):
    numb = await queue.delete_tasks(message.from_user.id)
    await message.reply(f"<i>All Your Tasks Deleted:- {numb} </i>")
  else:
    await message.reply("<i>There is no any your pending tasks.... </i>")


# --------------------------------------------------------------------------- #
# admin: users / premium
# --------------------------------------------------------------------------- #
@Bot.on_message(filters.command("info") & admin_only)
async def get_info_(client, message):
  try:
    user_id = str(message.command[1])
  except IndexError:
    return await message.reply("<code>/info user_id</code>")
  user = uts.get(user_id)
  if not user:
    return await message.reply("<code>User Not Found</code>")
  setting = user.get("setting", {})
  keys = ("file_name", "caption", "thumb", "banner1", "banner2", "dump", "type", "megre",
          "regex", "file_name_len", "password", "compress")
  txt = f"<b>User ID: {user_id}</b>\n" + "\n".join(f"<b>{k}: {setting.get(k, 'None')}</b>" for k in keys)
  await message.reply(txt[:4000])


@Bot.on_message(filters.command(["add", "add_premium"]) & admin_only)
async def add_handler(_, msg):
  try:
    user_id, days = int(msg.command[1]), int(msg.command[2])
  except (IndexError, ValueError):
    return await msg.reply("<code>/add user_id days</code>")
  await add_premium(user_id, days)
  await msg.reply("<code>User added to premium successfully.</code>")
  await igrone_error(_.send_message)(
    user_id, f"<i>You are now a premium user for {days} days... Thanks For Buying It.....</i>")


@Bot.on_message(filters.command(["del", "del_premium"]) & admin_only)
async def del_handler(_, msg):
  try:
    user_id = int(msg.command[1])
  except (IndexError, ValueError):
    return await msg.reply("<code>/del user_id</code>")
  await remove_premium(user_id)
  await msg.reply("<code>User removed from premium successfully.</code>")
  await igrone_error(_.send_message)(user_id, "<i>Your premium plan has ended. Please buy again or contact the owner.</i>")


@Bot.on_message(filters.command(["del_expired", "del_expired_premium"]) & admin_only)
async def del_expired_handler(_, msg):
  await remove_expired_users()
  await msg.reply("<code>Expired users removed successfully.</code>")


@Bot.on_message(filters.command(["premium", "premium_users"]) & admin_only)
async def premium_handler(_, msg):
  lines = ["<b>Premium Users:-</b>"]
  async for user_id, data in get_all_premuim():
    days = round((data["expiration_timestamp"] - time.time()) / 86400)
    lines.append(f"• <code>{user_id}</code> — {days} day(s) left")
  if len(lines) == 1:
    lines.append("<i>none</i>")
  await msg.reply("\n".join(lines)[:4000])


# --------------------------------------------------------------------------- #
# admin: broadcast
# --------------------------------------------------------------------------- #
@Bot.on_message(filters.command(["broadcast", "b"]) & admin_only)
async def b_handler(_, msg):
  return await broadcast_(_, msg)


@Bot.on_message(filters.command(["pbroadcast", "pb"]) & admin_only)
async def pb_handler(_, msg):
  return await broadcast_(_, msg, pin=True)


@Bot.on_message(filters.command(["forward", "fd"]) & admin_only)
async def fb_handler(_, msg):
  return await broadcast_(_, msg, forward=True)


@Bot.on_message(filters.command(["pforward", "pfd"]) & admin_only)
async def pfb_handler(_, msg):
  return await broadcast_(_, msg, pin=True, forward=True)


async def broadcast_(_, message, pin=None, forward=None):
  if not message.reply_to_message:
    return await message.reply_text("<code>Reply to a message to broadcast it.</code>")
  sts = await message.reply_text("<code>Broadcasting...</code>")
  source = message.reply_to_message
  users = get_users()
  stats = dict(ok=0, blocked=0, deleted=0, failed=0)

  async def send(user_id):
    return await (source.forward(user_id) if forward else source.copy(user_id))

  for user_id in users:
    try:
      try:
        sent = await send(user_id)
      except FloodWait as e:
        await asyncio.sleep(e.value + 1)
        sent = await send(user_id)
      if pin:
        await igrone_error(sent.pin)(both_sides=True)
      stats["ok"] += 1
    except (pyrogram.errors.UserIsBlocked, pyrogram.errors.UserNotParticipant):
      stats["blocked"] += 1
    except pyrogram.errors.InputUserDeactivated:
      stats["deleted"] += 1
    except Exception:
      stats["failed"] += 1
    await asyncio.sleep(0.05)           # stay far below Telegram's 30 msg/s limit

  await retry_on_flood(sts.edit)(
    f"<b><u>Broadcast Completed</u>\n\nTotal Users: <code>{len(users)}</code>\n"
    f"Successful: <code>{stats['ok']}</code>\nBlocked: <code>{stats['blocked']}</code>\n"
    f"Deleted Accounts: <code>{stats['deleted']}</code>\nFailed: <code>{stats['failed']}</code></b>")


# --------------------------------------------------------------------------- #
# admin: system
# --------------------------------------------------------------------------- #
@Bot.on_message(filters.command("restart") & admin_only)
async def restart_(client, message):
  from Tools.db import flush_now
  msg = await message.reply_text("<code>Restarting.....</code>", quote=True)
  with open("restart_msg.txt", "w") as file:
    file.write(f"{msg.chat.id}:{msg.id}")
  flush_now()
  execl(executable, executable, "-B", "main.py")


def humanbytes(size):
  if not size:
    return "0 B"
  size = float(size)
  for unit in ("B", "KB", "MB", "GB", "TB"):
    if size < 1024 or unit == "TB":
      return f"{size:.2f} {unit}"
    size /= 1024


@Bot.on_message(filters.command("stats"))
async def show_stats(client, message):
  t0 = time.time()
  status_msg = await message.reply("📊 <b>Accessing System Details...</b>")
  ping_ms = int((time.time() - t0) * 1000)

  proc = psutil.Process(os.getpid())
  proc.cpu_percent(None)
  psutil.cpu_percent(None)
  net_start = psutil.net_io_counters()
  await asyncio.sleep(1.5)                       # never block the event loop
  net_end = psutil.net_io_counters()
  span = 1.5

  total, used, free = shutil.disk_usage(".")
  ram = psutil.virtual_memory()
  uptime = time.strftime("%Hh %Mm %Ss", time.gmtime(time.time() - Vars.PING))
  mem = proc.memory_info()

  text = f"""🖥️ <b>System Statistics</b>

💾 <b>Disk</b>  <code>{humanbytes(used)} / {humanbytes(total)}</code> (free {humanbytes(free)})
🧠 <b>RAM</b>  <code>{humanbytes(ram.used)} / {humanbytes(ram.total)}</code> ({ram.percent}%)
⚡ <b>CPU</b>  <code>{psutil.cpu_percent(None)}%</code> on {os.cpu_count()} cores

🔌 <b>Bot process</b>
├ CPU: <code>{proc.cpu_percent(None)}%</code>
└ RAM: <code>{humanbytes(mem.rss)}</code>

🌐 <b>Network</b>
├ Up: <code>{humanbytes((net_end.bytes_sent - net_start.bytes_sent) / span)}/s</code>
└ Down: <code>{humanbytes((net_end.bytes_recv - net_start.bytes_recv) / span)}/s</code>

📟 {platform.system()} {platform.release()} · Python {platform.python_version()}
⏱ Uptime: <code>{uptime}</code> · Ping: <code>{ping_ms} ms</code>
📦 Queue: <code>{queue.qsize()}</code> waiting · <code>{len(queue.ongoing_tasks)}</code> running"""
  await retry_on_flood(status_msg.edit)(text)


@Bot.on_message(filters.command("shell") & owner_only)
async def shell(_, message):
  cmd = message.text.split(maxsplit=1)
  if len(cmd) == 1:
    return await message.reply("<code>No command to execute was given.</code>")
  proc = await asyncio.create_subprocess_shell(
    cmd[1], stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
  stdout, stderr = await proc.communicate()
  stdout, stderr = stdout.decode(errors="replace").strip(), stderr.decode(errors="replace").strip()
  reply = ""
  if stdout:
    reply += f"<b>Stdout</b>\n<pre>{stdout}</pre>\n"
  if stderr:
    reply += f"<b>Stderr</b>\n<pre>{stderr}</pre>"
  if len(reply) > 3000:
    bio = BytesIO(reply.encode())
    await message.reply_document(bio, file_name="shell_output.txt")
  else:
    await message.reply(reply or "No Reply")


@Bot.on_message(filters.command("export") & admin_only)
async def export_(_, message):
  cmd = message.text.split(maxsplit=1)
  if len(cmd) == 1:
    return await message.reply("<code>File Name Not given.</code>")
  name = cmd[1]
  if os.path.isfile(name):
    await message.reply_document(name)
  else:
    await message.reply("<code>File Not Found</code>")


@Bot.on_message(filters.command("import") & admin_only)
async def import_(_, message):
  cmd = message.text.split(maxsplit=1)
  if len(cmd) == 1 or not message.reply_to_message or not message.reply_to_message.document:
    return await message.reply("<code>Reply to a file with /import file_name</code>")
  if os.path.exists(cmd[1]):
    return await message.reply("<code>File already exists</code>")
  await message.reply_to_message.download(file_name=cmd[1])
  await message.reply("<code>Imported.</code>")


@Bot.on_message(filters.command(["clean", "c"]) & admin_only)
async def clean_files(_, message):
  """Delete leftover work files."""
  sts = await message.reply_text("🔍 Cleaning files...")
  shutil.rmtree("Process", ignore_errors=True)
  removed = 0
  for root, dirs, files in os.walk(".", topdown=True):
    dirs[:] = [d for d in dirs if d not in (".git", "venv", "env", "__pycache__", "data")]
    for file in files:
      if file.lower().endswith((".mkv", ".mp4", ".zip", ".pdf", ".cbz", ".temp")):
        try:
          os.remove(os.path.join(root, file))
          removed += 1
        except OSError:
          pass
  await sts.edit(f"🧹 Removed <b>{removed}</b> leftover file(s) and the Process folder.")
