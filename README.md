# Qasid — قاصد

**Post to your own WhatsApp Channel every day, from a folder on your own computer.**

You put pictures and text into dated folders. Qasid posts them, one at a time, at
the times you choose. It runs on your machine, using your own already-signed-in
WhatsApp Web session. Nothing is uploaded to anyone else's server, and nobody
else's server is involved.

---

## ⚠️ Read this before you install it

**Automating WhatsApp Web is against WhatsApp's Terms of Service. Your account
can be banned for it — temporarily or permanently.**

This is not a theoretical risk and there is no safe way around it:

- WhatsApp has **no official API for personal Channels**. The WhatsApp Business
  Platform does not cover them. So any tool that posts to a Channel for you —
  this one included — is unofficial, and WhatsApp is under no obligation to
  tolerate it.
- Qasid drives a real browser as a linked device, which is much closer to normal
  use than a bulk-sending API, and it deliberately posts slowly. That reduces the
  risk. It does not remove it.
- **Do not use this on a number you cannot afford to lose.** Not your only
  number, not a business number your livelihood depends on.

If that is not acceptable to you, stop here. That is a completely reasonable
decision, and this README would rather you make it now than after a ban.

**What Qasid will not do,** whatever anyone asks for later: send to lists of
strangers, scrape contacts, post to groups you were added to, or run as a hosted
service where your WhatsApp session lives on somebody else's computer. It posts
your own material to your own channel from your own machine. That is the whole
scope.

---

## How it works

You keep a folder. Qasid reads it.

```
MyPosts/
  2026-09-04/
      1.jpg
      1.txt          <- the caption for 1.jpg
      2.jpg
      2.txt
  2026-09-05/
      1.jpg
      1.txt
```

- One folder per date, named `YYYY-MM-DD`. Qasid posts the folder whose name is
  today's date, and ignores the rest.
- A picture and a `.txt` **with the same name** go out together: the picture with
  that text as its caption.
- A picture with no `.txt` is posted on its own.
- A `.txt` with no picture is posted as a plain text message.
- Posts go in filename order, starting at the time you set, with a gap between
  each one.

**To give one post its own time,** start its filename with the time:

```
      07-15 hamal.jpg
      07-15 hamal.txt
```

Anything else in the folder — notes, spare files, subfolders — is ignored.

## Installing

You need Python 3.10 or newer, and Google Chrome.

```
git clone https://github.com/farooqmusicai/qasid.git
cd qasid
python -m pip install -r requirements.txt
python -m playwright install chromium
```

Then start it:

- **Windows:** double-click `START.bat`
- **macOS / Linux:** `./start.sh`

Your browser opens at `http://127.0.0.1:8770`. From there you:

1. Choose your posts folder
2. Add your channel — the name exactly as it appears in WhatsApp
3. Sign in once by scanning a QR code, exactly like WhatsApp Web on a new computer
4. Press **Send today's posts now** to try it
5. Turn on the daily schedule once you have seen it work

## Where your things live

| What | Where | Leaves your computer? |
|---|---|---|
| Your pictures and text | the folder you chose | no |
| Your WhatsApp session | `profile/` | **no — never** |
| What has already been sent | `state.json` | no |
| Logs | `logs/` | no |

`profile/` is your WhatsApp login. Treat it like a password: do not copy it
anywhere, do not put it in a backup you share, and do not commit it. It is in
`.gitignore` already.

The web page is bound to `127.0.0.1`, which means only your own computer can
reach it. It is not on your network and not on the internet.

## The computer has to be awake

Qasid posts by driving a browser, so the machine must be switched on and not
asleep at posting time. It checks every 15 minutes and each channel has a window
of a few hours, so a late start still goes out — but a sleeping computer posts
nothing.

## Licence

MIT. See [LICENSE](LICENSE).

## Credit

Built by **Mohammad Farooq** ([@farooqmusicai](https://github.com/farooqmusicai)),
out of a working tool that posts daily to the
[farooqstars.com](https://farooqstars.com) and
[farooqmusic.com](https://farooqmusic.com) channels.

Most of what looks over-careful in `qasid/whatsapp.py` — waiting for an upload
that already said it was sent, checking the channel before every single post,
refusing the file input that is sitting right there — is not caution for its own
sake. Each one is a thing that went wrong in front of a real audience, and the
comments say which.
