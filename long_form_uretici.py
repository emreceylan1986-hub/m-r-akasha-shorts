#!/usr/bin/env python3
"""
long_form_uretici.py — Akasha haftalık long-form motoru (31 Tem 2026).

Demeter videosunun (CFjcA6bYtuc, 24 Tem) kanıtlanmış akışının otomasyonu:
  mit/arketip konusu (Gemini) → bölümlü Türkçe anlatım + bölüm başına
  Wikimedia tablo sorgusu → KAMU MALI klasik tablolar (lisans kontrollü)
  → Emel TTS → blur-pad + Ken Burns render (1920x1080) → PIL kapak
  → YouTube upload (bölüm zaman damgaları + tablo künyeleri).

Müzik BİLEREK yok — 20 Tem Jamendo Content-ID dersi (sf3WFM8aflU bloğu).

Kullanım:
    python3 long_form_uretici.py                # rotasyondan konu
    python3 long_form_uretici.py --konu "İkarus"
    python3 long_form_uretici.py --kuru         # upload yok
    python3 long_form_uretici.py --kuru --kisa  # 2 bölümlük hızlı uçtan uca test
"""
import argparse
import asyncio
import json
import re
import statistics
import subprocess
import time
import urllib.parse
import urllib.request
from datetime import datetime
from pathlib import Path

import bridge

PANEL = Path(__file__).parent
GECMIS = PANEL / "long_form_gecmis.json"
CIKTI_KOK = PANEL / "long_form_cikti"
TOKEN = PANEL / "token.json"

SES = "tr-TR-EmelNeural"
COMMONS_API = "https://commons.wikimedia.org/w/api.php"
HDR = {"User-Agent": "AkashaLongform/1.0 (contact: emreceylan1986@gmail.com)"}
KABUL_LISANS = ("public domain", "pd", "cc0", "cc by")  # başlangıç eşleşmesi, küçük harf

# Konu tohumları — Gemini tıkanırsa/tekrar üretirse buradan (Demeter formatının kanıtlı akrabaları)
TOHUM_KONULAR = [
    "İkarus'un düşüşü: hırsın ve sınır tanımamanın bedeli",
    "Narkissos ve Ekho: kendine hayranlığın yalnızlığı",
    "Orpheus ile Eurydike: geriye bakmanın bedeli",
    "Sisifos: anlamsız görünen emeğin gizli anlamı",
    "Psykhe ile Eros: ruhun aşk sınavları",
    "Prometheus: ateşi çalmanın ve bedel ödemenin miti",
    "İnanna'nın yeraltına inişi: soyunarak derinleşmek",
    "Persephone'nin narı: geri dönüşü olmayan dönüşümler",
    "Kronos: zamanın çocuklarını yutması",
    "Pandora: umudun kutuda kalması",
]

SENARYO_SISTEM = """Sen "Aydınlanmanın Doruk Noktası" kanalının long-form anlatıcısısın.
Niş: Yunan/dünya mitolojisi + Carl Jung arketipleri + tasavvuf bilgeliği.
Ton: Yunus Emre + Mevlana sıcaklığı — sakin, derin, bilge; "sen" hitabı yumuşak.
Dil: %100 TÜRKÇE.

Sana bir mit/konu verilecek. Çıktın SADECE şu JSON:
{
  "baslik": "İlk Harfleri Büyük, 45-75 karakter, Türkçe başlık",
  "aciklama_ozeti": "2 cümlelik video açıklaması",
  "etiketler": ["8-12 Türkçe etiket"],
  "bolumler": [
    {
      "ad": "bölümün 2-4 kelimelik adı (zaman damgası için)",
      "metin": "bu bölümün anlatım metni",
      "tablo_arama": "English Wikimedia Commons search for a CLASSICAL PAINTING matching this scene, e.g. 'Icarus fall painting Bruegel'"
    }
  ]
}

KURALLAR:
- {bolum_sayisi} bölüm; toplam {hedef_kelime} kelime (±%10). Bölümler dengeli.
- Yapı: kısa merak uyandıran giriş → mitin hikâyesi sahne sahne → Jung/arketip
  yorumu → izleyiciye dönen kapanış sorusu + tek cümle yumuşak abone daveti.
- Hikâyeyi SAHNE SAHNE anlat (Demeter videosu formatı): her bölüm görsel bir ana
  oturmalı ki tablo eşleşsin.
- tablo_arama: ünlü, ESKİ (1900 öncesi ağırlıklı) ressamların bilinen tablolarını
  hedefle — kamu malı olma ihtimali yüksek olanlar. Fotoğraf/heykel değil, tablo.
- Uydurma yok: mitin bilinen anlatısına sadık kal; Jung yorumunda "Jung'a göre" de.
- Kapanışta abartısız tek davet: "abone olarak bu yolculuğa eşlik edebilirsin" tonu."""


