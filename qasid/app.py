"""
The local web page.

Bound to 127.0.0.1 and nothing else. This is not a detail to be relaxed later
for convenience: the page can start a browser that is signed in to the user's
WhatsApp, so anything that can reach the page can post as them. On 0.0.0.0 that
would be everyone on their café wifi.

There is no login screen here, and that is the correct design — the only person
who can reach 127.0.0.1 is the person sitting at the machine.
"""

from __future__ import annotations

import threading
import webbrowser
from datetime import date
from pathlib import Path

from flask import Flask, jsonify, redirect, request

from . import engine
from . import folder_source as fs
from . import whatsapp as w

app = Flask(__name__)
_running: dict = {"busy": False, "what": "", "lines": []}


def _say(msg: str) -> None:
    _running["lines"].append(msg)
    del _running["lines"][:-400]


def _background(what: str, fn) -> bool:
    """One job at a time. Two browsers on one WhatsApp session fight each other."""
    if _running["busy"]:
        return False
    _running.update(busy=True, what=what, lines=[f"— {what} —"])

    def wrap():
        original = w.log
        try:
            w.log = lambda m: (_say(str(m)), original(m))[1]     # tee to the page
            fn()
        except Exception as e:
            _say(f"STOPPED: {e}")
        finally:
            w.log = original
            _running.update(busy=False)

    threading.Thread(target=wrap, daemon=True).start()
    return True


