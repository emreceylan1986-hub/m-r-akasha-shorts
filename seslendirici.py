"""
seslendirici.py — YouTube Shorts Seslendirme Üreticisi

Akış:
    1) haberler.json içindeki ilk haberi okur
    2) Gemini ile çarpıcı bir İngilizce Shorts senaryosu üretir
    3) Senaryoyu bridge.metin_onay_iste() ile denetler — REVIZE varsa
       revize edilmiş sürümü kullanır
    4) edge-tts (en-US-AriaNeural, sweet tone) ile MP3 dosyasına seslendirir
    5) Hem .txt (metin) hem .mp3 (ses) çıktısı verir

Çıktı klasörü: ses_ciktilari/
    senaryo_<damga>.txt
    seslendirme_<damga>.mp3
"""

import asyncio
import json
import sys
from datetime import datetime
from pathlib import Path

import edge_tts

import bridge


KAYNAK_DOSYA = Path(__file__).parent / "haberler.json"
CIKTI_KLASORU = Path(__file__).parent / "ses_ciktilari"

SES = "tr-TR-EmelNeural"          # Türkçe kadın sıcak ses (Akasha — kadın sahibi)
SES_IKINCI = "tr-TR-AhmetNeural"  # Türkçe erkek ses (dialog için)
HIZ = "-8%"        # Hafif yavaş — spiritüel/derin ton (Türkçe TTS biraz hızlı)
PERDE = "+0Hz"
SES_SEVIYESI = "+0%"

# FAZ 8: Çarşamba (haftada 1) → dialog formatı dene
DIALOG_GUN = 2  # Wednesday

SENARYO_SISTEM_PROMPTU = """Türkçe spiritüel/Jung-vari motivasyon YouTube Shorts
anlatıcısısın — kanal: **Aydınlanmanın Doruk Noktası** (@akashainme).
İşin RETENTION — ilk 2 saniye videonun yaşar ya da ölür.
İzleyici "vay bu ben" diye hissetmeli.

═══ KURAL #0 — KAYNAK SADAKATI (en üst kural) ═══
Senaryo kaynakla %100 uyumlu olmalı. Ne mesaj ne yazar ne de kavramı çarpıt.
- ACIM (Mucizeler Kursu) bir ders veriyorsa o dersin gerçek mesajını anlat
- Tao Te Jing bir bölüm: gerçek Lao Tzu metnini referans al
- Jung kavramı: Jung'un gerçek yazılarına sadık kal (gölge, persona, vb.)
- Sahte alıntı, uydurma yazar, abartı sayı YOK.

DİL: Sade, temiz, akıcı **TÜRKÇE**. Yabancı sözcük asgari.

TON: Sakin, derin, bilge — bağırmayan. Yunus Emre + Mevlana tonu.
"Sen" hitabı (yumuşak), asla "siz". Klişe motivasyon DEĞİL.

═══ YAPI (toplam 90-120 kelime ≈ 50-60 saniye Türkçe TTS) ═══
- HOOK (ilk cümle, MAX 8 kelime): kendini-görme açıcı.
  Örnek: "Carl Jung en güçlü hediyenin sandığın yerde olmadığını söyledi."
        "Tao Te Jing'de su, en güçsüzdür — ama her şeyi yener."
        "Mucizeler Kursu'nun ilk dersi seni nasıl özgür kılar?"
  YASAK açılışlar (AI sinyali):
     "Biliyor muydun..." / "Hiç düşündün mü..." / "Bir gün..."

- TURN (1 cümle): hook'u açan sürpriz gerçek
- CONTEXT (1-2 cümle): kavramın derin anlamı, sade dilde
  Mümkünse SOMUT bir yıl, alıntı, kavram adı geçsin (Jung 1916, ACIM Ders 137,
  Tao Te Jing Bölüm 8). Bu güven inşa eder.
- PAYOFF (1 kısa cümle): izleyiciyi içine döndüren düşünce.
  Örnek: "Belki de aradığın hiç kaybolmadı, sen onun kendini görmesini bekledin."
- SUBSCRIBE CTA (son cümle, MAX 7 kelime, opsiyonel-warm):
  Örnek: "Yolun aydın olsun — abone ol."
         "Bu seriyi kaçırma — abone ol."
         "İçsel yolculuğa devam — takip et."

YASAK:
- "Şimdi sana harika bir sır vereceğim" (reklamcı dil)
- "Hayat bir yolculuktur" (klişe)
- "Beynimizin %10'u" (pop-bilim yalan)
- 'Like', 'yorum yap', 'paylaş' (sadece abone ol)
- # hashtag, emoji (senaryo metninde)

Kısıt:
- Toplam: 90-120 kelime (CTA dahil). 120'yi geçme.
- Kısa cümleler, konuşma ritmi. "Bir gün düşündüm ki..." tarzı yumuşak akış.
- Sadece konuşulan metni çıktı ver — başlık yok, etiket yok, tırnak yok.
"""


