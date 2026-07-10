"""
montajci.py — Shorts Video Montaj Üreticisi

Akış (her adım terminale yazılır):
    1) En son MP3 + senaryo TXT bulunur (ses_ciktilari/)
    2) MP3 süresi mutagen ile okunur
    3) Senaryo Gemini'ye verilir → 3 görsel arama anahtar kelimesi çıkarılır
    4) Pexels Videos API'den her keyword için 9:16 portrait HD klip indirilir
    5) Her klip MP3 süresinin 1/3'üne ffmpeg ile kırpılır + 1080×1920'a normalize
    6) ffmpeg concat ile birleştirilir
    7) MP3 ses parçası ffmpeg ile mux'lenir → final 1080×1920 MP4

Çıktı: sorts_ciktilari/shorts_<damga>.mp4
"""

import json
import os
import re
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Iterable

import imageio_ffmpeg
import requests
from mutagen.mp3 import MP3

import bridge


PANEL_KOK = Path(__file__).parent
SES_KLASORU = PANEL_KOK / "ses_ciktilari"
GECICI_KLASOR = PANEL_KOK / "gecici_video"
CIKTI_KLASOR = PANEL_KOK / "shorts_ciktilari"

PEXELS_ARAMA_URL = "https://api.pexels.com/videos/search"
HEDEF_GENISLIK = 1080
HEDEF_YUKSEKLIK = 1920
KLIP_SAYISI = 3          # 5→3: tutarlılık (viral referans tek-özne mantığı)
ISTEK_ZAMAN_ASIMI = 30
INDIRME_ZAMAN_ASIMI = 90

# 26 Haz kalite paketi:
CROSSFADE_SN = 0.45      # klipler arası yumuşak geçiş (meditatif akış)
VIDEO_CRF = "20"         # 23→20: daha net kaynak (YouTube yeniden-kodlamasına dayanıklı)
# Sinematik/mistik renk grade + vignette + çok hafif film grain (spiritüel atmosfer).
# ffmpeg yerleşik filtreler — font/dış bağımlılık yok, GH Actions'ta güvenli.
CINEMATIC_GRADE = (
    "eq=contrast=1.05:saturation=1.10:gamma=0.98,"
    "colorbalance=rm=0.04:bm=-0.04:rs=0.02:bs=-0.03,"
    "vignette=PI/5,"
    "noise=alls=4:allf=t"
)

FFMPEG = imageio_ffmpeg.get_ffmpeg_exe()

# Altyazı artık ASS dosyasında stilli geliyor (sarı keyword highlight).
# force_style GEREKMİYOR — ASS kendi [V4+ Styles] bloğunu taşır.

KEYWORD_SISTEM_PROMPTU = """You output ONLY a JSON array of exactly 3 short
visual stock-footage search queries (1–4 English words each) for a viral
YouTube Short in the SPIRITUAL / JUNG / SUFI / MYSTICAL / MEDITATION niche
(Turkish channel "Aydınlanmanın Doruk Noktası"), IN NARRATIVE ORDER.

═══ TEMA EVRENİ (ZORUNLU) ═══
Bu kanalın görsel dünyası: meditasyon, doğa, gökyüzü, yıldız, ay, gün doğumu/
batımı, mum ışığı, sis, dağ silüeti, sakin deniz/göl, yapraklar, kuş uçuşu,
gölge, ışık huzmesi, eski kitap, Buddha/derviş silüeti, sema/sufi figürü,
yoga/lotus pozu, kapalı göz/yüz, su damlası, dua eli, mandala, kristal,
karanlık → ışık geçişi, orman güneşi, çay/buhar.

═══ HARD RULE — TEMA SADAKATİ ═══
Her senaryo bir KAVRAM anlatır (ego, gölge, anlam, teslimiyet, bireyleşme,
çakra, sinkroniste, vd.). Bu kavramı bilinçaltı görsel metaforla bağla.

- Query 1 = ana DUYGU/AKSİYON görseli (meditasyon, dua, düşünen yüz, kapalı
  göz, lotus pose). Soyut kavram (ego, gölge) değil — onu temsil eden HUMAN
  veya DOĞA görseli.
- Query 2 = ATMOSFER/DOĞA (gün doğumu, sis, dağ silüeti, yıldızlı gökyüzü,
  mum, ay, sakin deniz, orman güneşi).
- Query 3 = SEMBOL/DETAY (mandala kapatma, su damlası, ışık huzmesi, eski
  kitap sayfası, çay buharı, mum alevi, yaprak düşüşü).

═══ YASAKLAR ═══
- ASLA: ofis, laptop, beyaz tahta, post-it, plaza, takım elbise, market,
  AVM, telefon ekranı, çocuk oyuncağı, sanat stüdyosu, boş oda, mutfak,
  spor, kahve dükkanı, dans kulübü.
- ASLA Query 1 olarak "blank canvas" / "empty room" / "abstract texture" /
  "fresh perspective" gibi soyut/zayıf eşleşmeler.
- Yakın çekim insan yüzü > geniş peyzaj. Hareket > durağan.

═══ KOMBİNASYON ÖRNEKLERİ ═══
- Mucizeler Kursu — anlam:
  ["woman meditation eyes closed", "golden sunrise mountain", "candle flame slow"]
- Carl Jung — gölge:
  ["man silhouette mirror", "dark forest light beam", "shadow on wall flicker"]
- Tao — boşluk:
  ["lotus position water", "still mountain lake", "single leaf falling"]
- Sufi — teslimiyet:
  ["whirling dervish slow", "stars night sky", "hand reaching light"]
- Çakra — enerji:
  ["yoga lotus sunrise", "energy light spine", "mandala painting closeup"]

İngilizce yaz (Pexels EN arar) ama TEMA spiritüel/mistik olsun.
"""


