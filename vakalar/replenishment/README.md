# Replenishment — depodan mağazaya

Lumoda v4 sentetik verisi ve v4 motoru üstünde depodan mağazaya replenishment vakası.
Sitedeki `/replenishment/depodan-magazaya/` dizisinin (6 yazı) ve demo kadranının bütün
sayıları buradan, `cikti/rapor.txt`'ten çıkar (`cikti/` git dışıdır; dosyayı `rapor.py` yeniden
üretir, aşağıdaki 8. adım). Tasarım:
`docs/superpowers/specs/2026-10-10-depodan-magazaya-v4-design.md` (`docs/` ayrı depodur);
uygulamadaki sapmalar ve kararlar o belgenin §12'sinde, yürütme kaydı
`.superpowers/sdd/2026-10-10-dm-v4/progress.md` (Ruling R1–R40).

Replenishment burada **depodaki malın her pazartesi mağazalara dağıtılmasıdır**: satan ürünün
aynısını yerine koymak. Tedarikçiye tekrar sipariş (RPT; `vakalar/rpt/`) değildir. Sezon
başındaki ilk alım ve yeni dalgaların ilk dağıtımı Lumoda'nındır, bütün kollarda aynıdır; kollar
yalnız oyun penceresindeki replenishment kararını değiştirir.

## Kurulum

    cd vakalar/replenishment
    python -m venv .venv
    .venv/Scripts/pip install -e ../ortak              # perakende_analitik (Basit, kaynak, sayı denetimi)
    .venv/Scripts/pip install --no-deps -e ../../veri  # perakende_veri (v4 motoru; yalnız replenishment/motor.py açar)
    .venv/Scripts/pip install -e ".[dev]"

Veri `veri/cikti/v4/perakende.duckdb` (ya da `PERAKENDE_V4_DB`); yoksa yayımlanan `veri-v4`
dosyasını indirin ya da `cd veri && python -m perakende_veri.v4.uret`. Hakem önbelleği gerekmez:
gerçek talep her koşunun kendi gizli gerçeğinden (`Kosu.gercek`) ölçülür; yayımlanan dünya
`lumoda_kisitsiz` koşusunun kendisidir.