def ilk_haberi_oku() -> dict:
    if not KAYNAK_DOSYA.exists():
        raise FileNotFoundError(f"Kaynak yok: {KAYNAK_DOSYA}")
    veri = json.loads(KAYNAK_DOSYA.read_text(encoding="utf-8"))
    haberler = veri.get("haberler") or []
    if not haberler:
        raise ValueError("haberler.json içinde hiç haber yok.")
    return haberler[0]


def senaryo_uret(haber: dict) -> str:
    # FAZ 7 — 60 sn A/B: Pazartesi+Perşembe günlerinde 100-115 kelime uzun varyant
    # (~50-55 sn). Diğer günlerde standart 60-75 (~25-30 sn).
    # Watch-time YPP için kritik — uzun varyant test sayar.
    import datetime
    wd = datetime.datetime.utcnow().weekday()  # 0=Mon, 3=Thu
    hour = datetime.datetime.utcnow().hour
    # Uzun varyant: Pazartesi 12 UTC + Perşembe 16 UTC (haftada 2 video deneme)
    uzun_varyant = (wd == 0 and hour < 14) or (wd == 3 and 14 <= hour < 18)
    # FAZ 8: Çarşamba (DIALOG_GUN=2) — dialog formatı dene (ikili ses)
    dialog_varyant = (wd == DIALOG_GUN)

    if uzun_varyant:
        hedef_kelime = "100-115"
        min_kelime = 95
    elif dialog_varyant:
        hedef_kelime = "70-85"
        min_kelime = 60
    else:
        hedef_kelime = "100-130"
        min_kelime = 90  # 60-saniye Shorts → CPM 2x + watch time +%50

    temel_prompt = (
        f"Headline: {haber['baslik']}\n"
        f"Source URL: {haber['url']}\n"
        f"Engagement signal: score={haber.get('skor')}, "
        f"comments={haber.get('yorum_sayisi')}, age={haber.get('yas_saat')}h\n\n"
        f"Write the Shorts voice-over script now ({hedef_kelime} words, English only)."
    )
    if uzun_varyant:
        temel_prompt += (
            f"\n\nLONG-FORM VARIANT (test): aim for {hedef_kelime} words / ~50-55 sec.\n"
            f"Add 1-2 extra concrete examples or comparisons in CONTEXT.\n"
            f"Hook + subscribe CTA stay punchy; expansion in the middle."
        )
    elif dialog_varyant:
        temel_prompt += (
            f"\n\nDIALOG VARIANT (weekly test): write the script as a TWO-PERSON dialog.\n"
            f"Format STRICTLY:\n"
            f"  A: <line>\n"
            f"  B: <line>\n"
            f"  A: <line>\n"
            f"  ...\n"
            f"Roles: A = main narrator (curious, warm). B = reactive partner\n"
            f"  (surprised, asks short follow-ups: 'Wait, really?', 'How?', 'No way').\n"
            f"Keep the HOOK as A's first line (still max 8 words, truthful).\n"
            f"B's lines are SHORT (3-6 words). Total exchange = {hedef_kelime} words.\n"
            f"End with A's subscribe CTA on a new 'A:' line.\n"
            f"Output ONLY the dialog lines."
        )
    # Çok kısa çıkarsa 1 kez daha dene + FAZ 8: Hook Predictor ile zayıf hook'u rejene
    son_senaryo = ""
    for deneme in range(3):
        if deneme == 0:
            ek = ""
        elif son_senaryo and len(son_senaryo.split()) < min_kelime:
            ek = (f"\n\nYOUR PREVIOUS DRAFT WAS TOO SHORT ({len(son_senaryo.split())} words). "
                  f"Rewrite it {hedef_kelime} words by adding one concrete detail to CONTEXT. Keep the same hook.")
        else:
            # Hook zayıf — yeni hook iste
            ek = (f"\n\nYOUR PREVIOUS HOOK WAS WEAK. The first sentence must be MAX 8 words, "
                  f"with a concrete subject + a surprising specific detail (number, comparison, or contradiction). "
                  f"NO question marks, NO 'did you know', NO generic openers. Rewrite the entire script with a stronger hook.")

        senaryo = bridge.gemini_metin_uret(
            prompt=temel_prompt + ek,
            sistem_promptu=SENARYO_SISTEM_PROMPTU,
            sicaklik=0.85 if deneme > 0 else 0.8,
            max_token=2048,
        ).strip('"').strip()
        son_senaryo = senaryo

        if len(senaryo.split()) < min_kelime:
            continue  # Yetersiz uzunluk — bir sonraki deneme

        # FAZ 8: Hook predictor
        try:
            import hook_predictor
            skor, sebep, alt = hook_predictor.hook_skor_ver(senaryo)
            print(f"[seslendirici] Hook skor: {skor}/10 — {sebep[:80]}")
            if skor >= 6:
                return senaryo
            if alt:
                print(f"   ↪ Önerilen alt hook: {alt}")
            if deneme < 2:
                continue  # Yeniden dene
            else:
                # Son deneme — kabul et
                return senaryo
        except Exception as h:
            print(f"[seslendirici] Hook predictor hata: {str(h)[:120]} — kabul edildi")
            return senaryo
    return son_senaryo
    raise RuntimeError(
        f"Senaryo 2 denemede de çok kısa ({len(son_senaryo.split())} kelime). "
        f"Ham çıktı: {son_senaryo!r}"
    )


