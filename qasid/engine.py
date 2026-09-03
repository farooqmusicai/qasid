"""
The runner: read the folder, decide what is due, post it, remember it.

Deliberately thin. The two hard parts live elsewhere — folder_source.py knows
what the user wrote, whatsapp.py knows how to get it into WhatsApp without
breaking — and this file only joins them and keeps the books.
"""

from __future__ import annotations

import random
import time as _time
from datetime import date, datetime, time, timedelta
from pathlib import Path

from . import folder_source as fs
from . import whatsapp as w

DEFAULTS = {
    "posts_folder": "",
    "channels": [],
    "browser": {"channel": "chrome", "headless": False,
                "profile_dir": "profile", "offscreen": True,
                "keep_open_seconds": 0},
}

CHANNEL_DEFAULTS = {
    "name": "", "link": "", "enabled": True,
    "start": "07:15", "gap_minutes": 3, "window_minutes": 240,
}


def load_config() -> dict:
    cfg = w.load_json(w.CONFIG, {})
    out = {**DEFAULTS, **cfg}
    out["channels"] = [{**CHANNEL_DEFAULTS, **c} for c in out.get("channels", [])]
    return out


def save_config(cfg: dict) -> None:
    w.save_json(w.CONFIG, cfg)


def _hhmm(s: str, fallback=time(7, 15)) -> time:
    try:
        h, m = str(s).split(":")
        return time(int(h), int(m))
    except Exception:
        return fallback


def channel_id(ch: dict) -> str:
    """A stable key for the ledger. The name is what the user typed, so use it."""
    return (ch.get("name") or "channel").strip().lower().replace(" ", "-")


def due_now(ch: dict, now: datetime | None = None) -> tuple[bool, str]:
    """
    Is this channel's window open?

    A window rather than an instant, because the computer may have been asleep
    at the exact minute. Miss 07:15 but be awake by 10:00 and the day still goes
    out; past the window it is skipped rather than posted at a strange hour.
    """
    now = now or datetime.now()
    start = datetime.combine(now.date(), _hhmm(ch.get("start", "07:15")))
    window = int(ch.get("window_minutes", 240))
    mins = (now - start).total_seconds() / 60
    if mins < 0:
        return False, f"{int(-mins)} min before {start:%H:%M}"
    if mins > window:
        return False, f"{int(mins)} min past {start:%H:%M} — outside the {window} min window"
    return True, f"due ({int(mins)} min into the window)"


def posts_for(cfg: dict, ch: dict, day: date) -> list[fs.Post]:
    root = Path(cfg.get("posts_folder") or "")
    if not root.is_dir():
        return []
    sub = (ch.get("subfolder") or "").strip()
    return fs.read_day(root / sub if sub else root, day)


def already_sent(state: dict, cid: str, day: date) -> set[str]:
    return set(state.get("items", {}).get(cid, {}).get(day.isoformat(), []))


def mark_sent(state: dict, cid: str, day: date, key: str, caption: str) -> None:
    """
    Written only after the post is actually delivered.

    The order matters more than it looks: an earlier version recorded the send
    first, a post failed to upload, and the ledger then blocked the retry of a
    post that had never arrived.
    """
    state.setdefault("items", {}).setdefault(cid, {}).setdefault(
        day.isoformat(), []).append(key)
    state.setdefault("history", []).append(
        {"channel": cid, "date": day.isoformat(), "key": key,
         "at": datetime.now().isoformat(timespec="seconds"),
         "caption": caption[:200]})
    state["history"] = state["history"][-400:]


def forget_day(day: date) -> dict:
    """Undo a day in the ledger, for when the log says sent and the channel is empty."""
    st = w.load_json(w.STATE, {})
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    w.save_json(w.STATE.with_name(f"state.backup-{stamp}.json"), st)
    iso = day.isoformat()
    for cid, days in list(st.get("items", {}).items()):
        days.pop(iso, None)
        if not days:
            st["items"].pop(cid, None)
    st["history"] = [h for h in st.get("history", []) if h.get("date") != iso]
    w.save_json(w.STATE, st)
    return st