def log(m):
    print(f"[longform] {m}", flush=True)


# ── KONU ─────────────────────────────────────────────────────────────────────
def gecmis_oku() -> list:
    try:
        return json.loads(GECMIS.read_text(encoding="utf-8"))
    except Exception:
        return []


def konu_sec(zorla: str | None) -> str:
    if zorla:
        return zorla
    eski = set(gecmis_oku())
    for k in TOHUM_KONULAR:
        if k not in eski:
            return k
    # tohumlar bitti → Gemini'den taze konu
    cevap = bridge.gemini_metin_uret(
        prompt=("Şu konular işlendi:\n" + "\n".join(sorted(eski)) +
                "\n\nAynı formatta (mit adı: tek cümle tema) YENİ, işlenmemiş bir "
                "mitoloji/arketip long-form konusu öner. SADECE konuyu yaz."),
        sistem_promptu=SENARYO_SISTEM.replace("{bolum_sayisi}", "10").replace("{hedef_kelime}", "1000"),
        sicaklik=0.9, max_token=100)
    return cevap.strip().strip('"')


def konu_kaydet(konu: str):
    g = gecmis_oku()
    g.append(konu)
    GECMIS.write_text(json.dumps(g, ensure_ascii=False, indent=2), encoding="utf-8")


# ── SENARYO ──────────────────────────────────────────────────────────────────
def _bolum_normalize(b, i: int) -> dict:
    """Gemini alan adlarında kaprisli olabiliyor (31 Tem run 30626216760:
    KeyError 'metin'). Eş anlamlıları tek şemaya indir; string gelirse sar."""
    if isinstance(b, str):
        return {"ad": f"Bölüm {i}", "metin": b, "tablo_arama": ""}
    metin = next((b[k] for k in ("metin", "text", "anlatim", "anlatım", "icerik",
                                 "içerik", "content", "paragraf", "narration") if b.get(k)), "")
    arama = next((b[k] for k in ("tablo_arama", "arama", "search", "painting_search",
                                 "wikimedia_search", "gorsel_arama") if b.get(k)), "")
    ad = next((b[k] for k in ("ad", "baslik", "başlık", "name", "title") if b.get(k)), f"Bölüm {i}")
    return {"ad": str(ad)[:40], "metin": str(metin), "tablo_arama": str(arama)}


def senaryo_uret(konu: str, kisa: bool) -> dict:
    bolum, kelime = (2, 130) if kisa else (10, 1050)
    son_hata = None
    for deneme in range(3):
        ham = bridge.gemini_metin_uret(
            prompt=f"Konu: {konu}\n\nŞimdi JSON'u üret." + (
                "\nDİKKAT: her bölüm objesi TAM OLARAK şu alanları taşımalı: "
                "ad, metin, tablo_arama. Her bölümün metni EN AZ 100 kelime olmalı; "
                "hiçbir bölümü boş bırakma." if deneme else ""),
            sistem_promptu=SENARYO_SISTEM.replace("{bolum_sayisi}", str(bolum)).replace("{hedef_kelime}", str(kelime)),
            sicaklik=0.8, max_token=8192)
        ham = re.sub(r"^```(json)?|```$", "", ham.strip(), flags=re.M).strip()
        try:
            s = json.loads(ham)
            s["bolumler"] = [_bolum_normalize(b, i)
                             for i, b in enumerate(s.get("bolumler") or [], 1)]
            # tolerans: 1-2 boş bölüm varsa düş, kalan yeterliyse kabul (tam ret israf)
            s["bolumler"] = [b for b in s["bolumler"] if b["metin"].strip()]
            toplam_kelime = sum(len(b["metin"].split()) for b in s["bolumler"])
            alt_sinir = 60 if kisa else 700
            assert s.get("baslik") and len(s["bolumler"]) >= (2 if kisa else 6), \
                f"bölüm yetersiz: {len(s['bolumler'])}"
            assert toplam_kelime >= alt_sinir, f"kısa kaldı: {toplam_kelime}<{alt_sinir} kelime"
            return s
        except Exception as h:
            son_hata = h
            log(f"  senaryo şema hatası (deneme {deneme+1}/3): {str(h)[:100]}")
            log(f"  ham ilk 200: {ham[:200]!r}")
    raise RuntimeError(f"Senaryo 3 denemede şemaya oturmadı: {son_hata}")


