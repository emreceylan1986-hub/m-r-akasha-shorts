#!/usr/bin/env python3
"""
imla.py — Türkçe yazım/imla kapısı (16 Eyl 2026).

NEDEN VAR: Emre — "akashada imla ve yazım kurallarına dikkat et. alt yazılarda
ve açıklamalarda yazım ve imla kurallarına uyulsun."
Ölçüm: son 10 başlığın 10'u da küçük harfle başlıyordu ve özel isimler küçüktü
("mevlana ve mesnevinin ilk dizeleri", "ibn arabi ve alem i misal",
"yunus emre ve benliğin sınırları"). Kök sebep yukleyici.py'deki metadata
promptunda "Emoji yok, BÜYÜK HARF yok" ifadesiydi — ALL CAPS yasağı kastediliyordu
ama model "hiç büyük harf kullanma" diye uygulayıp özel isimleri de küçülttü.

Prompt düzeltildi, ama prompt tek başına yetmez (14 Ağu dersi: kural promptta
olmasına rağmen model %83 uymuyordu). Bu modül DETERMİNİSTİK son kapı:
cümle başını büyütür, bilinen özel isimleri düzeltir, özel isme gelen eki
kesme işaretiyle ayırır.
"""
import re

# Kanalın sık geçen özel adları — doğru yazımlarıyla.
# Anahtar: sadeleştirilmiş (küçük, şapkasız) hâli · Değer: doğru yazım.
OZEL_ADLAR = {
    "mevlana": "Mevlânâ", "mevlâna": "Mevlânâ", "rumi": "Rumi",
    "mesnevi": "Mesnevi", "şems": "Şems", "sems": "Şems",
    "yunus emre": "Yunus Emre", "hacı bektaş": "Hacı Bektaş",
    "ibn arabi": "İbn Arabî", "ibn arabî": "İbn Arabî", "ibnarabi": "İbn Arabî",
    "gazali": "Gazâlî", "hallac": "Hallâc", "niyazi mısri": "Niyazi Mısrî",
    "carl jung": "Carl Jung", "jung": "Jung", "freud": "Freud",
    "sigmund freud": "Sigmund Freud", "dostoyevski": "Dostoyevski",
    "nietzsche": "Nietzsche", "sokrates": "Sokrates", "platon": "Platon",
    "aristoteles": "Aristoteles", "epiktetos": "Epiktetos",
    "marcus aurelius": "Marcus Aurelius", "seneca": "Seneca",
    "lao tzu": "Lao Tzu", "konfüçyüs": "Konfüçyüs", "buda": "Buda",
    "mucizeler kursu": "Mucizeler Kursu", "kuran": "Kur'an", "kur'an": "Kur'an",
    "allah": "Allah", "tanrı": "Tanrı", "mesih": "Mesih",
    "tasavvuf": "tasavvuf", "sufi": "sufi",
    "alem i misal": "âlem-i misal", "alem-i misal": "âlem-i misal",
    "vahdet i vücud": "vahdet-i vücûd", "vahdet-i vücud": "vahdet-i vücûd",
    "fena fillah": "fenâ fillâh", "insan ı kamil": "insân-ı kâmil",
    "insan-ı kamil": "insân-ı kâmil", "nefs i emmare": "nefs-i emmâre",
    "sehnsucht": "Sehnsucht", "anima": "anima", "animus": "animus",
}

# Özel ada gelen ekler kesme işaretiyle ayrılır: Mesnevinin → Mesnevi'nin
_EK = (r"(?:n[ıiuü]n|[ıiuü]n|y[ıiuü]|[ıiuü]|[ae]|y[ae]|d[ae]|t[ae]|d[ae]n|t[ae]n|"
       r"l[ae]|yl[ae]|[ıiuü]m|[ıiuü]z|dir|d[ıi]r|t[ıi]r|nin|nun|nün)")


def _uzun_once(sozluk):
    """Uzun anahtarlar önce eşleşsin ('carl jung' > 'jung')."""
    return sorted(sozluk.items(), key=lambda x: -len(x[0]))


# Özel addan sonra BOŞLUKLA yazılmış ek ("Jung un" → "Jung'un"). "da/de/ta/te"
# BİLEREK dışarıda: onlar ayrı yazılan bağlaç da olabilir ("Jung da söyler").
_AYRIK_EK = (r"(?:n[ıiuü]n|[ıiuü]n|s[ıiuü]|y[ıiuü]|y[ae]|[ae]|d[ae]n|t[ae]n|"
             r"yl[ae]|l[ae]|l[ae]r[ıi]|n[ıi])")


def ayrik_ekleri_birlestir(metin: str) -> str:
    for _sade, dogru in _uzun_once(OZEL_ADLAR):
        if dogru[0].islower():
            continue
        metin = re.sub(rf"\b({re.escape(dogru)})\s+({_AYRIK_EK})\b",
                       lambda m: f"{m.group(1)}'{m.group(2)}", metin)
    return metin


def ozel_adlari_duzelt(metin: str) -> str:
    for sade, dogru in _uzun_once(OZEL_ADLAR):
        # Özel ad + (isteğe bağlı ek) — ek varsa kesme işaretiyle ayrılır
        kalip = re.compile(rf"\b{re.escape(sade)}({_EK})?\b", re.IGNORECASE)

        def _yaz(m):
            ek = m.group(1)
            if not ek:
                return dogru
            if dogru[0].islower():          # tasavvuf/sufi gibi cins ad → kesme yok
                return dogru + ek
            return f"{dogru}'{ek}"
        metin = kalip.sub(_yaz, metin)
    return metin


