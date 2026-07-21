"""
yorum_yanit_bot.py — Aydınlanmanın Doruk Noktası (Akasha) Yorum Otomatik Yanıt Botu.

Her run'da:
  1. Kanalın son 30 videosunun yorumlarını çek
  2. Daha önce cevaplanmamış + yaşı 5+ dakika olan + sahibimiz olmayan yorumları bul
  3. Gemini ile yoruma uygun, samimi, kısa TÜRKÇE cevap üret
  4. YouTube API üzerinden REPLY olarak gönder
  5. State'e işle (comment_replies.json) — aynı yoruma 2 kez cevap atmaz

Scope: youtube.force-ssl (zaten var — token upgrade'inde aktive edildi)

Kullanım:
    python3 yorum_yanit_bot.py
    python3 yorum_yanit_bot.py --kuru   # test modu, yorum atmaz sadece taslak yazar
    python3 yorum_yanit_bot.py --min-yas 5  # default 5 dakika
    python3 yorum_yanit_bot.py --max-cevap 20  # bir run'da max yanıt
"""
import argparse, json, os, sys, time
from datetime import datetime, timezone, timedelta
from pathlib import Path

PANEL_KOK = Path(__file__).parent
TOKEN = PANEL_KOK / "token.json"
DURUM = PANEL_KOK / "comment_replies.json"
LOG = PANEL_KOK / "yorum_yanit.log"
KOTA_STATE = PANEL_KOK / "kota_state.json"

# YouTube Data API günlük kota: 10.000 unit, Pacific gece yarısı (≈UTC 08:00 PST) sıfırlanır.
# Yorum bot kalan kotayı video upload için saklar — %85 doluysa hiç başlamaz.
KOTA_LIMIT = 10000
KOTA_GUARD_ESIK = 8500  # %85 dolduğunda bot dur

# Kısa "👏" "🔥" tipi yorumlar — Gemini'ye gitmeden hazır cevap
HIZLI_CEVAPLAR = {
    "👏": ["Teşekkür ederim 🙏", "Ulaştıysa ne mutlu 🙌", "Kalbimde yeri var ❤️"],
    "🔥": ["Değince mutlu oldum 🔥", "Bu enerji için teşekkürler 🙌", "Çok değerli, sağ ol"],
    "❤️": ["Teşekkür ederim ❤️", "Bu benim için çok kıymetli 🙏", "İçine işlediyse ne güzel"],
    "wow": ["Değil mi? Bazı sözler öyle bir vuruyor 🌙", "Ben de yazarken aynısını hissettim", "İçine dokunduysa amacına ulaşmış demektir"],
}

SISTEM_PROMPTU = """Sen "Aydınlanmanın Doruk Noktası" adlı YouTube Shorts kanalının
yaratıcısısın. Niş: spiritüel/mistik farkındalık, Carl Jung, tasavvuf, Sufi
bilgeliği, meditasyon, iç huzur. Kitle: Türkçe konuşan, manevi arayış içindeki
izleyiciler. Ton = Yunus Emre + Mevlana tonu — sakin, derin, bilge, asla
bağırmayan; müşteri hizmetleri gibi değil, bilge bir dost gibi.

Görevin: izleyici yorumuna KISA, sıcak, TONA UYGUN bir cevap yazmak.

═══ ADIM 1 — TONU ALGILA ═══

Kelimeler + emojilere BİRLİKTE bak.

Ton sinyalleri:
- "harika", "çok güzel", "içime işledi", "tam da ihtiyacım olan" + 🙏/❤️/✨ → SICAK ÖVGÜ
- Sade merak/soru → nötr, net
- Şaka/hafif takılma → hafif espri ile karşılık, ama saygılı kal
- GERÇEK eleştiri (görsel eksik / bilgi yanlış / kalite düşük) →
  **NOKTAYI KABUL ET — ASLA İNKÂR ETME, SAVUNMAYA GEÇME.** Kısa, dürüst
  bir kabul + niyet. Örnekler:
    "Haklısın, bunu daha iyi anlatabilirdim 🙏"
    "Doğru bir uyarı, elimden geleni yapacağım"
    "Dürüst geri bildirim için teşekkürler, düzeltmeye çalışacağım"
  Videoda olmayan bir şeyin olduğunu ASLA iddia etme.
- "X nerede / X ne demek" → kısa, sade bir açıklama + ince bir dokunuş

═══ ADIM 2 — TONU EŞLE ═══

- Sıcak övgü → sade, mütevazı bir teşekkür, emoji abartısı YOK
- Nötr soru → güvenli, kısa bir cevap
- Şaka → hafif bir sıcaklıkla karşılık ver, ciddiyetini koru
- Gerçek eleştiri → yukarıdaki kural

═══ KATI KURALLAR ═══

- 1-2 cümle, en fazla 20 kelime.
- Gerçek eleştiride kabul kelimeleri SERBEST ("haklısın", "doğru bir nokta",
  "teşekkürler", "elimden geleni yapacağım"). Yasak: "özür dilerim",
  "kusura bakma", uzun savunmalar, çok satırlı açıklamalar, bahaneler.
- Eleştiri dışı yorumlarda da ASLA özür dileme.
- Videoda olmayan bir şeyin olduğunu ASLA iddia etme — izleyici izledi, sen değil.
- ASLA abone ol / beğen / yorum yap / paylaş isteme.
- ASLA hashtag veya link kullanma.
- Yorumu birebir tekrar etme.
- SADECE TÜRKÇE yaz.
- "Sen" hitabı kullan (yumuşak), asla "siz" deme.
- En fazla 1 emoji (sadece anlamı güçlendiriyorsa).

Sadece cevap metnini yaz — tırnak yok, "Cevap:" ön eki yok, biçimlendirme yok."""