# ── WIKIMEDIA TABLO ──────────────────────────────────────────────────────────
def _commons_get(params: dict) -> dict:
    qs = urllib.parse.urlencode({**params, "format": "json"})
    req = urllib.request.Request(f"{COMMONS_API}?{qs}", headers=HDR)
    return json.loads(urllib.request.urlopen(req, timeout=30).read().decode())


def tablo_indir(sorgu: str, hedef: Path) -> dict | None:
    """Lisans-kontrollü tablo indirme. Dönüş: {dosya, sanatci} | None."""
    for deneme_sorgu in (sorgu, sorgu.rsplit(" ", 1)[0] + " painting"):
        try:
            r = _commons_get({"action": "query", "list": "search",
                              "srsearch": deneme_sorgu, "srnamespace": 6, "srlimit": 5})
            adaylar = [h["title"] for h in r["query"]["search"]
                       if h["title"].lower().endswith((".jpg", ".jpeg", ".png"))]
        except Exception as h:
            log(f"  arama hatası ({str(h)[:60]}) — 8s bekle"); time.sleep(8); adaylar = []
        for dosya in adaylar[:3]:
            try:
                time.sleep(2)  # Commons rate-limit nezaketi
                r2 = _commons_get({"action": "query", "titles": dosya, "prop": "imageinfo",
                                   "iiprop": "url|extmetadata", "iiurlwidth": 1600})
                sayfa = list(r2["query"]["pages"].values())[0]
                if "imageinfo" not in sayfa:
                    continue
                info = sayfa["imageinfo"][0]
                meta = info.get("extmetadata", {})
                lisans = str(meta.get("LicenseShortName", {}).get("value", "")).lower()
                if lisans and not lisans.startswith(KABUL_LISANS):
                    log(f"  lisans reddi: {dosya[:40]} ({lisans[:30]})"); continue
                img = urllib.request.urlopen(
                    urllib.request.Request(info.get("thumburl") or info["url"], headers=HDR),
                    timeout=120).read()
                if len(img) < 40_000:
                    continue
                hedef.write_bytes(img)
                sanatci = re.sub(r"<[^>]+>", "", str(meta.get("Artist", {}).get("value", ""))).strip()
                return {"dosya": dosya.replace("File:", ""), "sanatci": sanatci[:60]}
            except Exception as h:
                log(f"  indirme hatası: {str(h)[:60]}"); time.sleep(5)
    return None


# ── TTS + RENDER ─────────────────────────────────────────────────────────────
def tts_uret(metin: str, mp3: Path):
    """edge-tts Emel — YEDEK yol (Leda başarısızsa)."""
    async def _u():
        await edge_tts_modul.Communicate(metin, SES, rate="-5%").save(str(mp3))
    import edge_tts as edge_tts_modul
    asyncio.run(_u())


