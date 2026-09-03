"""
Driving WhatsApp Web.

This file is not new work. It is the browser layer of a tool that has been
posting daily to two real channels, and every awkward-looking line in it is the
scar of something that went wrong in front of a real audience:

  * attach_image      — the only file input present at rest is the STICKER one.
    Using it posts a sticker, stickers have no caption field, and the caption
    then escapes into the channel as a separate message. The photo input only
    exists after Attach > "Photos & videos" is clicked, and that opens the
    operating system's file dialog, which is why the click is wrapped in
    Playwright's file-chooser interception.

  * FOCUS_CAPTION_JS  — the media dialog's caption box is labelled "Type an
    update". The channel's own box, sitting behind the dialog, is "Type a
    message to <channel>". Typing into the second one splits every post in two.

  * wait_for_delivery — the dialog closing means WhatsApp ACCEPTED the post, not
    that it sent it. The upload runs afterwards. Close the browser in that
    window and the post dies silently while the log says SENT.

  * require_channel   — called before every single post, not once per run. A
    horoscope card once landed in a music channel because the app moved during
    a three-minute gap, and a post in the wrong channel cannot be recalled.

None of this can be simplified by reading it and thinking it looks redundant.
It looked redundant before, too.
"""

from __future__ import annotations

import json
import os
import random
import shutil
import sys
import time
from datetime import date, datetime
from pathlib import Path

from . import wa_selectors as wa   # not "wa" — it must not shadow anything

HERE = Path(os.environ.get("QASID_HOME", Path(__file__).resolve().parents[1]))
CONFIG = HERE / "config.json"
STATE = HERE / "state.json"
PAUSE = HERE / "PAUSE"
LOCK = HERE / "run.lock"
LOGS = HERE / "logs"
PROOF = HERE / "proof"
WORK = HERE / "work"
PROBE = HERE / "probe"

LOCK_STALE_SECONDS = 3600
LIMIT: int = 0
_DIALOG_SEND: str | None = None


def log(msg: str) -> None:
    line = f"{datetime.now():%Y-%m-%d %H:%M:%S}  {msg}"
    print(line, flush=True)
    LOGS.mkdir(exist_ok=True)
    with (LOGS / f"{date.today():%Y-%m}.log").open("a", encoding="utf-8") as f:
        f.write(line + "\n")


def die(msg: str, code: int = 1):
    log(f"STOP: {msg}")
    sys.exit(code)


def load_json(path: Path, default):
    if not path.is_file():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception as e:
        die(f"{path.name} is not valid JSON — {e}")


def save_json(path: Path, data) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)


def first_visible(page, candidates, timeout=8000, **fmt):
    """Return the first selector in the list that actually resolves."""
    deadline = time.time() + timeout / 1000
    tried = []
    while time.time() < deadline:
        for sel in candidates:
            s = sel.format(**fmt) if fmt else sel
            tried.append(s)
            try:
                loc = page.locator(s).first
                if loc.count() and loc.is_visible():
                    return loc
            except Exception:
                continue
        page.wait_for_timeout(400)
    raise RuntimeError("none of these matched: " + " | ".join(dict.fromkeys(tried)))


def any_present(page, candidates) -> bool:
    for sel in candidates:
        try:
            if page.locator(sel).first.count():
                return True
        except Exception:
            continue
    return False


def _pid_alive(pid: int):
    """True / False, or None when we genuinely cannot tell."""
    if not pid or pid <= 0:
        return None
    if os.name == "nt":
        try:
            import ctypes
            QUERY_LIMITED, STILL_ACTIVE = 0x1000, 259
            k = ctypes.windll.kernel32
            handle = k.OpenProcess(QUERY_LIMITED, False, pid)
            if not handle:
                return False
            code = ctypes.c_ulong()
            ok = k.GetExitCodeProcess(handle, ctypes.byref(code))
            k.CloseHandle(handle)
            return (code.value == STILL_ACTIVE) if ok else None
        except Exception:
            return None
    try:
        os.kill(pid, 0)          # signal 0 is a safe liveness probe on POSIX only
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except Exception:
        return None


