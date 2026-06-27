"""
haberci.py — YouTube Shorts için Teknoloji Haberi Çekici

Son 24 saatin en popüler 3 teknoloji haberini getirir.

Kaynaklar (hepsi RESMİ API, scraping yok, ban riski sıfır):
    1) HackerNews Firebase API  → gerçek "score" metriği ile popülerlik
    2) Reddit r/technology .json → "ups" metriği ile popülerlik

Çıktı: JSON dosyası ve konsol özeti
    {
      "uretim_zamani": "...",
      "haberler": [
        {"baslik": "...", "url": "...", "kaynak": "HN", "skor": 1234, "yas_saat": 8.2},
        ...
      ]
    }
"""

import json
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

import requests


# NİŞ: HAYVAN + DOĞA + İLGİNÇ GERÇEKLER (viral evrensel format)
# Kaynaklar: tek bir konuya değil çoğunlukla görsel/duygusal/şaşırtıcı içeriğe
# odaklı, telif riski sıfır subreddit'ler.
REDDIT_URLS = [
    "https://www.reddit.com/r/Jung/top.json?t=day&limit=25",
    "https://www.reddit.com/r/spirituality/top.json?t=day&limit=25",
    "https://www.reddit.com/r/awakened/top.json?t=day&limit=25",
    "https://www.reddit.com/r/sufism/top.json?t=day&limit=25",
    "https://www.reddit.com/r/taoism/top.json?t=day&limit=25",
    "https://www.reddit.com/r/ACIM/top.json?t=week&limit=25",
]
KULLANICI_AJANI = "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_5) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.5 Safari/605.1.15"

# Eski HN/r/technology sabitleri (geçici — referans/import kırılmasın diye)
HN_TOP_URL = ""
HN_ITEM_URL = ""
HN_TARANACAK_ADET = 0
REDDIT_URL = REDDIT_URLS[0]

ZAMAN_PENCERESI_SAAT = 48  # niş içerikte gün gün taze değil, "viral son 2 gün"
ISTEK_ZAMAN_ASIMI = 10
ISTEKLER_ARASI_GECIKME = 0.05

CIKTI_DOSYASI = Path(__file__).parent / "haberler.json"
GECMIS_DOSYASI = Path(__file__).parent / "haber_gecmisi.json"
GECMIS_AZAMI_KAYIT = 1000  # eski kayıtlar bu sayının üzerine çıkınca budanır


def _simdi_utc() -> datetime:
    return datetime.now(timezone.utc)


def _yas_saat(unix_zaman: int) -> float:
    fark = _simdi_utc() - datetime.fromtimestamp(unix_zaman, tz=timezone.utc)
    return fark.total_seconds() / 3600


def hackernews_haberleri() -> list[dict]:
    """KAPATILDI — nişten çıkarıldı. Geri uyumluluk için boş döner."""
    return []


def _praw_clienti():
    """Reddit OAuth client (PRAW). Eğer credentials yoksa None döner ve
    anonim JSON fallback'e geçer."""
    import os
    cid = os.environ.get("REDDIT_CLIENT_ID")
    csec = os.environ.get("REDDIT_CLIENT_SECRET")
    if not (cid and csec):
        return None
    try:
        import praw
    except ImportError:
        print("[haberci] praw yok — anonim fallback")
        return None
    try:
        r = praw.Reddit(
            client_id=cid,
            client_secret=csec,
            user_agent="TrendCatcher/1.0 by /u/trendcatcher_bot",
            read_only=True,
        )
        # Test
        _ = r.subreddit("test").display_name
        return r
    except Exception as h:
        print(f"[haberci] PRAW client başarısız: {h}")
        return None