def tts_bolumlu_leda(bolumler: list, is_kok: Path, ses_mp3: Path):
    """31 Tem: SES TUTARLILIĞI — Shorts'un ana sesi Gemini TTS Leda; long-form
    Emel'de kalmıştı (Emre fark etti). Bölüm bölüm Leda + concat. Herhangi bir
    bölüm 3 denemede de düşerse TAMAMI Emel'e döner (karışık ses ASLA).
    Dönüş: gerçek bölüm süreleri listesi | None (Emel'e düş)."""
    import gemini_tts
    b_dizin = is_kok / "tts_bolum"; b_dizin.mkdir(exist_ok=True)
    # 1 Ağu: free-tier TTS = 10 istek/gün → bölüm başına çağrı sürdürülemez
    # (31 Tem: 10 bölümlük İkarus kotayı yedi, 6. bölümde 429). Bölümleri 2'şerli
    # grupla → 10 bölüm = 5 çağrı; grup süresi kelime oranıyla alt bölümlere dağıtılır.
    gruplar = [bolumler[i:i+2] for i in range(0, len(bolumler), 2)]
    sureler, parcalar = [], []
    for gi, grup in enumerate(gruplar, 1):
        p = b_dizin / f"g{gi:02d}.mp3"
        metin = "\n\n".join(b["metin"] for b in grup)
        sure = gemini_tts.seslendir(metin, p)
        if not sure:
            log(f"  Leda grup {gi} başarısız → tamamı Emel'e düşüyor")
            return None
        parcalar.append(p)
        kel = [len(b["metin"].split()) for b in grup]
        for k in kel:  # grup süresini kelime oranıyla bölümlere dağıt
            sureler.append(sure * k / sum(kel))
        log(f"  Leda grup {gi}/{len(gruplar)} ({sure:.1f}sn, {len(grup)} bölüm)")
        time.sleep(8)  # TTS dakikalık limit nezaketi
    # bölümler arası 0.5sn nefes + concat (tek tip codec: hepsi gemini_tts mp3'ü)
    sessiz = b_dizin / "sessiz.mp3"
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi",
                    "-i", "anullsrc=r=24000:cl=mono", "-t", "0.5",
                    "-c:a", "libmp3lame", "-b:a", "128k", str(sessiz)], check=True)
    liste = b_dizin / "liste.txt"
    satirlar = []
    for j, p in enumerate(parcalar):
        satirlar.append(f"file '{p.name}'")
        if j < len(parcalar) - 1:
            satirlar.append(f"file '{sessiz.name}'")
    liste.write_text("\n".join(satirlar))
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "concat", "-safe", "0",
                    "-i", str(liste), "-c:a", "libmp3lame", "-b:a", "160k", str(ses_mp3)], check=True)
    # nefes payı gruplar arasına girdi → son bölümü hariç her GRUP-SONU bölümüne +0.5
    grup_son_idx = {sum(len(g) for g in gruplar[:k+1]) - 1 for k in range(len(gruplar) - 1)}
    return [s + (0.5 if i in grup_son_idx else 0) for i, s in enumerate(sureler)]


def sure_al(medya: Path) -> float:
    return float(subprocess.check_output(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", str(medya)]).decode().strip())


def render(bolumler: list, gorseller: list, ses: Path, final: Path, is_kok: Path,
           gercek_sureler: list | None = None):
    toplam_sure = sure_al(ses)
    if gercek_sureler:  # Leda yolu: bölüm süreleri kesin → görsel-anlatım tam senkron
        oranli = [toplam_sure * s / sum(gercek_sureler) for s in gercek_sureler]
    else:  # Emel yolu: kelime oranı tahmini
        kelimeler = [len(b["metin"].split()) for b in bolumler]
        oranli = [toplam_sure * k / sum(kelimeler) for k in kelimeler]
    klip_dizin = is_kok / "klipler"; klip_dizin.mkdir(exist_ok=True)
    parcalar = []
    for i, (g, seg) in enumerate(zip(gorseller, oranli), 1):
        still = klip_dizin / f"still_{i:02d}.png"
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(g), "-filter_complex",
                        "[0]scale=1920:1080:force_original_aspect_ratio=increase,gblur=sigma=25,crop=1920:1080[bg];"
                        "[0]scale=1920:1080:force_original_aspect_ratio=decrease[fg];"
                        "[bg][fg]overlay=(W-w)/2:(H-h)/2", "-frames:v", "1", str(still)], check=True)
        seg_mp4 = klip_dizin / f"seg_{i:02d}.mp4"
        n = int(seg * 25)
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(still), "-vf",
                        f"scale=2400:1350,zoompan=z='min(zoom+0.00045,1.10)':d={n}:"
                        f"x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':s=1920x1080:fps=25,format=yuv420p",
                        "-c:v", "libx264", "-preset", "fast", "-crf", "19",
                        "-t", f"{seg:.3f}", str(seg_mp4)], check=True)
        parcalar.append((seg_mp4, seg))
        log(f"  klip {i}/{len(bolumler)} ({seg:.1f}sn)")
    liste = klip_dizin / "liste.txt"
    liste.write_text("\n".join(f"file '{p.name}'" for p, _ in parcalar))
    birlesik = is_kok / "birlesik.mp4"
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "concat", "-safe", "0",
                    "-i", str(liste), "-c", "copy", str(birlesik)], check=True)
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(birlesik), "-i", str(ses),
                    "-af", f"afade=t=out:st={max(0, toplam_sure-2):.1f}:d=2",
                    "-c:v", "copy", "-c:a", "aac", "-b:a", "192k", "-shortest", str(final)], check=True)
    return [s for _, s in parcalar]


