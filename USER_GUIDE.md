# USER GUIDE - Finance Intelligence Engine V3

## Teslim Notu
Bu dokuman, Finance Intelligence Engine V3 projesinin resmi teslim dokumanidir.
Hedef kitle:
- Projeyi ilk kez kuracak ve calistiracak kullanici
- Sistemi isletecek geliştirici veya teknik sorumlu

Bu rehber, gunluk kullanimdan bakim operasyonlarina kadar tum kritik adimlari kapsar.

## Icindekiler
1. Projenin Amaci
2. Gunluk Kullanim Rehberi
3. Gunluk Akis
4. Telegram Mesajlarini Okuma Rehberi
5. Gun Icinde Ne Yapmaliyim?
6. Programi Sifirdan Baslatma
7. Program Calisirken Normal ve Kritik Loglar
8. Hata Durumlari ve Cozumler
9. Performans ve Sinirlar
10. Bakim ve Konfigurasyon Guncellemeleri
11. Dosya Yapisi ve Moduller
12. Kullanici Tavsiyeleri ve En Iyi Pratikler
13. Sonuc ve Gelecek Gelistirmeler

---

## 1) Projenin Amaci

### 1.1 Bu robot ne yapiyor?
Finance Intelligence Engine V3, BIST ve ABD hisseleri icin gunluk veri toplayan, kalite filtreleri uygulayan, skorlayan ve Telegram uzerinden aksiyon odakli ozet gonderen lokal bir analiz robotudur.

Sistem:
- Piyasa verisi toplar
- Haber ve KAP etkisini degerlendirir
- Teknik, temel ve piyasa zekasi skorlarini birlestirir
- Trend gucu ve olasi trend suresini hesaplar
- Karar motoru ile BUY, HOLD, EXIT gibi kararlar uretir
- Uygun adaylara sermaye dagitimi onerir
- Sonucu Telegram ile raporlar

### 1.2 Hangi piyasalari analiz ediyor?
- BIST (varsayilan acik)
- US market (varsayilan acik, ticker listesi env ile belirlenir)

Varsayilan US listesi:
- GOOGL, AMZN, TSLA, META, NFLX

### 1.3 Nasil karar veriyor?
Sistem, cok katmanli bir karar yapisina sahiptir:
1. Veri toplama
2. Helal filtre
3. Haber analizi
4. Teknik analiz
5. Temel analiz
6. Market intelligence analizi
7. Trend analizi
8. Decision Engine ile nihai karar
9. Quality gate esikleri
10. Capital allocation

Onemli V3 kurali:
- Sabit top 5 veya top 10 limiti yoktur.
- Kaliteyi gecen tum adaylar degerlendirilir.
- Kaliteyi gecen aday yoksa WAIT IN CASH doner.

### 1.4 Hangi teknolojileri kullaniyor?

| Katman | Teknoloji |
|---|---|
| API | FastAPI |
| Sunucu | Uvicorn |
| Scheduler | APScheduler |
| Veri islemleri | pandas, numpy |
| HTTP/entegrasyon | requests |
| Haber parse | BeautifulSoup, lxml |
| AI entegrasyonu | google-generativeai (Gemini) |
| Konfigurasyon | python-dotenv |
| Test | pytest |
| Storage | JSON dosyalari |

### 1.5 Gemini burada ne yapiyor?
Gemini, cekirdek hesap motorunun yerine gecmez. Cekirdek kararlar deterministic motor tarafindan hesaplanir.

Gemini'nin gorevi:
- Haber ve KAP metinlerine niteliksel yorum eklemek
- Gunluk piyasa metin ozetleri olusturmak
- Telegram mesajina AI aciklamasi katmak

Gemini yapmaz:
- Gecis noktasi, stop, hedef hesaplamasi
- Teknik indikator matematigi
- Karar motorunun baglayici kurallarini override etmek

### 1.6 Helal filtre nasil calisiyor?
Helal filtre su alanlarla calisir:
- Yasakli ticker listesi
- Yasakli anahtar kelimeler (sirket adi/sektor)
- Yasakli sektor listesi

Filtre sonucu:
- Uygunlar allowed_items
- Uygun olmayanlar rejected_items