def plan(cfg: dict, day: date | None = None) -> list[dict]:
    """What every channel would do today — for showing the user before sending."""
    day = day or date.today()
    state = w.load_json(w.STATE, {})
    out = []
    for ch in cfg.get("channels", []):
        cid = channel_id(ch)
        posts = posts_for(cfg, ch, day)
        done = already_sent(state, cid, day)
        ok, why = due_now(ch)
        out.append({
            "name": ch.get("name", ""), "id": cid, "enabled": ch.get("enabled", True),
            "due": ok, "why": why, "total": len(posts),
            "sent": len([p for p in posts if p.key in done]),
            "remaining": len([p for p in posts if p.key not in done]),
            "lines": [
                {"time": f"{when:%H:%M}", "key": p.key, "kind": p.kind,
                 "done": p.key in done,
                 "caption": (p.caption.splitlines() or [""])[0][:80],
                 "image": p.image.name if p.image else ""}
                for when, p in fs.schedule(posts, _hhmm(ch.get("start")),
                                           int(ch.get("gap_minutes", 3)), day)
            ],
        })
    return out


def run(day: date | None = None, dry: bool = False, only: str = "",
        limit: int = 0, force: bool = False) -> int:
    """
    Do the day's work. Returns how many posts were sent.

    `force` ignores the time window — that is the "Send today's posts now"
    button. The window still applies to the scheduled runs.
    """
    day = day or date.today()
    cfg = load_config()

    if w.PAUSE.exists():
        w.log("PAUSE file present — doing nothing")
        return 0
    root = Path(cfg.get("posts_folder") or "")
    if not root.is_dir():
        w.log(f"the posts folder is not set or does not exist: {root or '(none)'}")
        return 0

    todo = []
    for ch in cfg.get("channels", []):
        if not ch.get("enabled", True):
            continue
        if only and channel_id(ch) != only and ch.get("name") != only:
            continue
        ok, why = due_now(ch)
        if not (ok or force or dry):
            w.log(f"{ch['name']}: {why}, skipping")
            continue
        todo.append(ch)
    if not todo:
        w.log("nothing due right now — exiting without opening a browser")
        return 0

    state = w.load_json(w.STATE, {})
    sent = 0

    if dry:
        for ch in todo:
            for line in fs.describe(root, day, _hhmm(ch.get("start")),
                                    int(ch.get("gap_minutes", 3))).splitlines():
                w.log(f"{ch['name']}: {line}")
        w.log("DRY RUN — nothing was sent")
        return 0

    with w.Lock():
        pw, ctx, page = w.open_browser(cfg)
        try:
            w.open_whatsapp(page)
            for ch in todo:
                cid = channel_id(ch)
                posts = [p for p in posts_for(cfg, ch, day)
                         if p.key not in already_sent(state, cid, day)]
                if limit:
                    posts = posts[:limit]
                if not posts:
                    w.log(f"{ch['name']}: nothing left for today")
                    continue

                gap = int(ch.get("gap_minutes", 3)) * 60
                for n, post in enumerate(posts, 1):
                    # Every post, every time. Not once per run.
                    w.open_channel(page, ch["name"], ch.get("link", ""))
                    w.require_channel(page, ch["name"])
                    w.log(f"{ch['name']}: [{n}/{len(posts)}] {post.kind} — {post.key}")
                    w.attach_and_caption(page, post.image, post.caption)
                    w.press_send(page)

                    mark_sent(state, cid, day, post.key, post.caption)
                    w.save_json(w.STATE, state)      # after delivery, never before
                    sent += 1
                    w.log(f"{ch['name']}: sent {n}/{len(posts)} ({post.key})")

                    if n < len(posts):
                        wait = gap + random.randint(-15, 15)
                        w.log(f"{ch['name']}: waiting {wait}s before the next one")
                        _time.sleep(max(30, wait))
        finally:
            _time.sleep(5)   # never yank the window shut on an upload
            ctx.close()
            pw.stop()
    return sent
