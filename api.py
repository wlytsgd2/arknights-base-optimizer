"""API 请求模块 v1.0 - 鹰角通行证 + 森空岛"""
import requests, json, time, hmac, hashlib
from email.utils import parsedate_to_datetime
from config import *

class APIError(Exception): pass

# === 工具函数 ===

def _request(method, url, **kw):
    kw.setdefault("timeout", REQUEST_TIMEOUT)
    kw.setdefault("headers", HEADERS)
    for _ in range(MAX_RETRIES):
        try:
            resp = requests.request(method, url, **kw)
            if resp.status_code == 200:
                return resp
        except requests.RequestException:
            continue
    raise APIError(f"请求失败: {url}")

def _skland_timestamp():
    """获取服务器时间戳，避免本地时钟偏差"""
    try:
        r = requests.get(f"{SKLAND_BASE}/", headers=HEADERS, timeout=5)
        ts = int(parsedate_to_datetime(r.headers["Date"]).timestamp())
        return str(ts - 5)
    except Exception:
        return str(int(time.time()))

def _skland_sign(path, params, token, ts):
    """森空岛 API 签名"""
    header_json = json.dumps({
        "platform": SKLAND_PLATFORM, "timestamp": ts,
        "dId": SKLAND_DID, "vName": SKLAND_VNAME,
    }, separators=(",", ":"))
    raw = path + params + ts + header_json
    h = hmac.new(token.encode(), raw.encode(), hashlib.sha256).hexdigest()
    return hashlib.md5(h.encode()).hexdigest()

def _skland_request(method, path, params="", cred="", token=""):
    """带签名的森空岛 API 请求"""
    ts = _skland_timestamp()
    sign = _skland_sign(path, params, token, ts)
    headers = {**HEADERS, **SKLAND_HEADERS, "cred": cred, "token": token,
               "timestamp": ts, "sign": sign}
    url = f"{SKLAND_BASE}{path}" + (f"?{params}" if params else "")
    resp = _request(method, url, headers=headers)
    data = resp.json()
    if data.get("code", -1) != 0 or data.get("status", 0) != 0:
        raise APIError(data.get("msg") or data.get("message", "请求失败"))
    return data

# === 鹰角通行证 API ===

def get_user_info(token: str) -> dict:
    resp = _request("GET", AS_USER_INFO, params={"token": token})
    data = resp.json()
    if data.get("status", -1) != 0:
        raise APIError(data.get("msg", "获取失败"))
    return data

def get_oauth2_code(token: str) -> str:
    payload = {"token": token, "appCode": SKLAND_APP_CODE, "type": 0}
    resp = _request("POST", AS_OAUTH2_GRANT, json=payload)
    data = resp.json()
    if data.get("status", -1) != 0:
        raise APIError(data.get("msg", "OAuth2 失败"))
    return data["data"]["code"]

def get_skland_cred(code: str) -> dict:
    resp = _request("POST", SKLAND_GENERATE_CRED,
                    json={"code": code, "kind": 1},
                    headers={**HEADERS, **SKLAND_HEADERS})
    data = resp.json()
    if data.get("code", -1) != 0:
        raise APIError(data.get("msg") or data.get("message", "cred 失败"))
    d = data["data"]
    return {"cred": d["cred"], "token": d.get("token", ""), "userId": d.get("userId", "")}

# === 森空岛 API ===

def get_skland_user_info(cred: str, token: str = "") -> dict:
    return _skland_request("GET", "/api/v1/user/me", cred=cred, token=token)

def get_game_binding(cred: str, token: str = "") -> dict:
    return _skland_request("GET", "/api/v1/game/player/binding", cred=cred, token=token)

def get_game_data(cred: str, token: str, uid: str, channel: str = "1") -> dict:
    params = f"uid={uid}&channelMasterId={channel}"
    return _skland_request("GET", "/api/v1/game/player/info", params=params,
                           cred=cred, token=token)

def get_full_game_data(hg_token: str) -> dict:
    result = {}
    code = get_oauth2_code(hg_token)
    cred_info = get_skland_cred(code)
    cred, sk_token, _ = cred_info["cred"], cred_info["token"], cred_info["userId"]

    result["game_uid"] = ""
    result["cred"] = cred
    result["skland_token"] = sk_token

    # 获取绑定信息
    try:
        binding = get_game_binding(cred, sk_token)
        result["binding"] = binding
        for app in binding.get("data", {}).get("list", []):
            if app.get("appCode") == "arknights":
                for b in app.get("bindingList", []):
                    result["game_uid"] = b.get("uid", "")
                    result["nickname"] = b.get("nickName", "")
                    result["channel"] = b.get("channelMasterId", "1")
                    break
    except APIError:
        pass

    # 获取游戏内数据
    if result.get("game_uid"):
        try:
            result["game_data"] = get_game_data(cred, sk_token, result["game_uid"],
                                                 result.get("channel", "1"))
        except APIError as e:
            result["game_data_error"] = str(e)

    return result
