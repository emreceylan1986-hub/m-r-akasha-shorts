"""
gemini_tts.py — Akasha doğal seslendirme (Gemini 2.5 TTS)

edge-tts "dijital" kalıyordu; Emre 26 Haz "Leda" sesini seçti. Gemini TTS
gerçek insan gibi + ücretsiz (mevcut GEMINI_API_KEY, ~45k karakter/ay, limit 1M).

Tek sorun: Gemini TTS kelime-zamanlaması (WordBoundary) VERMEZ → karaoke ASS
altyazı için seslendirici.py edge-tts cue'larını alır ve Gemini süresine
ÖLÇEKLER (ikisi de aynı metni aynı sırada söyler → lineer ölçek yeterince
isabetli). Bu modül SADECE sesi üretir; cue/ASS işi seslendirici.py'de.

Çıktı: 24kHz mono 16-bit PCM → MP3 (ffmpeg).
"""
from __future__ import annotations

import subprocess
import wave
from pathlib import Path

import imageio_ffmpeg
from google.genai import types

import bridge

# Emre 26 Haz seçimi: Leda (genç/taze, sıcak). Alternatifler: Achernar(yumuşak),
# Sulafat(sıcak), Despina(pürüzsüz), Vindemiatrix(nazik).
SES = "Leda"
MODEL = "gemini-2.5-flash-preview-tts"

# Ton talimatı (konuşulmaz, sadece stil yönlendirir) — spiritüel/Mevlana havası
STIL = ("Sakin, sıcak ve şefkatli bir tonla, acele etmeden, derin bir huzurla, "
        "dinleyenin içini ferahlatacak şekilde söyle: ")

FFMPEG = imageio_ffmpeg.get_ffmpeg_exe()


def _pcm_to_mp3(pcm: bytes, mp3_yolu: Path) -> float:
    """24kHz mono 16-bit PCM → MP3. Saniye cinsinden süre döner."""
    gecici_wav = mp3_yolu.with_suffix(".tts.wav")
    with wave.open(str(gecici_wav), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(24000)
        w.writeframes(pcm)
    sure = len(pcm) / (24000 * 2)  # bytes / (örnek hızı * 2 byte)
    subprocess.run(
        [FFMPEG, "-y", "-i", str(gecici_wav), "-codec:a", "libmp3lame",
         "-b:a", "192k", str(mp3_yolu)],
        check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    gecici_wav.unlink(missing_ok=True)
    return sure


SES_YEDEK = "tr-TR-EmelNeural"   # edge-tts acil yedeği — Akasha'nın onaylı sesi DEĞİL


def seslendir(metin: str, mp3_yolu: Path, ses: str = SES) -> float | None:
    """
    Metni Gemini TTS ile seslendir → mp3_yolu. Süre (sn) döner.
    Başarısızsa None döner (çağıran edge-tts'e düşer).
    """
    client = bridge._client()
    son_hata = None
    # 🔴 30 Ağu: 3 deneme / en fazla 15sn bekleme YETMİYORDU. Son 8 koşunun 3'ünde
    # Leda 503 UNAVAILABLE ("model is currently experiencing high demand") aldı ve
    # video SESSİZCE edge-tts Emel sesiyle yayınlandı — Akasha'nın sesi o değil
    # (1 Ağu'da Emel sesli İkarus kopyaları bu yüzden gizlenmişti).
    # 503 geçici bir yoğunluk dalgasıdır; dakikalarca sürebilir. bridge'in ana
    # üreticisi 9 deneme / 90sn tavanla bekliyor, TTS ise 3/15 ile pes ediyordu.
    for deneme in range(6):
        try:
            r = client.models.generate_content(
                model=MODEL,
                contents=STIL + metin,
                config=types.GenerateContentConfig(
                    response_modalities=["AUDIO"],
                    speech_config=types.SpeechConfig(
                        voice_config=types.VoiceConfig(
                            prebuilt_voice_config=types.PrebuiltVoiceConfig(
                                voice_name=ses
                            )
                        )
                    ),
                ),
            )
            pcm = r.candidates[0].content.parts[0].inline_data.data
            if not pcm:
                raise RuntimeError("boş audio")
            return _pcm_to_mp3(pcm, mp3_yolu)
        except Exception as h:
            son_hata = h
            import time
            metin_h = str(h)
            if "429" in metin_h or "RESOURCE_EXHAUSTED" in metin_h:
                # 31 Tem dersi: free-tier TTS = 10 istek/gün/anahtar. Önce başka
                # anahtara geç (bridge rotasyonu); yoksa API'nin önerdiği süre bekle.
                if bridge._sonraki_anahtara_gec():
                    continue
                import re as _re
                m = _re.search(r"retry in (\d+)", metin_h)
                time.sleep(min(int(m.group(1)) + 5 if m else 60, 90))
            elif "503" in metin_h or "UNAVAILABLE" in metin_h or "500" in metin_h:
                bekle = min(2 ** (deneme + 2), 60)   # 4,8,16,32,60,60 → ~3 dk
                print(f"[gemini_tts] {ses} 503 yoğunluk — {bekle}sn sonra yeniden "
                      f"({deneme + 1}/6)", flush=True)
                time.sleep(bekle)
            else:
                time.sleep(min(2 ** (deneme + 1), 15))
    # 🔊 SESSİZ DÜŞÜŞ YASAK: yanlış sesle video çıkacaksa bunu bilerek yapıyoruz
    # ve HABER VERİYORUZ. Bayrağı workflow okuyup issue açar.
    print(f"[gemini_tts] başarısız ({son_hata}) → edge-tts'e düşülecek", flush=True)
    try:
        (Path(__file__).parent / ".ses_yedege_dustu").write_text(
            f"Leda (Gemini TTS) {6} denemede başarısız oldu, video edge-tts yedek sesiyle "
            f"({SES_YEDEK}) yayınlandı.\n\nSon hata: {str(son_hata)[:400]}\n\n"
            "Akasha'nın onaylı sesi LEDA'dır; Emel yalnızca acil yedektir "
            "(1 Ağu'da Emel sesli İkarus kopyaları bu yüzden gizlenmişti).",
            encoding="utf-8")
    except Exception:
        pass
    return None


if __name__ == "__main__":
    import sys
    metin = sys.argv[1] if len(sys.argv) > 1 else "Merhaba dostum, içindeki sessizliği dinle."
    sure = seslendir(metin, Path("/tmp/gemini_tts_cli.mp3"))
    print(f"süre: {sure}sn → /tmp/gemini_tts_cli.mp3" if sure else "BAŞARISIZ")