class Lock:
    """
    Stops two runs overlapping — but never stands in the way of a run whose
    owner is gone. A crashed or force-closed run used to leave a lock that
    blocked everything for an hour; now the recorded process is checked first.
    """

    def __enter__(self):
        if LOCK.is_file():
            age = time.time() - LOCK.stat().st_mtime
            try:
                owner = json.loads(LOCK.read_text(encoding="utf-8")).get("pid", 0)
            except Exception:
                owner = 0
            alive = _pid_alive(owner)
            if alive is True:
                # Never clear a lock whose owner is still running, however old it
                # is: a 12-card run legitimately holds the lock for half an hour.
                die(f"another run (process {owner}) is still going, started {int(age)}s ago")
            elif alive is False:
                log(f"clearing a lock left by run {owner}, which is no longer running")
            elif age < LOCK_STALE_SECONDS:
                die(f"another run started {int(age)}s ago — wait, or delete {LOCK.name}")
            else:
                log(f"clearing a stale lock ({int(age)}s old)")
        LOCK.write_text(json.dumps({"pid": os.getpid(),
                                    "started": datetime.now().isoformat(timespec="seconds")}),
                        encoding="utf-8")
        return self

    def __exit__(self, *exc):
        LOCK.unlink(missing_ok=True)


def open_browser(cfg: dict, headless_override=None, offscreen: bool = True):
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        die("Playwright is not installed — run SETUP.bat (or: pip install playwright)")

    b = cfg.get("browser", {})
    profile = HERE / b.get("profile_dir", "profile")
    profile.mkdir(exist_ok=True)
    headless = b.get("headless", False) if headless_override is None else headless_override

    pw = sync_playwright().start()
    kwargs = dict(
        user_data_dir=str(profile),
        headless=headless,
        viewport={"width": 1280, "height": 900},
        args=["--no-first-run", "--no-default-browser-check"],
    )
    # Twelve star cards three minutes apart is forty minutes of browser window
    # sitting in front of whatever you are actually doing. Moving it far off the
    # desktop keeps it running normally — the page still renders, uploads still
    # finish — while staying out of the way. Headless is deliberately NOT used:
    # WhatsApp Web behaves differently without a real window, and this finally
    # works. Set "offscreen": false in channels.json to watch a run.
    # ...but never when you need to SEE the window: scanning the QR code off the
    # side of the desktop is impossible, and a probe is for looking at.
    if offscreen and b.get("offscreen", True) and not headless:
        kwargs["args"] += ["--window-position=-32000,-32000"]
    if b.get("channel"):
        kwargs["channel"] = b["channel"]
    try:
        ctx = pw.chromium.launch_persistent_context(**kwargs)
    except Exception as e:
        if "channel" in kwargs:
            log(f"Chrome not available ({e}) — falling back to bundled Chromium")
            kwargs.pop("channel")
            ctx = pw.chromium.launch_persistent_context(**kwargs)
        else:
            raise
    page = ctx.pages[0] if ctx.pages else ctx.new_page()
    # Short on purpose: a click blocked by an overlay is not going to succeed on
    # the thirtieth retry, and a fast failure leaves a useful log instead of a
    # wall of "retrying click action".
    page.set_default_timeout(15000)
    return pw, ctx, page


def dismiss_interstitials(page, rounds: int = 4) -> int:
    """
    Close any 'What's new on WhatsApp Web' / announcement dialog sitting on top
    of the app. A fresh Chrome profile always gets one, and it silently blocks
    every click underneath it. Safe to call at any time: if nothing is there,
    it does nothing.
    """
    closed = 0
    for _ in range(rounds):
        hit = False
        for sel in wa.INTERSTITIAL_DISMISS + wa.INTERSTITIAL_CLOSE:
            try:
                loc = page.locator(sel).first
                if loc.count() and loc.is_visible():
                    loc.click(timeout=3000)
                    page.wait_for_timeout(1200)
                    closed += 1
                    hit = True
                    log(f"dismissed a WhatsApp dialog ({sel})")
                    break
            except Exception:
                continue
        if not hit:
            break
    return closed


def open_whatsapp(page, wait_seconds=60):
    log("opening WhatsApp Web …")
    page.goto(wa.WHATSAPP_URL, wait_until="domcontentloaded")
    deadline = time.time() + wait_seconds
    while time.time() < deadline:
        if any_present(page, wa.LOGGED_IN):
            log("WhatsApp Web is loaded and signed in")
            dismiss_interstitials(page)
            return True
        if any_present(page, wa.NEEDS_LOGIN):
            return False
        page.wait_for_timeout(1000)
    raise RuntimeError("WhatsApp Web did not finish loading in time")