def yt_istemci():
    from google.oauth2.credentials import Credentials
    from google.auth.transport.requests import Request
    from googleapiclient.discovery import build
    SCOPES = ["https://www.googleapis.com/auth/youtube.force-ssl",
              "https://www.googleapis.com/auth/youtube"]
    creds = Credentials.from_authorized_user_file(str(TOKEN), SCOPES)
    if creds.expired and creds.refresh_token:
        try:
            creds.refresh(Request())
        except Exception as _h:  # invalid_grant vb. — ana pipeline yorumları zaten işliyor
            print(f"[yorum-bot] Token yenileme başarısız ({str(_h)[:90]}) — bu tur atlandı (zarif çıkış)")
            import sys; sys.exit(0)
    return build("youtube", "v3", credentials=creds, cache_discovery=False)


def log(msg: str):
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    satir = f"[{ts}] {msg}"
    print(satir)
    try:
        LOG.write_text((LOG.read_text() if LOG.exists() else "") + satir + "\n")
    except Exception:
        pass


def durum_oku() -> dict:
    if not DURUM.exists():
        return {"replied": {}, "last_run": None}
    try:
        return json.loads(DURUM.read_text())
    except Exception:
        return {"replied": {}, "last_run": None}


def durum_yaz(d: dict):
    DURUM.write_text(json.dumps(d, ensure_ascii=False, indent=2))


# ─── KOTA GUARD ───────────────────────────────────────────────────────────
def _pacific_bugun() -> str:
    """Pacific date (PST UTC-8 sabit yaklaşıklık; PDT yaz olsa 1 saat erken sıfırlanır = güvenli)."""
    return (datetime.now(timezone.utc) - timedelta(hours=8)).date().isoformat()


def kota_oku() -> dict:
    if not KOTA_STATE.exists():
        return {"pacific_tarih": _pacific_bugun(), "tahmini_unit": 0}
    try:
        d = json.loads(KOTA_STATE.read_text())
        if d.get("pacific_tarih") != _pacific_bugun():
            return {"pacific_tarih": _pacific_bugun(), "tahmini_unit": 0}
        return d
    except Exception:
        return {"pacific_tarih": _pacific_bugun(), "tahmini_unit": 0}


def kota_ekle(unit: int):
    d = kota_oku()
    d["tahmini_unit"] = d.get("tahmini_unit", 0) + unit
    try:
        KOTA_STATE.write_text(json.dumps(d, ensure_ascii=False, indent=2))
    except Exception:
        pass


def kota_dolu_mu() -> tuple[bool, int]:
    d = kota_oku()
    unit = d.get("tahmini_unit", 0)
    return (unit > KOTA_GUARD_ESIK, unit)


def kanal_bilgisi(yt) -> dict:
    """Kanal sahibi ID — kendi yorumlarımıza cevap vermeyelim."""
    ch = yt.channels().list(part="id,snippet,contentDetails", mine=True).execute()
    ci = ch["items"][0]
    return {
        "id": ci["id"],
        "title": ci["snippet"]["title"],
        "uploads_playlist": ci["contentDetails"]["relatedPlaylists"]["uploads"],
    }