def senaryoyu_denetlet(senaryo: str, haber: dict) -> str:
    baglam = (
        f"Bu metin ~25-30 saniyelik viral YouTube Shorts seslendirme senaryosu.\n"
        f"Haber: {haber['baslik']}\n"
        f"Kaynak: {haber['url']}\n"
        f"Hedef: KESİN 60-75 İngilizce kelime (subscribe CTA dahil). ASLA uzatma — kısa = yüksek "
        f"tamamlanma oranı (en kritik Shorts sinyali). 70 kelimeyi aşan "
        f"revize KABUL EDİLEMEZ. Güçlü hook + curiosity bridge korunmalı, "
        f"dil İngilizce kalmalı."
    )
    rapor = bridge.metin_onay_iste(senaryo, baglam=baglam)
    print(f"[seslendirici] Metin denetimi → {rapor['karar']}: {rapor['ozet']}")
    if rapor.get("iyilestirmeler"):
        for i in rapor["iyilestirmeler"]:
            print(f"  ↪ {i}")
    return rapor.get("revize_metin", senaryo).strip()


_STOPWORDS = {
    "the", "a", "an", "is", "are", "was", "were", "to", "of", "in", "on",
    "at", "for", "and", "or", "but", "it", "its", "this", "that", "with",
    "as", "by", "be", "has", "have", "had", "you", "your", "can", "will",
    "just", "not", "no", "now", "so", "we", "they", "he", "she", "i",
    "from", "up", "out", "if", "all", "do", "does", "did", "what", "why",
}


def _ass_zaman(ms: float) -> str:
    """ASS zaman formatı: H:MM:SS.cc (centisecond)."""
    toplam = int(ms)
    sn, msec = divmod(toplam, 1000)
    saat, sn = divmod(sn, 3600)
    dk, sn = divmod(sn, 60)
    return f"{saat:d}:{dk:02d}:{sn:02d}.{msec // 10:02d}"