PAGE = """<!doctype html><html><head><meta charset="utf-8">
<title>Qasid</title><meta name="viewport" content="width=device-width,initial-scale=1">
<style>
 :root{--ink:#1a1a1a;--dim:#6b6b6b;--line:#e2e2e2;--bg:#fbfaf8;--card:#fff;
       --go:#1c7c4a;--warn:#8a5a00;--stop:#a12c2c}
 *{box-sizing:border-box}
 body{margin:0;background:var(--bg);color:var(--ink);font:15px/1.55 system-ui,Segoe UI,sans-serif}
 .wrap{max-width:860px;margin:0 auto;padding:28px 20px 80px}
 h1{font-size:26px;margin:0 0 2px} h1 small{font-weight:400;color:var(--dim);font-size:15px}
 h2{font-size:15px;text-transform:uppercase;letter-spacing:.07em;color:var(--dim);
    margin:30px 0 10px;font-weight:600}
 .card{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:18px;margin-bottom:14px}
 label{display:block;font-weight:600;margin:12px 0 4px;font-size:14px}
 input[type=text],input[type=time],input[type=number]{width:100%;padding:9px 11px;
   border:1px solid var(--line);border-radius:7px;font:inherit;background:#fff}
 .row{display:flex;gap:12px;flex-wrap:wrap} .row>div{flex:1;min-width:130px}
 button{font:inherit;font-weight:600;padding:10px 16px;border-radius:8px;
   border:1px solid var(--line);background:#fff;cursor:pointer}
 button.go{background:var(--go);border-color:var(--go);color:#fff}
 button:disabled{opacity:.5;cursor:not-allowed}
 .hint{color:var(--dim);font-size:13.5px;margin:6px 0 0}
 .warn{background:#fdf6e7;border:1px solid #f0dfb5;border-radius:10px;padding:14px 16px;
   margin-bottom:20px;font-size:14px;color:#5c4200}
 .warn b{color:var(--warn)}
 table{width:100%;border-collapse:collapse;font-size:14px}
 td,th{text-align:left;padding:6px 8px;border-bottom:1px solid var(--line);vertical-align:top}
 th{color:var(--dim);font-weight:600;font-size:12.5px;text-transform:uppercase}
 .done{color:var(--dim)} .done td{text-decoration:line-through}
 pre{background:#14161a;color:#dfe4ea;padding:14px;border-radius:9px;overflow:auto;
   max-height:340px;font:12.5px/1.5 ui-monospace,Consolas,monospace;white-space:pre-wrap}
 .pill{display:inline-block;padding:2px 9px;border-radius:99px;font-size:12.5px;font-weight:600}
 .pill.on{background:#e6f4ec;color:var(--go)} .pill.off{background:#f2f2f2;color:var(--dim)}
 .chan{border-top:1px solid var(--line);padding-top:14px;margin-top:14px}
 .chan:first-child{border-top:0;padding-top:0;margin-top:0}
 .del{color:var(--stop);border-color:#eccfcf;background:#fff}
</style></head><body><div class="wrap">
<h1>Qasid <small>قاصد</small></h1>
<p class="hint">Posts your own folder to your own WhatsApp channel, from this computer.</p>

<div class="warn">
<b>Before you rely on this:</b> automating WhatsApp Web is against WhatsApp's terms,
and accounts can be banned for it. There is no official API for Channels, so there is
no safe alternative — only the choice of whether to accept the risk.
Do not use a number you cannot afford to lose.
</div>

<div id="app">Loading…</div>

<script>
const $ = s => document.querySelector(s);
let S = null;

async function load(){ S = await (await fetch('/api/state')).json(); draw(); }
async function post(url, body){
  const r = await fetch(url, {method:'POST', headers:{'Content-Type':'application/json'},
                              body: JSON.stringify(body||{})});
  return r.json();
}

function esc(s){ return (s||'').replace(/[<>&]/g, c=>({'<':'&lt;','>':'&gt;','&':'&amp;'}[c])); }

function draw(){
  const c = S.config, busy = S.busy;
  let h = '';

  h += `<h2>1 · Your posts folder</h2><div class="card">
    <input type="text" id="folder" value="${esc(c.posts_folder)}"
           placeholder="D:\\\\MyPosts  —  the folder with your dated subfolders">
    <p class="hint">Inside it, one folder per date: <code>2026-09-04</code>.
       A picture and a <code>.txt</code> of the same name go out together.</p>
    <p style="margin:12px 0 0"><button onclick="saveFolder()">Save folder</button></p>
    ${S.folder_note ? `<p class="hint">${esc(S.folder_note)}</p>` : ''}
  </div>`;

  h += `<h2>2 · Your channels</h2><div class="card">`;
  if(!c.channels.length) h += `<p class="hint">No channel yet. Add one below.</p>`;
  c.channels.forEach((ch,i)=>{
    h += `<div class="chan"><div class="row">
      <div><label>Channel name (exactly as WhatsApp shows it)</label>
        <input type="text" value="${esc(ch.name)}" onchange="edit(${i},'name',this.value)"></div>
      <div><label>Starts at</label>
        <input type="time" value="${esc(ch.start)}" onchange="edit(${i},'start',this.value)"></div>
      <div><label>Gap (minutes)</label>
        <input type="number" min="1" max="120" value="${ch.gap_minutes}"
               onchange="edit(${i},'gap_minutes',+this.value)"></div>
    </div>
    <label>Invite link (optional — helps Qasid find the channel)</label>
    <input type="text" value="${esc(ch.link||'')}" onchange="edit(${i},'link',this.value)">
    <p style="margin:10px 0 0"><button class="del" onclick="delChan(${i})">Remove this channel</button></p>
    </div>`;
  });
  h += `<p style="margin:14px 0 0"><button onclick="addChan()">Add a channel</button></p></div>`;

  h += `<h2>3 · Sign in to WhatsApp</h2><div class="card">
    <p class="hint">Opens a browser window with a QR code. Scan it once with your phone:
       WhatsApp → Settings → Linked devices. Your login stays on this computer.</p>
    <p style="margin:12px 0 0"><button onclick="act('/api/login')" ${busy?'disabled':''}>
      Show the QR code</button></p></div>`;

  h += `<h2>4 · Today</h2><div class="card">`;
  if(!S.plan.length) h += `<p class="hint">Add a channel to see today's plan.</p>`;
  S.plan.forEach(p=>{
    h += `<div class="chan"><p style="margin:0 0 8px"><b>${esc(p.name)}</b>
      <span class="pill ${p.due?'on':'off'}">${p.due?'due now':esc(p.why)}</span>
      <span class="hint"> ${p.sent} sent, ${p.remaining} to go</span></p>`;
    if(p.lines.length){
      h += `<table><tr><th>Time</th><th>What</th><th>Caption</th></tr>`;
      p.lines.forEach(l=>{ h += `<tr class="${l.done?'done':''}"><td>${l.time}</td>
        <td>${esc(l.image||l.key)}</td><td>${esc(l.caption)}</td></tr>`; });
      h += `</table>`;
    } else h += `<p class="hint">Nothing in the folder for today's date.</p>`;
    h += `</div>`;
  });
  h += `<p style="margin:14px 0 0">
    <button class="go" onclick="act('/api/run')" ${busy?'disabled':''}>Send today's posts now</button>
    <button onclick="act('/api/dry')" ${busy?'disabled':''}>Check only, send nothing</button>
    <button onclick="act('/api/forget')" ${busy?'disabled':''}>Forget today</button>
    </p></div>`;

  h += `<h2>What it is doing</h2><div class="card">
    <pre id="log">${esc(S.lines.join('\\n')) || 'Nothing yet.'}</pre>
    ${busy ? `<p class="hint">Working: ${esc(S.what)} — this page updates itself.</p>` : ''}
  </div>`;

  $('#app').innerHTML = h;
}

async function saveFolder(){ await post('/api/folder',{folder:$('#folder').value}); load(); }
async function edit(i,k,v){ await post('/api/channel',{index:i,key:k,value:v}); load(); }
async function addChan(){ await post('/api/channel/add'); load(); }
async function delChan(i){ if(confirm('Remove this channel from Qasid?')){
  await post('/api/channel/del',{index:i}); load(); } }
async function act(url){ await post(url); load(); }

load();
setInterval(async ()=>{
  const s = await (await fetch('/api/state')).json();
  const wasBusy = S && S.busy;
  S = s;
  if(s.busy || wasBusy) draw();
}, 1500);
</script></div></body></html>"""


