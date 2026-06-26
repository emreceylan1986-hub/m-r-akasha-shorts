"""
instagram_paylas.py — Akasha YouTube videosunu @akashainme'ye STORY (+ReeL) akıt.

Resmi Instagram Graph API (Meta'nın sanal yöntemi, bot DEĞİL — @urunyacom'da
kullandığımız yöntemle aynı; 16 May engagement-bot yasağı kapsamı DIŞINDA).

Akış:
  1) MP4'ü public URL'e host et (Cloudflare R2 — S3 uyumlu)
  2) IG Graph: STORIES container oluştur → publish
  3) (opsiyon) REELS container oluştur → publish (kalıcı + erişim)

⚠️ GATE — şu env'ler yoksa GRACEFUL SKIP (video yine YouTube'da yayında):
  IG_AKASHA_TOKEN     : @akashainme access token (Akasha Sosyal app, appid 1919615585416373)
  IG_AKASHA_USER_ID   : IG business user id (@akashainme)
Host: VARSAYILAN catbox.moe (anahtarsız, ücretsiz). R2_* env'leri OPSİYONEL
(verilirse R2 tercih edilir, daha stabil). Yani host için kimlik GEREKMEZ.

⚠️ DURUM (26 Haz): Kod HAZIR ama CANLI TEST EDİLMEDİ — token + İşletme hesabı
gelince ilk gerçek story ile doğrulanacak. O ana kadar "çalışıyor" denmeyecek.

Kullanım:
  python instagram_paylas.py <mp4> "<caption>" [--reel-de]
"""
from __future__ import annotations

import os
import sys
import time
from pathlib import Path

import requests

# Akasha Sosyal = YENİ "Instagram API with Instagram login" (graph.instagram.com).
# Instagram app id: 998375079784414. Token = IG User access token (instagram_business_*).
# Yayın/publish/status uçları aynı şekil, sadece host graph.instagram.com.
GRAPH = "https://graph.instagram.com/v21.0"
STORY_MAX_SN = 60  # IG story video üst sınırı


# ---------------------------------------------------------------------------
def _env(*adlar: str) -> str | None:
    for a in adlar:
        v = os.environ.get(a)
        if v:
            return v.strip()
    return None


def _gate_ok() -> tuple[bool, str]:
    # Host artık catbox.moe (anahtarsız) → R2 zorunlu değil. Sadece IG token gerek.
    if not _env("IG_AKASHA_TOKEN"):
        return False, "IG_AKASHA_TOKEN yok"
    if not _env("IG_AKASHA_USER_ID"):
        return False, "IG_AKASHA_USER_ID yok"
    return True, ""


def catbox_yukle_public(mp4: Path) -> str | None:
    """MP4'ü catbox.moe'ye yükle (ücretsiz, anahtarsız, kalıcı) → public URL.
    IG video_url buradan çeker. 200MB'a kadar destekler."""
    try:
        with open(mp4, "rb") as f:
            r = requests.post(
                "https://catbox.moe/user/api.php",
                data={"reqtype": "fileupload"},
                files={"fileToUpload": (mp4.name, f, "video/mp4")},
                timeout=180,
            )
        if r.status_code == 200 and r.text.startswith("http"):
            return r.text.strip()
        print(f"[ig] catbox hata: {r.status_code} {r.text[:120]}")
    except Exception as h:
        print(f"[ig] catbox yükleme hatası: {str(h)[:120]}")
    return None


# ---------------------------------------------------------------------------
def r2_yukle_public(mp4: Path) -> str | None:
    """MP4'ü R2'ye yükle, public URL döner. boto3 (S3 uyumlu)."""
    try:
        import boto3
    except ImportError:
        print("[ig] boto3 yok → R2 yükleme atlanır"); return None
    endpoint = _env("R2_ENDPOINT")
    bucket = _env("R2_BUCKET") or "akasha-media"
    pub = _env("R2_PUBLIC_BASE")  # örn https://media.akasha.../  (r2.dev veya custom)
    if not (endpoint and pub):
        return None
    s3 = boto3.client(
        "s3", endpoint_url=endpoint,
        aws_access_key_id=_env("R2_ACCESS_KEY"),
        aws_secret_access_key=_env("R2_SECRET_KEY"),
        region_name="auto",
    )
    key = f"story/{mp4.name}"
    s3.upload_file(str(mp4), bucket, key, ExtraArgs={"ContentType": "video/mp4"})
    return pub.rstrip("/") + "/" + key


# ---------------------------------------------------------------------------
def _container_olustur(uid: str, token: str, video_url: str,
                       media_type: str, caption: str = "") -> str | None:
    """STORIES veya REELS container oluştur → creation_id döner."""
    data = {"media_type": media_type, "video_url": video_url, "access_token": token}
    if media_type == "REELS" and caption:
        data["caption"] = caption
    r = requests.post(f"{GRAPH}/{uid}/media", data=data, timeout=60)
    if r.status_code != 200:
        print(f"[ig] {media_type} container hata: {r.text[:200]}")
        return None
    return r.json().get("id")


def _yayinla(uid: str, token: str, creation_id: str) -> bool:
    """Container hazır olana kadar bekle, sonra publish."""
    # IG video işleme süresi: status_code FINISHED olana dek poll
    for _ in range(20):
        s = requests.get(f"{GRAPH}/{creation_id}",
                         params={"fields": "status_code", "access_token": token},
                         timeout=30)
        durum = s.json().get("status_code")
        if durum == "FINISHED":
            break
        if durum == "ERROR":
            print("[ig] container ERROR"); return False
        time.sleep(6)
    p = requests.post(f"{GRAPH}/{uid}/media_publish",
                      data={"creation_id": creation_id, "access_token": token},
                      timeout=60)
    if p.status_code != 200:
        print(f"[ig] publish hata: {p.text[:200]}")
        return False
    return True


# ---------------------------------------------------------------------------
def paylas(mp4: Path, caption: str = "", reel_de: bool = True) -> bool:
    ok, sebep = _gate_ok()
    if not ok:
        print(f"[ig] GATE kapalı ({sebep}) — story atlandı, video YouTube'da yayında")
        return False

    uid = _env("IG_AKASHA_USER_ID")
    token = _env("IG_AKASHA_TOKEN")

    # Host: R2 varsa onu kullan (daha stabil), yoksa catbox (anahtarsız varsayılan)
    video_url = (r2_yukle_public(mp4) if _env("R2_ENDPOINT") else None) \
        or catbox_yukle_public(mp4)
    if not video_url:
        print("[ig] public MP4 URL üretilemedi — atlandı")
        return False
    print(f"[ig] public video: {video_url}")

    basari = False
    # 1) STORY
    cid = _container_olustur(uid, token, video_url, "STORIES")
    if cid and _yayinla(uid, token, cid):
        print("[ig] ✓ STORY yayınlandı (@akashainme)")
        basari = True
    # 2) REEL (opsiyon)
    if reel_de:
        cid2 = _container_olustur(uid, token, video_url, "REELS", caption)
        if cid2 and _yayinla(uid, token, cid2):
            print("[ig] ✓ REEL yayınlandı (@akashainme)")
            basari = True
    return basari


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Kullanım: python instagram_paylas.py <mp4> \"<caption>\" [--reel-de]")
        raise SystemExit(1)
    mp4 = Path(sys.argv[1])
    cap = sys.argv[2] if len(sys.argv) > 2 else ""
    reel = "--reel-de" in sys.argv
    sonuc = paylas(mp4, cap, reel_de=reel)
    print("SONUÇ:", "OK" if sonuc else "atlandı/başarısız")