Bu filtre, adaylar AI ve karar adimina gitmeden once calisir.

### 1.7 Teknik analiz nasil calisiyor?
Sistem teknik sinyal seti kullanir:
- EMA20, EMA50, EMA200
- SMA
- RSI
- MACD
- ATR
- Bollinger Bands
- Gap kontrolu
- Hacim ve relative volume
- Destek/direnc yaklasik seviyeleri

Teknik skor 0-100 araliginda normalize edilir.
Trend etiketleri:
- Bullish
- Neutral
- Bearish

### 1.8 Temel analiz nasil calisiyor?
Fundamental katman, eldeki market metriklerinden turetilen bir kalite skoru üretir.
Pratikte su tip sinyalleri agirliklandirir:
- Buyume egilimi
- Marj benzeri guc
- Borcluluk/denge gorunumu
- Likidite yapisi

Cikti:
- Fundamental score (0-100)

### 1.9 News Intelligence nasil calisiyor?
Haber motoru:
- Kaynaklardan haber/KAP icerigi toplar
- Ticker eslestirme yapar
- Duygu tonu ve etki degerlendirir
- Ticker bazli ortalama haber skoru olusturur

Skorun etkisi:
- Negatif sentiment agirsa aday elenebilir
- News score kalite esigini gecmezse aday devam etmez

### 1.10 Trend Engine nasil calisiyor?
Trend Engine, coklu girdiden trend gucu hesaplar:
- Teknik skor
- Market intelligence skoru
- News skoru
- Volatilite
- Relative volume
- Trend etiketi

Ciktilar:
- Trend strength (0-100)
- Estimated trend duration (metinsel tahmin)

### 1.11 Portfolio Engine ne yapiyor?
Acilmis pozisyonlari gunluk yeniden degerlendirir.
Pozisyon bazli:
- Mevcut kar/zarar
- Trend gucu
- Guven
- ATR bazli stop guncelleme

Uretebilecegi kararlar:
- HOLD
- RAISE STOP
- PARTIAL TAKE PROFIT
- EXIT

### 1.12 Capital Allocation ne yapiyor?
BUY adaylarina sermaye dagitir.
Mantik:
- Once minimum nakit rezervi ayrilir
- Kalan sermaye confidence agirlikli dagitilir
- Tek hisseye ust limit uygulanir

Cikti:
- Hisse bazli oneri tutar
- Nakitte kalan tutar

### 1.13 Scheduler ne yapiyor?
Scheduler, hafta ici otomatik gorevleri calistirir.
Varsayilan zamanlar:
- 09:45 -> BIST raporu
- 16:00 -> US raporu
- 22:30 -> Portfolio update (opsiyonel, default kapali)

### 1.14 Telegram ne zaman mesaj gonderiyor?
Telegram mesaji su durumlarda gider:
- Scheduler tetigi calisinca
- API uzerinden manuel tetik yapinca
- Her rapor akisi sonunda notifier basariliysa

---

## 2) Gunluk Kullanim Rehberi

### 2.1 Sabah bilgisayari saat kacta acmaliyim?
Pratik onerilen saat:
- 09:30 - 09:40 arasi bilgisayar acik ve internete bagli olmali

Neden:
- 09:45 BIST scheduler tetigi kacirilmaz
- Ilk haber/market fetch adimi gecikmez

### 2.2 Programi saat kacta calistirmaliyim?
Program, scheduler ile calisacaksa:
- En gec 09:40'ta calisir durumda olmali

En iyi pratik:
- Sabah acista run.bat ile baslat
- Gun sonuna kadar acik birak

### 2.3 Program surekli acik kalmali mi?
Eger otomatik saatli calisma istiyorsaniz evet.

Kapatirsaniz:
- O saatte scheduler gorevi tetiklenmez
- Sonraki acista geriye donuk otomatik telafi yapmaz

### 2.4 Gorev bitince kapatabilir miyim?
Evet, manuel kullanimda kapatabilirsiniz.
Ancak bu durumda saatli otomasyon devre disi kalir.

### 2.5 Bilgisayar uyku moduna girerse ne olur?
- Scheduler sureci askida kalir
- Uykuda iken job tetiklenmez
- Uyaninca kacirilan cron olayi genellikle otomatik rerun etmez

