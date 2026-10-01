"""Post templates.

Three designs, selectable / previewable from /settings -> Post Design:

  1. Editorial - magazine layout: bold title, genre line, quoted synopsis,
                 small-caps labelled facts, hashtags.
  2. Noir      - dark spec-sheet: accent bar, CAPS title, a monospace facts
                 panel, quoted synopsis.
  3. Zen       - soft minimal: italic synopsis, one quiet facts line.

Design rules (what keeps them from looking cheap): real Telegram formatting
(bold / italic / blockquote / monospace) instead of unicode "fancy fonts",
at most one or two emoji accents per post, short rules that never wrap on a
phone, and generous blank lines. "Stylish text" means small-caps labels.

Premium emoji: each accent slot below can be mapped to a custom-emoji id
(/settings -> Post Design -> Premium Emoji). Unmapped slots use the plain
emoji, so posts always render, even without Telegram Premium.
"""
import html
import re

from bot import Vars
from Tools.config import emoji_map
from Tools.fonts import stylize

# slot -> (label shown in settings, fallback emoji). Only the accents the
# templates actually use - deliberately few: restraint is what makes a post
# look premium, and every slot here is one you can swap for a custom emoji.
SLOTS = {
  "star": ("Editorial · title", "⭐"),
  "arrow": ("Editorial · footer", "📌"),
  "fire": ("Noir · hashtags", "🔥"),
  "sparkle": ("Zen · title", "✨"),
  "heart": ("Zen · closing", "🤍"),
}
SLOT_ORDER = list(SLOTS)


def _emoji_tag():
  """pyrogram forks differ: <emoji id=".."> (pyrofork) vs <tg-emoji emoji-id=".."> (kurigram)."""
  try:
    import inspect
    import pyrogram.parser.html as parser
    if "tg-emoji" in inspect.getsource(parser):
      return "tg-emoji", "emoji-id"
  except Exception:
    pass
  return "emoji", "id"


_TAG, _ATTR = _emoji_tag()
_TAG_RE = re.compile(r"<[^>]+>")
_UTF16 = "utf-16-le"


def visible_len(text: str) -> int:
  return len(html.unescape(_TAG_RE.sub("", text)).encode(_UTF16)) // 2


def _tags(genres):
  out = []
  for g in genres:
    g = re.sub(r"\W+", "_", g.strip()).strip("_")
    if g:
      out.append("#" + g)
  return " ".join(out[:8])


def _split_genres(raw):
  if isinstance(raw, (list, tuple)):
    return [str(g) for g in raw]
  raw = str(raw or "")
  raw = raw.replace("#", " ")
  parts = raw.split(",") if "," in raw else raw.split()
  return [p for p in (x.strip() for x in parts) if p and p.upper() != "N/A"]


class _Ctx:
  """Formatting helpers bound to the current settings."""

  def __init__(self, premium=None, stylish=None, footer=None):
    self.stylish = Vars.POST_STYLISH if stylish is None else stylish
    self.premium = Vars.POST_PREMIUM_EMOJI if premium is None else premium
    self.footer = Vars.POST_FOOTER if footer is None else footer
    self._map = emoji_map() if self.premium else {}

  def e(self, slot):
    fallback = SLOTS[slot][1]
    cid = self._map.get(slot)
    if cid:
      return f'<{_TAG} {_ATTR}="{int(cid)}">{fallback}</{_TAG}>'
    return fallback

  def s(self, text, font):
    text = html.escape(str(text))
    return stylize(text, font) if self.stylish else text

  def label(self, text, font="smallcaps"):
    return f"<b>{self.s(text, font)}</b>"

  def cap(self, text):
    """A quiet label: small caps when stylish, plain otherwise."""
    text = html.escape(str(text))
    return stylize(text.lower(), "smallcaps") if self.stylish else text.capitalize()


# --------------------------------------------------------------------------- #
# templates - each returns HTML. `desc` is already escaped and length-limited.
# --------------------------------------------------------------------------- #
_NBSP = "\u00a0"


def _status_dot(status):
  """A purposeful colour cue - the one emoji that carries information."""
  s = (status or "").lower()
  if any(w in s for w in ("ongoing", "publishing", "releasing", "updating")):
    return "🟢"
  if any(w in s for w in ("complete", "finished", "ended")):
    return "🔵"
  if any(w in s for w in ("hiatus", "paused")):
    return "🟡"
  if any(w in s for w in ("cancel", "drop", "discontinu")):
    return "🔴"
  return ""


def _status_text(d):
  status = (d.get("status") or "").strip()
  if not status or status.upper() == "N/A":
    return ""
  dot = _status_dot(status)
  return f"{dot} {html.escape(status)}" if dot else html.escape(status)


def _chapters_text(d):
  n = d.get("chapters")
  if not n:
    return ""
  return f"{n} chapter" + ("" if str(n) == "1" else "s")


def _formats_text(d):
  return html.escape(d["formats"]).replace(" · ", " + ") if d.get("formats") else ""


def _genre_line(d, sep=" · ", n=4):
  return sep.join(html.escape(g) for g in d["genres"][:n])


def _hashtags(d):
  return " ".join(_tags(d["genres"]).split()[:6])