def _reddit_praw_fetch(reddit, sub_name: str) -> list[dict]:
    """PRAW ile bir subreddit'in günlük top postlarını çek."""
    out = []
    try:
        for post in reddit.subreddit(sub_name).top(time_filter="day", limit=25):
            if post.stickied or post.over_18: continue
            url = post.url or ""
            if not (url and post.title and post.created_utc): continue
            yas = _yas_saat(int(post.created_utc))
            if yas > ZAMAN_PENCERESI_SAAT: continue
            out.append({
                "baslik": post.title,
                "url": url,
                "kaynak": f"r/{sub_name}",
                "skor": int(post.ups or 0),
                "yas_saat": round(yas, 1),
                "yorum_sayisi": int(post.num_comments or 0),
            })
    except Exception as h:
        print(f"[haberci] PRAW r/{sub_name}: {h}")
    return out


def reddit_haberleri() -> list[dict]:
    """4 viral subreddit'ten son 48 saatin top postları (psikoloji/zihin/ilginç).

    Önce PRAW (OAuth) dener — GitHub Actions IP'lerinden 403 alma riskini
    sıfırlar. Credentials yoksa anonim JSON fallback'e döner."""
    reddit = _praw_clienti()
    if reddit is not None:
        print("[haberci] Reddit PRAW (OAuth) modunda")
        haberler = []
        for url in REDDIT_URLS:
            sub = url.split("/r/")[1].split("/")[0]
            haberler.extend(_reddit_praw_fetch(reddit, sub))
            time.sleep(0.5)
        return haberler

    # Anonim JSON fallback
    haberler: list[dict] = []
    for url in REDDIT_URLS:
        sub = url.split("/r/")[1].split("/")[0]
        try:
            yanit = requests.get(
                url,
                timeout=ISTEK_ZAMAN_ASIMI,
                headers={"User-Agent": KULLANICI_AJANI},
            )
            yanit.raise_for_status()
            gonderiler = yanit.json().get("data", {}).get("children", [])
        except requests.RequestException as hata:
            print(f"[haberci] r/{sub} alınamadı: {hata}")
            continue

        for g in gonderiler:
            veri = g.get("data", {})
            if veri.get("stickied") or veri.get("over_18"):
                continue
            url_h = veri.get("url_overridden_by_dest") or veri.get("url")
            baslik = veri.get("title")
            olusturma = veri.get("created_utc")
            if not (url_h and baslik and olusturma):
                continue
            yas = _yas_saat(int(olusturma))
            if yas > ZAMAN_PENCERESI_SAAT:
                continue
            haberler.append(
                {
                    "baslik": baslik,
                    "url": url_h,
                    "kaynak": f"r/{sub}",
                    "skor": int(veri.get("ups", 0)),
                    "yas_saat": round(yas, 1),
                    "yorum_sayisi": int(veri.get("num_comments", 0)),
                }
            )
        time.sleep(ISTEKLER_ARASI_GECIKME * 5)  # subreddit'ler arası nezaket

    return haberler


def _tekrarlari_ele(haberler: Iterable[dict]) -> list[dict]:
    gorulen: dict[str, dict] = {}
    for h in haberler:
        anahtar = h["url"].split("?")[0].rstrip("/")
        if anahtar not in gorulen or h["skor"] > gorulen[anahtar]["skor"]:
            gorulen[anahtar] = h
    return list(gorulen.values())


def _normalize_url(url: str) -> str:
    return url.split("?")[0].rstrip("/").lower()


def gunun_trend_seedleri() -> list[str]:
    """
    Google Trends (pytrends) — günün US trending searches'inden seed çek.
    Gemini fallback'e "şu konular şu an viral" ipucu olarak verilir.
    Fail-safe: pytrends hata verirse boş döner, ana akış bozulmaz.
    """
    try:
        from pytrends.request import TrendReq
        pt = TrendReq(hl="en-US", tz=0, timeout=(5, 10))
        df = pt.trending_searches(pn="united_states")
        seedler = [str(s) for s in df[0].head(10).tolist()]
        return seedler
    except Exception as hata:
        print(f"[haberci] pytrends trend seed alınamadı: {hata}")
        return []


