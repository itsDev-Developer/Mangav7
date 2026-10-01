# Session 5 — batch links, single storage DB, new templates

## 1. Batch links (`not_contiguous`) — fixed

Your log: `File Store API error (/api/v1/links/batch): not_contiguous - Reference-mode batch links…`

"Reference-mode" means the channel we send as `source_chat_id` is already a DB
channel of the File Store Bot — the best case (no copying), but the API then
requires the message ids to be one **contiguous run**, because a batch link is
encoded as a single id range. Our ids never were: every uploaded file was also
copied into the Constant Dump channel, and if that is the same channel (or
other uploads land in it meanwhile) the copies sit between the originals.

Fixed on two sides:
- **Writes are contiguous.** A post's files are now written to storage as one
  exclusive run (`Tools/storage_db.py: exclusive()`). Archive copies of other
  users' downloads wait and flush right after, so they can't land in the middle.
  The `/newpost` wizard now collects your files first and copies them together
  on `/done`, for the same reason.
- **The API client picks the right call** (`Tools/filestore_api.py`):
  contiguous ids → `message_ids` (reference, zero-copy); anything else, or a
  `not_contiguous` rejection → the API's own `items` style, which copies the
  exact selection into a clean range. Real errors (bad key, rate limit…) are
  no longer retried pointlessly. `409` (storage busy) gets one retry.

## 2. Constant Dump = the single file-storage DB — nothing stored/downloaded twice

Before: a post uploaded each file into the Dump Channel and
`send_manga_chapter` then copied it *again* into the Constant Dump; a
chapter wanted by two users/posts was downloaded, converted and uploaded twice.

Now (`Tools/storage_db.py`, `Tools/cworker.py`):
- **One storage channel:** the Constant Dump (the Dump Channel is only a
  fallback if no Constant Dump is set). Posts, `/newpost`, Auto-Publish,
  scheduled posts and File Store links all use it. Old posts keep working —
  each stores the channel it was made with.
- **Index of what's stored** (`filedb` table, included in `/backup`): a chapter
  in a given file configuration → its message ids. Before downloading anything
  the worker checks it; on a hit the file is **server-side copied** to whoever
  asked (post, user, subscription update) — no download, no conversion, no
  upload. A fresh chapter is produced once and stored once.
- **Safe reuse:** the key covers chapters + file name + types + quality +
  password + banners + thumbnail, so nobody gets a file built with someone
  else's settings. Stored files are verified to still exist (deleted from the
  channel → entry dropped → regenerated). Two simultaneous requests for the
  same new chapter produce it once.
- Never copies a file into the channel it's already in.
- New switch: `/settings` → ⚡ Performance → **Reuse stored files**.
- Side benefit for CPU/RAM/bandwidth: a new chapter many users subscribe to
  is now downloaded and converted once instead of once per subscriber.

**Setup:** set **Storage (Constant Dump)** in `/settings` → Channels, make the
bot an admin there, and add that same channel to the File Store Bot as a DB
channel (`/adddb`). Links then reference files in place.

**One honest limitation:** a post that reuses chapters stored earlier mixes old
and new message ids, which can't be one contiguous range. Those posts use the
`items` fallback (works, but the File Store Bot copies the files into its own
channel for that link). Posts made from fresh chapters never need it.

## 3. Templates redesigned

What made them look cheap: math-alphabet fonts on titles (𝙎𝙤𝙡𝙤…/𝓢𝓸𝓵𝓸…),
an emoji on every row, 28-character `━` rules that wrap on phones, kaomoji
clutter. All three are rebuilt around real Telegram formatting, ≤2 emoji
accents, and no wrapping frames:

1. **Editorial** — bold title, genre line, quoted synopsis, small-caps labelled
   facts, hashtags.
2. **Noir** — accent bar, CAPS title, monospace facts panel, quoted synopsis.
3. **Zen** — italic synopsis and one quiet facts line.

"Stylish fonts" now means small-caps labels (`ꜱᴛᴀᴛᴜꜱ`). The status gets a
colour dot (🟢 ongoing / 🔵 completed / 🟡 hiatus / 🔴 dropped) — the one emoji
that carries information. Premium-emoji slots were cut from 12 to the 5 accents
actually used (each labelled by where it appears); existing mappings for
`star/arrow/fire/sparkle/heart` carry over. Descriptions are still auto-trimmed
to fit Telegram's caption limit.

## Testing

No live Telegram / File Store Bot here, so I tested the logic against
stubs, using the real source files: the API client (including the exact
`not_contiguous` case from your log), the storage module (contiguity under
concurrent writers, index validation, in-flight guard) and `send_manga_chapter`
end-to-end with a fake Telegram (post → repost → user reuse → deleted-file
regeneration → different-settings → concurrent requests). Templates were
rendered and checked for valid HTML, length limits and escaping. Please still
try one post on a staging channel — especially the `/adddb` step on the File
Store Bot side.