OPEN_CHANNEL_JS = """
() => {
  // Every header on the page, not the first one. The first is the LEFT PANE's
  // title — "Updates in Status" — which has nothing to do with the open
  // conversation, and reading it turned the wrong-channel guard into a guard
  // that blocked correct posts.
  const line = el => (el.innerText || '').trim().split('\\n')[0].trim();
  const out = [];

  // Strongest signal of all, and the one the 19:05 probe handed us: the
  // message box spells out where it will send — "Type a message to FarooqStars".
  // It belongs to the open conversation and to nothing else.
  for (const e of document.querySelectorAll('[contenteditable="true"], [aria-label]')) {
    const a = e.getAttribute('aria-label') || '';
    if (/^type a message to /i.test(a))
      out.push({ text: a.replace(/^type a message to /i, '').trim(), from: 'composer' });
  }

  const main = document.querySelector('#main');
  const conv = main && main.querySelector('header');
  if (conv) out.push({ text: line(conv), from: 'conversation' });
  for (const h of document.querySelectorAll('header')) {
    const t = line(h);
    if (t && t.length < 60 && !out.some(o => o.text === t))
      out.push({ text: t, from: 'other' });
  }
  return out;
}
"""


def require_channel(page, name: str) -> None:
    """
    Refuse to post until the open conversation really is the intended channel.

    Written the moment a Taurus horoscope card appeared in FarooqMusic,
    underneath a song, because the channel was opened once and then trusted for
    the rest of the run. A post in the wrong channel cannot be taken back from
    the followers who already saw it, so this checks every single time.
    """
    try:
        heads = page.evaluate(OPEN_CHANNEL_JS) or []
    except Exception:
        heads = []

    # The channel's name has to appear in SOME header. When the right channel is
    # open its header carries the name; when the wrong one is open, no header
    # does — the other channel's name is there instead. That holds without
    # having to know which header WhatsApp will render where.
    for h in heads:
        if name.lower() in (h.get("text") or "").lower():
            if h.get("from") != "conversation":
                log(f'  channel confirmed by the "{h["text"]}" header')
            return

    seen = ", ".join(f'"{h.get("text")}"' for h in heads) or "nothing"
    dump_diagnostics(page, "wrong-channel")
    raise RuntimeError(
        f'"{name}" is not the open channel — the page shows {seen}. Refusing to '
        "send it to the wrong audience. See probe/")


def open_channel(page, name: str, link: str = "") -> None:
    """
    Open the channel.

    Route 1 is the Channels tab + search by name. This is the route that was
    proven to work on 1 Sep 2026 — it opened FarooqStars and attached the card.
    Do not demote it.

    Route 2, the invite link, is a FALLBACK only. Navigating to
    web.whatsapp.com/channel/<code> reloads the whole app, and if it does not
    land on the channel the reload has to be undone — which looks like the
    window closing and reopening. So it is tried only when the search fails.
    """
    try:
        first_visible(page, wa.CHANNELS_TAB, timeout=6000).click()
        page.wait_for_timeout(1500)
        log(f"channels tab opened")
    except Exception as e:
        log(f"note: could not click the Channels tab ({e}) — trying search anyway")

    try:
        row = first_visible(page, wa.CHANNEL_ROW, timeout=4000, name=name)
    except Exception:
        box = first_visible(page, wa.SEARCH_BOX, timeout=8000)
        box.click()
        page.keyboard.press("Control+A")
        box.type(name, delay=60)
        page.wait_for_timeout(1800)
        row = first_visible(page, wa.CHANNEL_ROW, timeout=8000, name=name)

    try:
        row.click(timeout=8000)
    except Exception:
        row.click(force=True, timeout=8000)     # overlay in the way — go through it
    page.wait_for_timeout(1800)
    log(f"channel open: {name}")