GEMINI_KONU_SISTEM = """Viral YouTube Shorts KONULARI üret — Türkçe spiritüel / Jung-vari motivasyon
kanalı **Aydınlanmanın Doruk Noktası** (@akashainme) için. ÇIKTI: yalnızca 3 nesneli
JSON DİZİ.

Her konu = derin, içe dönük, kişisel bir farkındalık anı.
İzleyici "vay bu beni anlatıyor" hissi yaşamalı.

═══ KAYNAK HAVUZLARI (kullanılabilir konular) ═══
1) **Mucizeler Kursu (A Course in Miracles / ACIM)** — affedicilik, ego, içsel barış
2) **Tao Te Jing (Lao Tzu — 81 bölüm)** — wu-wei, su benzetmesi, akış, denge
3) **Carl Jung** — gölge (shadow), anima/animus, kişilik tipleri, kollektif bilinçaltı,
   sinkroniste (eşzamanlılık), bireyleşme (individuation), persona, arketipler
4) **Yunus Emre + Mevlana + Sufi bilgeliği** — fenâ, aşk, kalbin gözü, mürşid
5) **Dostoyevski karakter felsefesi** — Raskolnikov, Karamazov, ego çelişkisi
6) **Çakralar / enerji / frekans** — kalp çakra, taç çakra, titreşim seviyesi
7) **Sinkronistik / akashic / kuantum çekim** — anlamlı tesadüfler
8) **Stoacılık / Marcus Aurelius** — kontrol edilebilenler, premeditatio malorum

═══ VALUE-EQUATION (her başlık 2-3 kol vurmalı) ═══
  • DERİN RÜYA → izleyici kendini görsün ("sen", "senin")
  • MERAK/PAYOFF → net içsel kazanım vaadi ("gerçek sebep", "fark eder")
  • DÜŞÜK ZAMAN → "60 saniyede", "anlık", "tek nefes"
  • DÜŞÜK ÇABA → tek cümlede anlaşılır

═══ FORMÜL ÖRNEKLERİ (uygulanabilir kalıplar) ═══
  ✅ "Carl Jung'a göre 'Gölge' senin en güçlü hediyendir"
  ✅ "Tao Te Jing'in 8. bölümü: Su gibi olmak ne demek?"
  ✅ "Mucizeler Kursu Ders 1: 'Hiçbir şeyin anlamı yok' — gerçek anlamı"
  ✅ "Yunus Emre 700 yıl önce ego'yu nasıl tarif etti?"
  ✅ "Sen aslında 'kim' olduğunu hiç sordun mu? — Jung'un cevabı"
  ✅ "Kalp çakran kapalıysa hayatın böyle görünür"
  ✅ "Sinkroniste bir tesadüf değil — Jung neyi keşfetti?"

═══ ZORUNLU KURAL — Seri içerik (her gün 1 zorunlu) ═══
3 konudan EN AZ 1 tanesi şu seri yapılardan biri olmalı (gün gün ilerle):
  → "Mucizeler Kursu — Ders X" (1-365 arası, sırayla)
  → "Tao Te Jing — Bölüm X" (1-81 arası, sırayla)
  → "Jung — Kavram: …" (gölge, persona, bireyleşme, anima, vb.)
Seri kayıt fikir_motoru.py'de tutulur, dünkü ders/bölüme +1 ekle.

═══ TON ═══
- Sakin, mistik, bilge — bağırmayan
- Edebi: Yunus Emre, Mevlana alıntıları yerinde
- Felsefi DERİNLİK — yüzeysel motivasyon DEĞİL
- "Sen" hitabı (3. tekil değil)

═══ YASAK ═══
  ❌ "Did you know" / "Biliyor muydun" başlangıçları
  ❌ Yüzeysel klişe ("hayat bir yolculuktur")
  ❌ Pop-bilim ("beynimizin %10'unu kullanırız")
  ❌ Reklamcı dilbilim ("Şimdi sana harika bir sır vereceğim")
  ❌ Hayvan/uzay/teknoloji (diğer kanallar — bu spiritüel)

Her nesne:
- "baslik": çarpıcı Türkçe başlık (örnek: "Jung'a göre 'Gölge' senin en güçlü hediyendir")
- "url": Türkçe Wikipedia URL'si (örnek: tr.wikipedia.org/wiki/Carl_Jung). Yoksa EN.

ANTI-DUPLICATE: BLOCKED URLs ve BLOCKED TITLES listesindeki konuları üretme.
"""