# ---------------------------------------------------------------------------
# Yardımcılar
# ---------------------------------------------------------------------------
def _adim(numara: int, mesaj: str) -> None:
    print(f"\n[montajcı · adım {numara}] {mesaj}", flush=True)


def _alt(mesaj: str) -> None:
    print(f"   ↳ {mesaj}", flush=True)


def _jamendo_anahtarini_oku() -> str:
    """Jamendo client_id — varsa müzik devreye girer, yoksa graceful skip.
    SADECE JAMENDO_CLIENT_ID arar. Pixabay key Jamendo'da geçersiz."""
    if os.environ.get("JAMENDO_CLIENT_ID"):
        return os.environ["JAMENDO_CLIENT_ID"]
    env = PANEL_KOK / ".env"
    if env.exists():
        for satir in env.read_text(encoding="utf-8").splitlines():
            if satir.startswith("JAMENDO_CLIENT_ID="):
                return satir.split("=", 1)[1].strip().strip('"').strip("'")
    return ""  # yoksa müzik atlanır


JAMENDO_URL = "https://api.jamendo.com/v3.0/tracks/"
MUZIK_SES_DB = "-22dB"  # arka plan TTS'in altında kalsın


def jamendo_muzik_indir(arama: str, hedef_mp3: Path, client_id: str) -> bool:
    """
    Jamendo Music API'den arka plan müziği indir (Creative Commons).
    arama: senaryo anahtar kelimesinden türetilmiş ton (örn 'nature ambient').
    """
    if not client_id:
        return False
    try:
        yanit = requests.get(
            JAMENDO_URL,
            params={
                "client_id": client_id,
                "format": "json",
                "limit": 20,
                "audioformat": "mp31",
                "search": arama,
                "tags": "meditation+ambient+relaxing+spiritual+calm",
                "duration_between": "25_180",
                "include": "musicinfo",
                "order": "popularity_total_desc",
            },
            timeout=ISTEK_ZAMAN_ASIMI,
        )
        yanit.raise_for_status()
        tracks = (yanit.json() or {}).get("results") or []
        if not tracks:
            # Geniş bant — tag'siz tekrar dene
            yanit = requests.get(
                JAMENDO_URL,
                params={
                    "client_id": client_id, "format": "json", "limit": 10,
                    "audioformat": "mp31", "search": arama,
                    "duration_between": "25_180",
                    "order": "popularity_total_desc",
                },
                timeout=ISTEK_ZAMAN_ASIMI,
            )
            yanit.raise_for_status()
            tracks = (yanit.json() or {}).get("results") or []
        if not tracks:
            return False
        sec = tracks[0]
        mp3_url = sec.get("audio") or sec.get("audiodownload")
        if not mp3_url:
            return False
        indir = requests.get(mp3_url, stream=True, timeout=INDIRME_ZAMAN_ASIMI)
        indir.raise_for_status()
        with open(hedef_mp3, "wb") as f:
            for parca in indir.iter_content(chunk_size=1 << 15):
                f.write(parca)
        return True
    except (requests.RequestException, KeyError, ValueError, OSError) as e:
        print(f"   ↳ Jamendo müzik indirilemedi: {e}")
        return False


# Geriye-uyum alias'ları (eski çağrılar kırılmasın)
_pixabay_anahtarini_oku = _jamendo_anahtarini_oku
pixabay_muzik_indir = jamendo_muzik_indir


def _pexels_anahtarini_oku() -> str:
    if os.environ.get("PEXELS_API_KEY"):
        return os.environ["PEXELS_API_KEY"]
    env = PANEL_KOK / ".env"
    if env.exists():
        for satir in env.read_text(encoding="utf-8").splitlines():
            if satir.startswith("PEXELS_API_KEY="):
                return satir.split("=", 1)[1].strip().strip('"').strip("'")
    raise RuntimeError(
        "PEXELS_API_KEY .env dosyasında veya environment'ta yok. "
        "https://www.pexels.com/api adresinden ücretsiz al."
    )


def _en_son_dosya(klasor: Path, desen: str) -> Path:
    adaylar = sorted(klasor.glob(desen), key=lambda p: p.stat().st_mtime, reverse=True)
    if not adaylar:
        raise FileNotFoundError(f"Bulunamadı: {klasor}/{desen}")
    return adaylar[0]