def cumle_basi_buyut(metin: str) -> str:
    """Metnin ve her cümlenin ilk harfini büyüt (Türkçe i→İ dahil)."""
    def _buyut(s: str) -> str:
        return s[:1].replace("i", "İ").upper() + s[1:] if s else s

    # 17 Eyl: eskiden tüm metni \s+ ile bölüp " " ile birleştiriyordu → açıklamanın
    # paragraf yapısı (satır sonları) SİLİNİYORDU. Artık satır satır.
    def _satir(satir: str) -> str:
        parcalar = re.split(r"(?<=[.!?…])[ \t]+", satir)
        return " ".join(_buyut(p.strip()) for p in parcalar if p.strip())

    return "\n".join(_satir(l) if l.strip() else "" for l in metin.split("\n"))


# 🔴 17 Eyl — LİNK KIRAN HATA. İlk sürüm iki noktadan sonra boşluk ekliyordu:
# "https://youtu.be/…" → "https: //youtu.be/…" oldu; açıklamadaki uzun video
# bağlantısı TIKLANAMAZ hale geldi (16 Eyl'den itibaren Akasha videolarında).
# Saat (20:15), oran (3:1), ayet (2:255) de aynı şekilde bozulurdu.
# Çözüm: dokunulmaması gereken parçalar önce MASKELENİR, iş bitince geri konur.
_KORUNAN = re.compile(
    r"(?:https?://|www\.)\S+"      # bağlantı
    r"|\b\d+[:.]\d+\b"            # saat 20:15 · oran 3:1 · ayet 2:255 · 1.5
    r"|[#@]\w+"                     # etiket, kullanıcı adı
)


def bosluk_ve_noktalama(metin: str) -> str:
    # [ \t] — \s DEĞİL: satır sonları KORUNUR (açıklama paragraflı)
    metin = re.sub(r"[ \t]+([,.;:!?…])", r"\1", metin)
    metin = re.sub(r"([,;:])(?=[^\s\x00])", r"\1 ", metin)
    metin = re.sub(r"[ \t]{2,}", " ", metin)
    return metin.strip()


def _duzelt_ic(metin: str, cumle_basi: bool = True) -> str:
    """Tam imla geçişi. cumle_basi=False → sadece özel ad + noktalama."""
    if not metin:
        return metin
    # Maskeleme EN DIŞTA: bağlantı, etiket (#mevlana), saat hiçbir adımdan
    # etkilenmez. (17 Eyl: özel ad düzeltici "#mevlana"yı "#Mevlânâ" yapıyordu.)
    saklanan: list[str] = []

    def _maskele(m):
        saklanan.append(m.group(0))
        return f"\x00{len(saklanan) - 1}\x00"

    metin = _KORUNAN.sub(_maskele, metin)
    metin = ozel_adlari_duzelt(metin)
    metin = ayrik_ekleri_birlestir(metin)
    metin = bosluk_ve_noktalama(metin)
    if cumle_basi:
        metin = cumle_basi_buyut(metin)
    return re.sub(r"\x00(\d+)\x00", lambda m: saklanan[int(m.group(1))], metin)


# ── ÖZ-TEST — kapı kendini doğrulayamazsa DEVRE DIŞI kalır.
# 17 Eyl dersi: imla kapısı açıklamadaki bağlantıyı kırdı ve bu bir gün boyunca
# fark edilmedi. Bozuk bir imla kapısı, hiç imla kapısı olmamasından KÖTÜDÜR.
# Aşağıdaki durumlardan biri bile bozulursa duzelt() metne HİÇ dokunmaz.
_OZ_TEST = [
    ("izle: https://youtu.be/tZiVYGabc123 şimdi", "https://youtu.be/tZiVYGabc123"),
    ("www.urunya.com adresi", "www.urunya.com"),
    ("saat 20:15 te", "20:15"),
    ("bakara 2:255 ayeti", "2:255"),
    ("#akasha #mevlana", "#akasha #mevlana"),
    ("birinci satır.\n\nikinci satır", "\n\n"),
    ("mevlana der ki:susmak", "Mevlânâ der ki: susmak"),
    ("carl jung un gölgesi", "Carl Jung'un gölgesi"),
    ("jung da bunu söyler", "Jung da bunu söyler"),
    ("Bu zaten düzgün.", "Bu zaten düzgün."),
]


def oz_test() -> list[str]:
    """Başarısız olan durumların listesi (boş = sağlıklı)."""
    hatalar = []
    for girdi, beklenen in _OZ_TEST:
        try:
            if beklenen not in _duzelt_ic(girdi):
                hatalar.append(girdi)
        except Exception as h:
            hatalar.append(f"{girdi} ({h})")
    return hatalar


OZ_TEST_HATALARI = oz_test()
SAGLIKLI = not OZ_TEST_HATALARI


def duzelt(metin: str, cumle_basi: bool = True) -> str:
    """Güvenli giriş noktası: öz-test geçmediyse metni OLDUĞU GİBİ döndürür."""
    if not SAGLIKLI:
        return metin
    return _duzelt_ic(metin, cumle_basi)


def tamami_buyuk_mu(metin: str) -> bool:
    harf = [c for c in metin if c.isalpha()]
    return bool(harf) and all(c.isupper() for c in harf)


if __name__ == "__main__":
    for t in ["mevlana ve mesnevinin ilk dizelerinde gizlenen o derin ev hasreti",
              "ibn arabi ve alem i misal rüyaların açıldığı kadim ara alem",
              "yunus emre ve benliğin sınırlarını aşarak saf öze ulaşma sırrı",
              "carl jung ve gölgeyi bilince çıkararak bireyleşme yolculuğu"]:
        print(f"  {t}\n→ {duzelt(t)}\n")
