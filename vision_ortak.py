"""
vision_ortak.py — Görsel QC çağrıları için ortak Gemini istemcisi (23 Ağu 2026).

SORUN (kanıt: cosmos run 32602340499, akasha run 22 Ağu 16:19):
  gorsel_qc.py ve pre_publish_qc.py kendi ham `genai.Client`'ını kurup TEK deneme
  yapıyordu. İlk 429'da (kota/rate-limit) görsel kapısı "kontrolsüz kabul", hook
  kapısı "ölçülemedi" diyordu. Günlük 5 videonun 4'ü HİÇ görsel denetiminden
  geçmiyordu — uzay videosuna dans eden insan görseli bu yüzden girdi
  (Gp1cTITX3TQ, hook QC 3/10).

ÇÖZÜM: bridge.py'de zaten olan olgunlaşmış yol (çoklu anahtar rotasyonu +
exponential backoff + PerDay kotasında YEDEK modele geçiş) burada da kullanılıyor.
QC bir yan-iş olduğu için deneme sayısı düşük tutuldu (pipeline'ı geciktirmesin).
"""
from __future__ import annotations


def vision_uret(contents, config, model: str = "gemini-3.5-flash", denemeler: int = 4):
    """bridge'in retry+anahtar rotasyonlu üreticisi. Hata olursa YÜKSELTİR (raise);
    çağıran taraf kendi 'ölçülemedi' davranışını uygular."""
    from bridge import _generate_retry
    return _generate_retry(model, contents, config, _denemeler=denemeler)
