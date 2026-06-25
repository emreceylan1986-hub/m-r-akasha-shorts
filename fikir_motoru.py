#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
fikir_motoru.py — Mindgaps fikir seçim motoru
Erkan Kolcu "13 dakikada 1000 abone" videosundaki yöntemin koda dökülmüş hali.

4 mekanik:
  1) ID Farming      — yan nişlerden çok sayıda fikir adayı topla
  2) Cross-niş        — kanıtlı viral fikri psikoloji/beyin temasına uyarla
  3) Değer Denklemi   — Değer = (Rüya × Başarı) / (Zaman × Çaba)
  4) 5'te-5 filtresi  — 100 fikri 3-5'e indir

Entegrasyon: haberci.py adayları üretir → fikir_motoru.en_iyi_fikirler() skorlar+filtreler.
Standalone test: python3 fikir_motoru.py
"""
import math, os, json

# ---------------------------------------------------------------------------
# CROSS-NİŞ BANKASI — psikoloji/beyin kanalının çekeceği yan nişler ve
# bu nişlerde KANITLANMIŞ viral Shorts format iskeletleri.
# (viral_radar.py canlı veriyle bunu besler; buradakiler tohum/fallback.)
# ---------------------------------------------------------------------------
YAN_NISLER = ["ilişki/aşk", "gizem/korku", "para/başarı", "vücut/sağlık",
              "rüya/uyku", "kişilik testi", "sosyal davranış", "hafıza/öğrenme"]

VIRAL_FORMAT_ISKELETLERI = [
    "Why you {everyday behavior} (the real reason)",
    "{Number} signs you're {trait} without knowing it",
    "Your brain does THIS when {common situation}",
    "The psychology trick that makes people {desired effect}",
    "What your {small habit} secretly says about you",
    "This is why you can't stop {behavior}",
    "{Number} things your brain does in the first {time}",
    "The reason {universal experience} feels so {emotion}",
]

# Rüya sonucu çok yüksek olan temalar (izleyici kendini görür = paylaşır)
YUKSEK_RUYA_TEMALARI = ["senin hakkında", "kişiliğin", "neden böyle yapıyorsun",
                        "zekâ", "çekicilik", "ilişkiler", "hafıza güçlendirme"]


# ---------------------------------------------------------------------------
# 1) DEĞER DENKLEMİ
# ---------------------------------------------------------------------------
def deger_skoru(ruya, basari, zaman, caba):
    """
    Girdiler 1-10:
      ruya   = Rüya sonucu (izleyicinin istediği şey) — YÜKSEK iyi
      basari = Başarı/inandırıcılık olasılığı          — YÜKSEK iyi
      zaman  = Zaman zarfı (ne kadar sürer)            — DÜŞÜK iyi
      caba   = Çaba/fedakârlık (izlemek/anlamak)       — DÜŞÜK iyi
    Çıktı: {skor: 0-100, guclu_kol: kaç kol >=7, kollar, uretilsin_mi}
    """
    d = max(1, min(10, ruya)) / 10
    s = max(1, min(10, basari)) / 10
    hiz = (11 - max(1, min(10, zaman))) / 10   # düşük zaman -> yüksek hız
    kolay = (11 - max(1, min(10, caba))) / 10  # düşük çaba  -> yüksek kolaylık

    # geometrik ortalama: tüm kollar makul olmalı, zayıf kol cezalandırılır
    deger = (d * s * hiz * kolay) ** 0.25
    kollar = {"ruya": d, "basari": s, "hiz": hiz, "kolay": kolay}
    guclu = sum(1 for v in kollar.values() if v >= 0.7)
    # video kuralı: en az 2-3 kolu vur. 3+ güçlü kol VEYA 2 güçlü + iyi denge
    uretilsin = guclu >= 3 or (guclu >= 2 and deger >= 0.6)
    return {"skor": round(deger * 100, 1), "guclu_kol": guclu,
            "kollar": {k: round(v, 2) for k, v in kollar.items()},
            "uretilsin_mi": uretilsin}


# ---------------------------------------------------------------------------
# 2) 5'TE-5 FİLTRESİ
# ---------------------------------------------------------------------------
def beste_bes(fikir):
    """
    fikir dict alanları:
      heyecan   (bool/0-1) : açı ayırt edici/merak güçlü mü
      mumkun    (bool)     : pipeline üretebilir mi
      kanit_izlenme (int)  : benzer videonun aldığı max izlenme
      hedef_izlenme (int)  : bizim beklentimiz
      paketlenebilir (bool): iyi başlık+kapak çıkar mı (deger_skoru'na bağlanır)
      trend_skoru (0-100)  : Google Trends / talep
    Çıktı: {gecti: bool, kalan_sorular: [...] }
    """
    kalan = []
    if not fikir.get("heyecan", True):
        kalan.append("①heyecan/ayırt-edicilik yok")
    if not fikir.get("mumkun", True):
        kalan.append("②üretilemez (imkân yok)")
    if fikir.get("kanit_izlenme", 0) < fikir.get("hedef_izlenme", 10000):
        kalan.append("③izlenme kanıtı yetersiz")
    if not fikir.get("paketlenebilir", True):
        kalan.append("④paketlenemiyor (başlık/kapak)")
    if fikir.get("trend_skoru", 100) < 25:
        kalan.append("⑤kitle/talep zayıf")
    return {"gecti": len(kalan) == 0, "kalan_sorular": kalan}


# ---------------------------------------------------------------------------
# 3) BİRLEŞİK SEÇİCİ — ID Farming çıktısını skorla+filtrele+sırala
# ---------------------------------------------------------------------------
def en_iyi_fikirler(adaylar, n=5):
    """
    adaylar: [{baslik, ruya, basari, zaman, caba, ...5te5 alanları}]
    Döner: en değerli n fikir (Değer Denklemi + 5'te-5 geçenler), skor sıralı.
    """
    degerlendirildi = []
    for a in adaylar:
        dv = deger_skoru(a.get("ruya", 5), a.get("basari", 5),
                         a.get("zaman", 5), a.get("caba", 5))
        # paketlenebilirlik = değer kollarının ortalaması yüksekse evet
        a.setdefault("paketlenebilir", dv["skor"] >= 50)
        bb = beste_bes(a)
        a["_deger"] = dv
        a["_5te5"] = bb
        a["_uygun"] = dv["uretilsin_mi"] and bb["gecti"]
        degerlendirildi.append(a)

    uygun = [a for a in degerlendirildi if a["_uygun"]]
    uygun.sort(key=lambda x: x["_deger"]["skor"], reverse=True)
    return uygun[:n], degerlendirildi


# ---------------------------------------------------------------------------
# CLI DEMO / TEST
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    # örnek ID Farming çıktısı (gerçekte haberci.py + viral_radar üretir)
    ornek = [
        {"baslik": "Why you check your phone the second you wake up",
         "ruya": 8, "basari": 9, "zaman": 2, "caba": 2,
         "kanit_izlenme": 1_200_000, "hedef_izlenme": 50_000, "trend_skoru": 80},
        {"baslik": "The 3-second rule that makes anyone trust you",
         "ruya": 9, "basari": 7, "zaman": 2, "caba": 3,
         "kanit_izlenme": 900_000, "hedef_izlenme": 50_000, "trend_skoru": 70},
        {"baslik": "A 40-minute deep dive into dopamine receptors",
         "ruya": 6, "basari": 6, "zaman": 9, "caba": 9,
         "kanit_izlenme": 8_000, "hedef_izlenme": 50_000, "trend_skoru": 30},
        {"baslik": "What your sleeping position reveals about you",
         "ruya": 9, "basari": 8, "zaman": 2, "caba": 2,
         "kanit_izlenme": 2_400_000, "hedef_izlenme": 50_000, "trend_skoru": 88},
        {"baslik": "Niche academic study nobody searches for",
         "ruya": 4, "basari": 5, "zaman": 6, "caba": 7,
         "kanit_izlenme": 1_500, "hedef_izlenme": 50_000, "trend_skoru": 10},
    ]
    secilen, hepsi = en_iyi_fikirler(ornek, n=3)
    print("=== TÜM ADAYLAR (değer skoru) ===")
    for a in sorted(hepsi, key=lambda x: x["_deger"]["skor"], reverse=True):
        d = a["_deger"]; b = a["_5te5"]
        durum = "✅ ÜRET" if a["_uygun"] else "❌ ELE"
        print(f"{durum} [{d['skor']:5.1f}] güçlü-kol:{d['guclu_kol']} | {a['baslik']}")
        if b["kalan_sorular"]:
            print(f"        5te5: {', '.join(b['kalan_sorular'])}")
    print(f"\n=== SEÇİLEN İLK {len(secilen)} (üretim kuyruğuna) ===")
    for i, a in enumerate(secilen, 1):
        print(f"{i}. [{a['_deger']['skor']}] {a['baslik']}")
