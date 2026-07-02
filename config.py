"""
明日方舟 API 配置 v1.0
"""
AS_BASE_URL = "https://as.hypergryph.com"
SKLAND_BASE = "https://zonai.skland.com"
SKLAND_API = f"{SKLAND_BASE}/api/v1"

# 鹰角通行证 API
AS_SEND_PHONE_CODE = f"{AS_BASE_URL}/general/v1/send_phone_code"
AS_TOKEN_BY_PHONE_CODE = f"{AS_BASE_URL}/user/auth/v2/token_by_phone_code"
AS_USER_INFO = f"{AS_BASE_URL}/user/info/v1/basic"
AS_OAUTH2_GRANT = f"{AS_BASE_URL}/user/oauth2/v2/grant"

# 森空岛 API
SKLAND_GENERATE_CRED = f"{SKLAND_API}/user/auth/generate_cred_by_code"
SKLAND_USER_ME = f"{SKLAND_API}/user/me"
SKLAND_GAME_BINDING = f"{SKLAND_API}/game/player/binding"
SKLAND_GAME_INFO = f"{SKLAND_API}/game/player/info"
SKLAND_CHAR_LIST = f"{SKLAND_API}/game/arknights/character/list"

SKLAND_APP_CODE = "4ca99fa6b56cc2ba"
SKLAND_PLATFORM = "1"
SKLAND_VNAME = "1.0.1"
SKLAND_VCODE = "100001014"
SKLAND_DID = "de9759a5afaa634f"

HEADERS = {
    "User-Agent": "Skland/1.0.1 (com.hypergryph.skland; build:100001014; Android 31; ) Okhttp/4.11.0",
    "Accept": "application/json",
    "Content-Type": "application/json",
}

SKLAND_HEADERS = {
    "dId": SKLAND_DID,
    "platform": SKLAND_PLATFORM,
    "vName": SKLAND_VNAME,
    "vCode": SKLAND_VCODE,
}

REQUEST_TIMEOUT = 15
MAX_RETRIES = 2