def _ffmpeg_calistir(args: list[str], cwd: str | None = None) -> None:
    sonuc = subprocess.run(
        [FFMPEG, "-hide_banner", "-loglevel", "error", "-y", *args],
        capture_output=True,
        text=True,
        cwd=cwd,
    )
    if sonuc.returncode != 0:
        raise RuntimeError(f"ffmpeg hata: {sonuc.stderr.strip()}")


# ---------------------------------------------------------------------------
# Adımlar
# ---------------------------------------------------------------------------
_DAMGA_RE = re.compile(r"_(\d{8}_\d{6})\.")


def _damga(yol: Path) -> str:
    eslesme = _DAMGA_RE.search(yol.name)
    if not eslesme:
        raise RuntimeError(f"Dosya adında zaman damgası yok: {yol.name}")
    return eslesme.group(1)


def en_son_seslendirmeyi_al() -> tuple[Path, Path, Path, float]:
    """En son MP3'ü + AYNI damgalı senaryo TXT + altyazı SRT eşleştirir."""
    mp3 = _en_son_dosya(SES_KLASORU, "seslendirme_*.mp3")
    damga = _damga(mp3)
    txt = SES_KLASORU / f"senaryo_{damga}.txt"
    ass = SES_KLASORU / f"altyazi_{damga}.ass"
    if not txt.exists():
        raise FileNotFoundError(
            f"MP3 ile eşleşen senaryo yok: {txt.name} (damga {damga})"
        )
    if not ass.exists():
        raise FileNotFoundError(
            f"MP3 ile eşleşen ASS altyazı yok: {ass.name} (damga {damga})"
        )
    sure = MP3(mp3).info.length
    return mp3, txt, ass, sure


_KEYWORD_YEDEK = ['misty mountain at dawn', 'candle flame in darkness', 'starry night sky', 'calm ocean reflection', 'sunlight through forest', 'golden abstract bokeh', 'flowing water meditation', 'sacred geometry mandala', 'fog over mountains', 'soft clouds time lapse']


def keywordleri_uret(senaryo: str) -> list[str]:
    try:
        import random
        # Her videoda FARKLI görsel açıya yönlendir → Pexels'te aynı klipler tekrar etmesin
        aci = random.choice([
            "yakın çekim doku/detay", "geniş manzara/dağ silüeti", "yıldızlı gece/kozmik",
            "su ve yansımalar", "mum/ateş/ışık huzmesi", "orman ve güneş",
            "soyut ışık/bokeh", "sis ve bulut", "el/jest/dokunuş", "mandala/kutsal geometri",
            "gün doğumu/altın saat", "yağmur/cam/damla",
        ])
        yanit = bridge.gemini_metin_uret(
            prompt=(f"Script:\n{senaryo}\n\nVISUAL DIVERSITY (ÖNEMLİ): bu sefer görselleri "
                    f"'{aci}' yönüne kaydır. En jenerik 'woman meditation' / 'misty forest' "
                    f"kliplerinden KAÇIN; her 3 keyword birbirinden ve önceki videolardan farklı, "
                    f"özgün görsel öğeler olsun."),
            sistem_promptu=KEYWORD_SISTEM_PROMPTU,
            sicaklik=0.9,   # 0.4→0.9: daha çeşitli, tekrar azalır
            max_token=512,
        )
        eslesme = re.search(r"\[.*?\]", yanit, re.DOTALL)
        if not eslesme:
            raise RuntimeError(f"Keyword çıkışı JSON dizi değil:\n{yanit}")
        keywords = json.loads(eslesme.group(0))
        if not isinstance(keywords, list) or len(keywords) != KLIP_SAYISI:
            raise RuntimeError(
                f"Tam {KLIP_SAYISI} keyword bekleniyordu, gelen: {keywords!r}"
            )
        return [str(k).strip() for k in keywords]
    except Exception as _h:
        import random as _r
        print(f"[montajci] keyword Gemini düştü ({str(_h)[:90]}) → niş yedek keyword", flush=True)
        return _r.sample(_KEYWORD_YEDEK, KLIP_SAYISI)


WIKIMEDIA_API = "https://commons.wikimedia.org/w/api.php"