def t_editorial(c: _Ctx, d, desc):
  """Magazine layout."""
  out = [f"{c.e('star')} <b>{html.escape(d['title'])}</b>"]
  genres = _genre_line(d)
  if genres:
    out.append(f"<i>{genres}</i>")
  out.append("")
  if desc:
    out += [f"<blockquote expandable>{desc}</blockquote>", ""]
  facts = [
    ("Status", _status_text(d)),
    ("Chapters", str(d["chapters"]) if d.get("chapters") else ""),
    ("Format", _formats_text(d)),
    ("Source", html.escape(d["source"]) if d.get("source") else ""),
  ]
  for label, value in facts:
    if value:
      out.append(f"{c.cap(label)}{_NBSP}{_NBSP}<b>{value}</b>")
  tags = _hashtags(d)
  if tags:
    out += ["", tags]
  if c.footer:
    out += ["", f"{c.e('arrow')} <i>{html.escape(c.footer)}</i>"]
  return "\n".join(out)


def t_noir(c: _Ctx, d, desc):
  """Dark spec-sheet: accent bar, CAPS title, monospace facts panel."""
  out = [f"▌<b>{html.escape(d['title'].upper())}</b>"]
  genres = _genre_line(d, sep=" / ")
  if genres:
    out.append(f"▌<i>{genres}</i>")
  out.append("")
  rows = [
    ("STATUS", html.escape((d.get("status") or "").strip()) if _status_text(d) else ""),
    ("CHAPTERS", str(d["chapters"]) if d.get("chapters") else ""),
    ("FORMAT", _formats_text(d)),
    ("SOURCE", html.escape(d["source"]) if d.get("source") else ""),
  ]
  rows = [(k, v) for k, v in rows if v]
  if rows:
    width = max(len(k) for k, _ in rows) + 2
    out.append("<pre>" + "\n".join(f"{k:<{width}}{v}" for k, v in rows) + "</pre>")
  if desc:
    out += ["", f"<blockquote expandable>{desc}</blockquote>"]
  tags = _hashtags(d)
  if tags:
    out += ["", f"{c.e('fire')} {tags}"]
  if c.footer:
    out += ["", f"<b>{html.escape(c.footer)}</b>"]
  return "\n".join(out)


def t_zen(c: _Ctx, d, desc):
  """Soft minimal: italic synopsis, one quiet facts line."""
  out = [f"{c.e('sparkle')} <b>{html.escape(d['title'])}</b>"]
  genres = _genre_line(d)
  if genres:
    out.append(f"<i>{genres}</i>")
  out.append("")
  if desc:
    out += [f"<blockquote expandable><i>{desc}</i></blockquote>", ""]
  facts = [x for x in (_status_text(d), _chapters_text(d), _formats_text(d)) if x]
  if d.get("source"):
    facts.append(f"via {html.escape(d['source'])}")
  if facts:
    out.append(f"{_NBSP}{_NBSP}·{_NBSP}{_NBSP}".join(facts))
    out.append("")
  closing = html.escape(c.footer) if c.footer else c.cap("happy reading")
  out.append(f"{c.e('heart')} <i>{closing}</i>")
  return "\n".join(out)


TEMPLATES = {
  1: ("Editorial", t_editorial),
  2: ("Noir", t_noir),
  3: ("Zen", t_zen),
}

SAMPLE = {
  "title": "Solo Leveling",
  "genres": ["Action", "Fantasy", "Adventure"],
  "status": "Completed",
  "chapters": 200,
  "formats": "PDF · CBZ",
  "source": "Asura Scans",
  "description": ("Ten years ago, a portal connecting our world to a world of monsters opened. "
                  "Sung Jin-Woo, the weakest of all hunters, gets a second chance to level up "
                  "in a way no one else can."),
}

MAX_VISIBLE = 1000   # Telegram caption limit is 1024; keep a margin


def _clip(text: str, n: int) -> str:
  text = re.sub(r"\s+", " ", text or "").strip()
  return text if len(text) <= n else text[: max(n - 1, 0)].rstrip() + "…"


def render_post(data: dict, template: int = None, premium=None, stylish=None, footer=None) -> str:
  """data: title, genres|genre, status, description, chapters, formats, source."""
  template = template or Vars.POST_TEMPLATE
  _, fn = TEMPLATES.get(int(template), TEMPLATES[1])
  c = _Ctx(premium=premium, stylish=stylish, footer=footer)
  d = dict(data)
  d["title"] = _clip(d.get("title") or "Unknown", 90)
  d["genres"] = _split_genres(d.get("genres", d.get("genre")))
  d["status"] = _clip(d.get("status") or "", 30)
  limit = max(40, int(Vars.POST_DESC_LEN))
  while True:
    desc = html.escape(_clip(d.get("description", ""), limit)) if d.get("description") else ""
    text = fn(c, d, desc).strip()
    if visible_len(text) <= MAX_VISIBLE or limit <= 40:
      return text
    limit = max(40, limit - 40)


def plain_emoji_version(data, template=None):
  """Same post without premium emoji (used if Telegram rejects the custom emoji)."""
  return render_post(data, template, premium=False)
