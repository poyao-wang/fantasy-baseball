"""
Fantasy Baseball Dashboard — 手動觸發排程的小 web UI
跑在 Pi5 port 5001，透過 Tailscale 存取
"""

import subprocess
import threading
from flask import Flask, Response, request, stream_with_context

app = Flask(__name__)

BASE = "/home/pi/fantasy-baseball"
PYTHON = f"{BASE}/venv/bin/python3"

JOBS = {
    "weekly": {
        "label": "全量更新（週一）",
        "desc": "update_roster + update_schedule + update_stats + sync_log",
        "cmds": [
            [PYTHON, f"{BASE}/sync/update_roster.py"],
            [PYTHON, f"{BASE}/sync/update_schedule.py"],
            [PYTHON, f"{BASE}/sync/update_stats.py"],
            [PYTHON, f"{BASE}/sync/sync_log.py"],
        ],
    },
    "roster": {
        "label": "陣容同步（每日）",
        "desc": "update_roster + sync_log",
        "cmds": [
            [PYTHON, f"{BASE}/sync/update_roster.py"],
            [PYTHON, f"{BASE}/sync/sync_log.py"],
        ],
    },
    "lineup": {
        "label": "打線更新 + 自動換人（每小時）",
        "desc": "update_lineup + auto_swap + sync_log",
        "cmds": [
            [PYTHON, f"{BASE}/sync/update_lineup.py"],
            [PYTHON, f"{BASE}/sync/auto_swap.py"],
            [PYTHON, f"{BASE}/sync/sync_log.py"],
        ],
    },
}

_lock = threading.Lock()
_running = False

TRADE_CARD = """<div class="card">
  <h2>新增交易目標</h2>
  <p>add_trade_target + sync_log</p>
  <div style="display:flex;gap:8px;align-items:center;">
    <input id="trade-input" type="text" placeholder="球員姓名 or Yahoo ID"
           style="flex:1;background:#0d0d1a;color:#e0e0e0;border:1px solid #00d4ff;border-radius:4px;
                  padding:8px 12px;font-family:monospace;font-size:14px;"
           onkeydown="if(event.key==='Enter')runTrade()">
    <button onclick="runTrade()">執行</button>
  </div>
</div>"""

HTML = """<!DOCTYPE html>
<html lang="zh-Hant">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Fantasy Baseball Dashboard</title>
<style>
  body { font-family: monospace; background: #1a1a2e; color: #e0e0e0; max-width: 800px; margin: 40px auto; padding: 0 20px; }
  h1 { color: #00d4ff; margin-bottom: 8px; }
  .subtitle { color: #888; margin-bottom: 32px; font-size: 13px; }
  .card { background: #16213e; border: 1px solid #0f3460; border-radius: 8px; padding: 20px; margin-bottom: 16px; }
  .card h2 { margin: 0 0 6px; color: #e94560; font-size: 16px; }
  .card p { margin: 0 0 14px; color: #aaa; font-size: 13px; }
  button { background: #0f3460; color: #00d4ff; border: 1px solid #00d4ff; border-radius: 4px;
           padding: 8px 20px; cursor: pointer; font-family: monospace; font-size: 14px; }
  button:hover { background: #00d4ff; color: #1a1a2e; }
  button:disabled { opacity: 0.4; cursor: not-allowed; }
  #log { background: #0d0d1a; border: 1px solid #333; border-radius: 4px; padding: 16px;
         height: 320px; overflow-y: auto; font-size: 13px; white-space: pre-wrap; margin-top: 24px; }
  .ok  { color: #4cff91; }
  .err { color: #ff6b6b; }
  .inf { color: #aaa; }
</style>
</head>
<body>
<h1>⚾ Fantasy Baseball Dashboard</h1>
<div class="subtitle">Pi5 手動觸發排程 — Tailscale Only</div>

__CARDS__

<div id="log"><span class="inf">等待執行...</span></div>

<script>
const log = document.getElementById('log');
const btns = document.querySelectorAll('button');

function appendLog(txt) {
  const line = document.createElement('span');
  if (txt.startsWith('ERROR') || txt.startsWith('✗')) line.className = 'err';
  else if (txt.startsWith('✓') || txt.includes('done') || txt.includes('完成')) line.className = 'ok';
  else line.className = 'inf';
  line.textContent = txt + '\\n';
  log.appendChild(line);
  log.scrollTop = log.scrollHeight;
}

function startStream(url) {
  btns.forEach(b => b.disabled = true);
  log.innerHTML = '<span class="inf">執行中...</span>\\n';
  const es = new EventSource(url);
  es.onmessage = e => appendLog(e.data);
  es.onerror = () => { es.close(); btns.forEach(b => b.disabled = false); };
}

function run(job) { startStream('/run/' + job); }

function runTrade() {
  const q = document.getElementById('trade-input').value.trim();
  if (!q) { alert('請輸入球員姓名或 Yahoo ID'); return; }
  startStream('/run/trade?q=' + encodeURIComponent(q));
}
</script>
</body>
</html>
"""

