# Mindgaps — Brand & Kurulum Dökümanı

**Niş:** İnsan zihni / psikoloji / "senin hakkındaki" gerçekler (faceless, global/EN)
**Format:** Daily Shorts (25-45 sn)
**Tagline:** *Facts about your mind.*
**Renk paleti:** #1A1A2E (gece) · #9D7BE8 (lavanta) · #7BE8C4 (mint)

---

## 📋 YouTube Studio — Kanal Açıklaması (kopyala-yapıştır)

```
Your mind is hiding things from you. Mindgaps reveals them — daily.

Quick, science-backed facts about how your brain, personality, habits, and
relationships actually work. Why you do what you do, in under 60 seconds.

🧠 New short every day
🔔 Subscribe and notice yourself differently

New here? Start with the playlist below.
```

## 🔑 Keyword / Tag havuzu (25+)
```
psychology facts, brain facts, human behavior, did you know, mind facts,
psychology shorts, why you do that, personality, self improvement, mindset,
cognitive bias, dopamine, habits, sleep psychology, body language,
relationship psychology, memory tricks, mental health facts, neuroscience,
fun facts, psychology hacks, social psychology, dark psychology, focus,
overthinking, anxiety facts, attraction psychology, dream meaning
```

## 🗓️ 7 Günlük Tema Rotasyonu (haberci.py DAILY_THEMES)
| Gün | Tema | Rüya sonucu açısı |
|---|---|---|
| Pzt | **Your brain** (nörobilim, dopamin, hafıza) | "beynin böyle çalışıyor" |
| Sal | **Why you do that** (alışkanlık, davranış) | kendini görme |
| Çar | **Personality** (kişilik, tipler, testler) | "sen busun" |
| Per | **Relationships & attraction** | ilişki/çekicilik |
| Cum | **Dark psychology / persuasion** | güç/etki (yüksek tık) |
| Cmt | **Sleep & dreams** | rüya/uyku merakı |
| Paz | **Mind hacks** (odak, hafıza, üretkenlik) | pratik kazanım |

## 🎯 Başlık formülü (Değer Denklemi — fikir_motoru.py)
Her başlık şu 4 koldan **en az 2-3'ünü** vursun:
- **Yüksek rüya:** izleyici kendini görsün ("your", "you")
- **Yüksek başarı/merak:** net payoff vaadi ("the real reason", "X reveals")
- **Düşük zaman:** kısa/anında ("in 5 seconds", "instantly")
- **Düşük çaba:** kolay/basit (tek cümlede anlaşılır)

Örnek 87 skor: *"What your sleeping position reveals about you"* (4/4 kol).

## ⚙️ Kurulum checklist (Emre — YouTube Studio, ~8 dk)
1. Kanal adı → **Mindgaps**
2. Handle → **@mindgaps** (boşsa; değilse @mindgapsdaily / @getmindgaps)
3. Açıklama → yukarıdaki bloğu yapıştır
4. Banner → `branding/banner.png` yükle
5. Profil → `branding/icon.png` yükle
6. Settings → Audience → **"No, not made for kids"** ⚠️ KRİTİK (yoksa yorum/CTA kapalı)
7. Varsa eski kişisel video → PRIVATE

## 🔌 Teknik (Claude)
- Repo: `emreceylan1986-hub/m-r-mindgaps-shorts`
- Cron kayması: TrendCatcher 12/16/19 · Cosmos 13/17/20 → **Mindgaps 14/18/21 UTC** (quota çakışmaz)
- ⚠️ 3. kanal: aynı GCP project (10K/gün quota) — TC+Cosmos+Mindgaps sığar; 4. kanalda ayrı GCP project gerekir
- Ses: edge-tts (ücretsiz, EN) · Görsel: Pexels + AI · Fikir: fikir_motoru.py + Gemini