`lightgbm` < 4.6 ve `scikit-learn` < 1.8 sabit (Windows çökmesi ve `force_all_finite`;
`pyproject.toml`'daki not).

## Koşum

Bütün komutlar `vakalar/replenishment` içinden, vakanın `.venv`'iyle.

- **Ortam:** Windows konsolunda `PYTHONIOENCODING=utf-8` (Türkçe karakter).
- **Sıralı:** koşu önbelleği eşzamanlı yazmaya güvenli değil. Aşağıdaki komutlardan ikisini
  (rapor ve testler dahil) aynı anda koşmayın; RPT vakasının koşularıyla da aynı anda koşmayın
  (bellek).
- **Makine uyanık kalmalı:** oyun ve yollar saatler sürer. `oyun` kendisi
  `SetThreadExecutionState` ile uykuyu engeller (`uyanik_tut`); yarım kalan iş kaldığı yerden
  sürer, yarım koşu baştan koşulur.
- **Kaynaklar:** bir TAM koşu tepe ~7,2–8,0 GB; uzun süreçte süreç ömrü tepesi ~11 GB (10,97 GB
  ölçüldü: ızgaranın alım 0,4 bloğu, yollarda eğitim + koşu). DuckDB bağlantıları 6 GB'la sınırlı
  (`oyun.DUCKDB_BELLEK`; aşınca `cikti/duckdb_gecici`'ye taşar). Disk ~15 GB (`cikti/kosular`
  14 GB, koşu başına ~160 MB; `cikti/yollar` 0,8 GB; günlük tablo 240 MB). Öndeki ağır
  uygulamalar koşuyu ~220 sn'den ~600 sn'ye çıkarabilir (bellek sıkıştırma).

Sıra ve ölçülen süreler (sıfırdan toplam ~7,5 sa):

    # 1. Hazırlık (~15 dk): yol 0 lumoda_kisitsiz koşusu (ilk seferde ~3 dk), LightGBM
    #    (~6 dk, 1.651.315 satır; cikti/tahmin/yol0.json), DM'nin kendi günlük tablosu
    #    (~8 dk, 69,4 M satır; cikti/gunluk.parquet, R19) ve kural_basit çarpanları
    .venv/Scripts/python -m replenishment.oyun hazirlik

    # 2. Kalibrasyon (18 TAM koşu ~80 dk; önbellekten birkaç dakika): AW24 penceresi;
    #    cikti/kalibrasyon.json (hedef bulunabilirlik, aile, koli kuralı, referans tavan)
    .venv/Scripts/python -m replenishment.oyun kalibrasyon

    # 3. Oyun ızgarası (48 TAM koşu ~4 sa; yeni koşu başına medyan ~220 sn, 169–619):
    #    eşdeğerlik 1 + demo 27 + tarama 20; cikti/oyun.json (--blok demo|tarama|... ile parça parça)
    .venv/Scripts/python -m replenishment.oyun izgara

    # 4. Eşitlik denetimi (~6,5 dk): çevrimdışı ↔ Görünüm LightGBM özellikleri; cikti/esitlik.json
    .venv/Scripts/python -m replenishment.oyun esitlik

    # 5. Yollar (~2 sa): yol 1–4 için Lumoda koşusu, yolun DuckDB'si, LightGBM (yol başına
    #    5–27 dk) ve 4 kol; yol 0 ızgaradan (önbellekten); cikti/yollar.json
    .venv/Scripts/python -m replenishment.yollar

    # 6. Hikâye girdisi (~40 sn) ve sahne seçimi (~50 sn): cikti/hikaye_girdi/, cikti/hikaye.json
    .venv/Scripts/python -m replenishment.oyun hikaye-girdi
    .venv/Scripts/python -m replenishment.hikaye_sec              # --adaylar, --hikaye OPTION:SKU

    # 7. Demo kadranı (bir saniyeden kısa; yalnız önbellekten): site/src/data/senaryolar/depodan-magazaya.json
    .venv/Scripts/python senaryolar.py

    # 8. Rapor (~2 dk; motor koşmaz, 33 koşu önbellekten; korunum tutmazsa stdout boş, çıkış 1)
    .venv/Scripts/python rapor.py > cikti/rapor.txt

    # 9. Yazılardaki her sayı raporda mı (çıkış 0; birkaç saniye)
    cd ../ortak && .venv/Scripts/python -m perakende_analitik.sayi_denetimi \
        --yazi ../../site/src/content/yazi/replenishment/depodan-magazaya --rapor ../replenishment/cikti/rapor.txt

Rapor demo dosyasını da denetler (sitedeki JSON = raporun bileşimleri), bu yüzden `senaryolar.py`
rapordan önce koşar. `senaryolar.py` JSON'a `surum` olarak HEAD'in kısa SHA'sını yazar; içerik
değişmese de commit'ten sonra koşulursa yalnız bu alan değişir. Aynı girdiyle iki rapor bayt bayt
aynıdır. Biten her motor koşusu ve hazırlık adımı `cikti/ilerleme.jsonl`'a yazılır.

Testler: `.venv/Scripts/python -m pytest -q -m "not veri"` (~5 dk; KÜÇÜK dünyada motor koşuları
dahil); `-m veri` gerçek v4 dosyasını ister (3 test, ~8 dk: eşdeğerlik `lumoda_kisitsiz`'i önbellekten açıp
yayımlanan tablolarla karşılaştırır, yol 0 LightGBM'i geçici dizinde yeniden eğitir). `tests/conftest.py`'deki `GECICI_V2` (v2'den kalan geçici atlama listesi) boştur ve yalnız
küçülebilir (`tests/test_iskelet.py`).

## Önbellek katmanları

| Katman | Yer | Anahtar | Değişince |
|---|---|---|---|
| Motor koşuları | `cikti/kosular/<ad>_<anahtar[:20]>` | `ad`, `parametreler` (kanonik JSON), `ilk_alim_orani`, `kaydedici` bayrağı, politika türü ve kimliği (kolun `Ayar`'ı, sardığı Lumoda kuralı, LightGBM modelinin `model_to_string` özeti, Basit çarpanlarının içerik özeti), talep ve operasyon tohumu, ölçek, gün sayısı, `motor.kod_ozeti` (`KOSU_MODULLERI` + onların ortak paket kapanışı + `perakende_veri/v4/**/*.py`), v4 dosyasının parmak izi (ad, boyut, mtime), numpy / pandas / pyarrow / lightgbm / scikit-learn sürümü | yeni anahtar, yeni koşu (eskisi diskte kalır) |
| LightGBM | `cikti/tahmin/yol<p>.json` + `yol<p>_ozet.json` | veri kimliği (yol 0: yayımlanan dosyanın parmak izi; yol p: Lumoda koşusunun anahtarı), `motor.kod_ozeti`, `EGITIM_BIT`, parametreler, ölçek | yeniden eğitilir (yol 0 ~6 dk, yol p 5–27 dk). Kimlik içerikten: aynı içerik aynı kimliği verir, koşular önbellekten gelir (RPT'nin pickle dersi burada yok) |
| Günlük tablo | `cikti/gunluk.parquet` + `gunluk.kaynak` | veri kimliği, `anlik.PENCERE`, ortak `hazirlik.py` + `stok.py` özeti | yeniden kurulur (~8 dk); yalnız `kural_basit`'in çarpanları okur (çarpanların içerik özeti koşu anahtarında) |
| Yol DuckDB'si | `cikti/yollar/yol<p>/perakende.duckdb` + `.kosu` | yolun Lumoda koşusunun anahtarı | yeniden yazılır (~10–15 sn) |
| Kalibrasyon | `cikti/kalibrasyon.json` | yok (her `oyun kalibrasyon` yeniden yazar; koşular önbellekten) | seçilen değerler kolların `Ayar`'ına, oradan bütün koşu anahtarlarına girer |
| Oyun ölçümleri | `cikti/oyun.json` | kayıt başına koşu anahtarı + `olcum_kodu` (`olcutler.py`'nin içe aktarmadaki özeti, `OLCUM_SURUMU`, referans tavan, pencere) | `oyun izgara` tutmayan kaydı yeniden ölçer (koşu önbellekten, ~20 sn); rapor eski ölçümü reddeder |
| Yollar | `cikti/yollar.json` | yol başına `yollar.kod_ozeti` (koşu kod özeti, v4 parmak izi, `olcutler.py` + `oyun.py` + `yollar.py` özeti) + koşu anahtarları | `yollar` tutmayan yolu yeniden hesaplar (25 koşu önbellekten, ~6,5 dk) |
| Hikâye girdisi | `cikti/hikaye_girdi/` (Parquet + `kaynak.json`) | rol → koşu adı ve anahtarı (`oyun.json`'dakilerle tutmalı), pencere | `oyun hikaye-girdi` yeniden yazar; `hikaye_sec` ve rapor anahtar uyuşmazlığını reddeder |
| Eşitlik | `cikti/esitlik.json` | yok | `oyun esitlik` yeniden yazar |

**Koşu anahtarına girenler kasıtlı dar.** `KOSU_MODULLERI` = `motor`, `sabitler`, `kaynak`,
`defter`, `ihtiyac`, `dagitim`, `tahmin`, `anlik`, `politika` (listedeki `bilgi` dosyası yok, atlanır);
`KOSU_DISI` = `olcutler`, `oyun`,
`yollar`, `hikaye_sec`, `senaryolar`, `kalibrasyon`. Vaka kökündeki `rapor*.py`, `senaryolar.py`
ve testler de dışarıda. `replenishment/`'deki her modül iki listeden birindedir
(`tests/test_motor.py`). Ölçümün sonucu politikaya yalnız `parametreler` / `Ayar` üstünden girer
(kalibrasyon, R5). Politikanın davranışını değiştiren ve nesnenin beyan etmediği her parametre
`parametreler`'e girmeli.

**Kod değişince ne olur, elle ne silinir:**

- `KOSU_MODULLERI`'nden bir dosya, onların ortak kapanışı (`vakalar/ortak/`) ya da `veri/`'deki v4
  kodu değişirse hiçbir şey silmeyin: bütün anahtarlar kendiliğinden değişir; kalibrasyon, ızgara,
  yollar ve LightGBM eğitimleri baştan koşar (~7,5 sa). `vakalar/ortak/` ya da `perakende_veri/v4`
  değişikliği RPT'nin ızgarasını da geçersiz kılar (`vakalar/rpt/README.md`); bu dalın
  `ilk_alim_orani` değişikliği (`v4/dunya.py`, `v4/plan.py`) RPT'nin kod özetini değiştirdi. Eski koşu dizinleri `cikti/kosular/`'da
  kalır; yer açmak için elle silinebilir.
- **v4 dosyasının mtime'ı anahtardadır.** Dosyayı yeniden indirmek, kopyalamak ya da `touch`
  etmek (içerik aynı olsa da) bütün koşuları geçersiz kılar.
- `olcutler.py` değişirse: `oyun izgara` (yeniden ölçüm), `yollar`, sonra 6–9.
- `oyun.py` ya da `yollar.py` değişirse: `yollar` (oyun.json'un ölçüm kodunda `oyun.py` yok;
  yalnız yollar yeniden ölçülür), sonra 8–9. `oyun.py`'deki ızgara tanımı (`IZGARA`) değişirse
  `oyun izgara` eksik koşuları koşar.
- `kalibrasyon.py` değişirse `oyun kalibrasyon`; seçim değişmişse bütün ızgara yeniden koşar.
- `hikaye_sec.py` değişirse 6'nın ikinci komutu, sonra 8–9; `senaryolar.py` değişirse 7–9;
  `rapor.py` / `rapor_b.py` değişirse yalnız 8–9.
- `cikti/duckdb_gecici/` geçici taşma dizinidir; koşu yokken silinebilir.

## Kararlar (özet; ayrıntı spec §12 ve kayıt defteri)

- **Koli açılmaz.** Depoda stok ya kapalı kolide ya açık adettir (gölge defter, `defter.py`).
  Mağazaya gönderim önce açık adetten (açık stok ve haftalık açık toplama tavanı yettiğince),
  kalan ihtiyaç için koli kuralı izin verirse tam koliyle. Koli dünyanın paket tablosundan:
  standart 7 adet, beden sırasıyla 1-2-2-1-1; tek bedenli aksesuar 6. Açık payı Collection ve
  Outlet %20, NOS ve Basic %40 (anlatı varsayımı). Koliler açık tavanına sayılmaz (R16).
- **Gölge defter brüt akışlardan (R8, R10, R11).** İlk dağıtım kaydı politikanın kararıdır,
  motorun uyguladığı değil: defter onu üst sınır olarak kullanır, lansman günü geçince havuz düşer.
  Açılış transferleri ve sezon sonu `stok_devri` kaydedicisizdir: uzlaştırmada "açıklanamayan"
  kalemlere düşer (rapor DEPO bölümü basar; 2025-11-24 haftasındaki büyük artı stok devridir).
- **Kısıtsız kalibrasyon (R23, R25, R26, R27).** Güvenlik stoku aileleri kısıtsız (tavan yok,
  koli zorunluluğu yok) bir yıl önceki aynı pencerede (AW24) kalibre edilir; hedef istatistik
  ailesinin bulunabilirliği (%67,11). Izgaralar sabit {1–4}, ros {3, 5, 6, 7, 10} gün, A α {0,4;
  0,6} × β {2, 3, 4}, B γ {0,5; 0,75}. Aile "aynı hedefte en az stok": sabit 4. Koli kuralı
  referans tavanda, "en iyinin 1 puan içinde en ucuz": A (α 0,4, β 3); α 0,4 ızgaranın alt ucunda
  kaldı (R26). C = A ∧ B kalibre edilmedi (C ⊆ B), oyunda ölçüldü.
- **Lumoda taban çizgisi (R33).** Lumoda'nın bugünkü kuralı (planın 4 haftası, ölü stok kapısı)
  aynı kısıtta (`lumoda_ref`) kollarla yarışır. Kural yalın: daha az stokla daha düşük
  bulunabilirlik. Kuralın hedef ufku kod değişmeden güvenlik stokuyla genişletildi (R30: ros 14 /
  21 / 28 gün); rapor iki kolu bulunabilirlik–mağaza stoğu sınırında, eşit stokta karşılaştırır.
- **Bulunabilirlik** (R22): fiziksel mağaza hücrelerinde, pencerede, talepli hücre-günlerin
  kendi satışı olan payı: |talep > 0 ∧ kendi_satis > 0| / |talep > 0| (stok ≥ 1 ve talep ≥ 1 ise
  kendi satış ≥ 1; stoksuzsa 0). Küçük bir yanlılığı var (R27): `kendi_satis` gelen ikame satışını
  düşer, başka hücrenin ikame müşterisi son adedi alırsa o hücre-gün stoksuz sayılır. Yanlılık
  bütün kollarda aynı yöndedir.
- **Kırık çift** (R29): stoklu bir mağaza–option çiftinin, çeşidinde bulunan çekirdek
  bedenlerinden (beden sırası 2–4; v4'te çok bedenli setlerin hepsi 5 beden) biri 0. Tek bedenli
  Standart çiftler evren dışı; pencerenin son fotoğrafında ölçülür. Pay = kırık / stoklu çift.
- **Hikâye merdiveni (R31, R32).** Sahne yayımlanan dünyada bir (pazartesi, SKU): Lumoda'nın
  istekleri depoyu aşmış (orantılı kesim), İstanbul'da isteyip alamayan (Ali) ve Anadolu'da alan
  (Veli) mağaza var, malı alamayan Ali mağazaları hem karar öncesi hem sonraki 28 günde stoklu gün
  hızıyla daha hızlı, ürün bedenli. "Kural ürün genelinde iyi" ölçüt değil, rapor sütunu.
- Öteki: `motor.py` RPT'den kopya (R1); dünya önbelleği (ölçek, oran) başına; Black Friday özel gün
  katsayısından ayrı (R12); hiç stok görmemiş çiftin öngörüsü 0 (R13); LightGBM eğitimi oyun
  penceresinden önce bir kez, `EGITIM_BIT`'e dek (R18); DM kendi günlük tablosunu kurar (R19).

## Sahneler

- **Seçilen (1. yazı):** MDL0639-BEJ-XL Fırfırlı Bluz Bej XL (Collection, Kadın Harf), oyunun 4.
  pazartesisi, lansmandan 35 gün sonra. 6 mağaza 32 adet istedi, depoda 1 adet vardı, o da Konya
  2'ye gitti; İstanbul 7, 8, 17 almadı. Hız (adet / stoklu gün) önce 1,12'ye karşı 0,68, sonra
  0,88'e karşı 0,36; mağaza bazında da her almayan Ali mağazası alan Veli mağazasından hızlı.
  Merdivenin ilk adayı, gevşeyen yok. Ürün genelinde kural bu option'da Lumoda'dan kötü (%88,73'e
  karşı %91,49); yazı bunu iddia etmez.
- **Alternatif:** MDL0646-HAK-L Blazer Ceket Haki L, oyunun 10. pazartesisi (istek 45, giden 11).

    .venv/Scripts/python -m replenishment.hikaye_sec --hikaye MDL0646-HAK:MDL0646-HAK-L   # sonra 8–9

## Modüller

| Modül | İşi |
|---|---|
| `sabitler.py` | Pencereler (`OYUN_BAS`…`OYUN_BIT`, `KAL_BAS`…`KAL_BIT`, `EGITIM_BIT`), açık payı, toplama maliyeti, tavan oranı, alım düzeyleri, tavan katları, yol sayısı, tohum tabanı |
| `motor.py` | Üretecin tek kapısı (vakada `perakende_veri`'yi yalnız bu modül içe aktarır): `dunya(olcek, ilk_alim_orani)`, `kos(...)` → `Kosu` / tembel `KosuKaydi`, `Kaydedici` (ilk dağıtım, outlet akışı), koşu önbelleği, `yayimlanan_bicim`, `lumoda(...)` |
| `kaynak.py` | Yayımlanan v4'ten okuma (ortak paketin temiz görünümleri), fiziksel mağazalar (Ali / Veli), günlük satış ve stoklu matrisler; `Harita` (hücre ↔ mağaza, option, SKU, line, beden payı) yalnız dünyanın açık alanlarından |
| `defter.py` | Gölge defter: option başına kapalı koli, SKU başına açık adet; brüt akışlarla haftalık `uzlastir`, değişmez denetimi, uzlaştırma kalemleri |
| `ihtiyac.py` | Özel gün katsayıları, güvenlik stoku aileleri (sabit, ros, istatistik), kural öngörüsü (stoklu güne bölünmüş 7 gün × hafta katsayısı), mağaza beden payları, bedene bölme |
| `dagitim.py` | Kısıtlı dağıtım: maske, açık aşama (tavan), koli aşaması (A / B / C ya da koli yok), öncelik (cover, ihtiyaç, eşit, orantılı) |
| `tahmin.py` | LightGBM: tek küresel Poisson model, çevrimdışı ve Görünüm yolu aynı özellik fonksiyonuyla, içerikten kimlik |
| `anlik.py` | `kural_basit` için motor içi karar anı Basit (RPT'nin `anlik` / `sansur` parçalarının kopyası) |
| `politika.py` | `KOLLAR`: `lumoda`, `kural`, `kural_basit`, `tahmin`, `tahmin_taban`; `Ayar`; `sevkiyatla_karsilastir` |
| `kalibrasyon.py` | AW24 penceresinde aile, koli kuralı ve referans tavan seçimi; koşu enjekte edilir (motoru görmez) |
| `olcutler.py` | Koşu ölçütleri (bulunabilirlik, kayıp, toplama maliyeti, doluluk, kırık çift, beden sapması, satışa dönme, STR, depo-boş kayıp payı), line kırılımı, korunum denetimi |
| `oyun.py` | CLI: `hazirlik`, `kalibrasyon`, `izgara`, `esitlik`, `hikaye-girdi`; `IZGARA`, referans nokta, `kos_bir` |
| `yollar.py` | 5 talep yolu, ayrışım (öngörü / politika etkisi), "kaç yolda önde"; `cikti/yollar.json` |
| `hikaye_sec.py` | Sahne merdiveni, mağaza tablosu, boş raf örneği; `cikti/hikaye.json` |
| `rapor.py`, `rapor_b.py` | Yayımlanacak her sayı (VERİ · DEPO · KALİBRASYON · YOL 0 · LUMODA VE KURAL · YOLLAR · LINE KIRILIMI · KOLİ VE TAVAN · ÖNCELİK · KURAL HEDEFİ · SANSÜR · BASİT · HİKÂYE · DEMO · ANLATI VARSAYIMLARI · KORUNUM); `rapor_b` girdileri önbellekten okur |
| `senaryolar.py` | Demo kadranının JSON'u (27 bileşim, yalnız önbellekten) |

## İlkeler

- **Sızıntı yok.** Karar modülleri (`kaynak`, `defter`, `ihtiyac`, `dagitim`, `tahmin`, `anlik`,
  `politika`, `kalibrasyon`, `hikaye_sec`) `perakende_veri`'yi, `replenishment.motor`'u ve hakemi
  içe aktarmaz; politika yalnız `Gorunum`'ü ve dünyanın açık alanlarını okur
  (`tests/test_sizinti.py`, bozma testi dahil). Kalibrasyon oyun penceresine hiç bakmaz; LightGBM
  oyun sezonunun ilk lansmanından önce biter.
- **Kollar arası gürültü yok.** Aynı tohumda koşu birebir tekrarlanır; kollar yalnız pencere
  içindeki replenishment'ı değiştirir. Pencere dışında kol sardığı Lumoda kuralını aynen döndürür.
- **Eşdeğerlik.** `lumoda_kisitsiz` (Lumoda + kaydediciler) yayımlanan v4'ü birebir üretir
  (`tests/test_esdegerlik.py`); `ilk_alim_orani=1.0` varsayılanı 18 tabloyu bayt bayt korur.
- **Motor isteği kesmez.** Kısıtlı her kolun kaydı motorun sevkiyatıyla birebir
  (`sevkiyatla_karsilastir` boş); değilse koşu geçersizdir.

## Bilinen sınırlar

- **Eşit stokta kalan fark açıklanmadı.** Lumoda aynı kısıtta kuraldan +8,77 puan önde; +5,45'i
  stok düzeyinden, eşit stokta +3,32 kalıyor (NOS ve Basic'te, pencerenin ikinci yarısında).
  "Plan yeni lansmanı bilir" hipotezi tutmadı. Aday mekanizma (Lumoda'nın beden düzeyinde istemesi;
  kırık çift %58,9'a karşı %69,5) ölçülmedi.
- **Lumoda planının isabeti ölçülmedi.** Lumoda'nın kuralı plana dayanır; planın bu pencerede ne
  kadar tuttuğu raporda yok.
- **İlk dağıtım bütün kollarda Lumoda'nındır**: yeni dalgaların ilk sevki karşılaştırmanın dışında.
- **LightGBM yol başına bir kez eğitilir**, sezon içinde yeniden eğitilmez; hiperparametreler
  daha önceki bir denemeden, bu veride yeniden aranmadı. Eğitim satırları hedef haftasında en az bir
  stoklu günü olanlar (R18-C): stoksuz haftalarda model iyimser olabilir.
- **C kuralı kalibre edilmedi** (R27); α'nın 0,4'ün altı denenmedi (R26). 1-2-2-1-1 kolide β 3 ile
  A'nın beden fazlası koşulu hiç bağlamaz (R38).
- **Sansür düzeltmesinin sonuç etkisi ölçülmedi** (düzeltmesiz kural koşusu ızgarada yok); yalnız
  hedefe etkisi (+%5,3) basılır.
- **Gölge defter uzlaştırma kalemleri.** Kalite reddi, iadeler, açılış transferleri ve sezon sonu
  `stok_devri` kaydedicisiz: "açıklanamayan" kalemlerde görünür; aynı hafta aynı SKU'daki artı ve
  eksi akışlar netleşir, kalemler brüt akışın alt sınırıdır.
- **Bulunabilirliğin ikame yanlılığı** (R27, yukarıda) ve kırık çiftin tek fotoğrafa bağlı olması.
- **Alternatif yollar yalnız talep tohumunu değiştirir**; kalibrasyon yol 0'ınkidir, yol başına
  yeniden seçilmez. p > 0 yollarında yeniden kurulan DuckDB'nin yayımlananla eşitliği ayrıca
  denetlenmez (yol 0 eşdeğerlik testiyle kilitli).
- Toplama maliyetleri, açık payı ve tavan oranı varsayımdır; rapor açık adet maliyetine
  duyarlılığı basar.
- `motor.py` ve `anlik.py` RPT'nin kopyalarıdır (R1); iki kopyanın bakımı ayrı.