def _vurgu_kelime(kelimeler: list[str]) -> int:
    """Bloktaki en güçlü kelimenin index'i: en uzun stopword-olmayan."""
    en_iyi, en_uzun = 0, -1
    for i, k in enumerate(kelimeler):
        sade = "".join(c for c in k.lower() if c.isalnum())
        if sade in _STOPWORDS:
            continue
        if len(sade) > en_uzun:
            en_uzun, en_iyi = len(sade), i
    return en_iyi


def _karaoke_ass(cues: list[tuple[int, int, str]], grup: int = 3) -> str:
    """
    Captacity-tarzı animasyonlu viral altyazı (Captacity repo mantığı, kendi
    implementasyonumuz — ek bağımlılık yok).
    - 3 kelimelik hızlı bloklar
    - Her bloğa POP animasyonu (\\t ile scale büyüt-küçült)
    - Hızlı fade-in (\\fad)
    - Ana kelime SARI + büyütülmüş scale
    - Kalın siyah outline + gölge (sessiz izleyene maksimum okunabilirlik)
    """
    bas = (
        "[Script Info]\n"
        "ScriptType: v4.00+\n"
        "PlayResX: 1080\n"
        "PlayResY: 1920\n"
        # WrapStyle 0: smart wrap (uzun satırı otomatik kırar — taşma yasak)
        "WrapStyle: 0\n"
        "ScaledBorderAndShadow: yes\n\n"
        "[V4+ Styles]\n"
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, "
        "OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, "
        "ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, "
        "Alignment, MarginL, MarginR, MarginV, Encoding\n"
        # Font 64 → 56 (uzun kelimeler için ekstra alan), kalın outline 6, gölge 3
        # Margin L/R 60 → 80 (taşma sıfır toleransı)
        "Style: Pop,Arial Black,56,&H00FFFFFF,&H000000FF,&H00000000,&H80000000,"
        "1,0,0,0,100,100,0,0,1,6,3,2,80,80,260,1\n\n"
        "[Events]\n"
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, "
        "MarginV, Effect, Text\n"
    )
    SARI = r"{\c&H0000FFFF&}"
    BEYAZ = r"{\c&H00FFFFFF&}"
    # Captacity-tarzı pop: ilk 120ms scale 70→105→100, fade-in 80ms.
    POP_GIRIS = r"{\fad(80,40)\t(0,80,\fscx110\fscy110)\t(80,160,\fscx100\fscy100)}"
    satirlar: list[str] = []
    # MAX_KARAKTER_PER_GRUP: 1080px ekran, 80px margin, font Arial Black 56pt
    # Tahmini her harf ~28-32 piksel → kullanılabilir 920px = ~30 karakter max
    # Güvenli sınır: 24 karakter (uzun kelime + boşluklar dahil)
    MAX_KARAKTER = 24

    def _akilli_grupla(kelimeler):
        """Karakter sayısına göre grup oluştur — uzun kelime taşmasın."""
        gruplar = []
        mevcut = []
        mevcut_uzunluk = 0
        for k in kelimeler:
            # Tek başına uzun kelime: ayrı gruba
            if len(k) >= MAX_KARAKTER:
                if mevcut:
                    gruplar.append(mevcut)
                    mevcut = []
                    mevcut_uzunluk = 0
                gruplar.append([k])
                continue
            # Eklemek taşırır mı?
            yeni_uzunluk = mevcut_uzunluk + len(k) + (1 if mevcut else 0)
            if yeni_uzunluk > MAX_KARAKTER and mevcut:
                gruplar.append(mevcut)
                mevcut = [k]
                mevcut_uzunluk = len(k)
            else:
                mevcut.append(k)
                mevcut_uzunluk = yeni_uzunluk
        if mevcut:
            gruplar.append(mevcut)
        return gruplar

    for offset, duration, metin in cues:
        kelimeler = metin.split()
        if not kelimeler:
            continue
        gruplar = _akilli_grupla(kelimeler)
        toplam = len(kelimeler)
        baslangic = offset
        for g in gruplar:
            pay = duration * (len(g) / toplam)
            bit = baslangic + pay
            vi = _vurgu_kelime(g)
            parcalar = []
            for i, w in enumerate(g):
                if i == vi:
                    # ana kelime: sarı + biraz daha büyük (15% scale)
                    parcalar.append(rf"{SARI}{{\fscx115\fscy115}}{w.upper()}{{\fscx100\fscy100}}{BEYAZ}")
                else:
                    parcalar.append(w)
            metin_ass = POP_GIRIS + " ".join(parcalar)
            satirlar.append(
                f"Dialogue: 0,{_ass_zaman(baslangic/10000.0)},"
                f"{_ass_zaman(bit/10000.0)},Pop,,0,0,0,,{metin_ass}"
            )
            baslangic = bit
    return bas + "\n".join(satirlar) + "\n"