Oneri:
- Is saatlerinde uyku modunu kapatin

### 2.6 Bilgisayar kapanirsa ne olur?
- API kapanir
- Scheduler durur
- Telegram gonderimleri olmaz

Tekrar acildiginda:
- Uygulamayi yeniden baslatmaniz gerekir

### 2.7 Internet kesilirse ne olur?
Muhtemel etkiler:
- Yahoo verisi cekilemez
- Haber kaynaklari okunamaz
- Gemini cagrilari duser
- Telegram gonderimi basarisiz olabilir

Sistem davranisi:
- Cok noktada exception yakalayip eldeki son veriyle devam etmeye calisir
- Bazen WAIT IN CASH veya bos rapor uretebilir

### 2.8 Gemini hata verirse ne olur?
- Cekirdek hesaplama durmaz
- AI summary bos kalabilir
- Karar motoru yine calisir

### 2.9 Telegram gonderemezse ne olur?
- Notifier retry dener
- Hala olmazsa telegram success false doner
- Islem tamamen kaybolmaz, ancak bildirim ulasmaz

### 2.10 Yahoo Finance calismazsa ne olur?
- US market fetch azalabilir veya bos donebilir
- O gun US raporunda aday cikmayabilir
- BIST akisindan bagimsiz kismi calismaya devam eder

### 2.11 Bu durumlarda sistemin genel prensibi
- Once dayanıklilik: exception yakalama
- Sonra fallback: eldeki veriyi kullanma veya guvenli bos sonuc
- Son mesaj: mumkunse Telegram'da ozet

---

## 3) Gunluk Akis

### 3.1 09:45 BIST akisi adim adim
1. BIST market collect baslar
2. Helal filter uygulanir
3. News analiz ve ticker ozetleri guncellenir
4. Market analysis olusur
5. Recommendation engine calisir
6. Quality gate eleyenler elenir
7. Kalanlar confidence bazli siralanir
8. Capital allocation hesaplanir
9. Gemini niteliksel ozet ekler
10. Telegram raporu gonderilir
11. Log satirinda ozet metrikler yazilir

### 3.2 16:00 US akisi adim adim
1. US ticker listesi cekilir
2. Yahoo/market verisi normalize edilir
3. Helal filter uygulanir
4. News ve ticker sentiment baglami birlestirilir
5. Karar motoru ile quality gate uygulanir
6. Uygunsa BUY/HOLD ciktilari olusur
7. Uygun degilse WAIT IN CASH olusur
8. Telegram US raporu gonderilir

### 3.3 22:30 Portfolio Update akisi adim adim
Not:
- Varsayilan olarak SCHEDULER_PORTFOLIO_ENABLED false gelebilir. Acik degilse bu job otomatik calismaz.

Calisma adimlari:
1. Guncel market verisi toplanir
2. Mevcut portfolio.json okunur
3. Her pozisyon icin trend ve kar/zarar degerlendirilir
4. HOLD/RAISE STOP/PARTIAL TAKE PROFIT/EXIT karari verilir
5. Portfolio analizi Telegram formatinda gonderilir

---

## 4) Telegram Mesajlarini Nasil Okuyacagim?

### 4.1 Mesaj bloklari
Tipik mesaj bolumleri:
- Baslik (BIST Daily Report veya US Market Report)
- Tarih
- Istatisik ozeti
- Yeni firsatlar listesi
- Acik pozisyonlar
- AI piyasa ozeti

### 4.2 Istatisik alanlari

| Alan | Anlami |
|---|---|
| Analiz Edilen | O markette islenen hisse sayisi |
| Helal Filtre | Helal filtreden gecen hisse sayisi |
| AI Analizi | Detay karar asamasina ulasan aday sayisi |
| Onerilen | Son kalite esigini gecip raporlanan adet |

### 4.3 Hisse satirindaki alanlar

