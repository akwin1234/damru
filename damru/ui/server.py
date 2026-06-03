"""Local web UI for Damru."""
from __future__ import annotations

import json
import os
import platform
import time
import webbrowser
from dataclasses import asdict
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

from .jobs import JobStore
from .redact import redact_dict

JOBS = JobStore()

_ACTIONS: dict[str, tuple[str, list[str]]] = {
    "setup": ("Setup", ["setup", "-y"]),
    "install-deps": ("Install dependencies", ["install-deps", "-y"]),
    "check-env": ("Check environment", ["check-env", "--viewer"]),
    "fix-wsl": ("Fix WSL", ["fix-wsl"]),
    "install-viewer": ("Install viewer", ["install-viewer", "-y"]),
    "install-apks": ("Install APK assets", ["install-apks", "--download"]),
    "install-image": ("Install image", ["install-image", "--download"]),
    "wsl-kernel-status": ("WSL kernel status", ["wsl-kernel", "status"]),
    "wsl-kernel-install": ("Install WSL kernel", ["wsl-kernel", "install", "--yes", "--confirm-wsl-kernel-risk"]),
    "devices": ("List ADB devices", ["devices"]),
    "worker-stop-all": ("Stop all workers", ["worker", "stop-all"]),
}


def run(host: str = "127.0.0.1", port: int = 8765, no_open: bool = False, wsl_distro: str | None = None) -> int:
    if wsl_distro:
        os.environ["DAMRU_WSL_DISTRO"] = wsl_distro
    if host not in {"127.0.0.1", "localhost", "::1"}:
        print("WARNING: Damru UI is intended for localhost. Public binding can expose local controls.")
    server = ThreadingHTTPServer((host, port), Handler)
    url = f"http://{host}:{port}"
    print(f"Damru UI running at {url}")
    if not no_open:
        try:
            webbrowser.open(url)
        except Exception:
            pass
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping Damru UI")
    finally:
        server.server_close()
    return 0