COMPOSER_PROBE_JS = """
() => {
  const vis = e => { const r = e.getBoundingClientRect();
                     return r.width > 40 && r.height > 40; };
  const blobs = [...document.querySelectorAll('img[src^="blob:"], video[src^="blob:"]')]
                  .filter(vis);
  let send = null;
  for (const e of document.querySelectorAll('[data-icon], [aria-label], button')) {
    const d = (e.getAttribute('data-icon') || '').toLowerCase();
    const a = (e.getAttribute('aria-label') || '').toLowerCase();
    if (d.includes('send') || a === 'send' || a.startsWith('send')) { send = d || a; break; }
  }
  const eds = [...document.querySelectorAll('[contenteditable="true"]')].filter(vis);
  return { blob: blobs.length, send: send, editables: eds.length };
}
"""


def composer_state(page) -> dict:
    try:
        return page.evaluate(COMPOSER_PROBE_JS)
    except Exception:
        return {"blob": 0, "send": None, "editables": 0}


DELIVERY_JS = """
() => {
  // Status ticks on outgoing messages: msg-time is the little clock, meaning
  // "not off this machine yet". The checks mean the server has it.
  const q = s => document.querySelectorAll(s).length;
  return { pending: q('[data-icon="msg-time"]') + q('[data-icon^="msg-time"]'),
           sent:    q('[data-icon="msg-check"]') + q('[data-icon="msg-dblcheck"]'),
           failed:  q('[data-icon="msg-error"]') + q('[data-icon^="msg-error"]') };
}
"""


def wait_for_delivery(page, seconds: int = 120) -> None:
    """
    Do not close the browser until the photo has actually gone up.

    The media dialog closes the instant WhatsApp accepts the post — the upload
    then runs in the background, and the message sits in the channel wearing a
    clock. Kill the browser during that window and the post dies with it: this
    is the 18:19 run, whose log read a flawless "SENT" while the channel stayed
    empty. The earlier posts that did arrive only survived because failed retry
    loops happened to keep the browser alive long enough.

    So the honest end of a send is the clock turning into a tick.
    """
    deadline = time.time() + seconds
    last = None
    while time.time() < deadline:
        try:
            st = page.evaluate(DELIVERY_JS)
        except Exception:
            break
        if st.get("failed"):
            dump_diagnostics(page, "delivery-failed")
            raise RuntimeError("WhatsApp marked the post as failed to send — see probe/")
        if not st.get("pending"):
            if not st.get("sent"):
                # No clock, but no tick either — the status icons in channels
                # are not the ones this looks for, so the reading is worthless
                # rather than good news. The 18:30 post went out on the settle
                # delay alone; do not let a bigger photo or a slower line fall
                # through the same gap unattended at six in the morning.
                log("no status icons to read — waiting a fixed 15s for the upload")
                page.wait_for_timeout(15000)
                return
            log(f"SENT — upload finished ({st['sent']} ticks on the page)")
            page.wait_for_timeout(2000)          # let the socket settle
            return
        if st != last:
            log(f"  uploading … {st['pending']} still pending")
            last = st
        page.wait_for_timeout(1000)

    dump_diagnostics(page, "upload-stuck")
    raise RuntimeError(
        f"the post was still uploading after {seconds}s — it may not have left "
        "this machine. Check the channel before running again, see probe/")


def dialog_open(page) -> bool:
    """
    Is the media dialog still up?

    Not by counting blob images. A photo that has already been posted is ALSO
    rendered from a blob: URL in the message list, so that count never returns
    to zero once anything has been sent. On 1 Sep this reported "did NOT send"
    for a post sitting in the channel — the worst kind of wrong, because a
    retry on top of it would have posted the song twice.

    The send control is the honest signal: it exists only while the dialog is
    up. The 14:36 log caught the transition exactly — "send 1 selected" one
    moment, "no send control to aim at" the next, and the photo was away.

    Rather than guess at WhatsApp's wording, remember what the control was
    called at the moment the dialog opened (when we know it was open) and watch
    for that same one to go. Self-calibrating, so a rename cannot fool it.
    """
    now = composer_state(page).get("send")
    if not now:
        return False
    return now == _DIALOG_SEND if _DIALOG_SEND else True


