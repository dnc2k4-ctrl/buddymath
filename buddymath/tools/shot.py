#!/usr/bin/env python
r"""
shot.py — Chụp screenshot từng màn hình của SmartBuddy bằng Chrome headless (CDP),
kèm đo tràn layout (scrollHeight/clientHeight) để kiểm tra yêu cầu "fit 1 màn hình, không thanh cuộn".

Cách dùng (từ thư mục project buddymath):
    venv\Scripts\python.exe tools\shot.py --out ..\shots\current
    venv\Scripts\python.exe tools\shot.py --out ..\shots\current --only home,buddy,profile
    venv\Scripts\python.exe tools\shot.py --out ..\shots\current --width 1440 --height 810

Script tự khởi động uvicorn (cổng 8137), đăng nhập tài khoản demo để lấy token,
seed localStorage trước khi trang chạy, rồi chụp + xuất report.json.
"""
from __future__ import annotations

import argparse
import asyncio
import base64
import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import requests

try:
    import websockets
except ImportError:  # pragma: no cover
    websockets = None

ROOT = Path(__file__).resolve().parents[1]
BE = ROOT / "BE"
PY = ROOT / "venv" / "Scripts" / "python.exe"
if not PY.exists():
    PY = Path(sys.executable)
PORT = 8137
BASE = f"http://127.0.0.1:{PORT}"


def _free_port() -> int:
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port

CHROME_CANDIDATES = [
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files (x86)\Microsoft\EdgeCore\msedge.exe",
]

CDP_PORT = 9339
STAGE_MODE = False


def set_stage(on: bool) -> None:
    global STAGE_MODE
    STAGE_MODE = on


def set_ports(server_port: int, cdp_port: int) -> None:
    global PORT, BASE, CDP_PORT
    PORT = server_port
    BASE = f"http://127.0.0.1:{PORT}"
    CDP_PORT = cdp_port


# ────────────────────────────────────────────────────────────── server ──
def start_server() -> subprocess.Popen:
    env = os.environ.copy()
    env["PYTHONUNBUFFERED"] = "1"
    env.setdefault("ENABLE_DEMO_ACCOUNTS", "1")
    log = open(Path(tempfile.gettempdir()) / "sb-uvicorn.log", "wb")
    proc = subprocess.Popen(
        [str(PY), "-m", "uvicorn", "app.main:app", "--port", str(PORT), "--log-level", "warning"],
        cwd=str(BE),
        stdout=log,
        stderr=log,
    )
    for _ in range(240):
        if proc.poll() is not None:
            raise SystemExit("uvicorn thoát sớm — xem log tại %TEMP%\\sb-uvicorn.log")
        try:
            if requests.get(BASE + "/health", timeout=0.6).ok:
                return proc
        except Exception:
            pass
        time.sleep(0.25)
    proc.kill()
    raise SystemExit("uvicorn không khởi động được sau 60s")


def api_login(email: str, password: str) -> dict | None:
    try:
        r = requests.post(BASE + "/auth/login", json={"email": email, "password": password}, timeout=20)
        if r.ok:
            return r.json()
        print(f"  ! login {email}: HTTP {r.status_code} {r.text[:160]}")
    except Exception as exc:
        print(f"  ! login {email}: {exc}")
    return None