def thumbnail_uret(baslik: str, ilk_gorsel: Path, hedef: Path):
    from PIL import Image, ImageDraw, ImageFont
    img = Image.open(ilk_gorsel).convert("RGB")
    W, H = 1280, 720
    oran = max(W / img.width, H / img.height)
    img = img.resize((int(img.width * oran), int(img.height * oran)))
    x, y = (img.width - W) // 2, int((img.height - H) * 0.25)
    img = img.crop((x, y, x + W, y + H))
    grad = Image.new("L", (1, H))
    for i in range(H):
        grad.putpixel((0, i), int(min(255, max(0, (i - H * 0.45) / (H * 0.55) * 230))))
    img = Image.composite(Image.new("RGB", (W, H), (8, 6, 12)), img, grad.resize((W, H)))
    d = ImageDraw.Draw(img)

    def font(sz):
        for p in ("/System/Library/Fonts/Supplemental/Arial Bold.ttf",
                  "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"):
            try:
                return ImageFont.truetype(p, sz)
            except Exception:
                pass
        return ImageFont.load_default()

    ana = baslik.split(":")[0].upper()[:26]
    alt = (baslik.split(":", 1)[1].strip() if ":" in baslik else "")[:40]
    f1 = font(84 if len(ana) <= 20 else 66)
    w = d.textlength(ana, font=f1)
    d.text(((W - w) / 2 + 3, 473), ana, font=f1, fill=(0, 0, 0))
    d.text(((W - w) / 2, 470), ana, font=f1, fill=(255, 215, 120))
    if alt:
        f2 = font(42)
        w2 = d.textlength(alt, font=f2)
        d.text(((W - w2) / 2, 585), alt, font=f2, fill=(235, 230, 220))
    img.save(hedef, quality=92)


# ── YOUTUBE ──────────────────────────────────────────────────────────────────
def yt_istemci():
    from google.oauth2.credentials import Credentials
    from google.auth.transport.requests import Request
    from googleapiclient.discovery import build
    creds = Credentials.from_authorized_user_file(str(TOKEN),
        ["https://www.googleapis.com/auth/youtube", "https://www.googleapis.com/auth/youtube.force-ssl"])
    if creds.expired and creds.refresh_token:
        creds.refresh(Request())
    return build("youtube", "v3", credentials=creds, cache_discovery=False)


def zaman_damgasi(sn: float) -> str:
    return f"{int(sn // 60)}:{int(sn % 60):02d}"


def yukle(final: Path, kapak: Path, senaryo: dict, seg_sureler: list, kunyeler: list) -> str:
    from googleapiclient.http import MediaFileUpload
    yt = yt_istemci()
    t = 0.0
    bolum_satirlari = []
    for b, s in zip(senaryo["bolumler"], seg_sureler):
        bolum_satirlari.append(f"{zaman_damgasi(t)} {b.get('ad', '—')}")
        t += s
    kunye_satirlari = [f"• {k['sanatci'] or k['dosya']}" for k in kunyeler if k]
    aciklama = (f"{senaryo.get('aciklama_ozeti', '')}\n\n"
                "Bölümler:\n" + "\n".join(bolum_satirlari) + "\n\n"
                "Bu videodaki tablolar (kamu malı / açık lisans, Wikimedia Commons):\n"
                + "\n".join(kunye_satirlari) +
                "\n\nAbone ol → https://youtube.com/@akashainme?sub_confirmation=1\n\n"
                "Her gün kendini biraz daha derinden tanı.\n\n"
                "#mitoloji #carljung #spiritüellik #farkındalık")
    body = {"snippet": {"title": senaryo["baslik"][:95], "description": aciklama[:4900],
                        "tags": senaryo.get("etiketler", [])[:12], "categoryId": "22",
                        "defaultLanguage": "tr", "defaultAudioLanguage": "tr"},
            "status": {"privacyStatus": "public", "selfDeclaredMadeForKids": False,
                       "madeForKids": False, "embeddable": True}}
    medya = MediaFileUpload(str(final), mimetype="video/mp4", chunksize=4 * 1024 * 1024, resumable=True)
    istek = yt.videos().insert(part="snippet,status", body=body, media_body=medya)
    yanit = None
    while yanit is None:
        _, yanit = istek.next_chunk()
    vid = yanit["id"]
    log(f"  ✓ video: {vid}")
    try:
        yt.thumbnails().set(videoId=vid, media_body=MediaFileUpload(str(kapak))).execute()
        log("  ✓ kapak")
    except Exception as h:
        log(f"  ✗ kapak: {str(h)[:80]}")
    try:
        yt.commentThreads().insert(part="snippet", body={"snippet": {"videoId": vid,
            "topLevelComment": {"snippet": {"textOriginal": "Bu hikâyede kendinden ne buldun? 👇"}}}}).execute()
        log("  ✓ creator yorum")
    except Exception as h:
        log(f"  ✗ yorum: {str(h)[:80]}")
    return vid