def wait_for_media_dialog(page, seconds: int = 25) -> bool:
    """
    Wait for the media composer.

    Detection is deliberately NOT selector-based. WhatsApp renames its CSS
    hooks freely, and on 1 Sep 2026 the composer was plainly on screen — card
    visible, send button visible — while every selector we had missed it.

    What does not change: once a file is attached, WhatsApp renders it from a
    blob: URL, and a send control appears. Either is proof enough.
    """
    deadline = time.time() + seconds
    while time.time() < deadline:
        st = composer_state(page)
        if st.get("blob") or st.get("send"):
            return True
        if any_present(page, wa.MEDIA_DIALOG):
            return True
        page.wait_for_timeout(500)
    return False


def dump_diagnostics(page, tag: str) -> Path:
    """Write what the page actually contains, so a failure explains itself."""
    PROBE.mkdir(exist_ok=True)
    path = PROBE / f"{datetime.now():%Y%m%d-%H%M%S}-{tag}.json"
    try:
        data = page.evaluate("""
        () => ({
          url: location.href,
          ariaLabels: [...new Set([...document.querySelectorAll('[aria-label]')]
                        .map(e => e.getAttribute('aria-label')))].slice(0, 150),
          dataIcons: [...new Set([...document.querySelectorAll('[data-icon]')]
                       .map(e => e.getAttribute('data-icon')))].slice(0, 150),
          testIds: [...new Set([...document.querySelectorAll('[data-testid]')]
                     .map(e => e.getAttribute('data-testid')))].slice(0, 150),
          fileInputs: [...document.querySelectorAll('input[type=file]')]
                        .map(e => ({accept: e.accept, multiple: e.multiple})),
          blobImages: document.querySelectorAll('img[src^="blob:"]').length,
          editables: [...document.querySelectorAll('[contenteditable="true"]')]
                       .map(e => e.getAttribute('aria-label') || e.dataset.tab || '?')
        })""")
        save_json(path, data)
        log(f"wrote diagnostics to {path}")
    except Exception as e:
        log(f"could not write diagnostics: {e}")
    try:
        page.screenshot(path=str(path.with_suffix(".png")))
    except Exception:
        pass
    return path


FOCUS_CAPTION_JS = """
(wantMedia) => {
  const vis = e => { const r = e.getBoundingClientRect();
                     return r.width > 60 && r.height > 10; };
  // Which box is which, settled by the 18:14 probe rather than by guessing.
  // At rest a channel has exactly one editable: "Type a message to <channel>",
  // the composer. Open the media dialog and a SECOND one appears, labelled
  // "Type an update" — that is the caption field. So "update" is the box we
  // want and "type a message" is the one that split the 14:36 post in two.
  //
  // An earlier version of this list had "type an update" down as forbidden,
  // and the guard duly threw away the only correct answer on the page.
  const GOOD = ['caption', 'update'];
  const BAD  = ['type a message', 'search'];
  const lbl = e => (e.getAttribute('aria-label') || '').toLowerCase();
  const bad = e => BAD.some(b => lbl(e).includes(b));
  const good = e => GOOD.some(g => lbl(e).includes(g));
  const eds = [...document.querySelectorAll('[contenteditable="true"]')].filter(vis);
  const take = box => { if (!box) return null; box.focus();
                        return { label: box.getAttribute('aria-label')
                                        || box.dataset.tab || 'contenteditable',
                                 text: (box.innerText || '').length }; };

  if (!wantMedia) return take(eds.filter(e => !bad(e)).pop() || eds.pop());

  // 1. The caption field by name — "Type an update".
  const named = eds.filter(good);
  if (named.length) { const r = take(named[named.length - 1]); r.how = 'label'; return r; }

  // 2. Otherwise anchor to the dialog: its preview <img src="blob:"> is inside
  //    it, so walk up to the first ancestor that also holds a usable editable.
  const previews = [...document.querySelectorAll('img[src^="blob:"]')]
                     .filter(i => i.getBoundingClientRect().width > 80);
  const preview = previews[previews.length - 1];
  if (preview) {
    for (let n = preview.parentElement, hop = 0; n && hop < 12; n = n.parentElement, hop++) {
      const c = [...n.querySelectorAll('[contenteditable="true"]')].filter(vis).filter(e => !bad(e));
      if (c.length) { const r = take(c[c.length - 1]); r.how = 'anchored'; return r; }
    }
  }
  const loose = eds.filter(e => !bad(e)).pop();
  if (!loose) return null;                     // only the channel composer left
  const r = take(loose); r.how = 'fallback'; return r;
}
"""