def _dialog_mu(metin: str) -> bool:
    """Senaryo 'A:' / 'B:' formatında mı?"""
    satirlar = [s.strip() for s in metin.splitlines() if s.strip()]
    a_b_satir = sum(1 for s in satirlar if s.startswith(("A:", "B:")))
    return a_b_satir >= 3


def _dialog_parse(metin: str) -> list[tuple[str, str]]:
    """[(speaker, text), ...] döner."""
    out = []
    for satir in metin.splitlines():
        satir = satir.strip()
        if not satir: continue
        if satir.startswith("A:"):
            out.append(("A", satir[2:].strip()))
        elif satir.startswith("B:"):
            out.append(("B", satir[2:].strip()))
    return out


async def _tts_tek_segment(metin: str, voice: str) -> tuple[bytes, list]:
    """Bir segmenti edge-tts ile sesli yap. Audio bytes + cues döner."""
    import asyncio as _aio
    son_hata = None
    for deneme in range(3):
        try:
            iletisim = edge_tts.Communicate(text=metin, voice=voice, rate=HIZ, pitch=PERDE, volume=SES_SEVIYESI)
            audio = bytearray()
            cues = []
            async for chunk in iletisim.stream():
                if chunk["type"] == "audio":
                    audio.extend(chunk["data"])
                elif chunk["type"] in ("WordBoundary", "SentenceBoundary"):
                    cues.append((chunk["offset"], chunk["duration"], chunk["text"]))
            if audio and cues: return bytes(audio), cues
            raise RuntimeError("boş audio")
        except Exception as h:
            son_hata = h
            await _aio.sleep(min(2 ** (deneme + 2), 30))
    raise RuntimeError(f"TTS fail: {son_hata}")


async def _seslendir_dialog_async(metin: str, mp3_yolu: Path, ass_yolu: Path):
    """Dialog formatı için 2 sesle render et."""
    parcalar = _dialog_parse(metin)
    if not parcalar:
        # Parse fail → standart mod
        return await _seslendir_async(metin, mp3_yolu, ass_yolu)

    print(f"[seslendirici] DIALOG modu — {len(parcalar)} parça (A={SES} B={SES_IKINCI})")
    tum_cues = []
    audio_parcalar = []
    offset_ms = 0
    for speaker, txt in parcalar:
        voice = SES if speaker == "A" else SES_IKINCI
        audio, cues = await _tts_tek_segment(txt, voice)
        # Cues'leri offset'le kaydır
        for of, du, te in cues:
            tum_cues.append((of + offset_ms, du, te))
        audio_parcalar.append(audio)
        # En son cue'nun bitiş zamanı
        if cues:
            son = cues[-1]
            offset_ms += son[0] + son[1] + 200  # 200ms boşluk arası
        # Aralarda kısa silence ekle
        import io
        audio_parcalar.append(b"")  # placeholder

    # Audio dosyalarını birleştir + 200ms silence
    with open(mp3_yolu, "wb") as f:
        for ap in audio_parcalar:
            if ap: f.write(ap)
    if not tum_cues:
        raise RuntimeError("dialog cues boş")
    ass_yolu.write_text(_karaoke_ass(tum_cues), encoding="utf-8")
    print(f"   ↳ Dialog MP3 yazıldı, {len(tum_cues)} cue")


