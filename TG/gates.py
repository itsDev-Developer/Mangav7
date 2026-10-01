"""Access control that runs before every other handler (early groups):

  -20  Tools.ask       (waiting-for-input router)
   -6  private mode    (IS_PRIVATE)
   -5  force-subscribe
"""
from pyrogram import filters
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup

import Tools.ask  # noqa: F401  (registers the group -20 handler)
from bot import Bot, Vars, is_admin
from Tools.base import igrone_error

from .storage import check_fsb, fsb_channels, safe_photo_reply, split_list


@Bot.on_message(filters.incoming & (filters.private | filters.regex(r"^/")), group=-6)
async def private_gate(client, message):
  user = message.from_user
  if not Vars.IS_PRIVATE or not user or is_admin(user.id):
    return
  # The "📖 Read Now" deep link under a channel post (/start get_<post_id>)
  # stays open even in private mode. Private mode is meant to restrict the
  # bot's interactive features (search, subscribe, downloading on demand,
  # etc.) to admins - it was never meant to stop someone from collecting a
  # file that was already published publicly in the channel, which is the
  # entire point of posting to a channel in the first place. Previously this
  # gate blocked that deep link too, so private mode silently broke file
  # delivery for every regular user.
  if message.text and message.text.startswith("/start get_"):
    return
  if message.chat.type.name == "PRIVATE":
    await igrone_error(message.reply_text)(Vars.PRIVATE_TXT, quote=True)
  message.stop_propagation()


@Bot.on_callback_query(group=-6)
async def private_gate_cb(client, query):
  if Vars.IS_PRIVATE and not is_admin(query.from_user.id):
    await igrone_error(query.answer)("🔒 This bot is private right now.", show_alert=True)
    query.stop_propagation()


@Bot.on_message(filters.private & filters.incoming, group=-5)
async def fsb_gate(client, message):
  user = message.from_user
  if not user or is_admin(user.id) or not fsb_channels():
    return
  buttons = await check_fsb(client, user.id)
  if not buttons:
    return
  rows = split_list(buttons) + [[InlineKeyboardButton("𝗥𝗘𝗙𝗥𝗘𝗦𝗛 ⟳", callback_data="refresh")]]
  await safe_photo_reply(message, Vars.FORCE_SUB_TEXT, InlineKeyboardMarkup(rows))
  message.stop_propagation()