# Read back whatever actually has focus, rather than guessing at the page again.
# Every "wrong box" bug so far came from re-picking an element by position.
CAPTION_TEXT_JS = """
() => { const a = document.activeElement;
        return a && a.isContentEditable ? (a.innerText || '').trim().length : -1; }
"""


LIST_INPUTS_JS = """
() => [...document.querySelectorAll('input[type=file]')]
        .map(e => e.getAttribute('accept') || '')
"""


def attach_image(page, image: Path) -> None:
    """
    Attach the card through Attach ▸ "Photos & videos", and no other way.

    The 1 Sep sticker incident: the only file input present on a freshly opened
    channel has accept="image/*" — that is the *sticker* input, the one behind
    "New sticker". Attaching to it publishes a sticker, stickers have no caption
    field, and the caption then escapes into the message box and goes out as a
    separate text message. That is exactly what both channels received.

    The 14:32 probe showed the rest: clicking Attach does open the menu
    ("Photos & videos", "Camera", "Poll", "New sticker" all appear as labels)
    but mounts no new input, because the real menu item opens the operating
    system's file dialog instead. So the click has to be wrapped in Playwright's
    file-chooser interception, which answers that dialog for us.

    "New sticker" sits in the very same menu. Never click it.
    """
    def video_input():
        try:
            for i, a in enumerate(page.evaluate(LIST_INPUTS_JS)):
                if "video" in (a or "").lower():
                    return i, a
        except Exception:
            pass
        return None, None

    idx, acc = video_input()
    if idx is not None:                       # some builds expose it directly
        log(f"media input already present: input[{idx}] accept={acc[:50]}")
        page.locator('input[type="file"]').nth(idx).set_input_files(str(image))
    else:
        attach = page.locator('[aria-label="Attach"]').first
        if not attach.count():
            dump_diagnostics(page, "no-attach-button")
            raise RuntimeError("no Attach button on the page — see probe/")
        attach.click()
        page.wait_for_timeout(900)

        item = page.locator('[aria-label="Photos & videos"]').first
        try:
            item.wait_for(state="visible", timeout=8000)
        except Exception:
            dump_diagnostics(page, "no-photos-item")
            raise RuntimeError('the attach menu has no "Photos & videos" item — see probe/')

        log('attach menu open — clicking "Photos & videos"')
        try:
            with page.expect_file_chooser(timeout=20000) as chooser:
                item.click()
            chooser.value.set_files(str(image))
        except Exception as e:
            dump_diagnostics(page, "file-chooser")
            raise RuntimeError(f"the file dialog never arrived: {str(e)[:90]}")

    if not wait_for_media_dialog(page, 25):
        dump_diagnostics(page, "no-composer")
        raise RuntimeError("the media composer never appeared — see probe/")

    global _DIALOG_SEND
    _DIALOG_SEND = composer_state(page).get("send")
    log(f"attached {image.name} ({image.stat().st_size // 1024} KB) as a photo"
        + (f" — dialog send control is \"{_DIALOG_SEND}\"" if _DIALOG_SEND else ""))


CLEAR_BOX_JS = CAPTION_TEXT_JS      # both just measure the focused box


