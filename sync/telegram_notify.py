"""
telegram_notify.py — 發送 Telegram 通知

config 存於 ~/.config/fantasy_baseball_telegram.json：
    {"token": "...", "chat_id": 123456789}

找不到 config 時靜默略過，不影響主流程。
"""
import json
import urllib.request
from pathlib import Path

_CONFIG_FILE = Path.home() / ".config" / "fantasy_baseball_telegram.json"
_config = None


def _load_config():
    global _config
    if _config is None and _CONFIG_FILE.exists():
        with open(_CONFIG_FILE) as f:
            _config = json.load(f)
    return _config


def send(message: str) -> bool:
    """發送 Telegram 訊息，失敗時靜默回傳 False。"""
    cfg = _load_config()
    if not cfg:
        return False
    try:
        url = f"https://api.telegram.org/bot{cfg['token']}/sendMessage"
        data = json.dumps({"chat_id": cfg["chat_id"], "text": message}).encode()
        req = urllib.request.Request(
            url, data=data, headers={"Content-Type": "application/json"}
        )
        urllib.request.urlopen(req, timeout=10)
        return True
    except Exception:
        return False
