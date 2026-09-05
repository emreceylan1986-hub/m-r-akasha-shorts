#!/usr/bin/env python3
"""
kanal_bekcisi.py — GÜNLÜK REGRESYON BEKÇİSİ (23 Ağu 2026).

NEDEN VAR:
  İki kanalda da izlenme çöküşü GÜNLERCE fark edilmedi.
  · Akasha 7 Ağu'da çöktü (1.012 → 164/gün), 16 gün sonra fark edildi.
    Sebep: "kaçan yayın telafisi" commit'i cron'a ERKEN saatler ekledi;
    günlük 4 tavanı ilk 4 slotta dolduğu için akşam slotları HİÇ ateşlenmedi.
    Prime bantta yayın oranı %49 → %25'e düştü, 20-21 UTC tamamen kayboldu.
  · Cosmos 14 Ağu'da çöktü (3.136 → 973/gün), 9 gün sonra fark edildi.
  Her iki vakada da workflow'lar "success" diyordu — çünkü kimse SONUCU ölçmüyordu.

NE YAPAR (her sabah):
  1) REGRESYON: son 7 günün günlük ortalama izlenmesi, ondan önceki 14 günün
     ortalamasına göre %EŞİK'ten fazla düştüyse ALARM.
  2) YAYIN SAATİ: son 7 günde yayınlananların kaçı kanalın ÖLÇÜLMÜŞ en iyi
     saat bandında? Oran %50'nin altına inerse ALARM (Akasha 7 Ağu tuzağı).
  3) Alarm varsa: kırılma penceresindeki commit'leri de basar — şüpheli
     değişiklik raporun içinde çıkar, aramaya gerek kalmaz.
Çıkış kodu 1 = ALARM (workflow issue açar). Ölçüm yapılamazsa 0 döner (sessiz).
"""
import datetime as dt
import json
import re
import statistics as st
import subprocess
import sys
from pathlib import Path

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

KOK = Path(__file__).parent
DUSUS_ESIGI = 0.30      # %30'dan fazla düşüş = alarm
BANT_ESIGI = 0.50       # prime bantta yayın oranı bunun altına inerse alarm
EN_IYI_BANT_SAYISI = 4  # kanalın en iyi kaç saati "prime bant" sayılsın


def _kimlik():
    c = Credentials.from_authorized_user_file(str(KOK / "token.json"))
    if c.expired and c.refresh_token:
        c.refresh(Request())
    return c


def _videolar(yt, azami=150):
    ch = yt.channels().list(part="contentDetails", mine=True).execute()["items"][0]
    up = ch["contentDetails"]["relatedPlaylists"]["uploads"]
    idler, tok = [], None
    while len(idler) < azami:
        r = yt.playlistItems().list(part="contentDetails", playlistId=up,
                                    maxResults=50, pageToken=tok).execute()
        idler += [i["contentDetails"]["videoId"] for i in r["items"]]
        tok = r.get("nextPageToken")
        if not tok:
            break
    idler = list(dict.fromkeys(idler))  # sıra korunarak tekilleştir
    out = []
    for i in range(0, len(idler), 50):
        for v in yt.videos().list(part="snippet,status,contentDetails",
                                  id=",".join(idler[i:i + 50])).execute()["items"]:
            m = re.match(r"PT(?:(\d+)M)?(?:(\d+)S)?", v["contentDetails"]["duration"])
            sn = (int(m.group(1) or 0) * 60 + int(m.group(2) or 0)) if m else 0
            out.append({"id": v["id"], "pub": v["snippet"]["publishedAt"],
                        "sn": sn, "gizli": v["status"]["privacyStatus"]})
    return out


def _izlenmeler(ya, idler):
    """Analytics'ten video başına toplam izlenme (yaş etkisini biz ayıklıyoruz)."""
    r = ya.reports().query(ids="channel==MINE", startDate="2026-01-01",
                           endDate=dt.date.today().isoformat(), metrics="views",
                           dimensions="video", sort="-views", maxResults=200).execute()
    return {x[0]: x[1] for x in r.get("rows", [])}