def type_caption(page, caption: str, media: bool) -> None:
    """
    Put the caption in WITHOUT clicking.

    Clicking is what broke this on 1 Sep 2026: WhatsApp lays a transparent
    layer over the composer, so Playwright refuses the click with
    "subtree intercepts pointer events" and retries for thirty seconds.

    Focusing the field through the DOM has no such problem — an overlay cannot
    intercept a .focus() call. Then the text is typed on the keyboard, which
    goes to whatever holds focus.
    """
    # The caption field is rendered a moment after the preview, so give it a
    # few seconds rather than deciding on the first frame.
    focused = None
    for _ in range(20):
        focused = page.evaluate(FOCUS_CAPTION_JS, media)
        if focused:
            break
        page.wait_for_timeout(500)
    if not focused:
        dump_diagnostics(page, "no-caption-box")
        raise RuntimeError("could not find a caption box — see probe/")

    label = (focused.get("label") or "").lower()
    if media and "type a message" in label:
        # This is the channel's own message box, not the dialog's caption field.
        # Typing here is exactly what split the 14:36 post into a photo and a
        # separate line of text. Stop instead.
        dump_diagnostics(page, "caption-box-is-composer")
        raise RuntimeError(
            f'the only box on offer was the channel composer ("{focused["label"]}"), '
            "not the photo's caption field — refusing to type, because that "
            "posts the text separately. See probe/")
    log('caption box focused ("{}" — found by {})'.format(
        focused["label"], focused.get("how", "position")))

    # Clear whatever is already in there. A draft left behind by an earlier run
    # merged with the new text on 1 Sep and two different songs went out in one
    # message. Never type into a box without emptying it first.
    stale = page.evaluate(CLEAR_BOX_JS)
    if stale and stale > 0:
        log(f"clearing {stale} characters of leftover draft")
        page.keyboard.press("Control+A")
        page.keyboard.press("Delete")
        page.wait_for_timeout(400)
        if page.evaluate(CAPTION_TEXT_JS) > 0:
            for _ in range(min(stale + 10, 400)):
                page.keyboard.press("Backspace")
            page.wait_for_timeout(300)

    for i, line in enumerate(caption.split("\n")):
        if i:
            page.keyboard.press("Shift+Enter")
        page.keyboard.type(line, delay=12)
    page.wait_for_timeout(800)

    landed = page.evaluate(CAPTION_TEXT_JS)
    if landed <= 0:
        # Focus went somewhere unexpected. force=True skips the interception
        # check that a normal click cannot get past.
        # NOT .last — that is the same "grab the last box on the page" guess
        # that put the caption in the channel composer at 14:36. Ask the same
        # anchored finder again; if it still cannot find the dialog's own box,
        # that is a real failure and belongs in the log, not in the channel.
        log("the text did not land — focusing the caption box again")
        try:
            again = page.evaluate(FOCUS_CAPTION_JS, media)
            if not again:
                raise RuntimeError("no caption box on the second attempt")
            lbl = (again.get("label") or "").lower()
            if media and any(b in lbl for b in ("type a message", "type an update")):
                raise RuntimeError(f'second attempt also landed on the composer ("{again["label"]}")')
            page.keyboard.type(caption.replace("\n", " "), delay=12)
            page.wait_for_timeout(800)
            landed = page.evaluate(CAPTION_TEXT_JS)
        except Exception as e:
            log(f"second attempt failed too: {str(e)[:90]}")
    if landed <= 0:
        dump_diagnostics(page, "caption-empty")
        raise RuntimeError("the caption would not go in — see probe/")
    log(f"caption typed ({len(caption)} chars, {landed} in the box)")


def attach_and_caption(page, image: Path | None, caption: str) -> None:
    dismiss_interstitials(page, rounds=2)
    if image:
        # A WhatsApp Web page holds several hidden file inputs (media, document,
        # profile photo, sticker). Try each media-ish one in turn and keep the
        # one that actually opens the composer, rather than assuming the first.
        attach_image(page, image)
        target = wa.CAPTION_BOX
    else:
        global _DIALOG_SEND      # forget the previous post's dialog, or a
        _DIALOG_SEND = None      # text-only post would watch for a stale button
        target = wa.COMPOSER

    if caption:
        type_caption(page, caption, media=bool(image))


FIND_SEND_JS = """
  const find = () => {
    // There can be more than one send control on the page: the media dialog's
    // and the channel composer's. Taking whichever comes first in the DOM is
    // the same coin-flip that caused today's other bugs, so collect them all
    // and prefer the dialog's — WhatsApp labels it with a count ("send 1
    // selected"), which the plain composer button never has.
    const hits = [];
    for (const e of document.querySelectorAll('[data-icon], [aria-label], button')) {
      const d = (e.getAttribute('data-icon') || '').toLowerCase();
      const a = (e.getAttribute('aria-label') || '').toLowerCase();
      if (d.includes('send') || a === 'send' || a.startsWith('send')) {
        hits.push({ el: e.closest('button, [role="button"]') || e, name: d || a });
      }
    }
    return hits.find(h => /\\d|selected/.test(h.name)) || hits[0] || null;
  };
"""


SEND_DOM_CLICK_JS = "() => {" + FIND_SEND_JS + """
  const f = find(); if (!f) return null;
  f.el.click();
  return f.name;
}"""