def wikimedia_foto_indir(keyword: str, foto_hedef: Path) -> dict:
    """Wikimedia Commons'tan keyword için en alakalı portrait fotoğrafı indir."""
    sonuc = requests.get(
        WIKIMEDIA_API,
        params={
            "action": "query",
            "format": "json",
            "generator": "search",
            "gsrsearch": f"{keyword} filetype:bitmap",
            "gsrnamespace": "6",
            "gsrlimit": 8,
            "prop": "imageinfo",
            "iiprop": "url|size|mime",
            "iiurlwidth": "1080",
        },
        headers={"User-Agent": "MR-Studio-Montajci/1.0 (https://urunya.com)"},
        timeout=ISTEK_ZAMAN_ASIMI,
    )
    sonuc.raise_for_status()
    sayfalar = (sonuc.json().get("query") or {}).get("pages") or {}
    # en iyi: yüksekliği genişliğinden büyük (portrait), JPG/PNG
    aday = None
    for s in sayfalar.values():
        ii = (s.get("imageinfo") or [{}])[0]
        if not ii:
            continue
        mime = ii.get("mime", "")
        if not mime.startswith("image/"):
            continue
        w, h = ii.get("width", 0), ii.get("height", 0)
        if h <= w:
            continue
        if aday is None or h > aday["h"]:
            aday = {"url": ii.get("thumburl") or ii.get("url"), "w": w, "h": h, "title": s.get("title", "")}
    if not aday:
        raise RuntimeError(f"'{keyword}' için Wikimedia portrait foto yok.")
    indirme = requests.get(
        aday["url"], stream=True, timeout=INDIRME_ZAMAN_ASIMI,
        headers={"User-Agent": "MR-Studio-Montajci/1.0"},
    )
    indirme.raise_for_status()
    with open(foto_hedef, "wb") as f:
        for parca in indirme.iter_content(chunk_size=1 << 15):
            f.write(parca)
    return {"keyword": keyword, "url": aday["url"], "boyut": (aday["w"], aday["h"]), "kaynak": "wikimedia", "title": aday["title"]}


def foto_video_yap(foto: Path, hedef: Path, sure_sn: float) -> None:
    """Tek foto → Ken Burns zoom'lu video (Pexels alternatifi)."""
    _ffmpeg_calistir(
        [
            "-loop", "1",
            "-i", str(foto),
            "-t", f"{sure_sn:.3f}",
            "-vf",
            f"scale={HEDEF_GENISLIK*2}:{HEDEF_YUKSEKLIK*2}:force_original_aspect_ratio=increase,"
            f"crop={HEDEF_GENISLIK*2}:{HEDEF_YUKSEKLIK*2},"
            f"zoompan=z='min(zoom+0.0007,1.20)':d=1:"
            f"x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':"
            f"s={HEDEF_GENISLIK}x{HEDEF_YUKSEKLIK}:fps=30,setsar=1,"
            f"{CINEMATIC_GRADE}",
            "-r", "30", "-an",
            "-c:v", "libx264", "-preset", "veryfast", "-crf", VIDEO_CRF,
            "-pix_fmt", "yuv420p",
            str(hedef),
        ]
    )


def _gorsel_qc_gecer_mi(klip_yolu: Path, keyword: str, baslik: str = "") -> bool:
    """Klibin ilk karesini Gemini Vision'a sor — konuyla eşleşir mi?"""
    try:
        import gorsel_qc
        import imageio_ffmpeg
        import subprocess, tempfile
        ffmpeg_bin = imageio_ffmpeg.get_ffmpeg_exe()
        tmp_png = Path(tempfile.mktemp(suffix=".png"))
        # 1. saniyenin karesini al
        subprocess.run(
            [ffmpeg_bin, "-y", "-ss", "1", "-i", str(klip_yolu),
             "-vframes", "1", "-q:v", "2", str(tmp_png)],
            capture_output=True, timeout=20,
        )
        if not tmp_png.exists():
            return True  # frame çıkmazsa kontrolsüz geç
        sonuc = gorsel_qc.gorsel_konuyla_eslesir_mi(tmp_png, keyword, baslik, esik_skor=7)
        tmp_png.unlink(missing_ok=True)
        return sonuc
    except Exception as h:
        print(f"   ↳ QC atlandı: {str(h)[:80]}")
        return True


def gemini_gorsel_uret(keyword: str, hedef_png: Path, baslik: str = "") -> bool:
    """Spiritüel/mistik temalı ÖZGÜN dikey görsel üret (gemini-2.5-flash-image).
    Pexels uygun klip bulamayınca devreye girer → niş'e %100 uygun görsel."""
    try:
        import bridge
        from google.genai import types as _gt
        client = bridge._client()
    except Exception as h:
        print(f"   ↳ Gemini görsel altyapı yok: {str(h)[:80]}")
        return False
    prompt = (
        f"Cinematic vertical 9:16 spiritual and mystical image for a calm meditation "
        f"video. Theme: {keyword}. Mood: serene, warm golden mystical light, soft "
        f"ethereal mist, Jungian/sufi spiritual atmosphere, peaceful. Photorealistic, "
        f"atmospheric, cinematic color. NO text, NO words, NO watermark, NO logo."
    )
    import time as _t
    gorsel_model = "gemini-2.5-flash-image"  # stil korunur; 404 olursa 3.1 halefine geçer
    for deneme in range(2):
        try:
            r = client.models.generate_content(
                model=gorsel_model, contents=prompt,
                config=_gt.GenerateContentConfig(response_modalities=["IMAGE", "TEXT"]),
            )
            for p in r.candidates[0].content.parts:
                if getattr(p, "inline_data", None) and p.inline_data.data:
                    with open(hedef_png, "wb") as f:
                        f.write(p.inline_data.data)
                    return True
        except Exception as h:
            print(f"   ↳ Gemini görsel hata ({deneme+1}/2): {str(h)[:100]}")
            if "404" in str(h) or "no longer available" in str(h):
                gorsel_model = "gemini-3.1-flash-image"  # 10 Tem: 2.5-image emekli olursa halef
            _t.sleep(3)
    return False


