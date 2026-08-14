#!/usr/bin/env python3
"""Bakım: kazara private kalan Akasha videolarını public yapar.

14 Ağu 2026 dersi: f1qMcE2Wr5c (11 Ağu, "mevlana felsefesinde başkasının kusuru")
3 gün private takılı kaldı, kimse fark etmedi. Cosmos'ta bu onarıcı 11 Ağu'dan
beri günlük koşuyor; Akasha'da yoktu çünkü burada BİLİNÇLİ private videolar var.
Çözüm: bilinçli olanları sabit listeyle koru, gerisini aç.

🔴 DOKUNMA listesi Emre Bey'in kararı — Leda öncesi Emel sesli İkarus kopyaları.
   Bu listeden ID silmek = yanlış sesli video yayına çıkar. Silme.

Cosmos'un onarim_public.py'sinden ayrılan yanlar:
  - DOKUNMA korkuluğu var (Cosmos'ta yok, orada bilinçli private yok)
  - Q/A başlık onarımı YOK (o Mindgaps/İngilizce kaynaklı bir sorundu)
GitHub Actions'ta çalışır — Mac'te googleapis DNS engelli. Idempotent.
"""
import datetime
import json
import re
import sys
from pathlib import Path

from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from googleapiclient.discovery import build

# 🔴 ASLA public yapılmayacak videolar (Emre onayı, 1 Ağu 2026)
DOKUNMA = {
    "rrVcKBrMmzc",  # İkarus — Emel sesli eski kopya
    "obS88cVVyDk",  # İkarus — Emel sesli eski kopya
}
PENCERE_GUN = 14  # eski arşivi yanlışlıkla yayınlamayı önleyen korkuluk


def yt_client():
    info = json.loads(Path("token.json").read_text())
    cs_raw = json.loads(Path("client_secret.json").read_text())
    cs = cs_raw.get("installed") or cs_raw.get("web") or {}
    creds = Credentials(
        token=info.get("token"),
        refresh_token=info.get("refresh_token"),
        token_uri=info.get("token_uri", "https://oauth2.googleapis.com/token"),
        client_id=info.get("client_id") or cs.get("client_id"),
        client_secret=info.get("client_secret") or cs.get("client_secret"),
        scopes=info.get("scopes"),
    )
    if creds.expired and creds.refresh_token:
        creds.refresh(Request())
    return build("youtube", "v3", credentials=creds, cache_discovery=False)


def son_pencere_idleri() -> list:
    """yuklemeler.json'dan son PENCERE_GUN günün video id'leri (DOKUNMA hariç)."""
    d = json.loads(Path("yuklemeler.json").read_text())
    items = d if isinstance(d, list) else d.get("yuklemeler", [])
    esik = (datetime.datetime.now() - datetime.timedelta(days=PENCERE_GUN)).strftime("%Y-%m-%d")
    out = []
    for k in items:
        vid = k.get("video_id") or ""
        if not vid and k.get("watch_url"):
            m = re.search(r"(?:youtu\.be/|v=)([\w-]{11})", k["watch_url"])
            vid = m.group(1) if m else ""
        if vid and vid not in DOKUNMA and str(k.get("zaman", ""))[:10] >= esik:
            out.append(vid)
    return out


def main():
    kuru = "--kuru" in sys.argv
    yt = yt_client()
    vids = son_pencere_idleri()
    print(f"son {PENCERE_GUN} günde {len(vids)} video taranıyor "
          f"(dokunma listesi: {len(DOKUNMA)} video korunuyor)")
    acilan = 0
    for i in range(0, len(vids), 50):
        grup = vids[i:i + 50]
        resp = yt.videos().list(part="status,snippet", id=",".join(grup)).execute()
        for item in resp.get("items", []):
            vid = item["id"]
            if vid in DOKUNMA:  # ikinci kapı — liste her iki katmanda da uygulanır
                continue
            if item["status"]["privacyStatus"] != "private":
                continue
            print(f"  🔓 public: {vid}  {item['snippet']['title'][:55]}")
            if not kuru:
                yt.videos().update(part="status", body={
                    "id": vid,
                    "status": {"privacyStatus": "public",
                               "selfDeclaredMadeForKids":
                                   item["status"].get("selfDeclaredMadeForKids", False)},
                }).execute()
            acilan += 1
    print(f"BİTTİ: {acilan} video public yapıldı{' (KURU koşu)' if kuru else ''}.")


if __name__ == "__main__":
    main()