CARD_TPL = """<div class="card">
  <h2>{label}</h2>
  <p>{desc}</p>
  <button onclick="run('{key}')">{label}</button>
</div>"""


@app.route("/")
def index():
    cards = "\n".join(
        CARD_TPL.format(key=k, label=v["label"], desc=v["desc"])
        for k, v in JOBS.items()
    )
    cards += "\n" + TRADE_CARD
    return HTML.replace("__CARDS__", cards)


@app.route("/run/<job_key>")
def run_job(job_key):
    global _running

    if job_key not in JOBS:
        return "unknown job", 404

    def generate():
        global _running
        with _lock:
            if _running:
                yield "data: ⚠ 已有任務執行中，請稍候\n\n"
                return
            _running = True

        try:
            for cmd in JOBS[job_key]["cmds"]:
                script = cmd[-1].split("/")[-1]
                yield f"data: ▶ {script}\n\n"
                proc = subprocess.Popen(
                    cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    cwd=BASE,
                )
                for line in proc.stdout:
                    line = line.rstrip()
                    if line:
                        yield f"data: {line}\n\n"
                proc.wait()
                status = "✓ 完成" if proc.returncode == 0 else f"✗ 錯誤 (exit {proc.returncode})"
                yield f"data: {status}\n\n"
            yield "data: ✓ 全部完成\n\n"
        finally:
            _running = False

    return Response(
        stream_with_context(generate()),
        mimetype="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.route("/run/trade")
def run_trade():
    q = request.args.get("q", "").strip()
    if not q:
        return "missing query", 400

    if q.isdigit():
        cmd = [PYTHON, f"{BASE}/sync/add_trade_target.py", "--id", q]
        label = f"ID={q}"
    else:
        cmd = [PYTHON, f"{BASE}/sync/add_trade_target.py", q]
        label = q

    def generate():
        global _running
        with _lock:
            if _running:
                yield "data: ⚠ 已有任務執行中，請稍候\n\n"
                return
            _running = True
        try:
            for run_cmd, script_label in [
                (cmd, f"add_trade_target ({label})"),
                ([PYTHON, f"{BASE}/sync/sync_log.py"], "sync_log"),
            ]:
                yield f"data: ▶ {script_label}\n\n"
                proc = subprocess.Popen(
                    run_cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    cwd=BASE,
                )
                for line in proc.stdout:
                    line = line.rstrip()
                    if line:
                        yield f"data: {line}\n\n"
                proc.wait()
                status = "✓ 完成" if proc.returncode == 0 else f"✗ 錯誤 (exit {proc.returncode})"
                yield f"data: {status}\n\n"
            yield "data: ✓ 全部完成\n\n"
        finally:
            _running = False

    return Response(
        stream_with_context(generate()),
        mimetype="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5001, threaded=True)