| Alan | Anlami | Nasil kullanilir |
|---|---|---|
| Ticker | Hisse kodu | Islem ekraninda ilk kontrol alanidir |
| Sirket | Sirket adi | Dogru enstruman dogrulama |
| Karar | BUY/HOLD/EXIT vb | Birincil aksiyon sinyali |
| Guven (Confidence) | 0-100 kalite guveni | Yuksek skor genelde daha guclu setup |
| Trend | Trend gucu 0-100 | Hareketin olgunluk gucu |
| Trend Suresi | Tahmini trend devam penceresi | Pozisyon bekleme ufku |
| Alis Araligi (Entry Range) | Planli alis bandi | Tek fiyat yerine bant yaklasimi |
| Guncel Hedef (Current Target) | Kisa-orta hedef seviye | Kar al senaryosu |
| Koruyucu Stop (Protective Stop) | Zarar kes seviyesi | Risk siniri |
| Risk/Odul (Risk/Reward) | Olasi getiri/risk orani | 1.2+ genelde minimum kalite |
| Sermaye Dagilimi (Capital Allocation) | Onerilen tutar | Portfoy agirlik planlama |
| AI Ozet (AI Summary) | Niteliksel haber/KAP yorumu | Baglamsal metin destegi |

### 4.4 Karar etiketleri ve ornek yorum

| Karar | Anlam | Pratik aksiyon |
|---|---|---|
| BUY | Yeni alim adayi | Entry Range, Stop ve R/R kontrol ederek alim planla |
| HOLD | Pozisyon koru | Mevcut pozisyonu tasimaya devam et |
| EXIT | Cikis onerisi | Riskten cikmayi degerlendir |
| PARTIAL TAKE PROFIT | Kismi kar al | Pozisyonun bir kismini realize et |
| RAISE STOP | Stop yukari tasi | Kazanci korumak icin stop guncelle |
| WAIT IN CASH | Uygun kalite yok | Yeni islem acma, nakitte bekle |

### 4.5 Ornek mesaj (temsilidir)

    📈 BIST Daily Report
    📅 19.07.2026

    Analiz Edilen : 595
    Helal Filtre : 430
    AI Analizi : 120
    Onerilen : 3

    🟢 Yeni Firsatlar

    THYAO
    Sirket : Turk Hava Yollari
    Karar : BUY
    Guven : 84
    Trend : 78
    Trend Suresi : 3-7 islem gunu
    Alis Araligi : 295.20 - 300.80
    Guncel Hedef : 318.50
    Koruyucu Stop : 286.40
    Risk/Odul : 1.75
    Sermaye Dagilimi : 3200.00 TL
    AI Ozet : Sektor talep tarafinda destekli, haber akisi olumlu.
    ---

### 4.6 WAIT IN CASH ornegi

    📌 Bugun analiz edilen hisseler arasinda minimum kalite kriterlerini saglayan uygun yatirim firsati bulunamadi.

    Bugunku oneri:
    WAIT IN CASH

Bu mesaj bir hata degildir. Sistem, kalite disiplinini korudugu icin bekleme karari uretebilir.

---

## 5) Ben Gun Icinde Ne Yapmaliyim?

### 5.1 Telegram mesaji geldikten sonra
1. Once rapor marketini kontrol edin (BIST veya US)
2. Onerilen adet ve istatistik blokunu okuyun
3. BUY adaylarini confidence ve risk/odul sirasiyla inceleyin
4. Portfoyunuz varsa HOLD/EXIT/RAISE STOP satirlarini onceleyin
5. Islem yapmadan once kendi risk limitinizi uygulayin

### 5.2 Hangi hisseyi once degerlendirmeliyim?
Oncelik sirasi onerisi:
1. Confidence yuksek
2. Risk/Odul yuksek
3. Trend gucu yuksek
4. Haber tonu net olumlu

### 5.3 Portfoyum varsa ne yapayim?
- Portfolio Update mesajini esas alin
- EXIT geldiyse zarar kes/kazanc koruma senaryosunu gecikmeden inceleyin
- RAISE STOP geldiyse stop seviyesini islem platformunuzda guncelleyin
- PARTIAL TAKE PROFIT geldiyse kismi realizasyon planlayin

### 5.4 Yeni alim yapacaksam nasil karar vereyim?
Kontrol listesi:
- Entry Range piyasada makul mu?
- Stop mesafesi sizin maksimum riskinize uygun mu?
- Islem basi risk sermayenizin yuzde kacina denk geliyor?
- Ayni sektorde asiri yigilma var mi?