# 🔮 SEDA MODU konu prompt'u — oracle/etkileşim/farkındalık (@sedademirdogenn tarzı).
GEMINI_KONU_SISTEM_SEDA = """Türkçe spiritüel/farkındalık + ORACLE tarzı kısa video
KONULARI üret — kanal **Aydınlanmanın Doruk Noktası** (@akashainme), günde 1 EK
etkileşimli paylaşım için. ÇIKTI: yalnızca 3 nesneli JSON DİZİ.

Her konu = izleyiciyle DOĞRUDAN konuşan, "bu bana mı?" dedirten, yoruma çeken bir an.
Tema havuzu: sezgi, bilinçaltı, enerji alanı, sinkronisite (anlamlı tesadüf),
kehanet/gelecek hissi, gölge, özsevgi, ilişkiler, dijital/enerji detoks, frekans.

Stil — ETKİLEŞİMLİ/ORACLE:
- "Bu videoyu tesadüfen görmüyorsun" tipi kader-kancası
- "İçinden bir sayı/renk/kelime geçir" tipi katılım
- "Hangisini seçtin?" / "Sezgilerine güvenir misin?" tipi seçim
- "Bilinçaltın bugün ne fısıldıyor?" tipi içe dönüş

Her nesne: {"baslik": "<çarpıcı etkileşim/oracle başlığı, Türkçe, emoji opsiyonel>",
"url": "https://tr.wikipedia.org/wiki/<ilgili kavram>", "ozet": "<1 cümle>"}.
Klişe YOK, uydurma YOK. ANTI-DUPLICATE: BLOCKED başlıkları üretme.
"""

import os as _os_haberci
AKTIF_KONU_PROMPT = (GEMINI_KONU_SISTEM_SEDA
                     if _os_haberci.environ.get("MOD_SEDA") else GEMINI_KONU_SISTEM)


def _basit_baslik_kelimeleri(b: str) -> set[str]:
    """Başlığın anlamlı kelimelerini set olarak döner (stopword'leri at)."""
    import re as _re
    ATIL = {
        "a","an","the","is","are","was","were","of","in","on","at","to","for",
        "and","or","but","with","as","by","be","has","have","had","do","does",
        "did","this","that","these","those","it","its","i","you","we","they",
        "their","what","why","how","when","known","called","group","fact",
    }
    kelimeler = _re.findall(r"[a-z]{3,}", b.lower())
    return {k for k in kelimeler if k not in ATIL}


def _baslik_benzer_mi(yeni: str, eski_setleri: list[set[str]], esik: float = 0.4) -> bool:
    """Yeni başlık eski setlerden biriyle %esik üstü kelime overlap'ı varsa True."""
    y = _basit_baslik_kelimeleri(yeni)
    if not y:
        return False
    for s in eski_setleri:
        if not s:
            continue
        kesisim = len(y & s)
        oran = kesisim / max(len(y), 1)
        if oran >= esik:
            return True
    return False