def son_video_idleri(yt, uploads_playlist: str, limit: int = 30) -> list[str]:
    """Son N videonun ID'si."""
    out = []
    nxt = None
    while len(out) < limit:
        r = yt.playlistItems().list(
            part="contentDetails", playlistId=uploads_playlist,
            maxResults=min(50, limit - len(out)), pageToken=nxt
        ).execute()
        kota_ekle(1)
        out.extend(it["contentDetails"]["videoId"] for it in r.get("items", []))
        nxt = r.get("nextPageToken")
        if not nxt: break
    return out[:limit]


def video_yorumlari(yt, video_id: str) -> list[dict]:
    """Bir videonun TOP-LEVEL yorumları (reply'lar değil)."""
    out = []
    try:
        r = yt.commentThreads().list(
            part="snippet", videoId=video_id, maxResults=100,
            order="time", textFormat="plainText",
        ).execute()
        kota_ekle(1)
        for it in r.get("items", []):
            s = it["snippet"]["topLevelComment"]["snippet"]
            out.append({
                "comment_id": it["snippet"]["topLevelComment"]["id"],
                "video_id": video_id,
                "author": s.get("authorDisplayName", ""),
                "author_channel_id": s.get("authorChannelId", {}).get("value", ""),
                "metin": s.get("textOriginal", "") or s.get("textDisplay", ""),
                "yayinlanma": s.get("publishedAt", ""),
                "begeni": s.get("likeCount", 0),
                "reply_sayisi": it["snippet"].get("totalReplyCount", 0),
            })
    except Exception as h:
        log(f"  video {video_id[:8]} yorum çekme fail: {str(h)[:140]}")
    return out


def hizli_cevap_var_mi(metin: str) -> str | None:
    """Çok kısa yorumlar için template cevap (Gemini quota tasarrufu)."""
    import random
    m = metin.strip().lower()
    if len(m) <= 4:
        for k, v in HIZLI_CEVAPLAR.items():
            if k in m:
                return random.choice(v)
    return None


def gemini_cevap_uret(yorum: str, video_baslik: str = "") -> str | None:
    """Yoruma uygun Gemini reply üret."""
    import bridge
    prompt = (
        f"Video başlığı: {video_baslik}\n"
        f"İzleyici yorumu: \"{yorum}\"\n\n"
        f"Şimdi cevabını yaz (1 cümle, en fazla 12 kelime, SADECE TÜRKÇE):"
    )
    try:
        cevap = bridge.gemini_metin_uret(
            prompt=prompt,
            sistem_promptu=SISTEM_PROMPTU,
            sicaklik=0.85,
            max_token=80,
        ).strip()
        # Tırnak/format temizle
        cevap = cevap.strip('"').strip("'").strip()
        # Hashtag/link varsa kes
        if "#" in cevap or "http" in cevap.lower():
            cevap = cevap.split("#")[0].split("http")[0].strip()
        if len(cevap) > 200:
            cevap = cevap[:200]
        if not cevap or len(cevap) < 3:
            return None
        return cevap
    except Exception as h:
        log(f"  Gemini cevap üretemedi: {str(h)[:120]}")
        return None


