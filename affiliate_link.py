"""
affiliate_link.py — Açıklama Affiliate Link Otomasyonu (Faz 5).

YouTube açıklamasına konuyla ilgili affiliate link otomatik ekler. YPP
eşiğinden BAĞIMSIZ gelir — affiliate satışları AdSense'den önce başlar.

Stratejiler:
  1) Amazon Associates US (TR'den signup yapılabilir, Payoneer ile ödeme)
  2) AliExpress Affiliate (TR'den OK)
  3) ShareASale (geniş kategori)
  4) Hostinger / NordVPN / digital tool affiliate'leri

Aktif olması için env'de ilgili affiliate tag/code'lar olmalı:
    AMAZON_ASSOCIATES_TAG=trendcatcher-20
    ALIEXPRESS_AFF_KEY=xxx

NOT: Hiç tag yoksa açıklamaya hiçbir şey eklenmez — güvenli no-op.

Kullanım (modül olarak):
    from affiliate_link import aciklama_zenginleştir
    yeni_aciklama = aciklama_zenginleştir(eski_aciklama, baslik, anahtar_kelimeler)
"""
import os
from pathlib import Path


PANEL_KOK = Path(__file__).parent

# Niş — psikoloji/zihin — anahtar kelime → product arama eşlemesi (psikoloji kitapları)
NIS_PRODUCT_HARITASI = {
    "habit": "atomic habits james clear",
    "dopamine": "dopamine nation book",
    "memory": "moonwalking with einstein memory book",
    "thinking": "thinking fast and slow kahneman",
    "persuasion": "influence robert cialdini",
    "psychology": "the psychology of money book",
    "brain": "behave robert sapolsky brain book",
    "overthinking": "stop overthinking book",
    "confidence": "the confidence gap book",
    "body language": "what every body is saying book",
    "personality": "personality isn't permanent book",
    "focus": "deep work cal newport",
    "emotions": "emotional intelligence daniel goleman",
    "mindset": "mindset carol dweck book",
}


def _aff_tag(servis: str) -> str | None:
    """Env veya .env'den affiliate code oku."""
    key = {
        "amazon": "AMAZON_ASSOCIATES_TAG",
        "aliexpress": "ALIEXPRESS_AFF_KEY",
    }.get(servis)
    if not key: return None
    v = os.environ.get(key)
    if v: return v
    envf = PANEL_KOK / ".env"
    if envf.exists():
        for line in envf.read_text().splitlines():
            if line.startswith(f"{key}="):
                return line.split("=", 1)[1].strip()
    return None


def en_uygun_keyword(baslik: str, tags: list[str]) -> str | None:
    """Başlık + tag'lardan en uygun keyword bul."""
    metin = (baslik + " " + " ".join(tags or [])).lower()
    for keyword in NIS_PRODUCT_HARITASI:
        if keyword in metin:
            return keyword
    return None


def amazon_link(keyword: str, tag: str) -> str:
    """Amazon US arama URL'si + affiliate tag."""
    import urllib.parse
    q = urllib.parse.quote_plus(NIS_PRODUCT_HARITASI[keyword])
    return f"https://www.amazon.com/s?k={q}&tag={tag}"


def aciklama_zenginleştir(aciklama: str, baslik: str, tags: list[str] = None) -> str:
    """Açıklamaya konuyla ilgili affiliate link bloğu ekle. Aktif tag yoksa
    no-op (güvenli)."""
    tags = tags or []
    keyword = en_uygun_keyword(baslik, tags)
    if not keyword:
        return aciklama

    blok_satirlari = []

    amazon_tag = _aff_tag("amazon")
    if amazon_tag:
        blok_satirlari.append(f"📖 Related read: {amazon_link(keyword, amazon_tag)}")

    if not blok_satirlari:
        return aciklama

    blok = "\n\n--\n" + "\n".join(blok_satirlari) + "\n(As an Amazon Associate, we earn from qualifying purchases.)"
    return aciklama.rstrip() + blok


if __name__ == "__main__":
    # Self test
    test = aciklama_zenginleştir(
        "Glass sponges live for 15000 years.",
        "Glass Sponges Live for 15,000 Years in the Deep Ocean",
        ["nature", "ocean", "biology"],
    )
    print(test)