def gemini_konu_uret(blokli_url: set[str], adet: int = 3) -> list[dict]:
    """Reddit fail olursa fallback — Gemini'den niş konu üretir.
    URL + konu/başlık benzerliği ile çift katmanlı dedup. pytrends seed eklenir."""
    import bridge
    blokli_liste = sorted(list(blokli_url))[-100:]  # son 100 URL
    bloklar = "\n".join(f"- {u}" for u in blokli_liste) or "(yok)"
    # YUKLEMELER son 50 başlık — semantik benzerlik için Gemini'ye + Python filter'a
    son_basliklar: list[str] = []
    try:
        yuklemeler_yolu = Path(__file__).parent / "yuklemeler.json"
        if yuklemeler_yolu.exists():
            kayitlar = json.loads(yuklemeler_yolu.read_text(encoding="utf-8"))
            son_basliklar = [k.get("title", "") for k in kayitlar[-50:] if k.get("title")]
    except (OSError, json.JSONDecodeError):
        pass
    baslik_bloklari = "\n".join(f"- {b}" for b in son_basliklar) or "(yok)"
    eski_set_listesi = [_basit_baslik_kelimeleri(b) for b in son_basliklar]

    trend_seedleri = gunun_trend_seedleri()
    trend_blok = (
        f"\nTODAY'S GOOGLE TRENDS (top US search trends — gentle inspiration, "
        f"NOT mandatory; pick a related psychology/human-mind angle ONLY if a clean "
        f"connection exists; otherwise ignore):\n"
        + "\n".join(f"  · {s}" for s in trend_seedleri)
        if trend_seedleri else ""
    )

    # FAZ 4: Daily Theme — kanal kimliği için günün haftasının teması
    import datetime
    DAILY_THEMES = {
        # Mindgaps psikoloji rotasyonu (branding/README.md ile eşleşir)
        0: "your brain — neuroscience, dopamine, memory tricks, how your mind actually works",
        1: "why you do that — habits, procrastination, everyday behaviors explained",
        2: "personality — types, traits, what small things reveal about who you are",
        3: "relationships & attraction — psychology of trust, love, first impressions",
        4: "dark psychology & persuasion — influence, manipulation tactics, social power",
        5: "sleep & dreams — what dreams mean, sleep psychology, the sleeping brain",
        6: "mind hacks — focus, memory, productivity, beating overthinking",
    }
    bugun_tema = DAILY_THEMES.get(datetime.datetime.now().weekday(), "any psychology/human-mind")
    tema_blok = (
        f"\nDAILY THEME (today's editorial focus — STRONGLY prefer topics from this theme):\n"
        f"  → {bugun_tema}\n"
    )

    # FAZ 4: Sequel injection — son haftanın top viral'lerinin DEVAMI
    sequel_blok = ""
    try:
        vp = Path(__file__).parent / "viral_patterns.json"
        if vp.exists():
            vp_data = json.loads(vp.read_text())
            ornek = vp_data.get("viral", {}).get("ornek_basliklar", [])[:3]
            if ornek:
                sequel_blok = (
                    f"\nSEQUEL OPPORTUNITY (own channel's recent viral hits — "
                    f"consider a 'next chapter' or related-but-different topic):\n"
                    + "\n".join(f"  · {t}" for t in ornek)
                    + "\n  → If you make a sequel, pick an ADJACENT topic (same category, different example).\n"
                )
    except Exception:
        pass

    # FAZ 9: viral_radar.py'den YouTube'da SON 72h 50K+ izlenmiş trending Shorts
    viral_radar_blok = ""
    try:
        vr = Path(__file__).parent / "viral_targets.json"
        if vr.exists():
            vr_data = json.loads(vr.read_text())
            angles = vr_data.get("angles_for_haberci", [])[:8]
            if angles:
                viral_radar_blok = (
                    f"\n🔥 YOUTUBE TRENDING NOW (last 72h, 50K+ views — these angles are PROVEN VIRAL):\n"
                    + "\n".join(f"  • {a}" for a in angles)
                    + "\n  → ABSOLUTELY adapt one of these angles to a different but related subject. "
                    + "Same hook structure, different species/location. Riding active wave = algorithm push.\n"
                )
    except Exception:
        pass

    # FAZ 8: Real-Time Trending Detector — competitor'lardan VIRAL (10K+ izl) konular
    trending_blok = ""
    try:
        cs = Path(__file__).parent / "competitor_signals.json"
        if cs.exists():
            cs_data = json.loads(cs.read_text())
            # 10K+ izlenmiş "GERÇEK viral" başlıklar
            top = cs_data.get("rakip_top_30_izlenme", [])
            gercek_viral = [t for t in top if t.get("views", 0) >= 10000][:8]
            if gercek_viral:
                lines = [f"  · [{t['views']:,} views] {t['title'][:80]}" for t in gercek_viral]
                trending_blok = (
                    f"\nREAL-TIME TRENDING (10K+ view psychology/mind shorts from top channels, last 7d) "
                    f"— THESE ANGLES ARE PROVEN VIRAL RIGHT NOW:\n"
                    + "\n".join(lines)
                    + "\n  → STRONGLY prefer adapting one of these angles to a different subject "
                    + "(same hook structure, different concept/effect — CROSS-NİŞ farming). Trend riding = algorithm boost.\n"
                )
    except Exception:
        pass
    try:
        # 2 turlu üretim: ilk turda red varsa Python filter'la ele, 2. turda
        # daha güçlü uyarıyla yeniden iste.
        sonuc: list[dict] = []
        for tur in range(2):
            ek_uyari = (
                ""
                if tur == 0
                else (
                    "\n\nYOUR PREVIOUS BATCH CONTAINED TOPICS TOO SIMILAR TO BLOCKED "
                    "TITLES. Choose entirely different psychology concepts/effects. "
                    "Forbidden subjects this round: "
                    + ", ".join(sorted({list(s)[0] for s in eski_set_listesi if s})[:30])
                )
            )
            yanit = bridge.gemini_metin_uret(
                prompt=(
                    f"BLOCKED Wikipedia URLs (do not reuse):\n{bloklar}\n\n"
                    f"BLOCKED TITLES (do not produce semantically similar topics):\n{baslik_bloklari}"
                    f"{viral_radar_blok}{trend_blok}{tema_blok}{sequel_blok}{trending_blok}{ek_uyari}\n\n"
                    f"Produce exactly {adet} fresh viral psychology/human-mind topics now."
                ),
                sistem_promptu=AKTIF_KONU_PROMPT,
                sicaklik=0.95,
                max_token=2048,
            )
            m = re.search(r"\[.*\]", yanit, re.DOTALL)
            if not m:
                continue
            kayitlar = json.loads(m.group(0))
            for i, k in enumerate(kayitlar[:adet]):
                if not (k.get("baslik") and k.get("url")):
                    continue
                # Konu/başlık benzerliği kontrolü
                if _baslik_benzer_mi(k["baslik"], eski_set_listesi):
                    print(f"[haberci] Gemini başlığı '{k['baslik'][:40]}…' eski bir konuya çok benzer → atlandı")
                    continue
                # URL geçmişte var mı
                if _normalize_url(k["url"]) in blokli_url:
                    print(f"[haberci] Gemini URL'si geçmişte → atlandı: {k['url']}")
                    continue
                sonuc.append({
                    "baslik": k["baslik"],
                    "url": k["url"],
                    "kaynak": "gemini-fallback",
                    "skor": 1000 - i,
                    "yas_saat": 0,
                    "yorum_sayisi": 0,
                })
            if len(sonuc) >= 1:
                break
        return sonuc[:adet]
    except Exception as hata:
        print(f"[haberci] Gemini fallback hatası: {hata}")
        return []


