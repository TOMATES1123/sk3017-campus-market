"""用本地 Chrome（CDP 协议）批量截取页面整页截图。

不依赖 Selenium/Playwright：直接启动 headless Chrome，通过 DevTools 协议
设置登录 Cookie、模拟 1440x900 视口、按内容高度截整页。

用法：
    python tools/screenshot.py
"""
import base64
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import requests
import websocket

BASE_URL = "http://127.0.0.1:5000"
ROOT = Path(__file__).resolve().parent.parent
OUT_DIR = ROOT / "screenshots"
CHROME_CANDIDATES = [
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
]
PORT = 9222


class CDP:
    def __init__(self, ws_url):
        self.ws = websocket.create_connection(ws_url, timeout=40)
        self.seq = 0

    def call(self, method, params=None):
        self.seq += 1
        message_id = self.seq
        self.ws.send(json.dumps({"id": message_id, "method": method, "params": params or {}}))
        while True:
            message = json.loads(self.ws.recv())
            if message.get("id") == message_id:
                if "error" in message:
                    raise RuntimeError(f"{method}: {message['error']}")
                return message.get("result", {})

    def close(self):
        self.ws.close()


def login_cookie(username="xiaoming", password="123456") -> str:
    session = requests.Session()
    page = session.get(f"{BASE_URL}/auth/login", timeout=10)
    token = re.search(r'name="csrf_token"\s+value="([^"]+)"', page.text).group(1)
    response = session.post(
        f"{BASE_URL}/auth/login",
        data={"account": username, "password": password, "csrf_token": token},
        allow_redirects=False,
        timeout=10,
    )
    assert response.status_code == 302, "登录失败"
    return session.cookies.get("session")


def wait_ready(cdp: CDP, extra_seconds: float = 1.6) -> None:
    """等待加载完成、字体就绪、滚动触发懒加载，再截图。"""
    for _ in range(40):
        state = cdp.call(
            "Runtime.evaluate",
            {"expression": "document.readyState", "returnByValue": True},
        )
        if state["result"]["value"] == "complete":
            break
        time.sleep(0.2)
    cdp.call(
        "Runtime.evaluate",
        {
            "expression": "document.fonts ? document.fonts.ready.then(()=>true) : true",
            "awaitPromise": True,
            "returnByValue": True,
        },
    )
    cdp.call(
        "Runtime.evaluate",
        {
            "expression": (
                "window.scrollTo(0, document.body.scrollHeight);"
                "setTimeout(()=>window.scrollTo(0,0), 400); true"
            ),
            "returnByValue": True,
        },
    )
    time.sleep(extra_seconds)


def capture(cdp: CDP, url: str, filename: str, cookie: str | None, extra_seconds=1.6) -> None:
    cdp.call("Network.enable")
    cdp.call("Network.clearBrowserCookies")
    if cookie:
        cdp.call(
            "Network.setCookie",
            {"name": "session", "value": cookie, "domain": "127.0.0.1", "path": "/"},
        )
    cdp.call(
        "Emulation.setDeviceMetricsOverride",
        {"width": 1440, "height": 900, "deviceScaleFactor": 1, "mobile": False},
    )
    cdp.call("Page.navigate", {"url": url})
    wait_ready(cdp, extra_seconds)

    metrics = cdp.call("Page.getLayoutMetrics")
    content = metrics["cssContentSize"]
    height = min(int(content["height"]) + 2, 5200)
    cdp.call(
        "Emulation.setDeviceMetricsOverride",
        {"width": 1440, "height": height, "deviceScaleFactor": 1, "mobile": False},
    )
    time.sleep(0.4)

    result = cdp.call(
        "Page.captureScreenshot",
        {
            "format": "png",
            "captureBeyondViewport": True,
            "clip": {"x": 0, "y": 0, "width": 1440, "height": height, "scale": 1},
        },
    )
    path = OUT_DIR / filename
    path.write_bytes(base64.b64decode(result["data"]))
    size_kb = path.stat().st_size // 1024
    print(f"  saved {filename} ({1440}x{height}, {size_kb} KB)")


def main() -> int:
    OUT_DIR.mkdir(exist_ok=True)
    chrome = next((path for path in CHROME_CANDIDATES if Path(path).exists()), None)
    if not chrome:
        print("未找到 Chrome/Edge，无法截图")
        return 1

    os.environ["NO_PROXY"] = "127.0.0.1,localhost"
    profile = tempfile.mkdtemp(prefix="sk3017-shot-")
    process = subprocess.Popen(
        [
            chrome,
            "--headless=new",
            f"--remote-debugging-port={PORT}",
            f"--user-data-dir={profile}",
            "--no-first-run",
            "--no-default-browser-check",
            "--disable-gpu",
            "--hide-scrollbars",
            "--force-device-scale-factor=1",
            "about:blank",
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )

    try:
        for _ in range(60):
            try:
                targets = requests.get(f"http://127.0.0.1:{PORT}/json", timeout=2).json()
                if targets:
                    break
            except requests.RequestException:
                time.sleep(0.4)
        else:
            print("Chrome 调试端口未就绪")
            return 1

        page = next(target for target in targets if target["type"] == "page")
        cdp = CDP(page["webSocketDebuggerUrl"])
        cookie = login_cookie()

        shots = [
            (f"{BASE_URL}/", "01-home.png", None, 1.8),
            (f"{BASE_URL}/?q=教材", "02-search.png", None, 1.8),
            (f"{BASE_URL}/item/5", "03-detail.png", None, 1.8),
            (f"{BASE_URL}/auth/login", "04-login.png", None, 1.2),
            (f"{BASE_URL}/item/new", "05-publish.png", cookie, 1.4),
            (f"{BASE_URL}/me/", "06-user-center.png", cookie, 1.4),
            (f"{BASE_URL}/me/items", "07-my-items.png", cookie, 1.4),
            (f"{BASE_URL}/me/messages", "08-messages.png", cookie, 1.4),
            (f"{BASE_URL}/stats/", "09-stats.png", None, 3.0),
        ]
        for url, filename, auth, delay in shots:
            print(f"capturing {url}")
            capture(cdp, url, filename, auth, delay)

        cdp.close()
    finally:
        process.terminate()
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()
        shutil.rmtree(profile, ignore_errors=True)

    print("全部截图完成")
    return 0


if __name__ == "__main__":
    sys.exit(main())