def gorsel_kaynak_indir(keyword: str, hedef: Path, sure_sn: float, api_key: str,
                         baslik: str = "") -> dict:
    """
    Önce Pexels video; başarısız olursa Wikimedia foto → Ken Burns video.
    Faz 7: Gemini Vision QC — Pexels klibi konuyla eşleşmiyorsa Wikimedia'ya düş.
    Wikimedia da fail olursa Pexels'i ZORLA kullanır (pipeline'ı koparma).
    """
    # 1. Pexels deneme (QC ile)
    pexels_bilgi = None
    qc_passed = True
    try:
        pexels_bilgi = pexels_video_indir(keyword, hedef, api_key)
        if hedef.exists() and not _gorsel_qc_gecer_mi(hedef, keyword, baslik):
            print(f"   ↳ Pexels '{keyword}' konuyla eşleşmedi (QC red) — Wikimedia denenecek")
            # Backup'a kaydet, sonra zorla geri yüklemek için
            backup = hedef.with_suffix(".pexels_backup.mp4")
            import shutil as _sh
            _sh.copy(str(hedef), str(backup))
            qc_passed = False
            hedef.unlink(missing_ok=True)
    except (requests.RequestException, RuntimeError) as e:
        print(f"   ↳ Pexels '{keyword}' bulunamadı ({str(e)[:80]}) → Wikimedia denenecek")
        qc_passed = False

    if qc_passed and pexels_bilgi:
        return pexels_bilgi

    # 2. AI ÖZGÜN GÖRSEL (gemini-2.5-flash-image) — niş'e %100 uygun, Wikimedia'dan
    #    daha temalı. Pexels QC'den geçemeyince devreye girer.
    ai_png = hedef.with_suffix(".ai.png")
    try:
        if gemini_gorsel_uret(keyword, ai_png, baslik):
            foto_video_yap(ai_png, hedef, sure_sn)
            ai_png.unlink(missing_ok=True)
            print(f"   ↳ AI özgün görsel üretildi (Gemini) — '{keyword}'")
            return {"sure": sure_sn, "fotograf": f"AI-Gemini: {keyword}",
                    "boyut": (HEDEF_GENISLIK, HEDEF_YUKSEKLIK)}
    except Exception as e:
        print(f"   ↳ AI görsel video'ya çevrilemedi ({str(e)[:80]}) → Wikimedia")

    # 3. Wikimedia deneme
    foto = hedef.with_suffix(".jpg")
    try:
        bilgi = wikimedia_foto_indir(keyword, foto)
        foto_video_yap(foto, hedef, sure_sn)
        bilgi["sure"] = sure_sn
        bilgi["fotograf"] = f"Wikimedia: {bilgi.get('title','?')[:30]}"
        return bilgi
    except Exception as e:
        print(f"   ↳ Wikimedia '{keyword}' de fail ({str(e)[:80]})")

    # 3. Son çare: Pexels backup'ı zorla kullan (QC red olsa bile)
    backup = hedef.with_suffix(".pexels_backup.mp4")
    if backup.exists():
        print(f"   ↳ Son çare: Pexels QC-red klibi zorla kullan")
        import shutil as _sh
        _sh.move(str(backup), str(hedef))
        return pexels_bilgi or {"sure": sure_sn, "fotograf": f"Pexels(QC-red): {keyword}",
                                "boyut": (HEDEF_GENISLIK, HEDEF_YUKSEKLIK)}

    # 4. Hiç bulunamadıysa exception
    raise RuntimeError(f"'{keyword}' için ne Pexels ne Wikimedia bulundu")


def pexels_video_indir(keyword: str, hedef: Path, api_key: str) -> dict:
    yanit = requests.get(
        PEXELS_ARAMA_URL,
        params={"query": keyword, "orientation": "portrait", "size": "medium", "per_page": 8},
        headers={"Authorization": api_key},
        timeout=ISTEK_ZAMAN_ASIMI,
    )
    yanit.raise_for_status()
    veri = yanit.json()
    videolar = veri.get("videos") or []
    if not videolar:
        raise RuntimeError(f"'{keyword}' için Pexels'te portrait video yok.")

    # Aynı keyword her seferinde aynı klibi vermesin → sonuçları karıştır (çeşitlilik)
    import random
    random.shuffle(videolar)

    en_iyi_dosya = None
    en_iyi_video = None
    for v in videolar:
        for f in v.get("video_files", []):
            if f.get("width", 0) < f.get("height", 0):  # portrait emniyet
                if en_iyi_dosya is None or (f.get("height", 0) > en_iyi_dosya.get("height", 0)):
                    en_iyi_dosya = f
                    en_iyi_video = v
        if en_iyi_dosya:
            break

    if not en_iyi_dosya:
        raise RuntimeError(f"'{keyword}' için portrait dosyası yok.")

    indirme = requests.get(en_iyi_dosya["link"], stream=True, timeout=INDIRME_ZAMAN_ASIMI)
    indirme.raise_for_status()
    with open(hedef, "wb") as f:
        for parca in indirme.iter_content(chunk_size=1 << 15):
            f.write(parca)

    return {
        "keyword": keyword,
        "url": en_iyi_dosya["link"],
        "boyut": (en_iyi_dosya.get("width"), en_iyi_dosya.get("height")),
        "sure": en_iyi_video.get("duration"),
        "fotograf": en_iyi_video.get("user", {}).get("name", "?"),
    }