# ─────────────────────────────────────────────────────────────── CDP ──
class Page:
    def __init__(self, ws, target_id: str):
        self.ws = ws
        self.target_id = target_id
        self._id = 0
        self.events: list[dict] = []

    async def send(self, method: str, params: dict | None = None, timeout: float = 60) -> dict:
        self._id += 1
        mid = self._id
        await self.ws.send(json.dumps({"id": mid, "method": method, "params": params or {}}))
        while True:
            raw = await asyncio.wait_for(self.ws.recv(), timeout=timeout)
            msg = json.loads(raw)
            if msg.get("id") == mid:
                if "error" in msg:
                    raise RuntimeError(f"{method}: {msg['error']}")
                return msg.get("result", {})
            self.events.append(msg)

    async def eval(self, expression: str, await_promise: bool = False, timeout: float = 60):
        res = await self.send(
            "Runtime.evaluate",
            {"expression": expression, "returnByValue": True, "awaitPromise": await_promise},
            timeout=timeout,
        )
        if res.get("exceptionDetails"):
            desc = res["exceptionDetails"].get("text") or ""
            detail = res["exceptionDetails"].get("exception", {}).get("description", "")
            return {"__error": (desc + " " + detail).strip()[:400]}
        return res.get("result", {}).get("value")

    async def eval_ctx(self, expression: str, context_id: int, await_promise: bool = False, timeout: float = 30):
        res = await self.send(
            "Runtime.evaluate",
            {"expression": expression, "returnByValue": True, "awaitPromise": await_promise,
             "contextId": context_id},
            timeout=timeout,
        )
        if res.get("exceptionDetails"):
            desc = res["exceptionDetails"].get("text") or ""
            detail = res["exceptionDetails"].get("exception", {}).get("description", "")
            return {"__error": (desc + " " + detail).strip()[:400]}
        return res.get("result", {}).get("value")

    async def frame_ids(self) -> list[str]:
        tree = await self.send("Page.getFrameTree", timeout=15)
        out = []

        def walk(node):
            out.append(node["frame"]["id"])
            for ch in node.get("childFrames", []):
                walk(ch)
        walk(tree["frameTree"])
        return out

    async def iframe_context(self):
        try:
            ids = await self.frame_ids()
        except Exception:
            return None
        if len(ids) < 2:
            return None
        fid = ids[1]
        ctx = None
        for ev in self.events:
            if ev.get("method") == "Runtime.executionContextCreated":
                c = ev["params"]["context"]
                ad = c.get("auxData") or {}
                if ad.get("frameId") == fid and ad.get("isDefault"):
                    ctx = c["id"]
        return ctx


SEED_JS = """
(function(){
  try {
    var tok = %(token)s, usr = %(user)s;
    if (tok) localStorage.setItem('sb_token', tok); else localStorage.removeItem('sb_token');
    if (usr) localStorage.setItem('sb_user', JSON.stringify(usr)); else localStorage.removeItem('sb_user');
    if (tok) localStorage.setItem('sb_parent_token', tok); else localStorage.removeItem('sb_parent_token');
    if (usr) localStorage.setItem('sb_parent_user', JSON.stringify(usr)); else localStorage.removeItem('sb_parent_user');
    // tránh modal hướng dẫn tự bật khi chụp baseline
    localStorage.setItem('sb_welcomed', '1');
    if (usr && usr.id) {
      try { localStorage.setItem('sb_guide_seen_' + usr.id + '_' + usr.role, '1'); } catch(e) {}
      try { localStorage.setItem('sb_guide_seen_' + usr.id + '_parent_portal', '1'); } catch(e) {}
    }
  } catch(e) {}
})();
"""

LOAD_JS = """
(async () => {
  const sleep = (ms) => new Promise(r => setTimeout(r, ms));
  const withTimeout = (p, ms) => Promise.race([p, sleep(ms)]);
  const waitDoc = async (d) => {
    if (!d) return;
    for (let i = 0; i < 120; i++) { if (d.readyState === 'complete') break; await sleep(50); }
    try { if (d.fonts && d.fonts.ready) await withTimeout(d.fonts.ready, 1500); } catch(e) {}
    const imgs = Array.from(d.images || []);
    await withTimeout(Promise.all(imgs.map(img => img.complete ? Promise.resolve() : new Promise(res => {
      img.addEventListener('load', res, { once: true });
      img.addEventListener('error', res, { once: true });
      setTimeout(res, 2000);
    }))), 3500);
  };
  const ifr = document.getElementById('sb-stage-frame');
  if (ifr) {
    // Trang ngoài là "sân khấu" (đã window.stop) -> chỉ chờ tài liệu bên trong iframe
    await new Promise(res => {
      const d = ifr.contentDocument;
      if (d && d.readyState === 'complete') return res();
      ifr.addEventListener('load', res, { once: true });
      setTimeout(res, 6000);
    });
    try { await waitDoc(ifr.contentDocument); } catch (e) {}
    await sleep(250);
    return true;
  }
  await waitDoc(document);
  await sleep(150);
  return true;
})()
"""