### 5.5 Robot HOLD dediyse ne yapmaliyim?
- Yeni islem acmak zorunda degilsiniz
- Mevcut pozisyonu koruyun
- Gunun sonunda tekrar update ile teyit edin

### 5.6 EXIT dediyse ne yapmaliyim?
- Cikis gerekcesini oncelikli degerlendirin
- Teknik bozulma ve guven dususu varsa gecikmeden aksiyon alin
- Kesinlikle otomatik emir gibi degil, karar destek sinyali olarak uygulayin

### 5.7 WAIT IN CASH dediyse ne yapmaliyim?
- Yeni pozisyon acmayin
- Nakit korunumu yapin
- Sonraki rapor periyodunu bekleyin

### 5.8 Pratik mini rutin
- 09:50 BIST mesaji kontrol
- 16:05 US mesaji kontrol
- 22:35 Portfolio update (aktifse) kontrol
- Haftalik bir kez threshold degerlerini gozden gecirme

---

## 6) Programi Nasil Baslatacagim? (Sifirdan)

Bu bolum Python bilmeyen bir kullanici icin sade adimlarla yazilmistir.

### 6.1 On kosullar
- Windows bilgisayar
- Internet baglantisi
- Python 3.12 kurulu

### 6.2 Proje klasorunu hazirlama
- Projeyi bir klasore acin: ornek C:/Users/kullanici/Desktop/finance

### 6.3 Virtual Environment olusturma
Komutlar (PowerShell):

    cd C:/Users/kullanici/Desktop/finance
    py -3.12 -m venv .venv

### 6.4 Virtual Environment aktif etme

    ./.venv/Scripts/Activate.ps1

Not:
- Ilk calistirmada execution policy engeli alirsaniz gecici olarak:

    Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass

### 6.5 Bagimlilik kurma

    python -m pip install --upgrade pip
    python -m pip install -r requirements.txt

### 6.6 ENV dosyasini hazirlama

    Copy-Item .env.example .env

Sonra .env dosyasini acip su alanlari doldurun:
- TELEGRAM_BOT_TOKEN
- TELEGRAM_CHAT_ID
- GEMINI_API_KEY (ve opsiyonel key pool)

Guvenlik notu:
- API keyleri asla paylasmayin
- .env dosyasini public repo'ya koymayin

### 6.7 Programi baslatma (kolay yol)

    .\run.bat

Bu komut uvicorn sunucusunu 127.0.0.1:8000 adresinde baslatir.

### 6.8 API ayakta mi kontrol
Tarayicida acin:
- http://127.0.0.1:8000/health

Beklenen cevap:
- status healthy
- gemini_enabled true/false
- gemini_healthy true/false

### 6.9 Scheduler aktif mi?
- Uygulama acilisinda scheduler joblari register edilir
- BIST ve US default aciktir
- Portfolio default kapali olabilir, .env'den acabilirsiniz

### 6.10 Manuel tetik endpointleri
Ornek PowerShell cagrilari:

    Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8000/run/bist
    Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8000/run/us
    Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8000/run/portfolio

### 6.11 Programi durdurma

    .\stop.bat

### 6.12 Programi yeniden baslatma

    .\restart.bat

---

## 7) Program Calisirken Ne Gormeliyim?

### 7.1 Normal loglar

| Log ornegi | Anlam |
|---|---|
| Application starting with timezone=Europe/Istanbul | Uygulama aciliyor |
| Gemini status on startup: enabled=True healthy=True | Gemini ulasilabilir |
| Registered scheduler job weekday_bist_report | BIST cron kaydi tamam |
| Scheduler started | Scheduler aktif |
| BIST | Toplam Hisse=... | Gunluk akis ozeti |

### 7.2 Hata olmayan uyarilar
- Gemini paketinin deprecated olduguna dair FutureWarning
- Gecici timeout sonra retry basari loglari

Bu uyarilar her zaman kritik degildir.

### 7.3 Kritik hata loglari

| Tip | Etki | Aciliyet |
|---|---|---|
| Uvicorn boot hatasi | API acilmaz | Yuksek |
| Scheduler baslamama | Otomatik raporlar gitmez | Yuksek |
| Telegram chunk fail son deneme | Bildirim ulasmaz | Orta-Yuksek |
| Market data bos + tekrarli | Oneri kalitesi duser | Orta |
| JSON parse bozulmasi | Akis kesilebilir | Yuksek |