SEND_POINTER_JS = "() => {" + FIND_SEND_JS + """
  const f = find(); if (!f) return null;
  const r = f.el.getBoundingClientRect();
  const x = r.x + r.width / 2, y = r.y + r.height / 2;
  const opts = { bubbles: true, cancelable: true, composed: true,
                 clientX: x, clientY: y, button: 0, buttons: 1,
                 pointerId: 1, pointerType: 'mouse', isPrimary: true };
  for (const type of ['pointerover','pointerenter','pointerdown','mousedown',
                      'pointerup','mouseup','click']) {
    const Ctor = type.startsWith('pointer') ? PointerEvent : MouseEvent;
    f.el.dispatchEvent(new Ctor(type, type === 'pointerup' || type === 'mouseup'
                                       ? { ...opts, buttons: 0 } : opts));
  }
  return f.name;
}"""


def press_send(page) -> None:
    """
    Send, then PROVE it was sent.

    Two ways in, because the send button's markup keeps moving: press Enter
    (WhatsApp sends the attachment from the caption box), and if the composer
    is still up, hunt for the button and click it.

    Success is not "we clicked something". It is the composer closing — the
    blob: preview disappearing — which is what actually happens when the
    message leaves. Anything else is reported as a failure, not a send.
    """
    dismiss_interstitials(page, rounds=2)
    before = composer_state(page)
    if not (before.get("blob") or before.get("send")):
        raise RuntimeError("asked to send but the composer is not open")

    page.keyboard.press("Enter")
    page.wait_for_timeout(3000)

    if dialog_open(page):
        # No Playwright click here on purpose. The overlay that sits above the
        # composer makes a normal click impossible ("subtree intercepts pointer
        # events"). A DOM .click() is dispatched straight at the element and
        # goes through regardless of what is painted on top of it.
        log("Enter did not send it — trying a DOM click on the send control")
        try:
            hit = page.evaluate(SEND_DOM_CLICK_JS)
            log(f"DOM click on ({hit})" if hit else "no send control found in the DOM")
        except Exception as e:
            log(f"DOM click failed: {str(e)[:80]}")
        page.wait_for_timeout(3000)

    if dialog_open(page):
        # WhatsApp is React, and React components often listen for real pointer
        # events rather than a plain .click(). Synthesise the whole sequence.
        log("still open — dispatching real pointer events on the send control")
        try:
            hit = page.evaluate(SEND_POINTER_JS)
            log(f"pointer events sent to ({hit})" if hit else "no send control to aim at")
        except Exception as e:
            log(f"pointer dispatch failed: {str(e)[:80]}")
        page.wait_for_timeout(3000)

    if dialog_open(page):
        # Last resort: a real mouse, moved to the button's own coordinates.
        log("still open — moving the real mouse to the send button")
        try:
            box = page.evaluate("""
            () => {
              for (const e of document.querySelectorAll('[data-icon], [aria-label], button')) {
                const d = (e.getAttribute('data-icon') || '').toLowerCase();
                const a = (e.getAttribute('aria-label') || '').toLowerCase();
                if (d.includes('send') || a === 'send' || a.startsWith('send')) {
                  const t = e.closest('button, [role="button"]') || e;
                  const r = t.getBoundingClientRect();
                  return {x: r.x + r.width / 2, y: r.y + r.height / 2};
                }
              }
              return null;
            }""")
            if box:
                page.mouse.click(box["x"], box["y"])
                log(f"clicked the real mouse at ({int(box['x'])}, {int(box['y'])})")
            else:
                log("could not locate the send button on screen")
        except Exception as e:
            log(f"mouse click failed: {str(e)[:80]}")
        page.wait_for_timeout(3000)

    for _ in range(12):
        if not dialog_open(page):
            log("the media dialog closed — waiting for the upload to finish")
            wait_for_delivery(page)
            return
        page.wait_for_timeout(1000)

    dump_diagnostics(page, "still-open-after-send")
    raise RuntimeError("the media dialog is still open, so the post did NOT send — see probe/")


def shot(page, name: str) -> Path:
    PROOF.mkdir(exist_ok=True)
    path = PROOF / f"{date.today():%Y-%m-%d}-{name}.png"
    try:
        page.screenshot(path=str(path), full_page=False)
    except Exception as e:
        log(f"could not save a screenshot: {e}")
    return path