def klip_kirp_normalize(kaynak: Path, hedef: Path, sure_sn: float) -> None:
    """
    Kaynağı 1080×1920'a normalize eder + KEN BURNS yavaş içe-zoom (statik
    stok bile sinematik/dinamik görünür → retention). TAM `sure_sn` saniye;
    kaynak yetmezse -stream_loop -1 ile döngüye alınır.
    """
    filtre = (
        f"scale={HEDEF_GENISLIK}:{HEDEF_YUKSEKLIK}:force_original_aspect_ratio=increase,"
        f"crop={HEDEF_GENISLIK}:{HEDEF_YUKSEKLIK},"
        f"zoompan=z='min(zoom+0.0007,1.15)':d=1:"
        f"x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':"
        f"s={HEDEF_GENISLIK}x{HEDEF_YUKSEKLIK}:fps=30,"
        f"setsar=1,"
        f"{CINEMATIC_GRADE}"
    )
    _ffmpeg_calistir(
        [
            "-stream_loop", "-1",
            "-i", str(kaynak),
            "-t", f"{sure_sn:.3f}",
            "-vf", filtre,
            "-r", "30",
            "-an",
            "-c:v", "libx264", "-preset", "veryfast", "-crf", VIDEO_CRF,
            "-pix_fmt", "yuv420p",
            str(hedef),
        ]
    )


def klipleri_birlestir(klipler: list[Path], hedef: Path,
                       klip_sure: float | None = None,
                       crossfade: float = CROSSFADE_SN) -> None:
    """
    Klipleri birleştirir. klip_sure verilirse xfade ile YUMUŞAK GEÇİŞ
    (meditatif akış); yoksa eski sert-kesim concat (geriye-uyum).
    Tüm klipler eşit `klip_sure` uzunlukta (klip_kirp_normalize -t ile sabit).
    Toplam süre korunur: ana akış klip süresini crossfade'e göre uzatır.
    """
    n = len(klipler)
    if n == 1:
        shutil.copyfile(klipler[0], hedef)
        return

    if not klip_sure or crossfade <= 0:
        # Eski yöntem — sert kesim (re-encode yok)
        liste = GECICI_KLASOR / "concat_list.txt"
        liste.write_text("\n".join(f"file '{p.resolve()}'" for p in klipler), encoding="utf-8")
        _ffmpeg_calistir(["-f", "concat", "-safe", "0", "-i", str(liste), "-c", "copy", str(hedef)])
        return

    # xfade zinciri: offset_i = i*(L - d)
    L, d = klip_sure, crossfade
    girdiler: list[str] = []
    for p in klipler:
        girdiler += ["-i", str(p)]
    onceki = "[0:v]"
    fc: list[str] = []
    for i in range(1, n):
        cikti = "[vout]" if i == n - 1 else f"[x{i}]"
        offset = i * (L - d)
        fc.append(f"{onceki}[{i}:v]xfade=transition=fade:duration={d:.3f}:offset={offset:.3f}{cikti}")
        onceki = cikti
    _ffmpeg_calistir(
        girdiler + [
            "-filter_complex", ";".join(fc),
            "-map", "[vout]",
            "-r", "30", "-an",
            "-c:v", "libx264", "-preset", "veryfast", "-crf", VIDEO_CRF,
            "-pix_fmt", "yuv420p",
            str(hedef),
        ]
    )


def _hook_ass_satiri(hook_metin: str) -> str:
    """Üst-orta büyük başlık (libass — font güvenli).
    Normal: ilk 2.6sn hook. SEDA modu (MOD_SEDA): tüm video boyunca KALICI
    dekoratif GOLD başlık (oracle/etkileşim sorusu) — @sedademirdogenn tarzı."""
    seda = bool(os.environ.get("MOD_SEDA"))
    t = " ".join(hook_metin.replace("{", "").replace("}", "").split())
    if seda:
        # Başlık: ilk cümlenin vurucu kısmı. Virgülden önceki bölüm yeterince
        # uzunsa onu al (daha temiz başlık). Kelime sınırında ~50 char'a kır.
        ham = t.split(".")[0].strip()
        if "," in ham and len(ham.split(",")[0].split()) >= 4:
            ham = ham.split(",")[0].strip()
        if len(ham) > 50:
            ham = ham[:50].rsplit(" ", 1)[0]
        ilk = ham.strip()
        if not ilk:
            return ""
        # an8=üst-orta, KALICI (0→9:59), gold metin + kalın koyu kenar (kutu hissi)
        return (f"Dialogue: 1,0:00:00.00,0:09:59.00,Pop,,0,0,0,,"
                f"{{\\an8\\fs60\\b1\\bord9\\shad3\\1c&H30C8F5&\\3c&H101010&\\fad(300,0)}}{ilk}\n")
    # Normal: ilk cümle / ilk ~7 kelime, max 58 karakter, 2.6sn
    ilk = t.split(".")[0].strip()
    kelime = ilk.split()
    if len(kelime) > 7:
        ilk = " ".join(kelime[:7])
    ilk = ilk[:58].strip()
    if not ilk:
        return ""
    return (f"Dialogue: 1,0:00:00.00,0:00:02.60,Pop,,0,0,0,,"
            f"{{\\an8\\fs74\\b1\\bord6\\shad2\\1c&H30F5F8&\\3c&H000000&\\fad(250,450)}}{ilk}\n")