### 7.4 Ornek loglar

    2026-07-19 09:40:01 | INFO | shared.app | Application starting with timezone=Europe/Istanbul
    2026-07-19 09:40:02 | INFO | scheduler.jobs | Registered scheduler job weekday_bist_report
    2026-07-19 09:40:02 | INFO | scheduler.jobs | Registered scheduler job weekday_us_report
    2026-07-19 09:40:02 | INFO | scheduler.jobs | Scheduler started
    2026-07-19 09:45:16 | INFO | services.pipeline | BIST | Toplam Hisse=595 | Helal Filtre=430 | AI Analizi=157 | Onerilen=0 | Toplam Sure=24.12s | Gemini Cagrisi=0 | API Key=KEY_1

---

## 8) Hata Durumlari

### 8.1 Gemini calismazsa
Belirti:
- health endpointte gemini_healthy false
- AI Ozet bos veya yok

Sistem davranisi:
- Cekirdek karar motoru calismaya devam eder

Cozum:
1. .env keylerini kontrol et
2. GEMINI_MODEL degerini dogrula
3. Internet/Firewall kontrol et
4. Manuel /run/bist tetikleyip tekrar dene

### 8.2 Yahoo calismazsa
Belirti:
- US adaylari az veya yok
- US raporda WAIT IN CASH siklasir

Cozum:
1. Internet ve DNS kontrol
2. US ticker listesi dogru mu kontrol
3. Kisa sure sonra tekrar dene

### 8.3 Telegram calismazsa
Belirti:
- Notification sonucu success false

Cozum:
1. TELEGRAM_BOT_TOKEN dogru mu
2. TELEGRAM_CHAT_ID dogru mu
3. Botun ilgili chatte yetkisi var mi
4. Rate limit durumunda birkac dakika sonra tekrar dene

### 8.4 Scheduler calismazsa
Belirti:
- Saat geldi ama mesaj yok

Cozum:
1. Uygulama calisiyor mu
2. Bilgisayar uyku modunda mi
3. SCHEDULER_*_ENABLED true mu
4. Saat/dakika ayarlari dogru mu
5. Timezone dogru mu

### 8.5 portfolio.json bozulursa
Belirti:
- Portfolio update akisinda hata
- Pozisyonlar okunamaz

Cozum:
1. storage/data/portfolio.json yedegini geri yukle
2. JSON formatini dogrula
3. Gecici olarak bos liste ile ac

Ornek gecerli format:

    [
      {
        "ticker": "THYAO",
        "average_price": 190.0,
        "quantity": 10,
        "current_profit": 0.0,
        "current_stop": 180.0,
        "current_decision": "HOLD"
      }
    ]

### 8.6 Genel kurtarma proseduru
1. stop.bat
2. .env kontrol
3. JSON dosya sagligi kontrol
4. restart.bat
5. health endpoint kontrol
6. run/bist manuel tetik

---

## 9) Performans

### 9.1 Guclu yonler
- Katmanli kalite filtresi
- Helal uygunluk adimi
- Deterministic karar motoru
- Telegram operasyonel raporlama
- Scheduler ile rutin otomasyon
- AI yorumun cekirdekten ayrik olmasi (dayaniklilik)

### 9.2 Sinirlamalar
- Veri kalitesi kaynak bagimlidir
- Ani haber rejim degisimlerini gec algilayabilir
- Kurallar gecmise iyi uysa da gelecekte ayni calismayabilir
- Lokal makinaya bagimli uptime

### 9.3 AI neden bazen yanlis olabilir?
- Gemini metin yorumlarinda baglamsal hata yapabilir
- Haber metni eksik/yaniltici olabilir
- AI summary, karar motorundan bagimsiz bir niteliksel katmandir

### 9.4 Sistem hangi durumlarda daha basarili olur?
- Verinin temiz ve gunluk aktigi donemler
- Trendlerin daha net oldugu piyasa kosullari
- Asiri volatil olmayan rejimler

