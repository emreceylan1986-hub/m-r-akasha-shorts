#!/usr/bin/env python3
"""
ikarus_final_yayinla.py — TEK SEFERLİK kapanış scripti (1 Ağu 2026).

Gece Leda sesiyle üretilen İkarus long-form'unu (long_form_cikti/ en yenisi)
YouTube kotası açıldıktan sonra yayınlar ve iki eski Emel'li kopyayı gizler.
Çalışma sırası: upload → kapak → creator yorum → rrVcKBrMmzc + obS88cVVyDk
private → long_form_son.json + long_form_gecmis.json güncelle + push → Telegram.

İş bitince kendini imzalar: .ikarus_final_tamam dosyası oluşur; ikinci kez
çalıştırılırsa dokunmadan çıkar.
"""
import json
import subprocess
import urllib.parse
import urllib.request
from datetime import datetime
from pathlib import Path

PANEL = Path(__file__).parent
KILIT = PANEL / ".ikarus_final_tamam"
ESKILER = ["rrVcKBrMmzc", "obS88cVVyDk"]  # 31 Tem'in iki Emel'li İkarus'u
KONU = "İkarus'un düşüşü: hırsın ve sınır tanımamanın bedeli"


def log(m):
    print(f"[ikarus-final] {m}", flush=True)


def telegram(msg):
    try:
        satirlar = {}
        for l in Path("/opt/urunya/telegram_creds.env").read_text().strip().splitlines():
            k, v = l.split("=", 1); satirlar[k] = v
    except Exception:
        return  # Mac'te creds yoksa sessiz geç (Hetzner'dekiyle aynı bot, Mac'te kopya yok)
    data = urllib.parse.urlencode({"chat_id": satirlar["TELEGRAM_CHAT"], "text": msg}).encode()
    urllib.request.urlopen(f"https://api.telegram.org/{satirlar['TELEGRAM_TOKEN']}/sendMessage", data, timeout=20)


def main():
    if KILIT.exists():
        log("zaten tamamlanmış — çıkılıyor"); return

    def leda_mi(kok: Path) -> bool:
        # Leda yolu bölümleri gruplar hâlinde üretir: 10 bölüm → g01..g05.
        # Emel yedeğine düşen üretimde gruplar eksik kalır (1 Ağu gecesi: sadece g01).
        return len(list((kok / "tts_bolum").glob("g*.mp3"))) >= 5

    # en yeni üretim klasörü (senaryo.json + final.mp4 + kapak.jpg şart)
    adaylar = sorted((PANEL / "long_form_cikti").glob("*/final.mp4"), reverse=True)
    assert adaylar, "final.mp4 yok — gece üretimi başarısız olmuş"
    is_kok = adaylar[0].parent

    if not leda_mi(is_kok):
        # 1 Ağu gecesi dersi: TTS kotası gece TÜKENIKTI, üretim Emel'e düştü.
        # Sabah 10:00'da hem Gemini hem YouTube kotası taze → baştan Leda ile üret.
        log("mevcut üretim EMEL sesli — Leda ile YENİDEN üretiliyor (kota taze)...")
        import subprocess as _sp
        r = _sp.run(["python3", "long_form_uretici.py", "--kuru", "--konu", KONU],
                    cwd=PANEL, capture_output=True, text=True, timeout=2400)
        print(r.stdout[-1500:])
        adaylar = sorted((PANEL / "long_form_cikti").glob("*/final.mp4"), reverse=True)
        is_kok = adaylar[0].parent
        if not leda_mi(is_kok):
            raise RuntimeError(
                "Yeniden üretim de Emel'e düştü — YANLIŞ SESLE YAYIN YAPILMAZ. "
                "TTS kota durumunu araştır (Emre'nin onayı: SADECE Leda).")
    senaryo = json.loads((is_kok / "senaryo.json").read_text(encoding="utf-8"))
    log(f"üretim klasörü: {is_kok.name} — '{senaryo['baslik']}'")

    from google.oauth2.credentials import Credentials
    from google.auth.transport.requests import Request
    from googleapiclient.discovery import build
    from googleapiclient.http import MediaFileUpload
    creds = Credentials.from_authorized_user_file(str(PANEL / "token.json"),
        ["https://www.googleapis.com/auth/youtube", "https://www.googleapis.com/auth/youtube.force-ssl"])
    if creds.expired and creds.refresh_token:
        creds.refresh(Request())
    yt = build("youtube", "v3", credentials=creds, cache_discovery=False)

    import long_form_uretici as lfu
    # bölüm süreleri: ses dosyasından toplam + kelime oranı (yeterli hassasiyet)
    ses = is_kok / "ses.mp3"
    toplam = lfu.sure_al(ses)
    kel = [len(b["metin"].split()) for b in senaryo["bolumler"]]
    seg = [toplam * k / sum(kel) for k in kel]
    kunyeler = json.loads((is_kok / "kunyeler.json").read_text()) if (is_kok / "kunyeler.json").exists() else []

    log("upload...")
    vid = lfu.yukle(is_kok / "final.mp4", is_kok / "kapak.jpg", senaryo, seg, kunyeler)
    log(f"✓ yayında: https://youtu.be/{vid}")

    for eski in ESKILER:
        try:
            yt.videos().update(part="status", body={"id": eski,
                "status": {"privacyStatus": "private", "selfDeclaredMadeForKids": False}}).execute()
            log(f"✓ {eski} private")
        except Exception as h:
            log(f"✗ {eski}: {str(h)[:80]}")

    lfu.konu_kaydet(KONU)
    (PANEL / "long_form_son.json").write_text(json.dumps(
        {"video_id": vid, "etiket": f"Uzun video — {senaryo['baslik'][:50]}",
         "tarih": datetime.now().strftime("%Y-%m-%d")}, ensure_ascii=False), encoding="utf-8")
    for cmd in (["git", "-c", "core.fsmonitor=false", "add", "long_form_son.json", "long_form_gecmis.json"],
                ["git", "-c", "core.fsmonitor=false", "commit", "-q", "-m", "🤖 İkarus Leda finali — state"],
                ["git", "-c", "core.fsmonitor=false", "fetch", "-q", "origin", "main"],
                ["git", "-c", "core.fsmonitor=false", "merge", "-q", "origin/main", "-m", "merge CI state"],
                ["git", "-c", "core.fsmonitor=false", "push", "-q", "origin", "HEAD:main"]):
        subprocess.run(cmd, cwd=PANEL, timeout=120)

    KILIT.write_text(vid)
    telegram(f"✅ İkarus Leda finali yayında: https://youtu.be/{vid} — 2 eski Emel kopyası gizlendi")
    log("TAMAM")


if __name__ == "__main__":
    main()
