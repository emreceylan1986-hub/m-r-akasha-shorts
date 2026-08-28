#!/usr/bin/env python3
"""
slot_kapisi.py — YAYIN SLOTU KARARI (tek kaynak, 24 Ağu 2026).

23 Ağu'da hedef-saat kapısı yukleyici.py'nin İÇİNE kondu. 24 Ağu'da görüldü ki
kapı DOĞRU karar veriyor ama ÇOK GEÇ: pipeline önce senaryo + Gemini TTS + montaj
yapıyor, kapı en sonda "hedef dolu" deyip çıkıyordu. Ölçülen israf:
  · Cosmos'ta atlanan her koşu 4,5 dk (18:23-23:17 arası 2 koşu boşa)
  · Akasha'da 6 dk + boşa Gemini/TTS kotası (günlük kota bu yüzden tükeniyor)
  · 23 Ağu 20:08 Akasha koşusu: 4K kaynak klip (2160×3840) + boşa render →
    35 dk timeout'a çarpıp CANCELLED oldu; slot komple kayboldu.
Bu modül kararı stdlib'le, saniyeler içinde verir; workflow ilk iş bunu çağırır ve
slot kapalıysa job hiç başlamaz. yukleyici de aynı fonksiyonu kullanır (çift kapı).
"""
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

KOK = Path(__file__).parent
YUKLEME_LOGU = KOK / "yuklemeler.json"


def _bugunku_sayi(simdi: datetime) -> int:
    try:
        kayitlar = json.loads(YUKLEME_LOGU.read_text(encoding="utf-8"))
    except Exception:
        return -1  # log okunamıyor → kapıyı açık bırak (yayını engelleme)
    bugun = simdi.strftime("%Y-%m-%d")
    return sum(1 for k in kayitlar
               if str(k.get("zaman", k.get("tarih", "")))[:10] == bugun)


def slot_karari(hedef_saatler, simdi=None) -> tuple:
    """(acik: bool, mesaj: str) döndürür. Kural:
       · bugünkü yayın >= hedef saat sayısı        → KAPALI (yığın basım koruması)
       · şu an hedef saatteysek                    → AÇIK
       · telafi saatindeyiz ve gün GERİDEYSE       → AÇIK
       · telafi saatindeyiz ama gün programındaysa → KAPALI
         (yoksa telafi slotu, kendisinden SONRAKİ hedef saatin kontenjanını yer —
          Akasha'yı 7 Ağu'da öldüren tuzak buydu)"""
    simdi = simdi or datetime.now(timezone.utc)
    sayi = _bugunku_sayi(simdi)
    if sayi < 0:
        return True, "[slot] yuklemeler.json okunamadı → kapı açık bırakıldı"
    if sayi >= len(hedef_saatler):
        return False, (f"⛔ GÜNLÜK HEDEF DOLDU: bugün {sayi} yayın var "
                       f"(hedef {len(hedef_saatler)}). Yığın basım koruması.")
    if simdi.hour in hedef_saatler:
        return True, f"[slot] {simdi.hour:02d} UTC HEDEF saat — yayın açık ({sayi}/{len(hedef_saatler)})"
    # 🔴 28 Ağu — GÜNÜ ASLA KAYBETME. GitHub'ın zamanlayıcısı 26 Ağu'da çöktü
    # (6 koşu/gün → 1) ve kalan tek koşu 02:00-04:12 UTC gibi hedef DIŞI saatlere
    # düştü. Kapı onları da atlayınca 27-28 Ağu'da iki kanalda SIFIR video çıktı.
    # Kötü saatte yayın, hiç yayınlamamaktan iyidir.
    if sayi == 0:
        return True, (f"[slot] {simdi.hour:02d} UTC hedef saat değil AMA bugün hiç yayın "
                      f"yok → günü kaybetmemek için yayın açık")
    gecmis = sum(1 for h in hedef_saatler if h < simdi.hour)
    if sayi < gecmis:
        return True, (f"[slot] {simdi.hour:02d} UTC telafi — gün geride "
                      f"({sayi} yayın, {gecmis} hedef saat geçti) → yayın açık")
    kalan = [h for h in hedef_saatler if h > simdi.hour]
    # Günün hedef saatleri bitti ama hedef dolmadıysa son şans verilir; bekleyecek
    # hedef saat kalmadığı için burada bir kontenjan çalma riski YOK.
    if not kalan:
        return True, (f"[slot] {simdi.hour:02d} UTC — günün hedef saatleri bitti, hedef "
                      f"dolmadı ({sayi}/{len(hedef_saatler)}) → son şans yayını açık")
    return False, (f"⏭️ {simdi.hour:02d} UTC telafi slotu ATLANDI: gün programında "
                   f"({sayi} yayın / {gecmis} geçmiş hedef saat). "
                   f"Sıradaki hedef saat {kalan} korunuyor.")


def main() -> int:
    """CLI: çıkış 0 = slot AÇIK, 1 = KAPALI. Workflow ilk adımda bunu çağırır."""
    from hedef_saatler import HEDEF_SAATLER
    acik, mesaj = slot_karari(HEDEF_SAATLER)
    print(mesaj, flush=True)
    return 0 if acik else 1


if __name__ == "__main__":
    sys.exit(main())
