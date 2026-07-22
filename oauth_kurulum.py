#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
oauth_kurulum.py — Akasha ilk OAuth token üretimi.

Emre Studio'da Akasha kanalını oluşturduktan SONRA çalıştırılır:
  python3 oauth_kurulum.py
Tarayıcı açılır → Emre **Akasha kanalının bağlı olduğu Google hesabını** seçer
→ "İzin ver" → token.json üretilir. Sonra Claude TOKEN_JSON secret'ına yükler.

3 scope: youtube (upload/yönetim) + analytics.readonly + force-ssl (caption/community).
"""
from pathlib import Path
from google_auth_oauthlib.flow import InstalledAppFlow

KOK = Path(__file__).parent
CLIENT_SECRET = KOK / "client_secret.json"
TOKEN = KOK / "token.json"

SCOPES = [
    "https://www.googleapis.com/auth/youtube",
    "https://www.googleapis.com/auth/yt-analytics.readonly",
    "https://www.googleapis.com/auth/youtube.force-ssl",
]


def main():
    if not CLIENT_SECRET.exists():
        raise SystemExit(f"client_secret.json yok: {CLIENT_SECRET}")
    print("🧠 Akasha OAuth — tarayıcı açılıyor...")
    print("   ⚠️ Açılan ekranda MUTLAKA Akasha kanalının Google hesabını seç!")
    flow = InstalledAppFlow.from_client_secrets_file(str(CLIENT_SECRET), SCOPES)
    creds = flow.run_local_server(port=0, prompt="consent",
                                  authorization_prompt_message="Tarayıcıda izin ver: {url}")
    TOKEN.write_text(creds.to_json(), encoding="utf-8")
    print(f"✅ token.json üretildi → {TOKEN}")
    print("   Sıradaki: Claude `gh secret set TOKEN_JSON` ile yükleyecek + ilk videoyu tetikleyecek.")


if __name__ == "__main__":
    main()