METRICS_JS = """
(() => {
  const f = document.getElementById('sb-stage-frame');
  let doc = document, win = window, staged = false;
  try {
    if (f && f.contentDocument) { doc = f.contentDocument; win = f.contentWindow; staged = true; }
  } catch (e) {}
  const se = doc.scrollingElement || doc.documentElement;
  const out = { sw: se.scrollWidth, sh: se.scrollHeight, cw: se.clientWidth, ch: se.clientHeight,
                staged, iw: win.innerWidth, ih: win.innerHeight,
                bodyOverflow: (doc.body ? getComputedStyle(doc.body).overflowY : ''),
                docOverflow: getComputedStyle(doc.documentElement).overflowY, overflows: [] };
  for (const el of doc.querySelectorAll('*')) {
    if (!(el instanceof win.HTMLElement)) continue;
    const cs = win.getComputedStyle(el);
    if (cs.display === 'none' || cs.visibility === 'hidden' || cs.position === 'fixed') continue;
    if (el === se) continue;
    const scrollableY = (cs.overflowY === 'auto' || cs.overflowY === 'scroll') && el.scrollHeight > el.clientHeight + 2;
    const scrollableX = (cs.overflowX === 'auto' || cs.overflowX === 'scroll') && el.scrollWidth > el.clientWidth + 2;
    if (scrollableY || scrollableX) {
      out.overflows.push({
        sel: el.id ? '#' + el.id : (typeof el.className === 'string' && el.className ? '.' + el.className.trim().split(/\\s+/)[0] : el.tagName.toLowerCase()),
        sw: el.scrollWidth, cw: el.clientWidth, sh: el.scrollHeight, ch: el.clientHeight, y: scrollableY, x: scrollableX
      });
    }
  }
  return out;
})()
"""

CONSOLE_JS = """
(() => {
  const out = [];
  return out;
})()
"""


def chrome_path() -> str:
    for p in CHROME_CANDIDATES:
        if Path(p).exists():
            return p
    raise SystemExit("Không tìm thấy Chrome/Edge")