def reply_gonder(yt, parent_comment_id: str, metin: str) -> bool:  # 50 unit/çağrı
    """YouTube'a reply gönder."""
    try:
        r = yt.comments().insert(
            part="snippet",
            body={"snippet": {"parentId": parent_comment_id, "textOriginal": metin}},
        ).execute()
        kota_ekle(50)
        return True
    except Exception as h:
        msg = str(h)
        log(f"  Reply gönderim fail: {msg[:180]}")
        if "quotaExceeded" in msg or "exceeded your" in msg.lower():
            kota_ekle(KOTA_LIMIT)
            log(f"  ⚠️ QUOTA EXCEEDED — bugün için kilitlendi.")
        return False


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--kuru", action="store_true", help="Test modu — sadece taslak yazar, göndermez")
    p.add_argument("--min-yas", type=int, default=5, help="Yorumun min yaşı (dakika)")
    p.add_argument("--max-cevap", type=int, default=20, help="Bir run'da max cevap sayısı")
    p.add_argument("--video-sayisi", type=int, default=30, help="Son N video taranır")
    args = p.parse_args()

    # KOTA GUARD
    dolu, mevcut = kota_dolu_mu()
    if dolu:
        log(f"⚠️ Kota guard: tahmini {mevcut}/{KOTA_LIMIT} unit dolu (>%85). Bot bugün skip — video upload için saklanıyor.")
        return 0

    yt = yt_istemci()
    kanal = kanal_bilgisi(yt)
    kota_ekle(1)
    log(f"=== Bot başladı — Kanal: {kanal['title']} (tahmini kota: {mevcut}u) ===")

    durum = durum_oku()
    replied = durum.get("replied", {})

    now = datetime.now(timezone.utc)
    min_yas = timedelta(minutes=args.min_yas)

    video_ids = son_video_idleri(yt, kanal["uploads_playlist"], args.video_sayisi)
    log(f"Son {len(video_ids)} video taranıyor...")

    aday_yorumlar = []
    for vid in video_ids:
        for yorum in video_yorumlari(yt, vid):
            # Atlama kuralları
            if yorum["comment_id"] in replied:
                continue
            if yorum["author_channel_id"] == kanal["id"]:
                continue  # Kendi yorumumuza cevap verme
            if not yorum["metin"].strip():
                continue
            # Yaş kontrolü
            try:
                t = datetime.fromisoformat(yorum["yayinlanma"].replace("Z", "+00:00"))
                if (now - t) < min_yas:
                    continue
            except Exception:
                continue
            yorum["yayinlanma_dt"] = t
            aday_yorumlar.append(yorum)
        time.sleep(0.05)

    # En eski (en az 5 dk önce) önce, ama 24 saat içi
    aday_yorumlar = [y for y in aday_yorumlar if (now - y["yayinlanma_dt"]) < timedelta(hours=72)]
    aday_yorumlar.sort(key=lambda y: y["yayinlanma_dt"])
    log(f"Cevaplanacak aday yorum: {len(aday_yorumlar)} (max {args.max_cevap} işlenecek)")

    cevaplanan = 0
    for yorum in aday_yorumlar[:args.max_cevap]:
        # Cevap loop'unda da guard
        dolu, mevcut = kota_dolu_mu()
        if dolu:
            log(f"⚠️ Kota mid-run %85+ ({mevcut}u) — kalan {len(aday_yorumlar) - cevaplanan} yorum yarına bırakıldı.")
            break

        log(f"\n→ Yorum: {yorum['author']}: {yorum['metin'][:80]}")
        # Önce hızlı cevap dene
        cevap = hizli_cevap_var_mi(yorum["metin"])
        kaynak = "hizli"
        if not cevap:
            # Video başlığını al — daha iyi prompt
            try:
                vr = yt.videos().list(part="snippet", id=yorum["video_id"]).execute()
                kota_ekle(1)
                baslik = vr["items"][0]["snippet"]["title"] if vr.get("items") else ""
            except Exception:
                baslik = ""
            cevap = gemini_cevap_uret(yorum["metin"], baslik)
            kaynak = "gemini"

        if not cevap:
            log(f"  Cevap üretilemedi, atlandı")
            continue

        log(f"  Cevap ({kaynak}): {cevap}")

        if args.kuru:
            log(f"  [KURU MOD] Gönderim atlandı")
            continue

        if reply_gonder(yt, yorum["comment_id"], cevap):
            log(f"  ✓ Reply gönderildi")
            replied[yorum["comment_id"]] = {
                "video_id": yorum["video_id"],
                "author": yorum["author"],
                "asıl_yorum": yorum["metin"][:200],
                "cevap": cevap,
                "kaynak": kaynak,
                "ts": now.isoformat(timespec="seconds"),
            }
            cevaplanan += 1
            durum["replied"] = replied
            durum_yaz(durum)
        else:
            log(f"  ✗ Gönderim başarısız")

        # Rate limit — bot izlenimi vermesin, yorum'lar arası 4-8 sn
        time.sleep(5)

    durum["last_run"] = now.isoformat(timespec="seconds")
    durum["last_replied_count"] = cevaplanan
    durum_yaz(durum)

    log(f"\n=== Bot bitti — {cevaplanan} cevap gönderildi (toplam history: {len(replied)}) ===")
    return 0


if __name__ == "__main__":
    sys.exit(main())