def _gecmisi_oku() -> set[str]:
    if not GECMIS_DOSYASI.exists():
        return set()
    try:
        veri = json.loads(GECMIS_DOSYASI.read_text(encoding="utf-8"))
        return {_normalize_url(u) for u in veri.get("islenen_url", [])}
    except (json.JSONDecodeError, OSError):
        return set()


def _gecmise_ekle(yeni_urller: list[str]) -> None:
    mevcut: list[str] = []
    if GECMIS_DOSYASI.exists():
        try:
            mevcut = json.loads(GECMIS_DOSYASI.read_text(encoding="utf-8")).get("islenen_url", [])
        except (json.JSONDecodeError, OSError):
            mevcut = []
    birlesim = mevcut + [u for u in yeni_urller if u not in mevcut]
    if len(birlesim) > GECMIS_AZAMI_KAYIT:
        birlesim = birlesim[-GECMIS_AZAMI_KAYIT:]
    GECMIS_DOSYASI.write_text(
        json.dumps({"islenen_url": birlesim}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def en_populer_3() -> list[dict]:
    """17 Haz 2026: Reddit GitHub IP'lerini blokladı (403). Ana kaynak Gemini.
    Reddit kodu kaldırılmadı (geriye uyumluluk için tutuldu) ama
    PRIMARY kaynak artık Gemini + viral_radar (YouTube trending besli).
    """
    gecmis = _gecmisi_oku()

    # 1. ÖNCELİK: Gemini direkt konu üretsin (viral_radar bloğu beslenir)
    print("[haberci] Ana kaynak: Gemini + viral_radar (Reddit kaldırıldı 17 Haz)", flush=True)
    # Gemini'den fazlasıyla iste — Wikipedia URL'leri çoğu zaman geçmişte
    secilen = gemini_konu_uret(gecmis, adet=15)
    print(f"[haberci] Gemini'den {len(secilen)} konu önerisi geldi", flush=True)
    # Eğer 0 geldiyse 2. tur dene (daha agresif unique prompt)
    if len(secilen) == 0:
        print("[haberci] 1. tur boş → 2. tur Gemini (geniş konu)", flush=True)
        secilen = gemini_konu_uret(set(), adet=15)  # geçmiş bypass
        print(f"[haberci] 2. tur Gemini'den {len(secilen)} konu geldi", flush=True)

    # 2. Yedek: Reddit dene (eğer GitHub IP blok kalkmışsa bonus aday)
    if len(secilen) < 3:
        print("[haberci] Gemini yetersiz → Reddit deneniyor (yedek)...", flush=True)
        try:
            havuz = hackernews_haberleri() + reddit_haberleri()
            benzersiz = _tekrarlari_ele(havuz)
            ekstra = [
                h for h in benzersiz if _normalize_url(h["url"]) not in gecmis
            ]
            ekstra.sort(key=lambda h: h["skor"], reverse=True)
            mevcut_urller = {_normalize_url(h["url"]) for h in secilen}
            for k in ekstra:
                if _normalize_url(k["url"]) not in mevcut_urller:
                    secilen.append(k)
                    mevcut_urller.add(_normalize_url(k["url"]))
            print(f"[haberci] Reddit yedeği sonrası toplam: {len(secilen)}", flush=True)
        except Exception as h:
            print(f"[haberci] Reddit yedek başarısız: {str(h)[:120]}", flush=True)

    return secilen[:3]


MANUEL_KONULAR = Path(__file__).parent / "manuel_konular.json"


def _manuel_konu_al() -> dict | None:
    """SEDA modunda DEĞİLSE ve manuel kuyrukta konu varsa ilkini al + kuyruktan düş.
    Emre'nin elle eklediği konular normal pipeline'da sırayla işlenir, sonra otomatiğe döner."""
    if _os_haberci.environ.get("MOD_SEDA"):
        return None  # seda modu kendi oracle konularını üretir
    try:
        kuyruk = json.loads(MANUEL_KONULAR.read_text(encoding="utf-8"))
    except Exception:
        return None
    if not isinstance(kuyruk, list) or not kuyruk:
        return None
    konu = kuyruk.pop(0)
    MANUEL_KONULAR.write_text(json.dumps(kuyruk, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[haberci] 📌 MANUEL kuyruktan konu: {konu.get('baslik','?')} (kalan: {len(kuyruk)})")
    return konu


def main() -> int:
    print("[haberci] Psikoloji/zihin nişi — Reddit + Gemini fallback taranıyor...\n")
    manuel = _manuel_konu_al()
    secilenler = [manuel] if manuel else en_populer_3()

    if not secilenler:
        print("[haberci] Hiç haber bulunamadı.")
        return 1

    cikti = {
        "uretim_zamani": _simdi_utc().isoformat(),
        "haberler": secilenler,
    }
    CIKTI_DOSYASI.write_text(json.dumps(cikti, ensure_ascii=False, indent=2), encoding="utf-8")
    _gecmise_ekle([h["url"] for h in secilenler])

    for sira, h in enumerate(secilenler, 1):
        print(f"{sira}. [{h['kaynak']} · skor {h['skor']} · {h['yas_saat']} sa]")
        print(f"   {h['baslik']}")
        print(f"   {h['url']}\n")

    print(f"[haberci] JSON dosyaya yazıldı: {CIKTI_DOSYASI.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