class Chrome:
    def __init__(self, headless_args: list[str], profile: str):
        self.proc = subprocess.Popen(
            [chrome_path(), *headless_args],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        self.profile = profile
        self.cdp = f"http://127.0.0.1:{CDP_PORT}"
        for _ in range(160):
            try:
                requests.get(self.cdp + "/json/version", timeout=0.5)
                return
            except Exception:
                if self.proc.poll() is not None:
                    raise SystemExit("Chrome thoát sớm")
                time.sleep(0.2)
        raise SystemExit("Chrome DevTools không phản hồi")

    def new_page(self) -> dict:
        r = requests.put(self.cdp + "/json/new?about:blank", timeout=10)
        r.raise_for_status()
        return r.json()

    def close_page(self, target_id: str):
        try:
            requests.get(self.cdp + f"/json/close/{target_id}", timeout=5)
        except Exception:
            pass

    def close(self):
        try:
            self.proc.terminate()
            self.proc.wait(timeout=6)
        except Exception:
            try:
                self.proc.kill()
            except Exception:
                pass
        shutil.rmtree(self.profile, ignore_errors=True)


async def safe_eval(page: "Page", expression: str, await_promise: bool = False,
                    tries: int = 6, timeout: float = 15):
    """Eval chịu được navigation và tự chọn đúng context (iframe app khi --stage)."""
    last = None
    for _ in range(tries):
        try:
            ctx = None
            if STAGE_MODE:
                ctx = await page.iframe_context()
                if ctx is None:                     # khung stage chưa dựng xong
                    await asyncio.sleep(0.5)
                    continue
            if ctx is not None:
                return await page.eval_ctx(expression, ctx, await_promise=await_promise, timeout=timeout)
            return await page.eval(expression, await_promise=await_promise, timeout=timeout)
        except Exception as exc:      # noqa: BLE001 - retry sau khi trang ổn định
            last = exc
            await asyncio.sleep(0.6)
    raise last if last else RuntimeError("eval failed")


async def run_shot(chrome: Chrome, shot: dict, width: int, height: int, out_dir: Path) -> dict:
    target = chrome.new_page()
    ws_url = target["webSocketDebuggerUrl"]
    result = {"name": shot["name"], "url": shot["url"]}
    try:
        async with websockets.connect(ws_url, max_size=64 * 1024 * 1024, open_timeout=20) as ws:
            page = Page(ws, target["id"])
            await page.send("Page.enable")
            await page.send("Runtime.enable")
            await page.send("Log.enable")
            await page.send("Emulation.setDeviceMetricsOverride",
                            {"width": width, "height": height, "deviceScaleFactor": 1, "mobile": False})
            seed = SEED_JS % {
                "token": json.dumps(shot.get("token")),
                "user": json.dumps(shot.get("user"), ensure_ascii=False),
            }
            await page.send("Page.addScriptToEvaluateOnNewDocument", {"source": seed})
            nav = await page.send("Page.navigate", {"url": shot["url"]})
            if nav.get("errorText"):
                result["nav_error"] = nav["errorText"]
            await asyncio.sleep(0.2)
            await safe_eval(page, "document.readyState")
            await safe_eval(page, LOAD_JS, await_promise=True)
            if shot.get("eval"):
                try:
                    ev = await safe_eval(page, shot["eval"], await_promise=True, tries=5)
                    if isinstance(ev, dict) and "__error" in ev:
                        result["eval_error"] = ev["__error"]
                except Exception as exc:
                    result["eval_error"] = str(exc)[:300]
            await asyncio.sleep(shot.get("wait", 0.6))
            await safe_eval(page, LOAD_JS, await_promise=True)

            metrics = await safe_eval(page, METRICS_JS, tries=3)
            result["metrics"] = metrics

            logs = []
            for ev in page.events:
                if ev.get("method") == "Log.entryAdded":
                    e = ev["params"]["entry"]
                    logs.append({"level": e.get("level"), "text": (e.get("text") or "")[:300]})
                elif ev.get("method") == "Runtime.consoleAPICalled" and ev["params"].get("type") in ("error", "warning"):
                    args = [str(a.get("value", a.get("description", "")))[:200] for a in ev["params"].get("args", [])]
                    logs.append({"level": ev["params"]["type"], "text": " ".join(args)})
            # flush log entries
            try:
                while True:
                    raw = await asyncio.wait_for(ws.recv(), timeout=0.35)
                    msg = json.loads(raw)
                    if msg.get("method") == "Log.entryAdded":
                        e = msg["params"]["entry"]
                        logs.append({"level": e.get("level"), "text": (e.get("text") or "")[:300]})
            except Exception:
                pass
            if logs:
                result["console"] = logs[:40]

            data = (await page.send("Page.captureScreenshot", {"format": "png", "captureBeyondViewport": False}))["data"]
            out_dir.mkdir(parents=True, exist_ok=True)
            (out_dir / f"{shot['name']}.png").write_bytes(base64.b64decode(data))
    finally:
        chrome.close_page(target["id"])
    return result


SHOTS = [
    {"name": "login", "url": "/"},
    {"name": "home", "url": "/app", "as": "student", "wait": 1.2},
    {"name": "onboarding", "url": "/app", "as": "student", "eval": "openLearningGuide(true)", "wait": 1.0},
    {"name": "buddy", "url": "/app", "as": "student", "eval": "document.querySelector('[data-topic=\\\"buddy\\\"]').click()", "wait": 1.2},
    {"name": "prompt", "url": "/app", "as": "student", "eval": "document.querySelector('[data-nav=\\\"prompt-playground\\\"]').click()", "wait": 1.2},
    {"name": "math", "url": "/app", "as": "student", "eval": "document.querySelector('[data-topic=\\\"math_hub\\\"]').click()", "wait": 1.2},
    {"name": "english", "url": "/app", "as": "student", "eval": "document.querySelector('[data-topic=\\\"english_hub\\\"]').click()", "wait": 1.2},
    {"name": "lifeskills", "url": "/app", "as": "student", "eval": "document.querySelector('[data-topic=\\\"life_skills\\\"]').click()", "wait": 1.2},
    {"name": "history", "url": "/app", "as": "student", "eval": "document.querySelector('[data-topic=\\\"score_history\\\"]').click()", "wait": 1.4},
    {"name": "achievements", "url": "/app", "as": "student", "eval": "document.querySelector('[data-nav=\\\"achievements\\\"]').click()", "wait": 1.2},
    {"name": "profile", "url": "/app", "as": "student", "eval": "document.querySelector('[data-nav=\\\"profile\\\"]').click()", "wait": 1.2},
    {"name": "settings", "url": "/app", "as": "student", "eval": "document.querySelector('[data-nav=\\\"settings\\\"]').click()", "wait": 1.0},
    {"name": "guide", "url": "/app", "as": "student", "eval": "openLearningGuide(true)", "wait": 1.0},
    {"name": "parent", "url": "/parent-portal", "as": "parent", "wait": 1.4},
    {"name": "admin", "url": "/admin", "wait": 1.0},
    {"name": "terms", "url": "/terms", "wait": 0.6},
    {"name": "privacy", "url": "/privacy", "wait": 0.6},
    {"name": "404", "url": "/khong-ton-tai-404", "wait": 0.6},
]


async def main_async(args):
    out_dir = Path(args.out).resolve()
    tokens: dict[str, dict | None] = {}
    if not args.no_login:
        for role, creds in {"student": ("student@demo.vn", "demo123"), "parent": ("parent@demo.vn", "demo123")}.items():
            data = api_login(*creds)
            tokens[role] = data
            print(f"  login {role}: {'OK' if data else 'FAILED'}")

    shots = SHOTS
    if args.only:
        wanted = {s.strip() for s in args.only.split(",") if s.strip()}
        shots = [s for s in shots if s["name"] in wanted]
        if args.from_json:
            pass
    if args.extra_json:
        shots = json.loads(Path(args.extra_json).read_text(encoding="utf-8"))

    profile = tempfile.mkdtemp(prefix="sb-chrome-")
    chrome = Chrome([
        "--headless=new",
        "--disable-gpu",
        "--no-first-run",
        "--no-default-browser-check",
        "--disable-extensions",
        "--disable-background-networking",
        "--hide-scrollbars",
        "--force-device-scale-factor=1",
        f"--window-size={args.width},{args.height}",
        f"--remote-debugging-port={CDP_PORT}",
        f"--user-data-dir={profile}",
        "about:blank",
    ], profile)

    report = []
    try:
        for shot in shots:
            role = shot.get("as")
            if role:
                data = tokens.get(role)
                if data:
                    shot = {**shot, "token": data["token"], "user": data["user"]}
            url = shot["url"]
            # Mặc định: chụp bên trong khung thiết kế 1672×941 (?embed=1).
            # --stage: chụp TRANG NGOÀI (design canvas scale) để kiểm chứng stage-loader.
            if not STAGE_MODE and "embed=1" not in url:
                url += ("&" if "?" in url else "?") + "embed=1"
            shot = {**shot, "url": BASE + url}
            print(f"  • {shot['name']} {url}")
            try:
                res = await run_shot(chrome, shot, args.width, args.height, out_dir)
            except Exception as exc:
                res = {"name": shot["name"], "url": url, "error": f"{type(exc).__name__}: {exc}"}
            m = res.get("metrics") or {}
            if m:
                flag = "OK " if (m.get("sh", 0) <= m.get("ch", 0) + 1 and m.get("sw", 0) <= m.get("cw", 0) + 1) else "SCROLL"
                res["fits"] = flag == "OK "
                print(f"    {flag} {m.get('sw')}x{m.get('sh')} viewport {m.get('cw')}x{m.get('ch')} "
                      f"overflows={len(m.get('overflows', []))}")
            if res.get("eval_error"):
                print(f"    eval error: {res['eval_error']}")
            report.append(res)
    finally:
        chrome.close()

    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")
    bad = [r["name"] for r in report if not r.get("fits")]
    print(f"\nẢnh: {out_dir}  |  {len(report)} màn  |  tràn/không đo được: {bad if bad else 'không'}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(ROOT.parent / "shots" / "current"))
    ap.add_argument("--width", type=int, default=1672)
    ap.add_argument("--height", type=int, default=941)
    ap.add_argument("--only", default="")
    ap.add_argument("--extra-json", default="")
    ap.add_argument("--from-json", action="store_true")
    ap.add_argument("--no-login", action="store_true")
    ap.add_argument("--server-port", type=int, default=0, help="0 = tự chọn cổng trống")
    ap.add_argument("--cdp-port", type=int, default=0, help="0 = tự chọn cổng trống")
    ap.add_argument("--stage", action="store_true", help="chụp trang ngoài (design canvas scale)")
    args = ap.parse_args()

    set_stage(args.stage)
    set_ports(args.server_port or _free_port(), args.cdp_port or _free_port())
    print(f"▶ SmartBuddy screenshots {args.width}x{args.height} → {args.out} (server :{PORT}, cdp :{CDP_PORT})")
    server = start_server()
    try:
        asyncio.run(main_async(args))
    finally:
        server.terminate()
        try:
            server.wait(timeout=8)
        except Exception:
            server.kill()


if __name__ == "__main__":
    main()
