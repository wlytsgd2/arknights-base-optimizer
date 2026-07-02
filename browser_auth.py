"""
浏览器自动捕获 Token - CDP Network 监听版

启动 Chrome → 用户在网页中任意方式登录 →
通过 CDP Network.getResponseBody 自动读取 API 响应中的 token
"""

import json, time, os, subprocess, requests as req
from websocket import create_connection, WebSocketTimeoutException

CHROME = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
EDGE = r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"
DEBUG_PORT = 9223
LOGIN_URL = "https://user.hypergryph.com/"


def _find_browser():
    for p in [EDGE, CHROME]:  # Edge 优先
        if os.path.exists(p):
            return p
    return None


def _get_ws_url():
    try:
        pages = req.get(f"http://127.0.0.1:{DEBUG_PORT}/json", timeout=3).json()
        for p in pages:
            if p.get("type") == "page" and "webSocketDebuggerUrl" in p:
                return p["webSocketDebuggerUrl"], p["id"]
    except Exception:
        pass
    return None, None


def _launch_browser():
    browser = _find_browser()
    if not browser:
        return None

    user_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".cdp_profile")
    os.makedirs(user_dir, exist_ok=True)

    # 杀旧进程
    try:
        subprocess.run(
            f'for /f "tokens=5" %a in (\'netstat -ano ^| findstr :{DEBUG_PORT}\') do taskkill /F /PID %a',
            shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except Exception:
        pass
    time.sleep(0.5)

    subprocess.Popen([
        browser,
        f"--remote-debugging-port={DEBUG_PORT}",
        f"--user-data-dir={user_dir}",
        "--remote-allow-origins=*",
        "--no-first-run", "--no-default-browser-check",
        LOGIN_URL,
    ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
       creationflags=subprocess.CREATE_NEW_CONSOLE if os.name == "nt" else 0)

    for _ in range(25):
        time.sleep(0.4)
        ws, _ = _get_ws_url()
        if ws:
            return ws
    return None


def capture_token(timeout: int = 180) -> tuple:
    """返回 (token, error_msg)"""
    ws_url, _ = _get_ws_url()
    if not ws_url:
        ws_url = _launch_browser()
    if not ws_url:
        return "", "无法启动浏览器"

    print(f"  [CDP] 已连接，监听网络请求...")

    try:
        ws = create_connection(ws_url, timeout=10)

        # 启用 Network 域
        ws.send(json.dumps({"id": 1, "method": "Network.enable"}))
        ws.recv()

        start = time.time()
        captured = ""
        request_ids = {}  # requestId -> url

        ws.settimeout(1)

        while time.time() - start < timeout:
            try:
                raw = ws.recv()
                msg = json.loads(raw)
            except WebSocketTimeoutException:
                continue
            except Exception:
                time.sleep(0.5)
                continue

            method = msg.get("method", "")

            # 收集请求 URL + 提取 token
            if method == "Network.requestWillBeSent":
                req_data = msg.get("params", {}).get("request", {})
                rid = msg["params"]["requestId"]
                url = req_data.get("url", "")
                request_ids[rid] = url
                if any(kw in url for kw in ["token", "auth", "login", "user"]):
                    print(f"  [CDP] 请求: {url[:120]}")

                # 从 URL query 参数中提取 token
                if "token=" in url:
                    import urllib.parse
                    parsed = urllib.parse.urlparse(url)
                    qs = urllib.parse.parse_qs(parsed.query)
                    t = qs.get("token", [None])[0]
                    if t and len(t) > 10:
                        from urllib.parse import unquote
                        t = unquote(t)
                        captured = t
                        print(f"  [CDP] 从 URL 捕获到 token: {t[:20]}...")
                        break

            elif method == "Network.responseReceived":
                resp = msg.get("params", {}).get("response", {})
                rid = msg["params"]["requestId"]
                url = resp.get("url", "") or request_ids.get(rid, "")
                # 记录 requestId 等待 loadingFinished
                request_ids[rid] = url
                if any(kw in url for kw in ["token_by", "user/auth"]):
                    print(f"  [CDP] 响应: {resp.get('status')} {url[:120]}")
                    request_ids[f"pending_{rid}"] = rid

            elif method == "Network.loadingFinished":
                rid = msg["params"]["requestId"]
                url = request_ids.get(rid, "")
                if not any(kw in url for kw in ["token_by_phone", "token_by_password"]):
                    continue
                print(f"  [CDP] 加载完成: {url[:120]}")
                try:
                    ws.send(json.dumps({
                        "id": 100, "method": "Network.getResponseBody",
                        "params": {"requestId": rid}
                    }))
                    body_msg_raw = ws.recv()
                    body_msg = json.loads(body_msg_raw)
                    body = body_msg.get("result", {}).get("body", "")
                    if body and len(body) > 10:
                        try:
                            data = json.loads(body)
                            token = (data.get("data", {}).get("token") or
                                     data.get("token", ""))
                            if token and len(token) > 10:
                                captured = token
                                print(f"  [CDP] 从响应体捕获到 token!")
                                break
                        except Exception:
                            pass
                except Exception:
                    pass

        ws.close()

        if captured:
            return captured, ""
        return "", "超时 - 未检测到登录请求"

    except Exception as e:
        return "", f"CDP 错误: {e}"