### 9.5 Hangi durumlarda dikkatli olunmali?
- Makro sok gunleri
- Sirket bazli ani/regulasyonel haber gunleri
- Likiditenin dustugu seanslar
- Gap ve spread'in asiri arttigi anlar

### 9.6 Gercekcilik notu
Bu sistem kesin kazanc vaat etmez.
Karar destek aracidir. Nihai sorumluluk kullanicidadir.

---

## 10) Bakim

### 10.1 API anahtari degisirse ne yapacagim?
1. .env dosyasini ac
2. Ilgili alanlari guncelle
3. restart.bat ile servisi yeniden baslat
4. health endpoint ile dogrula

### 10.2 Yeni Gemini key nasil eklenir?
Key pool mantigi vardir.
Ornek:

    GEMINI_API_KEY=ana_key
    GEMINI_API_KEY_1=yedek_key_1
    GEMINI_API_KEY_2=yedek_key_2

Not:
- Sistem keyleri sirayla dener
- Basarisiz key durumunda failover olabilir

### 10.3 Yeni Telegram bot nasil eklenir?
1. BotFather ile yeni bot olustur
2. Token al
3. Chat id belirle
4. .env'de TELEGRAM_BOT_TOKEN ve TELEGRAM_CHAT_ID guncelle
5. restart.bat

### 10.4 Yeni market nasil eklenir?
Gelir yolu:
1. Yeni collector ekle
2. normalize_records uyumlulugu sagla
3. market field ile ayristir
4. pipeline collect_market ve analyze_market akisini genislet
5. scheduler/job endpoint ekle
6. testleri guncelle

### 10.5 Yeni hisse listesi nasil guncellenir?
US icin:
- .env -> US_MARKET_TICKERS alanini guncelle

Ornek:

    US_MARKET_TICKERS=GOOGL,AMZN,NVDA,MSFT,AMD

BIST icin:
- Collector kaynagi ve normalize edilen cikti uzerinden otomatik akar

### 10.6 Yeni helal filter nasil guncellenir?
Dosya:
- storage/config/halal_filter.json

Guncellenebilir alanlar:
- blocked_tickers
- blocked_keywords
- blocked_sectors

Degisiklik sonrasi:
- Servisi restart edin
- Manuel run/bist ile dogrulayin

### 10.7 Threshold bakimi
Kalite esikleri .env uzerinden ayarlanir.
Kritik alanlar:
- MIN_CONFIDENCE_SCORE
- MIN_RISK_REWARD_RATIO
- MIN_TREND_STRENGTH
- MIN_RELATIVE_VOLUME
- MIN_FUNDAMENTAL_SCORE
- MIN_MARKET_INTELLIGENCE_SCORE
- MIN_NEWS_SCORE
- MIN_TECHNICAL_SCORE

Pratik not:
- Esikleri cok yuksek tutmak WAIT IN CASH frekansini artirir
- Esikleri cok dusurmek kaliteyi bozabilir

---

## 11) Dosya Yapisi

### 11.1 Ust seviye dosyalar

| Yol | Gorev |
|---|---|
| main.py | Uygulama giris noktasi |
| run.bat | Sunucuyu baslatir |
| stop.bat | 8000 portundaki sureci durdurur |
| restart.bat | Durdurup tekrar baslatir |
| requirements.txt | Python bagimliliklari |
| .env / .env.example | Ortam konfigurasyonu |
| USER_GUIDE.md | Bu teslim dokumani |

### 11.2 Klasorler

| Klasor | Gorev |
|---|---|
| analyzers | Kural bazli skorlayicilar |
| collectors | Veri toplama katmani |
| config | Runtime settings |
| decision | Nihai karar motoru |
| indicators | Teknik indikator fonksiyonlari |
| notifier | Telegram/console bildirimleri |
| scheduler | Saatli job kaydi ve yonetimi |
| services | Pipeline ve Gemini entegrasyonu |
| shared | Uygulama/factory/logging/common |
| storage | JSON config ve runtime data |
| tests | Birim testler |

### 11.3 storage/config dosyalari

| Dosya | Islev |
|---|---|
| news_keywords.json | Haber kelime agirliklari |
| technical_scoring.json | Teknik skor agirliklari |
| halal_filter.json | Helal filtre blok listeleri |