def _commitler(bas: str, bit: str) -> list:
    try:
        c = subprocess.run(["git", "log", f"--since={bas}", f"--until={bit}",
                            "--format=%ad %s", "--date=format:%m-%d %H:%M"],
                           cwd=KOK, capture_output=True, text=True, timeout=30)
        return [s for s in c.stdout.splitlines()
                if not re.match(r"^\d\d-\d\d \d\d:\d\d (state|merge CI|🤖)", s)][:12]
    except Exception:
        return []


def main() -> int:
    alarmlar, rapor = [], []
    try:
        c = _kimlik()
        yt = build("youtube", "v3", credentials=c, cache_discovery=False)
        ya = build("youtubeAnalytics", "v2", credentials=c, cache_discovery=False)
    except Exception as h:
        print(f"[bekçi] kimlik kurulamadı ({str(h)[:90]}) — sessiz çıkış")
        return 0

    # ── 1) REGRESYON
    try:
        bugun = dt.date.today()
        r = ya.reports().query(ids="channel==MINE",
                               startDate=(bugun - dt.timedelta(days=23)).isoformat(),
                               endDate=(bugun - dt.timedelta(days=1)).isoformat(),
                               metrics="views", dimensions="day").execute()
        satir = sorted(r.get("rows", []))
        # Analytics son 1-2 günü geç işler; en yeni günü hesaba katma.
        gunler = [x[1] for x in satir]
        if len(gunler) >= 18:
            son7 = gunler[-7:]
            onceki14 = gunler[-21:-7]
            a, b = sum(son7) / 7, sum(onceki14) / len(onceki14)
            fark = (b - a) / b if b else 0
            rapor.append(f"son 7 gün ort **{a:.0f}** izlenme/gün · önceki 14 gün ort **{b:.0f}** "
                         f"→ {'-' if fark > 0 else '+'}%{abs(fark) * 100:.0f}")
            if fark > DUSUS_ESIGI:
                # kırılma gününü bul: en büyük ardışık düşüş
                en_kotu, kirilma = 0, None
                for i in range(3, len(satir) - 3):
                    onc = st.median([x[1] for x in satir[max(0, i - 5):i]])
                    son = st.median([x[1] for x in satir[i:i + 5]])
                    if onc and (onc - son) / onc > en_kotu:
                        en_kotu, kirilma = (onc - son) / onc, satir[i][0]
                alarmlar.append(f"📉 İZLENME DÜŞÜŞÜ %{fark * 100:.0f} "
                                f"(eşik %{DUSUS_ESIGI * 100:.0f})")
                if kirilma:
                    rapor.append(f"kırılma günü tahmini: **{kirilma}** (medyan %{en_kotu * 100:.0f} düştü)")
                    k = dt.date.fromisoformat(kirilma)
                    cl = _commitler((k - dt.timedelta(days=2)).isoformat(),
                                    (k + dt.timedelta(days=1)).isoformat())
                    if cl:
                        rapor.append("kırılma penceresindeki değişiklikler:\n"
                                     + "\n".join(f"  - `{s}`" for s in cl))
        else:
            rapor.append(f"regresyon ölçülemedi (yalnız {len(gunler)} günlük veri)")
    except Exception as h:
        rapor.append(f"regresyon ölçülemedi: {str(h)[:110]}")

    # ── 2) YAYIN SAATİ BANDI
    try:
        vid = _videolar(yt)
        izl = _izlenmeler(ya, [v["id"] for v in vid])
        simdi = dt.datetime.now(dt.timezone.utc)

        def yas(v):
            return (simdi - dt.datetime.fromisoformat(v["pub"].replace("Z", "+00:00"))).days

        olgun = [v for v in vid if v["gizli"] == "public" and v["sn"] <= 180 and yas(v) >= 3]
        saat = {}
        for v in olgun:
            saat.setdefault(v["pub"][11:13], []).append(izl.get(v["id"], 0))
        # yalnız yeterli örneği olan saatler sıralamaya girsin
        sirali = sorted(((h, st.median(l), len(l)) for h, l in saat.items() if len(l) >= 4),
                        key=lambda x: -x[1])
        # 24 Ağu FIX: alarm YAPILANDIRILMIŞ hedef saatlere göre verilir. Eskiden
        # her gün yeniden hesaplanan "en iyi 4 saat"e bakıyordu; o liste artık
        # kullanılmayan eski saatleri (00, 15 UTC) da içerdiği için program DOĞRU
        # olduğu hâlde alarm sonsuza kadar çalıyordu. Susturulan bekçi = olmayan bekçi.
        from hedef_saatler import HEDEF_SAATLER
        hedef = {f"{h:02d}" for h in HEDEF_SAATLER}
        if sirali:
            rapor.append("ölçülmüş en iyi saatler (UTC): "
                         + ", ".join(f"{h}→{m:.0f}(n{n})" for h, m, n in sirali[:EN_IYI_BANT_SAYISI]))
        rapor.append(f"yapılandırılmış hedef saatler: {sorted(hedef)}")
        son7 = [v for v in vid if v["gizli"] == "public" and v["sn"] <= 180 and yas(v) <= 7]
        if len(son7) >= 8:
            # (a) PROGRAMA UYUM — yayınlar hedef saatlere düşüyor mu? (asıl alarm)
            oran = sum(1 for v in son7 if v["pub"][11:13] in hedef) / len(son7)
            dagilim = {}
            for v in son7:
                dagilim[v["pub"][11:13]] = dagilim.get(v["pub"][11:13], 0) + 1
            rapor.append("son 7 günün yayın saatleri: "
                         + ", ".join(f"{h}:{n}" for h, n in sorted(dagilim.items()))
                         + f" → hedef saatlerde %{oran * 100:.0f}")
            if oran < BANT_ESIGI:
                alarmlar.append(f"🕐 YAYINLARIN %{(1 - oran) * 100:.0f}'İ HEDEF SAAT DIŞINDA "
                                "— cron'a hedeften ÖNCE telafi slotu eklenmiş olabilir "
                                "(7 Ağu Akasha tuzağı) ya da hedef_saatler.py cron ile uyumsuz")
            # (b) YAPILANDIRMA BAYAT MI — sadece BİLGİ, alarm değil (ölçüm gürültülü)
            if sirali:
                en_iyi = {h for h, _, _ in sirali[:EN_IYI_BANT_SAYISI]}
                disarida = en_iyi - hedef
                if disarida:
                    rapor.append(f"ℹ️ ölçümde iyi görünüp hedefte OLMAYAN saatler: "
                                 f"{sorted(disarida)} — hedef_saatler.py gözden geçirilebilir "
                                 f"(00-02 UTC bilerek dışarıda: günlük sayaç UTC'de sıfırlanıyor)")
    except Exception as h:
        rapor.append(f"saat bandı ölçülemedi: {str(h)[:110]}")

    # ── 3) GÜNLÜK YAYIN ADEDİ (28 Ağu: GitHub cron çöküşü 2 gün boyunca 0 video
    #        yayınlattı ve bunu kimse görmedi — izlenme alarmı 7 günlük ortalamaya
    #        baktığı için geç kalıyordu. Adet, izlenmeden ÖNCE bozulur.)
    try:
        from hedef_saatler import HEDEF_SAATLER as _HS
        hedef_adet = len(_HS)
        vid = vid if "vid" in dir() else _videolar(yt)
        simdi = dt.datetime.now(dt.timezone.utc)
        gunluk = {}
        for v in vid:
            if v["sn"] <= 180:
                g = v["pub"][:10]
                gunluk[g] = gunluk.get(g, 0) + 1
        son = [(simdi.date() - dt.timedelta(days=i)).isoformat() for i in range(1, 8)]
        adetler = [(g, gunluk.get(g, 0)) for g in reversed(son)]
        rapor.append("son 7 günün yayın adedi (hedef {}/gün): ".format(hedef_adet)
                     + " · ".join(f"{g[5:]}:{n}" for g, n in adetler))
        # 31 Ağu: bekçi SADECE eksiğe bakıyordu; 30 Ağu'da Cosmos 6, Akasha 5 video
        # yayınladı (üç tetik yolu yarıştı) ve hiçbir alarm çalmadı. Fazla basım,
        # eksikten DAHA tehlikeli: 2 Tem'de yığın basım TrendCatcher'ın feed
        # dağıtımını kalıcı öldürmüştü. Artık iki yön de denetleniyor.
        # 5 Eyl: adet doğru ama DAĞILIM bozuk olabilir. Akasha son 7 günde saat 19'a
        # 10, saat 20'ye 1 video basmıştı — bekçi bunu görmüyordu çünkü sadece
        # günlük TOPLAMA bakıyordu. Kullanılmayan hedef saat = kayıp prime slot.
        try:
            kullanim = {h: 0 for h in _HS}
            for v in vid:
                if v["sn"] <= 180 and 1 <= (simdi - dt.datetime.fromisoformat(
                        v["pub"].replace("Z", "+00:00"))).days <= 7:
                    h = int(v["pub"][11:13])
                    if h in kullanim:
                        kullanim[h] += 1
            rapor.append("hedef saat kullanımı (son 7 gün): "
                         + " · ".join(f"{h:02d}→{n}" for h, n in sorted(kullanim.items())))
            aclar = [h for h, n in kullanim.items() if n <= 1]
            if aclar and max(kullanim.values() or [0]) >= 5:
                alarmlar.append(f"⏰ HEDEF SAAT AÇ KALIYOR: {aclar} saatlerine 7 günde en fazla "
                                f"1 video düştü, başka saat {max(kullanim.values())} aldı — "
                                "aynı saate çift basım olabilir (slot_kapisi kontrol et)")
        except Exception:
            pass
        fazla = [(g, n) for g, n in adetler if n > hedef_adet]
        if fazla:
            alarmlar.append("📛 HEDEFTEN FAZLA YAYIN: "
                            + ", ".join(f"{g[5:]}→{n} (hedef {hedef_adet})" for g, n in fazla)
                            + " — tetikleyiciler yarışıyor olabilir (concurrency kilidi + "
                              "aktif-koşu kapısı kontrol et)")
        eksik = [(g, n) for g, n in adetler if n < hedef_adet]
        toplam_eksik = sum(hedef_adet - n for _, n in eksik)
        if eksik:
            bos = [g for g, n in eksik if n == 0]
            if bos:
                alarmlar.append(f"🎬 {len(bos)} GÜN HİÇ YAYIN YOK ({', '.join(b[5:] for b in bos)}) "
                                f"— tetik zinciri kopuk (GitHub cron + Mac tetikleyici ikisi de)")
            elif toplam_eksik >= hedef_adet:
                alarmlar.append(f"🎬 SON 7 GÜNDE {toplam_eksik} VİDEO EKSİK "
                                f"(hedef {hedef_adet}/gün)")
    except Exception as h:
        rapor.append(f"günlük adet ölçülemedi: {str(h)[:110]}")

    print("\n".join(rapor))
    if alarmlar:
        print("\nALARM:")
        for a in alarmlar:
            print(" " + a)
        Path(KOK / ".bekci_alarm").write_text(
            "## " + "\n## ".join(alarmlar) + "\n\n" + "\n".join(rapor), encoding="utf-8")
        return 1
    print("\nALARM YOK.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
