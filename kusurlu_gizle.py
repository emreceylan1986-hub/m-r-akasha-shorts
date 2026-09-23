#!/usr/bin/env python3
"""
kusurlu_gizle.py — Yeni uzun video KALİTE EŞİĞİNİ GEÇERSE, yerine geçtiği
kusurlu videoları private yapar. Eşik tutmazsa HİÇBİR ŞEY yapmaz.

Neden var (23 Eyl 2026): iki uzun video kusurlu yayınlandı —
  C5V8HR4QNjI  15 dakika boyunca 1/10 farklı görsel (Leda sesi doğru)
  sk6jhyQuvjY  9/10 farklı görsel ✓ ama yedek Emel sesiyle (kota bitmişti)
Emre "evet yap" dedi: kota sıfırlanınca temiz üretim yapılacak, bu ikisi gizlenecek.
Gizleme İNSANA BAĞLI KALMASIN diye buraya bağlandı — ama yalnız yeni video
GERÇEKTEN iyiyse. Kanıtsız gizleme yok.

Eşik: ses == leda  VE  farkli_gorsel >= ASGARI_GORSEL
"""
import json
import os
import sys
from pathlib import Path

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

KOK = Path(__file__).parent
KUNYE = KOK / ".longform_kalite.json"
LISTE = KOK / "gizlenecek_videolar.json"
ASGARI_GORSEL = 5


def yt():
    c = Credentials.from_authorized_user_file(str(KOK / "token.json"))
    if c.expired and c.refresh_token:
        c.refresh(Request())
    return build("youtube", "v3", credentials=c, cache_discovery=False)


def main() -> int:
    if not KUNYE.exists() or not LISTE.exists():
        print("[gizle] kalite künyesi ya da liste yok — işlem yapılmadı")
        return 0
    k = json.loads(KUNYE.read_text(encoding="utf-8"))
    hedefler = [v for v in json.loads(LISTE.read_text(encoding="utf-8")) if v]
    print(f"[gizle] yeni video {k.get('video_id')} · ses={k.get('ses')} · "
          f"{k.get('farkli_gorsel')} farklı görsel / {k.get('bolum')} bölüm")

    if k.get("ses") != "leda":
        print(f"[gizle] ⛔ ses '{k.get('ses')}' (leda değil) → gizleme YOK")
        return 0
    if int(k.get("farkli_gorsel", 0)) < ASGARI_GORSEL:
        print(f"[gizle] ⛔ görsel çeşitliliği {k.get('farkli_gorsel')} < "
              f"{ASGARI_GORSEL} → gizleme YOK")
        return 0
    if not hedefler:
        print("[gizle] gizlenecek video yok")
        return 0

    y = yt()
    kalan = []
    for vid in hedefler:
        if vid == k.get("video_id"):
            print(f"[gizle] {vid} yeni videonun kendisi — atlandı")
            kalan.append(vid)
            continue
        try:
            item = y.videos().list(part="status,snippet", id=vid).execute().get("items")
            if not item:
                print(f"[gizle] {vid} bulunamadı (silinmiş olabilir) — listeden düşüyor")
                continue
            st = item[0]["status"]
            if st["privacyStatus"] == "private":
                print(f"[gizle] {vid} zaten private")
                continue
            y.videos().update(part="status", body={
                "id": vid,
                "status": {"privacyStatus": "private",
                           "selfDeclaredMadeForKids": st.get("selfDeclaredMadeForKids", False)},
            }).execute()
            teyit = y.videos().list(part="status", id=vid).execute()["items"][0]["status"]
            print(f"[gizle] 🔒 {vid} → {teyit['privacyStatus']}  "
                  f"{item[0]['snippet']['title'][:44]}")
        except Exception as h:
            print(f"[gizle] {vid} gizlenemedi: {str(h)[:110]}")
            kalan.append(vid)
    LISTE.write_text(json.dumps(kalan, ensure_ascii=False), encoding="utf-8")
    print(f"[gizle] bitti · listede kalan: {len(kalan)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