### 11.4 storage/data dosyalari

| Dosya | Islev |
|---|---|
| news.json | Ham/normalize haberler |
| kap.json | KAP kayitlari |
| market.json | Helal filtreden gecmis market verisi |
| news_analysis.json | Haber sentiment ciktilari |
| ticker_news_summary.json | Ticker bazli haber ozeti |
| market_analysis.json | Teknik-temel-market-trend birlesik analiz |
| recommendations.json | Genel veya son rapor onerileri |
| bist_recommendations.json | BIST ozel oneriler |
| us_recommendations.json | US ozel oneriler |
| portfolio.json | Kullanici pozisyon listesi |
| portfolio_analysis.json | Pozisyon analiz ciktilari |
| history.json | Oneri arsivi |
| performance.json | Paper performance metrikleri |

---

## 12) Kullanici Tavsiyeleri

### 12.1 En verimli kullanim senaryosu
1. Bilgisayari 09:30 civari ac
2. Uygulamayi 09:40'tan once baslat
3. 09:45 BIST mesaji geldikten sonra 10-15 dk inceleme yap
4. 16:00 US raporunu ikinci kontrol penceresi olarak kullan
5. Portfolio update aciksa 22:30 sonrasi stop/pozisyon revizesi yap

### 12.2 Hangi saatlerde bilgisayar acik olmali?
Minimum:
- 09:40-10:00
- 15:55-16:15

Tam otomasyon icin:
- 09:30-23:00 arasi acik

### 12.3 Telegram ne zaman kontrol edilmeli?
- 09:45 sonrasi hemen
- 16:00 sonrasi hemen
- 22:30 sonrasi (portfolio job aciksa)

### 12.4 Portfoyu ne siklikla guncellemeliyim?
- Yeni islem actikca portfolio.json guncellenmeli
- En az gunde 1 kez kontrol edilmesi onerilir

### 12.5 Yatirim kararlarini nasil degerlendirmeliyim?
- Robotu tek karar merci yapmayin
- Kendi risk profilinizi ustte tutun
- Islem basi maksimum zarar limiti belirleyin
- Sektor yogunlasmasi riskini takip edin

### 12.6 Operasyonel checklist
- Uygulama acik mi?
- Health endpoint saglikli mi?
- Telegram token/chat id gecerli mi?
- Internet stabil mi?
- .env ve JSON dosyalari saglam mi?

---

## 13) Sonuc

### 13.1 Gelistirici olarak teslim ozeti
Bu proje teslim aninda su kabiliyetlere sahiptir:
- BIST ve US icin gunluk otomatik analiz
- Helal filtreyle aday temizleme
- Teknik, temel, market intelligence, trend ve karar motoru
- Quality gate esikleriyle secici sinyal mekanizmasi
- Dynamic recommendation count (sabit top N yok)
- WAIT IN CASH fallback
- Portfolio yeniden degerlendirme
- Telegram raporlama
- Scheduler tabanli otomasyon

### 13.2 Dürüst sinirlar
Bu sistem:
- Kesin kazanc garantisi vermez
- Veri kesintisi olan gunlerde eksik cikti uretebilir
- AI metin yorumunda hataya acik olabilir
- Lokal makine acikligina bagimlidir

### 13.3 Gelecekte yapilabilecek gelistirmeler
1. Backtest modulu ve walk-forward dogrulama
2. Risk parity veya volatilite hedefli allocation
3. Gercek zamanli websocket feed entegrasyonu
4. Multi-notifier (email, push, Slack) iyilestirmeleri
5. Dashboard UI ile KPI izleme
6. Otomatik self-healing ve watchdog servisleri
7. Paper trading simulasyon raporunun zenginlestirilmesi

### 13.4 Son teslim notu
Proje, gunluk karar destek operasyonu icin kullanima hazirdir.
Operasyonel guvenilirlik icin:
- Saatli calisma pencerelerine uyun
- Konfigurasyonu duzenli kontrol edin
- Telegram mesajlarini disiplinli okuyun
- Risk yonetimini daima birinci sirada tutun

Bu dokuman ile birlikte proje, kullaniciya tam operasyon ve bakim transferi hedefiyle teslim edilmistir.