def altyazi_yak(video: Path, ass: Path, hedef: Path, hook_metin: str = "") -> None:
    """
    ASS altyazıyı videoya GÖMER (libass). ASS kendi stilini (sarı keyword
    highlight) taşır — force_style gerekmez. Türkçe/boşluklu path sorununu
    aşmak için dosyalar geçici klasöre ASCII adla kopyalanır.
    hook_metin verilirse ilk 2.6sn üst-orta büyük hook overlay eklenir.
    """
    yerel_ass = GECICI_KLASOR / "altyazi_aktif.ass"
    shutil.copyfile(ass, yerel_ass)
    # Hook satırını ASS'e enjekte et (dosya sonuna; libass layer'a göre çizer)
    if hook_metin:
        hs = _hook_ass_satiri(hook_metin)
        if hs:
            with open(yerel_ass, "a", encoding="utf-8") as f:
                f.write(hs)
    yerel_video = GECICI_KLASOR / "altyazi_girdi.mp4"
    shutil.copyfile(video, yerel_video)
    yerel_cikti = GECICI_KLASOR / "altyazi_cikti.mp4"
    _ffmpeg_calistir(
        [
            "-i", "altyazi_girdi.mp4",
            "-vf", "ass=altyazi_aktif.ass",
            "-c:v", "libx264", "-preset", "medium", "-crf", VIDEO_CRF,
            "-pix_fmt", "yuv420p", "-an",
            "altyazi_cikti.mp4",
        ],
        cwd=str(GECICI_KLASOR),
    )
    shutil.move(str(yerel_cikti), str(hedef))


def ses_mux(video: Path, mp3: Path, hedef: Path, muzik: Path | None = None) -> None:
    """
    Video + TTS sesi (+ varsa arka plan müziği) → final MP4.
    Arka plan müzik TTS'in -22dB altında, aynı süreye kırpılır.
    """
    if muzik and muzik.exists():
        _ffmpeg_calistir(
            [
                "-i", str(video),
                "-i", str(mp3),
                "-i", str(muzik),
                "-filter_complex",
                f"[2:a]volume={MUZIK_SES_DB},aloop=loop=-1:size=2e+09[bg];"
                "[1:a][bg]amix=inputs=2:duration=first:dropout_transition=2[aout]",
                "-map", "0:v", "-map", "[aout]",
                "-c:v", "copy",
                "-c:a", "aac", "-b:a", "192k",
                "-shortest",
                "-movflags", "+faststart",
                str(hedef),
            ]
        )
    else:
        _ffmpeg_calistir(
            [
                "-i", str(video),
                "-i", str(mp3),
                "-c:v", "copy",
                "-c:a", "aac", "-b:a", "192k",
                "-shortest",
                "-movflags", "+faststart",
                str(hedef),
            ]
        )