class Handler(BaseHTTPRequestHandler):
    server_version = "DamruUI/0.1"

    def do_GET(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        path = parsed.path
        if path == "/":
            self._html(INDEX_HTML)
        elif path == "/api/status":
            self._json(status_payload())
        elif path == "/api/profiles":
            self._json(profiles_payload())
        elif path == "/api/jobs":
            self._json({"jobs": JOBS.list()})
        elif path.startswith("/api/jobs/") and path.endswith("/events"):
            self._job_events(path.split("/")[3])
        elif path.startswith("/api/jobs/"):
            self._job(path.split("/")[3])
        else:
            self.send_error(HTTPStatus.NOT_FOUND)

    def do_POST(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        path = parsed.path
        data = self._read_json()
        if path == "/api/actions":
            self._start_action(str(data.get("action", "")), data)
        else:
            self.send_error(HTTPStatus.NOT_FOUND)

    def log_message(self, fmt: str, *args: object) -> None:
        return

    def _read_json(self) -> dict[str, object]:
        length = int(self.headers.get("content-length", "0") or 0)
        if length <= 0:
            return {}
        raw = self.rfile.read(length).decode("utf-8", errors="replace")
        try:
            payload = json.loads(raw)
            return payload if isinstance(payload, dict) else {}
        except json.JSONDecodeError:
            return {}

    def _json(self, data: dict[str, object], status: int = 200) -> None:
        body = json.dumps(redact_dict(data), indent=2).encode("utf-8")
        self.send_response(status)
        self.send_header("content-type", "application/json; charset=utf-8")
        self.send_header("cache-control", "no-store")
        self.send_header("content-length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _html(self, text: str) -> None:
        body = text.encode("utf-8")
        self.send_response(200)
        self.send_header("content-type", "text/html; charset=utf-8")
        self.send_header("content-length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _job(self, job_id: str) -> None:
        job = JOBS.get(job_id)
        if not job:
            self._json({"error": "job not found"}, 404)
            return
        self._json({"job": job.as_dict()})

    def _job_events(self, job_id: str) -> None:
        job = JOBS.get(job_id)
        if not job:
            self.send_error(HTTPStatus.NOT_FOUND)
            return
        self.send_response(200)
        self.send_header("content-type", "text/event-stream")
        self.send_header("cache-control", "no-store")
        self.end_headers()
        last = -1
        while True:
            current = job.as_dict()
            logs = current["logs"]
            if isinstance(logs, list) and len(logs) != last:
                last = len(logs)
                self.wfile.write(f"data: {json.dumps(current)}\n\n".encode("utf-8"))
                self.wfile.flush()
            if current["status"] in {"success", "failed"}:
                break
            time.sleep(0.5)

    def _start_action(self, action: str, data: dict[str, object]) -> None:
        if action in _ACTIONS:
            name, args = _ACTIONS[action]
        elif action in {"worker-start", "worker-stop", "worker-reset"}:
            index = str(int(data.get("index", 0) or 0))
            command = action.split("-", 1)[1]
            args = ["worker", command, "--index", index]
            name = f"Worker {command} {index}"
        elif action == "screenshot":
            serial = _clean_arg(data.get("serial"))
            output = _clean_arg(data.get("output")) or "damru-ui-screenshot.png"
            args = ["screenshot", "--output", output]
            if serial:
                args.extend(["--serial", serial])
            name = "Screenshot"
        elif action == "record":
            serial = _clean_arg(data.get("serial"))
            output = _clean_arg(data.get("output")) or "damru-ui-record.mp4"
            args = ["record", "--output", output, "--time-limit", str(int(data.get("time_limit", 15) or 15))]
            if serial:
                args.extend(["--serial", serial])
            name = "Record"
        elif action == "view":
            serial = _clean_arg(data.get("serial"))
            args = ["view"]
            if serial:
                args.extend(["--serial", serial])
            if data.get("no_control"):
                args.append("--no-control")
            name = "Open viewer"
        else:
            self._json({"error": "unknown action"}, 400)
            return
        job = JOBS.start(name, args)
        self._json({"job": job.as_dict()})


def _clean_arg(value: object) -> str:
    if not value:
        return ""
    text = str(value).strip()
    allowed = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789._:/\\- ")
    return "".join(ch for ch in text if ch in allowed)[:240]


def _probe(cmd: list[str], timeout: int = 12) -> dict[str, object]:
    try:
        import subprocess

        proc = subprocess.run(cmd, capture_output=True, text=True, errors="replace", timeout=timeout)
        return {"ok": proc.returncode == 0, "code": proc.returncode, "out": (proc.stdout or proc.stderr).strip()[-500:]}
    except Exception as exc:
        return {"ok": False, "code": -1, "out": str(exc)}


def status_payload() -> dict[str, object]:
    try:
        from damru import cli

        wsl_distro = cli._configured_wsl_distro()
        adb_text = cli._adb_devices_text()
        adb_count = sum(1 for line in adb_text.splitlines()[1:] if "device" in line.split())
        docker = cli._linux_run("docker info --format '{{.ServerVersion}}'", timeout=12)
        image = cli._linux_run("docker image inspect damru-redroid:latest >/dev/null 2>&1", timeout=12)
        apks = _apk_status()
        return {
            "platform": platform.platform(),
            "windows": cli._is_windows(),
            "wsl_linux": cli._is_wsl_linux(),
            "wsl_distro": wsl_distro,
            "docker": {"ok": docker.returncode == 0, "detail": (docker.stdout or docker.stderr).strip()},
            "redroid_image": {"ok": image.returncode == 0},
            "adb": {"ok": adb_count > 0, "devices": adb_count, "detail": adb_text.strip()},
            "apk_bundle": apks,
            "jobs": JOBS.list()[:5],
        }
    except Exception as exc:
        return {"platform": platform.platform(), "error": str(exc), "jobs": JOBS.list()[:5]}


def _apk_status() -> dict[str, object]:
    try:
        from damru.apk_assets import find_apk_bundle_root, validate_apk_bundle

        root = find_apk_bundle_root(None)
        if not root:
            return {"ok": False, "detail": "not found"}
        validation = validate_apk_bundle(root)
        return {"ok": validation.ok, "root": str(root), "detail": validation.message}
    except Exception as exc:
        return {"ok": False, "detail": str(exc)}


def profiles_payload() -> dict[str, object]:
    from damru.devices import get_device, list_device_names

    profiles = []
    for name in list_device_names():
        item = asdict(get_device(name))
        item["name"] = name
        profiles.append(item)
    return {"profiles": profiles}

INDEX_HTML = r"""
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Damru UI</title>
  <style>
    :root { color-scheme: dark; --bg:#0d1117; --panel:#151b23; --line:#30363d; --text:#e6edf3; --muted:#8b949e; --good:#2ea043; --warn:#d29922; --bad:#f85149; --accent:#58a6ff; }
    * { box-sizing: border-box; }
    body { margin:0; background:var(--bg); color:var(--text); font:14px/1.45 Inter, ui-sans-serif, system-ui, Segoe UI, Arial, sans-serif; }
    header { height:60px; display:flex; align-items:center; justify-content:space-between; padding:0 22px; border-bottom:1px solid var(--line); background:#0b1016; position:sticky; top:0; z-index:2; }
    .brand { display:flex; align-items:center; gap:12px; font-weight:800; font-size:18px; }
    .brand img { width:34px; height:34px; }
    .wrap { display:grid; grid-template-columns:220px 1fr; min-height:calc(100vh - 60px); }
    nav { border-right:1px solid var(--line); padding:18px 12px; background:#0b1016; }
    nav a { display:block; color:var(--muted); text-decoration:none; padding:10px 12px; border-radius:8px; margin-bottom:4px; }
    nav a:hover, nav a.active { color:var(--text); background:#1f2630; }
    main { padding:24px; max-width:1220px; width:100%; }
    section { margin-bottom:28px; }
    h1,h2,h3 { margin:0 0 12px; letter-spacing:0; }
    .grid { display:grid; grid-template-columns:repeat(auto-fit,minmax(230px,1fr)); gap:14px; }
    .card { background:var(--panel); border:1px solid var(--line); border-radius:8px; padding:16px; }
    .muted { color:var(--muted); }
    .status { display:inline-flex; align-items:center; gap:6px; padding:4px 9px; border:1px solid var(--line); border-radius:999px; font-size:12px; color:var(--muted); }
    .ok { color:var(--good); } .bad { color:var(--bad); } .warn { color:var(--warn); }
    button, input, select { background:#21262d; color:var(--text); border:1px solid var(--line); border-radius:7px; padding:9px 11px; font:inherit; }
    button { cursor:pointer; margin:4px 6px 4px 0; }
    button:hover { border-color:var(--accent); }
    input { width:100%; max-width:520px; }
    table { width:100%; border-collapse:collapse; background:var(--panel); border:1px solid var(--line); border-radius:8px; overflow:hidden; }
    th,td { text-align:left; border-bottom:1px solid var(--line); padding:10px; vertical-align:top; }
    th { color:var(--muted); font-size:12px; text-transform:uppercase; }
    pre { background:#05080d; border:1px solid var(--line); border-radius:8px; padding:14px; overflow:auto; min-height:220px; white-space:pre-wrap; }
    .hidden { display:none; }
    .hero { display:flex; justify-content:space-between; gap:18px; align-items:flex-start; }
    .hero p { max-width:760px; color:var(--muted); margin-top:0; }
  </style>
</head>
<body>
<header>
  <div class="brand"><img src="/favicon.ico" onerror="this.style.display='none'">Damru UI</div>
  <div class="status">Official local control panel - localhost only</div>
</header>
<div class="wrap">
<nav>
  <a href="#overview" class="active">Overview</a>
  <a href="#setup">Setup</a>
  <a href="#workers">Workers</a>
  <a href="#profiles">Profiles</a>
  <a href="#viewer">Viewer</a>
  <a href="#logs">Logs</a>
  <a href="#docs">Docs</a>
</nav>
<main>
<section id="overview">
  <div class="hero"><div><h1>Damru Control Center</h1><p>Manage setup, WSL repair, Redroid workers, profiles, screenshots, video, and viewer tools from one local dashboard. No cloud. No telemetry. No public bind by default.</p></div><button onclick="refreshAll()">Refresh</button></div>
  <div class="grid" id="statusCards"></div>
</section>
<section id="setup">
  <h2>Setup</h2>
  <div class="card">
    <button onclick="action('setup')">Run setup</button>
    <button onclick="action('install-deps')">Install deps</button>
    <button onclick="action('check-env')">Check env</button>
    <button onclick="action('fix-wsl')">Fix WSL</button>
    <button onclick="action('install-apks')">Install APKs</button>
    <button onclick="action('install-image')">Install image</button>
    <button onclick="action('wsl-kernel-status')">Kernel status</button>
    <button onclick="confirmAction('wsl-kernel-install','Install WSL kernel and update .wslconfig?')">Install WSL kernel</button>
  </div>
</section>
<section id="workers">
  <h2>Workers</h2>
  <div class="card">
    <button onclick="action('devices')">List ADB devices</button>
    <label>Worker index</label><br><input id="workerIndex" value="0" style="max-width:120px">
    <div style="margin-top:8px">
      <button onclick="worker('worker-start')">Start worker</button>
      <button onclick="worker('worker-reset')">Reset worker</button>
      <button onclick="worker('worker-stop')">Stop worker</button>
      <button onclick="confirmAction('worker-stop-all','Stop all damru-worker containers?')">Stop all</button>
    </div>
    <label>Serial</label><br><input id="serial" placeholder="wsl:127.0.0.1:5600 or 127.0.0.1:5555">
    <div style="margin-top:8px">
      <button onclick="withSerial('screenshot')">Screenshot</button>
      <button onclick="withSerial('record')">Record 15s</button>
    </div>
  </div>
</section>
<section id="profiles">
  <h2>Profiles</h2>
  <input id="profileSearch" placeholder="Search Pixel, Samsung, Xiaomi..." oninput="renderProfiles()">
  <div id="profilesTable" style="margin-top:12px"></div>
</section>
<section id="viewer">
  <h2>Viewer</h2>
  <div class="card">
    <button onclick="action('install-viewer')">Install viewer tools</button>
    <button onclick="withSerial('view')">Open viewer</button>
    <button onclick="withSerial('view', {no_control:true})">Open watch-only viewer</button>
  </div>
</section>
<section id="logs">
  <h2>Logs</h2>
  <div id="jobs"></div>
  <pre id="logbox">No job selected.</pre>
</section>
<section id="docs">
  <h2>Docs</h2>
  <div class="grid">
    <div class="card"><a href="https://github.com/akwin1234/damru">Official repository</a><p class="muted">Do not trust unofficial binaries or rebranded installers.</p></div>
    <div class="card"><a href="https://github.com/akwin1234/damru/blob/main/docs/PYTHON_API.md">Python API</a><p class="muted">Open in repo/docs if served from source.</p></div>
    <div class="card"><a href="https://discord.gg/GsxFdjdrT">Discord</a><p class="muted">Community and support.</p></div>
  </div>
</section>
</main>
</div>
<script>
let profiles=[]; let activeJob=null;
function badge(ok){ return ok ? '<span class="ok">ready</span>' : '<span class="bad">needs attention</span>'; }
async function api(path, opts){ const r=await fetch(path, opts); return await r.json(); }
async function refreshAll(){ await refreshStatus(); await refreshProfiles(); await refreshJobs(); }
async function refreshStatus(){
  const s=await api('/api/status');
  const cards=[
    ['Host', s.platform || 'unknown'], ['WSL distro', s.wsl_distro || 'n/a'],
    ['Docker', badge(s.docker && s.docker.ok), s.docker && s.docker.detail],
    ['Redroid image', badge(s.redroid_image && s.redroid_image.ok)],
    ['ADB devices', (s.adb && s.adb.devices || 0)+' online'],
    ['APK bundle', badge(s.apk_bundle && s.apk_bundle.ok), s.apk_bundle && (s.apk_bundle.root || s.apk_bundle.detail)]
  ];
  document.getElementById('statusCards').innerHTML=cards.map(c=>`<div class="card"><h3>${c[0]}</h3><div>${c[1]}</div><p class="muted">${c[2]||''}</p></div>`).join('');
}
async function refreshProfiles(){ if(profiles.length) return; const p=await api('/api/profiles'); profiles=p.profiles||[]; renderProfiles(); }
function renderProfiles(){
  const q=(document.getElementById('profileSearch').value||'').toLowerCase();
  const rows=profiles.filter(p=>JSON.stringify(p).toLowerCase().includes(q)).slice(0,80).map(p=>`<tr><td>${p.name}</td><td>${p.brand||''} ${p.model||''}</td><td>${p.screen_width||''}x${p.screen_height||''} @ ${p.density_dpi||''}</td><td>${p.device_memory||''} GB</td><td>${p.hardware_concurrency||''}</td></tr>`).join('');
  document.getElementById('profilesTable').innerHTML=`<table><thead><tr><th>Name</th><th>Device</th><th>Display</th><th>RAM</th><th>CPU</th></tr></thead><tbody>${rows}</tbody></table>`;
}
async function action(name, extra={}){ const res=await api('/api/actions',{method:'POST',headers:{'content-type':'application/json'},body:JSON.stringify({action:name,...extra})}); if(res.job){ followJob(res.job.id); } }
function confirmAction(name,msg){ if(confirm(msg)) action(name); }
function withSerial(name, extra={}){ action(name,{serial:document.getElementById('serial').value,...extra}); }
function worker(name){ action(name,{index:document.getElementById('workerIndex').value || 0}); }
async function refreshJobs(){ const j=await api('/api/jobs'); document.getElementById('jobs').innerHTML=(j.jobs||[]).map(x=>`<button onclick="followJob('${x.id}')">${x.name} - ${x.status}</button>`).join(''); }
async function followJob(id){ activeJob=id; const j=await api('/api/jobs/'+id); renderLog(j.job); const es=new EventSource('/api/jobs/'+id+'/events'); es.onmessage=e=>{ const data=JSON.parse(e.data); renderLog(data); if(['success','failed'].includes(data.status)){ es.close(); refreshJobs(); refreshStatus(); } }; }
function renderLog(job){ document.getElementById('logbox').textContent=(job.logs||[]).join('\n'); document.getElementById('logbox').scrollTop=999999; }
refreshAll(); setInterval(refreshJobs, 4000);
</script>
</body>
</html>
"""