async def _seslendir_async(metin: str, mp3_yolu: Path, ass_yolu: Path) -> None:
    """
    MP3 ses + viral-Shorts stili ASS altyazı (sarı keyword highlight).
    Dialog formatı ('A:' / 'B:') varsa otomatik 2 ses kullanır.
    """
    # FAZ 8: Dialog detect
    if _dialog_mu(metin):
        return await _seslendir_dialog_async(metin, mp3_yolu, ass_yolu)

    import asyncio as _aio
    son_hata: Exception | None = None
    for deneme in range(5):
        try:
            iletisim = edge_tts.Communicate(
                text=metin,
                voice=SES,
                rate=HIZ,
                pitch=PERDE,
                volume=SES_SEVIYESI,
            )
            cues: list[tuple[int, int, str]] = []
            with open(mp3_yolu, "wb") as ses:
                async for chunk in iletisim.stream():
                    if chunk["type"] == "audio":
                        ses.write(chunk["data"])
                    elif chunk["type"] in ("WordBoundary", "SentenceBoundary"):
                        cues.append((chunk["offset"], chunk["duration"], chunk["text"]))
            if not cues:
                raise RuntimeError("edge-tts hiç altyazı zamanlaması döndürmedi.")
            ass_yolu.write_text(_karaoke_ass(cues), encoding="utf-8")
            return
        except Exception as hata:
            son_hata = hata
            bekle = min(2 ** (deneme + 2), 60)
            print(
                f"[seslendirici] edge-tts hata ({type(hata).__name__}) — "
                f"{bekle}s sonra yeniden ({deneme+1}/5)",
                flush=True,
            )
            await _aio.sleep(bekle)
    raise RuntimeError(f"edge-tts 5 denemede de başarısız: {son_hata}")


def seslendir(metin: str, mp3_yolu: Path, ass_yolu: Path) -> None:
    asyncio.run(_seslendir_async(metin, mp3_yolu, ass_yolu))


def main() -> int:
    try:
        CIKTI_KLASORU.mkdir(exist_ok=True)
        damga = datetime.now().strftime("%Y%m%d_%H%M%S")

        print("[seslendirici] İlk haber okunuyor...")
        haber = ilk_haberi_oku()
        print(f"  → {haber['baslik']}")

        print("[seslendirici] Gemini ile senaryo üretiliyor...")
        taslak = senaryo_uret(haber)
        print("─" * 60)
        print(taslak)
        print("─" * 60)

        print("[seslendirici] Senaryo denetime gönderiliyor...")
        final_metin = senaryoyu_denetlet(taslak, haber)
        print("─" * 60)
        print("FİNAL METİN:")
        print(final_metin)
        print("─" * 60)

        txt_yolu = CIKTI_KLASORU / f"senaryo_{damga}.txt"
        mp3_yolu = CIKTI_KLASORU / f"seslendirme_{damga}.mp3"
        ass_yolu = CIKTI_KLASORU / f"altyazi_{damga}.ass"
        txt_yolu.write_text(final_metin, encoding="utf-8")

        print(f"[seslendirici] edge-tts ile ses + ASS altyazı üretiliyor ({SES})...")
        seslendir(final_metin, mp3_yolu, ass_yolu)

        boyut_kb = mp3_yolu.stat().st_size / 1024
        ass_dialog = ass_yolu.read_text(encoding="utf-8").count("Dialogue:")
        print(f"[seslendirici] MP3 hazır: {mp3_yolu.name} ({boyut_kb:.1f} KB)")
        print(f"[seslendirici] ASS hazır: {ass_yolu.name} ({ass_dialog} altyazı bloğu, sarı vurgulu)")
        print(f"[seslendirici] TXT hazır: {txt_yolu.name}")
        return 0
    except (FileNotFoundError, ValueError) as hata:
        print(f"[seslendirici] Veri hatası: {hata}", file=sys.stderr)
        return 2
    except RuntimeError as hata:
        print(f"[seslendirici] Gemini/bridge hatası: {hata}", file=sys.stderr)
        return 3
    except OSError as hata:
        print(f"[seslendirici] Dosya/ağ hatası: {hata}", file=sys.stderr)
        return 4


if __name__ == "__main__":
    sys.exit(main())