# ---------------------------------------------------------------------------
# Ana akış
# ---------------------------------------------------------------------------
def main() -> int:
    try:
        GECICI_KLASOR.mkdir(exist_ok=True)
        CIKTI_KLASOR.mkdir(exist_ok=True)

        _adim(1, "En son seslendirme bulunuyor...")
        mp3, txt, ass, sure_sn = en_son_seslendirmeyi_al()
        damga = _damga(mp3)  # final MP4 kaynak MP3 ile aynı damgayı taşısın
        _alt(f"MP3:    {mp3.name}")
        _alt(f"TXT:    {txt.name}")
        _alt(f"ASS:    {ass.name}")
        _alt(f"Süre:   {sure_sn:.2f} saniye")

        senaryo = txt.read_text(encoding="utf-8").strip()
        # Crossfade telafisi: her klip biraz uzun → xfade örtüşmesi toplamı korur.
        # toplam = n*L - (n-1)*d = sure_sn  →  L = (sure_sn + (n-1)*d)/n
        klip_basina = (sure_sn + (KLIP_SAYISI - 1) * CROSSFADE_SN) / KLIP_SAYISI

        _adim(2, "Pexels API anahtarı kontrol ediliyor...")
        api_key = _pexels_anahtarini_oku()
        _alt(f"PEXELS_API_KEY uzunluğu: {len(api_key)} karakter ✓")

        _adim(3, "Senaryo Gemini'ye → 3 görsel arama keyword'ü...")
        keywords = keywordleri_uret(senaryo)
        for k in keywords:
            _alt(k)

        _adim(4, f"Görsel kaynak (Pexels → Wikimedia fallback) — klip başına {klip_basina:.2f} sn...")
        ham_klipler: list[Path] = []
        for sira, kw in enumerate(keywords, 1):
            ham = GECICI_KLASOR / f"ham_{damga}_{sira}.mp4"
            bilgi = gorsel_kaynak_indir(kw, ham, klip_basina, api_key)
            ham_klipler.append(ham)
            _boyut = bilgi.get("boyut", ("?", "?"))
            _alt(
                f"#{sira} '{kw}' → {_boyut[0]}×{_boyut[1]}, "
                f"kaynak: {bilgi.get('fotograf','?')} "
                f"({ham.stat().st_size/1024:.0f} KB)"
            )

        _adim(5, f"Her klip 1080×1920'a kırpılıp normalize ediliyor...")
        normal_klipler: list[Path] = []
        for sira, ham in enumerate(ham_klipler, 1):
            normal = GECICI_KLASOR / f"normal_{damga}_{sira}.mp4"
            klip_kirp_normalize(ham, normal, klip_basina)
            normal_klipler.append(normal)
            _alt(f"#{sira} → {normal.name} ({normal.stat().st_size/1024:.0f} KB)")

        _adim(6, "Klipler xfade ile yumuşak geçişle birleştiriliyor...")
        birlesik = GECICI_KLASOR / f"birlesik_{damga}.mp4"
        klipleri_birlestir(normal_klipler, birlesik, klip_sure=klip_basina)
        _alt(f"birlesik → {birlesik.name} ({birlesik.stat().st_size/1024:.0f} KB)")

        _adim(7, "ASS altyazı (sarı keyword highlight) videoya gömülüyor...")
        altyazili = GECICI_KLASOR / f"altyazili_{damga}.mp4"
        altyazi_yak(birlesik, ass, altyazili, hook_metin=senaryo)
        _alt(f"altyazılı → {altyazili.name} ({altyazili.stat().st_size/1024:.0f} KB)")

        _adim(8, "Arka plan müzik — önce Suno kütüphane, sonra Jamendo CC fallback...")
        muzik_yolu = GECICI_KLASOR / f"bgm_{damga}.mp3"
        muzik_var = False

        # 1. öncelik: Suno Pro elle üretilmiş kütüphane (suno_tracks/*.mp3)
        try:
            import suno_kutuphane
            suno_yolu = suno_kutuphane.track_sec(keywords[0] if keywords else None)
            if suno_yolu and Path(suno_yolu).exists():
                # NOT: 'shutil' modül seviyesinde import edili — local 'import shutil'
                # kullanma; Python local-scope shadowing modül sonundaki shutil.rmtree'yi
                # bozar (UnboundLocalError).
                import shutil as _shutil
                _shutil.copy(suno_yolu, muzik_yolu)
                muzik_var = True
                _alt(f"Müzik (Suno): {Path(suno_yolu).name} → {muzik_yolu.name}")
        except Exception as h:
            _alt(f"Suno kütüphane atlandı: {h}")

        # 2. fallback: Jamendo CC API
        if not muzik_var:
            muzik_key = _jamendo_anahtarini_oku()
            if not muzik_key:
                _alt("Müzik atlandı: Jamendo key yok + Suno kütüphane boş.")
            else:
                muzik_arama = (keywords[0] if keywords else "nature") + " ambient"
                _alt(f"DEBUG: Jamendo arama sorgusu='{muzik_arama}'")
                muzik_var = jamendo_muzik_indir(muzik_arama, muzik_yolu, muzik_key)
                if muzik_var:
                    _alt(f"Müzik (Jamendo): '{muzik_arama}' → {muzik_yolu.name} ({muzik_yolu.stat().st_size/1024:.0f} KB)")
                else:
                    _alt(f"Müzik atlandı: Jamendo aramasından dosya gelmedi.")

        _adim(9, "TTS + müzik mux'lanıyor → final MP4...")
        final = CIKTI_KLASOR / f"shorts_{damga}.mp4"
        ses_mux(altyazili, mp3, final, muzik_yolu if muzik_var else None)
        boyut_mb = final.stat().st_size / (1024 * 1024)
        _alt(f"FİNAL: {final.name} ({boyut_mb:.2f} MB)")

        print(f"\n[montajcı] HAZIR ✓  → {final}")
        return 0

    except FileNotFoundError as hata:
        print(f"[montajcı] Veri eksik: {hata}", file=sys.stderr)
        return 2
    except requests.RequestException as hata:
        print(f"[montajcı] Pexels/HTTP hatası: {hata}", file=sys.stderr)
        return 3
    except RuntimeError as hata:
        print(f"[montajcı] Çalışma hatası: {hata}", file=sys.stderr)
        return 4
    except OSError as hata:
        print(f"[montajcı] Dosya/sistem hatası: {hata}", file=sys.stderr)
        return 5
    finally:
        if GECICI_KLASOR.exists():
            shutil.rmtree(GECICI_KLASOR, ignore_errors=True)
            print(f"[montajcı] Geçici klasör temizlendi: {GECICI_KLASOR.name}", flush=True)


if __name__ == "__main__":
    sys.exit(main())
