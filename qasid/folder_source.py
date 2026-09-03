"""
Read the user's own folder of posts.

The whole public version of Qasid rests on this one idea: the user keeps their
material in plain files, in folders named by date, and Qasid does no more than
read them. No scraping, no accounts, no service. If someone can name a folder
2026-09-04 and drop a picture in it, they can use this.

    MyPosts/
      2026-09-04/
          1.jpg
          1.txt        <- caption for 1.jpg
          2.jpg

Rules, kept deliberately few, because every extra rule is something a user has
to be told and can get wrong:

  * The folder name is the date it goes out. Other dates are left alone.
  * Picture + .txt of the same name  -> picture with that caption.
  * Picture alone                    -> picture, no caption.
  * .txt alone                       -> a plain text message.
  * Order is by filename.
  * A filename may start with "HH-MM " to pin that one post to its own time.
  * Anything else in the folder is ignored, not an error. People keep notes
    next to their work.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta
from pathlib import Path

IMAGE_TYPES = {".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp"}
TEXT_TYPES = {".txt", ".md"}

# "07-15 hamal.jpg" or "0715 hamal.jpg" or "07.15-hamal.jpg"
TIME_PREFIX = re.compile(r"^(?P<h>[01]?\d|2[0-3])[-._: ]?(?P<m>[0-5]\d)\s+(?P<rest>.+)$")


@dataclass
class Post:
    """One thing to send: a picture, a caption, or both."""
    key: str                       # stable id for the ledger, unique within a day
    image: Path | None
    caption: str
    at: time | None = None         # set only when the filename pinned a time
    sources: list[Path] = field(default_factory=list)

    @property
    def kind(self) -> str:
        if self.image and self.caption:
            return "picture with caption"
        if self.image:
            return "picture"
        return "text"


def _stem_and_time(name: str) -> tuple[str, time | None]:
    """Split "07-15 hamal" into ("hamal", 07:15). No prefix -> (name, None)."""
    m = TIME_PREFIX.match(name)
    if not m:
        return name, None
    return m.group("rest").strip(), time(int(m.group("h")), int(m.group("m")))


def day_folder(root: Path, day: date) -> Path:
    return Path(root) / day.isoformat()


def read_day(root: Path, day: date) -> list[Post]:
    """
    Everything due on `day`, in the order it should go out.

    Returns [] when the folder is missing or holds nothing usable — an empty day
    is a normal thing (the user has not written tomorrow yet), not a failure.
    """
    folder = day_folder(root, day)
    if not folder.is_dir():
        return []

    # Group by the name without extension, so "1.jpg" and "1.txt" are one post.
    groups: dict[str, dict] = {}
    for f in sorted(folder.iterdir()):
        if not f.is_file() or f.name.startswith("."):
            continue
        ext = f.suffix.lower()
        if ext not in IMAGE_TYPES and ext not in TEXT_TYPES:
            continue                       # notes, spare files: not an error
        stem, at = _stem_and_time(f.stem)
        g = groups.setdefault(stem.lower(), {"stem": stem, "image": None,
                                             "caption": "", "at": None,
                                             "sources": []})
        if at and not g["at"]:
            g["at"] = at
        g["sources"].append(f)
        if ext in IMAGE_TYPES:
            if g["image"] is None:         # first picture wins, quietly
                g["image"] = f
        else:
            text = f.read_text(encoding="utf-8", errors="replace").strip()
            g["caption"] = (g["caption"] + "\n" + text).strip() if g["caption"] else text

    posts = [
        Post(key=g["stem"], image=g["image"], caption=g["caption"],
             at=g["at"], sources=g["sources"])
        for g in groups.values()
        if g["image"] is not None or g["caption"]
    ]
    posts.sort(key=lambda p: (p.at or time(0, 0), p.key.lower()))
    return posts


def schedule(posts: list[Post], start: time, gap_minutes: int,
             day: date | None = None) -> list[tuple[datetime, Post]]:
    """
    Give every post a clock time.

    Posts that named their own time keep it. The rest are laid out from `start`,
    one every `gap_minutes`. The gap is not decoration: a burst of messages is
    what gets an account flagged, so posts are spread out on purpose.
    """
    day = day or date.today()
    out: list[tuple[datetime, Post]] = []
    n = 0
    for p in posts:
        if p.at:
            when = datetime.combine(day, p.at)
        else:
            when = datetime.combine(day, start) + timedelta(minutes=gap_minutes * n)
            n += 1
        out.append((when, p))
    out.sort(key=lambda t: (t[0], t[1].key.lower()))
    return out


def available_days(root: Path) -> list[date]:
    """Every date folder present, oldest first — for showing the user what is ready."""
    root = Path(root)
    if not root.is_dir():
        return []
    days = []
    for f in root.iterdir():
        if not f.is_dir():
            continue
        try:
            days.append(date.fromisoformat(f.name))
        except ValueError:
            continue                        # a folder named something else
    return sorted(days)


def describe(root: Path, day: date, start: time, gap_minutes: int) -> str:
    """A plain-language summary for the web page, so the user can check it."""
    posts = read_day(root, day)
    if not posts:
        return f"Nothing for {day.isoformat()} — no folder, or nothing usable in it."
    lines = [f"{len(posts)} post(s) for {day.isoformat()}:"]
    for when, p in schedule(posts, start, gap_minutes, day):
        head = (p.caption.splitlines() or [""])[0][:60]
        lines.append(f"  {when:%H:%M}  {p.kind:20} {p.key}" + (f"  — {head}" if head else ""))
    return "\n".join(lines)
