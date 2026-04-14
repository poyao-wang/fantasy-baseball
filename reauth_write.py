"""
Yahoo OAuth2 重新授權腳本
用於更換 App 或 token 過期時重新取得 oauth2.json

注意：Yahoo Fantasy Sports API 不開放 fspt-w (Write) scope 給一般開發者，
      本腳本只能取得 Read token。陣容寫入需透過 Playwright 瀏覽器自動化。

用法：
    python3.12 reauth_write.py
    （需在本機互動式終端機執行，會開啟瀏覽器授權）
"""
import json
import time
import webbrowser
from pathlib import Path
import requests
from requests.auth import HTTPBasicAuth

OAUTH2_FILE = "oauth2.json"
AUTH_URL    = "https://api.login.yahoo.com/oauth2/request_auth"
TOKEN_URL   = "https://api.login.yahoo.com/oauth2/get_token"
REDIRECT    = "oob"


def main():
    creds  = json.loads(Path(OAUTH2_FILE).read_text())
    key    = creds["consumer_key"]
    secret = creds["consumer_secret"]

    # 1. 產生授權 URL
    auth_url = (
        f"{AUTH_URL}"
        f"?client_id={key}"
        f"&redirect_uri={REDIRECT}"
        f"&response_type=code"
    )
    print("\n=== Yahoo OAuth2 重新授權 ===\n")
    print(f"授權 URL：\n{auth_url}\n")
    print("正在開啟瀏覽器…（若未自動開啟請手動複製上方 URL）\n")
    webbrowser.open(auth_url)

    # 2. 取得 verifier code
    code = input("請貼上 Yahoo 給的 verifier code：").strip()

    # 3. 換 token
    r = requests.post(
        TOKEN_URL,
        auth=HTTPBasicAuth(key, secret),
        data={"grant_type": "authorization_code", "code": code, "redirect_uri": REDIRECT},
    )
    r.raise_for_status()
    token = r.json()

    # 4. 存回 oauth2.json（相容 yahoo_oauth 格式）
    new_creds = {
        "access_token":   token["access_token"],
        "consumer_key":   key,
        "consumer_secret": secret,
        "refresh_token":  token["refresh_token"],
        "token_time":     time.time(),
        "token_type":     token.get("token_type", "bearer"),
    }
    Path(OAUTH2_FILE).write_text(json.dumps(new_creds, indent=2))
    print(f"\n完成！token 已存回 {OAUTH2_FILE}")
    print(f"scope: {token.get('scope', '（未回傳）')}")


if __name__ == "__main__":
    main()