# ── ANA AKIŞ ─────────────────────────────────────────────────────────────────
def main():
    p = argparse.ArgumentParser()
    p.add_argument("--konu", default=None)
    p.add_argument("--kuru", action="store_true")
    p.add_argument("--kisa", action="store_true", help="2 bölümlük hızlı test")
    args = p.parse_args()

    log("=== AKASHA LONG-FORM BAŞLA ===")
    # Hafta koruması: yedek cron çift üretmesin
    try:
        son = json.loads((PANEL / "long_form_son.json").read_text(encoding="utf-8"))
        gecen = (datetime.now() - datetime.strptime(son.get("tarih","2000-01-01"), "%Y-%m-%d")).days
        if gecen < 6 and not args.kuru and not args.konu:  # zorlanan konu = bilinçli istek
            log(f"Bu hafta üretilmiş ({gecen} gün önce) — çık."); return
    except Exception:
        pass
    konu = konu_sec(args.konu)
    log(f"Konu: {konu}")
    is_kok = CIKTI_KOK / datetime.now().strftime("%Y%m%d_%H%M%S")
    is_kok.mkdir(parents=True)

    log("1) Senaryo (Gemini)...")
    senaryo = senaryo_uret(konu, args.kisa)
    (is_kok / "senaryo.json").write_text(json.dumps(senaryo, ensure_ascii=False, indent=2))
    bolumler = senaryo["bolumler"]
    log(f"  ✓ '{senaryo['baslik']}' — {len(bolumler)} bölüm, "
        f"{sum(len(b['metin'].split()) for b in bolumler)} kelime")

    log("2) Wikimedia tabloları (lisans kontrollü)...")
    gorsel_dizin = is_kok / "gorseller"; gorsel_dizin.mkdir()
    gorseller, kunyeler = [], []
    for i, b in enumerate(bolumler, 1):
        hedef = gorsel_dizin / f"{i:02d}.jpg"
        k = tablo_indir(b["tablo_arama"], hedef)
        if not k and gorseller:  # bulunamadı → önceki tabloyu tekrar kullan (asla çökme)
            hedef.write_bytes(gorseller[-1].read_bytes())
            k = kunyeler[-1]
            log(f"  {i}: bulunamadı → önceki tablo tekrar")
        elif not k:
            raise RuntimeError(f"İlk bölüm için tablo bulunamadı: {b['tablo_arama']}")
        else:
            log(f"  {i}: {k['dosya'][:50]}")
        gorseller.append(hedef); kunyeler.append(k)

    log("3) TTS (Leda — Shorts ile aynı ses; yedek: Emel)...")
    ses = is_kok / "ses.mp3"
    gercek_sureler = tts_bolumlu_leda(bolumler, is_kok, ses)
    if gercek_sureler is None:
        log("  Emel yedeğine düşüldü")
        tts_uret("\n\n".join(b["metin"] for b in bolumler), ses)
    log(f"  ✓ {sure_al(ses):.0f} sn")

    log("4) Render...")
    final = is_kok / "final.mp4"
    seg_sureler = render(bolumler, gorseller, ses, final, is_kok, gercek_sureler)

    log("5) Kapak...")
    kapak = is_kok / "kapak.jpg"
    thumbnail_uret(senaryo["baslik"], gorseller[0], kapak)

    if args.kuru:
        log(f"KURU MOD — upload yok. Çıktı: {final}")
        return
    log("6) Upload...")
    vid = yukle(final, kapak, senaryo, seg_sureler, kunyeler)
    konu_kaydet(konu)
    (PANEL / "long_form_son.json").write_text(json.dumps(
        {"video_id": vid, "etiket": f"Uzun video — {senaryo['baslik'][:50]}",
         "tarih": datetime.now().strftime("%Y-%m-%d")}, ensure_ascii=False), encoding="utf-8")
    log(f"🎉 https://youtu.be/{vid}")


if __name__ == "__main__":
    main()