@app.route("/")
def index():
    return PAGE


@app.route("/api/state")
def api_state():
    cfg = engine.load_config()
    note = ""
    root = Path(cfg.get("posts_folder") or "")
    if cfg.get("posts_folder"):
        if not root.is_dir():
            note = "That folder does not exist yet."
        else:
            days = fs.available_days(root)
            note = (f"{len(days)} date folder(s) found — "
                    f"{days[0]} to {days[-1]}." if days else
                    "No date folders inside yet. Make one named like 2026-09-04.")
    return jsonify({
        "config": cfg,
        "plan": engine.plan(cfg),
        "busy": _running["busy"],
        "what": _running["what"],
        "lines": _running["lines"],
        "folder_note": note,
    })


@app.route("/api/folder", methods=["POST"])
def api_folder():
    cfg = engine.load_config()
    cfg["posts_folder"] = (request.json or {}).get("folder", "").strip()
    engine.save_config(cfg)
    return jsonify(ok=True)


@app.route("/api/channel", methods=["POST"])
def api_channel():
    d = request.json or {}
    cfg = engine.load_config()
    i = int(d.get("index", -1))
    if 0 <= i < len(cfg["channels"]):
        cfg["channels"][i][d["key"]] = d["value"]
        engine.save_config(cfg)
    return jsonify(ok=True)


@app.route("/api/channel/add", methods=["POST"])
def api_channel_add():
    cfg = engine.load_config()
    cfg["channels"].append(dict(engine.CHANNEL_DEFAULTS))
    engine.save_config(cfg)
    return jsonify(ok=True)


@app.route("/api/channel/del", methods=["POST"])
def api_channel_del():
    cfg = engine.load_config()
    i = int((request.json or {}).get("index", -1))
    if 0 <= i < len(cfg["channels"]):
        cfg["channels"].pop(i)
        engine.save_config(cfg)
    return jsonify(ok=True)


@app.route("/api/run", methods=["POST"])
def api_run():
    ok = _background("sending today's posts", lambda: engine.run(force=True))
    return jsonify(started=ok)


@app.route("/api/dry", methods=["POST"])
def api_dry():
    ok = _background("checking", lambda: engine.run(dry=True))
    return jsonify(started=ok)


@app.route("/api/forget", methods=["POST"])
def api_forget():
    engine.forget_day(date.today())
    _say("Today's record cleared — the posts can be sent again.")
    return jsonify(ok=True)


@app.route("/api/login", methods=["POST"])
def api_login():
    def job():
        cfg = engine.load_config()
        # Visible on purpose: a QR code pushed off the side of the screen
        # cannot be scanned.
        pw, ctx, page = w.open_browser(cfg, offscreen=False)
        try:
            page.goto(w.wa.WHATSAPP_URL, wait_until="domcontentloaded")
            w.log("Scan the QR code with your phone: WhatsApp → Settings → Linked devices.")
            import time as t
            end = t.time() + 300
            while t.time() < end:
                if w.any_present(page, w.wa.LOGGED_IN):
                    w.log("Signed in. Your login is saved on this computer.")
                    t.sleep(3)
                    return
                t.sleep(2)
            w.log("Five minutes passed without a sign-in — try again when ready.")
        finally:
            ctx.close()
            pw.stop()
    return jsonify(started=_background("waiting for the QR scan", job))


def main(port: int = 8770, open_browser_window: bool = True) -> None:
    url = f"http://127.0.0.1:{port}"
    print(f"\n  Qasid is running at {url}")
    print("  Leave this window open. Close it to stop Qasid.\n")
    if open_browser_window:
        threading.Timer(1.0, lambda: webbrowser.open(url)).start()
    # host is not configurable, and that is on purpose — see the note at the top.
    app.run(host="127.0.0.1", port=port, debug=False, use_reloader=False)


if __name__ == "__main__":
    main()
