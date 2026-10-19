# Allocation — ilk sevkiyat

Lumoda v4 sentetik verisi ve v4 motoru üstünde ilk sevkiyat (initial allocation) vakası: yeni bir
sezonun dalgası mağazalara ilk kez dağıtılırken, depoda ne kadarının tutulacağı ve kalanın hangi
mağazaya, hangi pakete gideceği. Sitedeki `/allocation/ilk-sevkiyat/` dizisinin (6 yazı) ve demo
kadranının bütün sayıları buradan, `cikti/rapor.txt`'ten çıkar (`cikti/` git dışıdır; dosyayı
`rapor.py` yeniden üretir, aşağıdaki 6. adım). Tasarım:
`docs/superpowers/specs/2026-10-19-ilk-sevkiyat-design.md` (`docs/` ayrı depodur); uygulamadaki
sapmalar ve kararlar o belgenin §12'sinde (Ruling R1–R50).

İlk sevkiyat burada **bir dalganın ilk dağıtımıdır**: depoya gelen malın ne kadarının satış
görülmeden mağazalara paket paket gideceği. Karar dalga başına tek seferdir; kollar yalnız bu kararı
değiştirir. Lumoda'nın bugünkü kuralı taban çizgisidir: option'ın ilk alımının %70'i, mağazanın
planındaki (sezon × üst kategori) satış hedefi payıyla, en büyük kalanla. Karşılaştırılan kollar:
eşit dağıtım, benzer ürün (kural tabanlı), LightGBM, kahin (gerçek erken talebi bilen üst sınır);
kapsama tavanı, depoda tutma ve belirsizliğe göre tutma bu kollara eklenen ayarlardır. Oyun sezonu
SS25, line Collection, 210 option, üç dalga.

## Kurulum

    cd vakalar/allocation
    python -m venv .venv
    .venv/Scripts/pip install -e ../ortak              # perakende_analitik (kaynak, stok, sayı denetimi)
    .venv/Scripts/pip install --no-deps -e ../../veri  # perakende_veri (v4 motoru; yalnız allocation/motor.py açar)
    .venv/Scripts/pip install -e ".[dev]"

Kütüphaneler pinlidir (`pyproject.toml`): `lightgbm` < 4.6 (Windows çökmesi) ve `scikit-learn` < 1.8
(`force_all_finite`); kurulu sürümler lightgbm 4.5.0, scikit-learn 1.7.2, numpy 2.5.4, pandas 2.3.3,
duckdb 1.5.6, pyarrow 26.0.0. Sürümler koşu önbelleğinin anahtarındadır.

**Veri.** `veri/cikti/v4/perakende.duckdb` (ya da `PERAKENDE_V4_DB`) ve Parquet kopyası
`veri/cikti/v4/parquet/` (testler yayımlanan 18 tabloyu bununla karşılaştırır; `PERAKENDE_V4_PARQUET`
ile değiştirilebilir). Yoksa yayımlanan `veri-v4` dosyalarını indirin ya da
`cd veri && python -m perakende_veri.v4.uret`. Hakem önbelleği gerekmez: gizli gerçek her koşunun
kendisinden okunur; yayımlanan dünya `lumoda` koşusunun kendisidir.

## Koşum

Bütün komutlar `vakalar/allocation` içinden, vakanın `.venv`'iyle.

- **Ortam:** Windows konsolunda `PYTHONIOENCODING=utf-8` (Türkçe karakter).
- **Sıralı:** koşu önbelleği eşzamanlı yazmaya güvenli değil. Aşağıdaki komutlardan ikisini (rapor ve
  testler dahil) aynı anda koşmayın; RPT ve DM vakalarının koşularıyla da aynı anda koşmayın (bellek).
- **Makine uyanık kalmalı:** `oyun` kendisi `SetThreadExecutionState` ile uykuyu engeller
  (`uyanik_tut`); yarıda kalan ızgara aynı komutla kaldığı yerden sürer (`cikti/ilerleme.jsonl`).
- **Kaynaklar:** bir TAM koşu tepe ~8 GB bellek; `cikti/kosular/` 70 dizin, ~11 GB (bayat anahtarlı
  dizinler dahil). TAM koşu başına motor ~150–200 sn.

Sıra ve ölçülen süreler:

    # 1. Kalibrasyon (~1.150–1.413 sn; SS24, oyun sezonuna bakmaz): koşusuz seçimler ~1 dk (69,2 sn),
    #    7 TAM kol koşusu + önbellekli lumoda; cikti/kalibrasyon.json
    .venv/Scripts/python -m allocation.oyun kalibrasyon

    # 2. Oyun ızgarası (4.575 sn + R46'nın iki tavansız sabit takvim koşusu 646 sn):
    #    yol 0 için 37 ad, 34 TAM koşu; cikti/oyun.json, cikti/secim.json
    .venv/Scripts/python -m allocation.oyun izgara             # --blok pay | --ad <koşu> ile parça parça

    # 3. Yollar (5.809 sn): yol 1–4 için Lumoda koşusu, endeks ve LightGBM yeniden öğrenme,
    #    benzer / tahmin tavansız ve esit, kahin; yol 0 ızgaradan; cikti/yollar.json
    .venv/Scripts/python -m allocation.yollar

    # 4. Hikâye sahnesi (yalnız önbellekten okur): cikti/hikaye.json
    .venv/Scripts/python -m allocation.hikaye_sec              # --hikaye OPTION, --adaylar

    # 5. Demo kadranı (yalnız önbellekten): site/src/data/senaryolar/ilk-sevkiyat.json
    .venv/Scripts/python senaryolar.py

    # 6. Rapor (~51 sn; motor koşmaz, önbellekten; korunum tutmazsa stdout boş, çıkış 1)
    .venv/Scripts/python rapor.py > cikti/rapor.txt            # --taslak: eksik koşuyla biçim denetimi, çıkış 2

    # 7. Yazılardaki her sayı raporda mı (çıkış 0; birkaç saniye)
    .venv/Scripts/python -m perakende_analitik.sayi_denetimi \
        --yazi ../../site/src/content/yazi/allocation/ilk-sevkiyat --rapor cikti/rapor.txt

Bu süreler toplamı sıfırdan yaklaşık 12.200 sn (~3,4 sa). Izgara sırası önemlidir: bloklar `esdegerlik`
→ `pay` → `eslesik` → `sabit_takvim` → `tutma` → `strateji` → `demo`; sonrakiler pay bloğunun
seçtiği "en iyi" kola (`cikti/secim.json`) bakar. Çözümü aynı olan iki ad bir kez koşulur (Ruling R30;
ikinci ad `ayni` takma adıdır). Yollar ızgaranın pay bloğundan sonra koşulur. Rapor demo dosyasını da
denetler, bu yüzden `senaryolar.py` rapordan önce koşar; JSON'a `surum` olarak HEAD'in kısa SHA'sı
yazılır. Aynı girdiyle iki rapor bayt bayt aynıdır.

Testler: `.venv/Scripts/python -m pytest -q -m "not veri"`; `veri` işaretli testler gerçek v4 dosyasını
ve TAM dünyayı kurar (yavaş: iki eşdeğerlik testi önbellekten ~590 sn; `lumoda` ve sabit takvimde
`lumoda_takvimli` yayımlanan 18 tabloyla birebir).

## Önbellek katmanları

| Katman | Yer | Anahtar | Değişince |
|---|---|---|---|
| Motor koşuları | `cikti/kosular/<ad>_<anahtar[:20]>` | `ad`, `parametreler` (kanonik JSON), politika türü ve kimliği (kolun `Ayar`'ı, sardığı Lumoda kuralı, endeks / LightGBM kimliği), talep ve operasyon tohumu, ölçek, gün sayısı, `motor.kod_ozeti`, v4 dosyasının parmak izi (ad, boyut, mtime), kütüphane sürümleri | yeni anahtar, yeni koşu (eskisi diskte kalır) |
| Kalibrasyon | `cikti/kalibrasyon.json` | yok (her `oyun kalibrasyon` yeniden yazar; koşular önbellekten) | seçilen değerler kolların `Ayar`'ına, oradan bütün koşu anahtarlarına girer |
| Oyun ölçümleri | `cikti/oyun.json`, `cikti/secim.json` | kayıt başına koşu anahtarı + `olcum_kodu` (`olcutler.py` ve `kalibrasyon.py` özeti, `OLCUM_SURUMU`) | `oyun izgara` tutmayan kaydı yeniden ölçer (koşu önbellekten); rapor eski ölçümü reddeder |
| Yollar | `cikti/yollar.json` | yol başına `yollar.kod_ozeti` (koşu kod özeti, v4 parmak izi, `olcutler.py` + `oyun.py` + `kalibrasyon.py` + `yollar.py` özeti) + koşu anahtarları | `yollar` tutmayan yolu yeniden ölçer / hesaplar |
| Hikâye | `cikti/hikaye.json` | oyun.json'daki koşu anahtarları | `hikaye_sec` yeniden yazar; rapor anahtar uyuşmazlığını reddeder |

**Koşu anahtarına girenler kasıtlı dar.** `motor.KOSU_MODULLERI` = `motor`, `sabitler`, `kaynak`,
`ogrenme`, `benzer`, `tahmin`, `paylastir`, `politika`; `KOSU_DISI` = `olcutler`, `oyun`, `yollar`,
`hikaye_sec`, `senaryolar`, `kalibrasyon`. Vaka kökündeki `rapor*.py` ve testler de dışarıda.
`allocation/`'daki her modül iki listeden birindedir (`tests/test_motor.py`). Koşu kod özeti ayrıca
`KOSU_MODULLERI`'nin ortak paket kapanışını (`vakalar/ortak/`) ve `perakende_veri/v4/**/*.py`'yi
kapsar. Ölçümün sonucu politikaya yalnız `parametreler` / `Ayar` üstünden girer (kalibrasyon, R22–R23).

**Kod değişince ne olur, elle ne silinir:**

- `KOSU_MODULLERI`'nden bir dosya, ortak paketin kapanışı ya da `veri/`'deki v4 kodu değişirse
  hiçbir şey silmeyin: bütün anahtarlar kendiliğinden değişir ve ızgara baştan koşar. Bu yüzden
  karar modüllerinin düzeltmeleri ızgaradan ÖNCE yapılır (R7, R20). `vakalar/ortak/` ya da
  `perakende_veri/v4` değişikliği RPT ve DM önbelleklerini de geçersiz kılar. Eski koşu dizinleri
  `cikti/kosular/`'da kalır; yer açmak için elle silinebilir.
- **v4 dosyasının mtime'ı anahtardadır.** Dosyayı yeniden indirmek, kopyalamak ya da `touch` etmek
  (içerik aynı olsa da) bütün koşuları geçersiz kılar.
- `olcutler.py` ya da `kalibrasyon.py` değişirse: `oyun izgara` (yeniden ölçüm, koşu yok), `yollar`,
  sonra 4–7.
- `oyun.py` ya da `yollar.py` değişirse: `oyun.py` yollar'ın kod özetindedir ama oyun.json'un ölçüm
  kodunda yoktur; yalnız yollar yeniden ölçülür, sonra 6–7. `oyun.py`'deki ızgara tanımı değişirse
  `oyun izgara` eksik koşuları koşar.
- `hikaye_sec.py` değişirse 4. adım, sonra 6–7; `senaryolar.py` değişirse 5–7; `rapor.py` /
  `rapor_b.py` değişirse yalnız 6–7.

## Tanımlar

Ayrıntı `allocation/olcutler.py`'nin modül notunda; ölçütler yüzde, `pay_wape` 0–1.

- **Pencere ve kapsam.** Option `o` için pencere `[b_o, c_o)`: `b_o` option'ın ilk dağıtımının
  mağazaya ilk varış günü, `c_o` çıkış günü (outlet akışı başlar; hariç). Fiziksel mağaza = Online ve
  Outlet tipi hariç. Kapsam oyun sezonunun Collection option'larıdır; online ayrı satırlarda.
- **Bulunabilirlik.** Fiziksel mağaza hücrelerinde, pencerede, talepli hücre-günlerin kendi satışı
  olan payı: |talep > 0 ∧ kendi_satis > 0| ÷ |talep > 0| (DM R22). `bulunabilirlik_ilk4` aynısı
  varıştan ilk 28 günde. Küçük bir yanlılığı vardır (DM R27): `kendi_satis` gelen ikame satışını
  düşer; yanlılık bütün kollarda aynı yöndedir.
- **Erken pencere.** Her (fiziksel mağaza, option) için ilk dağıtım varışından 42 gün; sezonun
  indirim başlangıcından 29 gün önce kesilir (SS25: 2025-06-01; SS24: 2024-06-02, Ruling R5).
  Kahinin girdisi, benzer endeksi ve LightGBM'in hedefi bu pencerenin (stoksuz günler sansür
  düzeltmeli) birincil talebidir. `pay_wape` = option başına mağaza payı (ilk dağıtım adedi) ile erken
  birincil talep payı arasında Σ|fark| ÷ 2, ilk alımla ağırlıklı.
- **`U` ve `t`.** `U` = min(Lumoda'nın kuralı, depodaki en dar bedenin paket sayısı), paket cinsinden:
  kural ⌊ilk alım × 0,70 ÷ paket adedi⌋ (Lumoda'nın kayan nokta ifadesi, R11). Tutma oranı `t`
  `U`'ya göredir: kol ⌊U × (1 − t)⌋ paket gönderir, kalanı depoda kalır. `t = 0` Lumoda'nın fiilî
  hâlidir ve kollar için üst sınırdır; Lumoda'nın kendi "%30 tutuyoruz"u ilk alıma göredir ve U'ya
  göre `t = 0`'a denk gelir (R27). Koli açılmaz: ilk sevkiyatın birimi pakettir (standart 1-2-2-1-1 =
  7 adet; aksesuar tek beden 6 adet; içerik dünyanın açık `paketler` alanından).
- **Sezon sonu kalan.** 100 × (kalan mağaza + kalan depo) ÷ toplam mal; toplam mal = teslim edilmiş
  ilk alım + RPT − kalite reddi. Kalan = çıkışta mağazalardan ve depodan outlet'e akan + çıkıştan
  sonra depoda kalan (`kalan_depo_ek_adet`: çıkış sonrası depoya eklenen stok devri, RPT varışı,
  online iadesi). Çıkıştan önceki stok devri (sezon içinde kapanan mağaza) kalan sayılmaz (R31).
  Tutma kolları depoda mal bırakır; o mal çıkışta outlet akışıyla kalana girer.
- **Tam fiyat STR.** v4 kalibrasyon tanımı: kampanyasız, pozitif, ilk markdown haftasından önce
  satılan adet ÷ teslim alınan ilk + RPT sipariş adedi; fiyat hattı hücreden (R32).
- **Markdown TL ve brüt kâr.** `markdown_tl` brüt indirim tutarıdır: kampanyasız satış satırlarının
  `indirim_tutari`'sı, option'ın o hattaki haftalık markdown oranı sıfırdan büyükken. Kampanya ve
  işlem indirimi girmez. `brut_kar_tl` net satış − alış maliyetidir (iade satırları dahil). İkisi
  toplanmaz; rapor ikisini yan yana basar.
- **Beden.** Kırık çift, beden kaybı payı, depoda kalan beden ve ilk tükenen beden (DM R29 tanımı);
  `alimdan_kalan_beden_b` ilk alıma göre gönderilmeyen payı, `depoda_kalan_beden_b` depoda fiilen
  duranı gösterir (R33).
- **Korunum.** Her kol koşusu: satış ≤ talep, motor kollarda paket kırpmaz (`kirpilan_adet` = 0),
  `t = 0`'da ilk dağıtım + tavanın bıraktığı = U, kahinin bağımsızlığı. Rapor 165 denetimi basar.

## Sahne

1. yazının sahnesi (spec §6; seçim `hikaye_sec`, yürütücünün, kullanıcı yetki verdi):
**MDL0553-IND Bodycon Elbise İndigo** (Elbise & Tulum), merdivenin 0. basamağı (gevşeme yok). İzmir 4
(M029) option'ın 4.368 adetlik ilk dağıtımından 448 adet aldı (%10,3, en büyük pay), varıştan 28
günde 33 sattı (%7,4); planda SS25 Elbise & Tulum hedefinin fiziksel mağazalar arasında 1. sırası.
Erzurum 2 (M069) 112 adet aldı, 14 günde 102 sattı (%91,1). Kol (`pay_tahmin_tavansiz`, yalnız karar
öncesi bilgiyle) İzmir 4'e 119, Erzurum 2'ye 609 adet gönderirdi. Sahnenin adedi mağazaya varan ilk
dağıtımdır (R35).

**Alternatif:** MDL0564-KRM Regular Fit Gömlek Kiremit (basamak 1; "28 günde satış ≤ %20" gevşedi):
taşan Antalya 3 (539 adet, 28 günde 63 satış, kol 189), biten Van 2 (140 adet, 14 günde 162 satış, kol 322).

    .venv/Scripts/python -m allocation.hikaye_sec --hikaye MDL0564-KRM    # sonra 6–7; yazı 1'in sahne sayıları

## Modüller

| Modül | İşi |
|---|---|
| `sabitler.py` | Sezonlar, line, `LUMODA_ILK_PAYI`, erken pencere, tutma düzeyleri, tavan kapsaması, `hiz` pencereleri, yol sayısı, tohum tabanı |
| `motor.py` | Üretecin tek kapısı (vakada `perakende_veri`'yi yalnız bu modül içe aktarır): `dunya`, `kos` → `Kosu` / tembel `KosuKaydi`, `Kaydedici`, koşu önbelleği, `lumoda(...)`, `kirpma_tablosu`, `Takvim` |
| `kaynak.py` | Yayımlanan v4'ten okuma, fiziksel mağazalar (Ali / Veli), günlük satış ve stoklu matrisler, `Harita` (hücre ↔ mağaza, option, SKU) yalnız dünyanın açık alanlarından |
| `ogrenme.py` | Geçmiş sezonların sansür düzeltmeli erken talebi ve öğrenme tablosu |
| `benzer.py` | Benzer ürün endeksi: açık öznitelik hiyerarşisi, `en_az` eşiği |
| `tahmin.py` | LightGBM (Poisson), mağaza × option erken talep tahmincisi; içerikten kimlik |
| `paylastir.py` | Paket içeriği, `U`, aday maskesi, kapsama tavanı, en az gösterim, paylaştırma |
| `politika.py` | Kollar (`LumodaTutKol`, `EsitKol`, `BenzerKol`, `TahminKol`, `KahinKol`, `BelirsizlikKol`), `hiz` replenishment'ı, sabit takvim yeniden oynatıcıları |
| `kalibrasyon.py` | SS24'te koşusuz seçimler (`en_az`, LightGBM parametreleri, belirsizlik ölçüsü) ve simülasyon seçimleri (tavan, taban, γ); koşu enjekte edilir (motoru görmez) |
| `olcutler.py` | Koşu ölçütleri, `Kapsam` (option → SKU eşlemesi), erken birincil talep |
| `oyun.py` | CLI: `kalibrasyon`, `izgara`; `IZGARA`, "en iyi" seçimi, `kos_bir`, `uyanik_tut` |
| `yollar.py` | 5 talep yolu, "kaç yolda önde"; `cikti/yollar.json` |
| `hikaye_sec.py` | Sahne merdiveni, alternatif; `cikti/hikaye.json` |
| `rapor.py`, `rapor_b.py` | Yayımlanacak her sayı; başlık soruları ilgili bölümde `SORU n · …` satırı; `rapor_b` veri sorgularını ve korunumları kurar |
| `senaryolar.py` | Demo kadranının JSON'u (12 bileşim, yalnız önbellekten) |

## Kollar ve ayarlar

Pay kaynağı: `esit` (aday mağazalara eşit), `benzer` (mağazanın geçmiş payı; hiyerarşi `en_az = 80`),
`tahmin` (LightGBM), `kahin` (gerçek erken talep), `lumoda_tut` (Lumoda'nın plan payı, tutma ekseni için).
Ayarlar: kapsama tavanı (öngörülen erken talebin katı), `t` (sabit ya da option başına
`belirsizlik`), replenishment (Lumoda ya da `hiz`).

`benzer` benzerliği en özelden en genele hiyerarşiyle kurar (`benzer.HIYERARSI`):

| düzey | eşleşen öznitelikler |
|---|---|
| 0 | alt kategori × fiyat segmenti × kalıp |
| 1 | alt kategori × fiyat segmenti |
| 2 | alt kategori |
| 3 | üst kategori |
| 4 | mağazanın bütün geçmiş Collection'ı |

Seçilen düzey, yeni option'la bütün sütunlarında eşleşen en az `en_az` geçmiş option'ı olan ilk
düzeydir; SS option'ları yalnız SS sezonlarından öğrenir (`mevsim="SS"`, R9). Kalibrasyon `en_az` için
{3, 5, 10, 20, 40, 80} ızgarasında 80'i seçti; pay WAPE'si 40'tan sonra düzleşir (0,235 → 0,235) ve
seçim ızgaranın ucunda kaldı (R24, R25). `hiz` replenishment'ı: son 14 günün stoklu gün hızı × 28 gün,
kapısız (ölü stok kapısı yok); son 14 günde hiç stoklu gün yoksa hız option'ın ilk dağıtımından bu yana
(R16); kapanış kararı verilmiş mağazaya kapanışa dek gönderir (Lumoda gibi).

## Kalibrasyon

SS24'te, oyun sezonuna (SS25) bakmadan (spec §4.1): koşusuz seçimler SS23'le öğrenip SS24
Collection'ın ilk 6 haftasına karşı pay WAPE'siyle; simülasyon 7 TAM koşuyla. Seçimler: `en_az` 80,
LightGBM 63 yaprak × yaprakta en az 100 örnek, belirsizlik ölçüsü `benzer_tahmin_ayrisma` (Spearman
0,107: sinyal zayıf), kapsama tavanı açık, belirsizliğin tabanı tahmin, γ 2,0 (üç γ'nın bulunabilirliği
0,03 puan içinde; seçim sezon sonu kalanla). Izgaralar kenarda kalan seçimler için bir kez genişletildi
(R24). Kalibrasyonun iki ölçütü oyunun ölçütleriyle tek tanımdır (`olcutler.py`). Oyunun "en iyi" kolu
SS25'te, tavansız benzer ve tahmin arasından seçilir (R43): bu, tutma ve strateji ölçümlerinin örneklem
içi olduğu anlamına gelir; rapor ve yazılar bunları örneklem dışı karar diye sunmaz.

## İlkeler

- **Sızıntı yok.** Karar modülleri (`kaynak`, `ogrenme`, `benzer`, `tahmin`, `paylastir`, `politika`,
  `kalibrasyon`, `hikaye_sec`) `perakende_veri`'yi, `allocation.motor`'u ve hakemi içe aktarmaz;
  politika yalnız `Gorunum`'ü ve dünyanın açık alanlarını okur (`tests/test_sizinti.py`, bozma testi
  dahil). Kahinin girdisi `parametreler` üstünden gelen ölçülmüş dizidir (R4). Kalibrasyon oyun
  sezonuna hiç bakmaz.
- **Kollar arası gürültü yok.** Aynı tohumda koşu birebir tekrarlanır; kollar yalnız ilk dağıtım
  kararını değiştirir. Motor kollarda paket kırpmaz; Lumoda'nın kararını kırpar (aşağıda).
- **Eşdeğerlik.** `lumoda` (Lumoda + kaydediciler) yayımlanan v4'ü birebir üretir
  (`tests/test_esdegerlik.py`); sabit takvimde `lumoda_takvimli` aynı 18 tabloyu ve gizli gerçeği
  yeniden üretir.
- **`veri/` ve `vakalar/ortak/` salt okunur** (RPT ve DM önbellek anahtarları).

## Bilinen sınırlar

- **"Benzer ürün" fiilen kaba.** En iyi `en_az` ızgara ucunda (80) çıktı; oyunda option'ların 143'ü
  üst kategori düzeyinde, 67'si bütün Collection düzeyinde eşleşiyor (daha ince düzey 0). Kol pratikte
  "mağazanın geçmiş payı" kuralıdır; demo kadranı da böyle etiketler (R25).
- **γ tavanlı tabanda seçildi.** Belirsizliğin γ'sı SS24'te tavanlı tahmin tabanıyla kalibre edildi;
  oyunda taban tavansız (R43). γ'ların bulunabilirlik aralığı kalibrasyonda 0,03 puandı; seçim bu
  tabana taşınabilir sayıldı, yeniden sınanmadı.
- **Sezon içi okuma yok.** Karar dalga başına tek sefer ve satış görülmeden verilir; kollar erken
  satışı okuyup düzeltmez. Replenishment, RPT ve markdown Lumoda'nın tepkili kararıdır; `hiz` bu
  vakanın basit bir kuralıdır (stoklu gün hızı), kalibre edilmiş bir replenishment politikası değil.
- **Transfer simüle edilmez.** Kollar mağazalar arası transfer kararı vermez; `elle_transfer_adet`
  yalnız Lumoda'nın kararlarının sonucunu ölçer.
- **Tek sezon.** Oyun SS25 (üç dalga), kalibrasyon SS24. "En iyi" kol, tutma ve strateji SS25'te
  seçilir ya da ölçülür (R29, R43). Öğrenme SS25 kararı için SS23 ve SS24'ten, kalibrasyon için yalnız SS23'ten gelir.
- **Yollar yalnız müşteri akışını değiştirir.** Ürün sürprizleri (λ), dünya ve operasyon çekilişleri
  aynıdır; kalibrasyon yol 0'ınkidir, yol başına yeniden seçilmez. Yollarda tavan ve sabit takvim
  etkisi ölçülmez (R44); tavan etkisi yol 0'da eşleşik koşularla ölçülür.
- **Varış günü kapalı mağaza modellenmez (R21).** SS25 ve SS24 lansmanlarında kapalı ya da tadilatlı
  mağaza yok; her TAM koşuda oyun option'larına süzülmüş `kirpma_tablosu`'nun boş olduğu iddia edilir.
  Başka bir sezonda kollar sessizce paket kaybedebilir (assert yakalar).
- **Lumoda'yı motor kırpar.** Lumoda'nın kararı depodaki SKU'lara sığmaz: 177 / 210 option, 1.791
  (option, mağaza), 2.051 paket, 14.357 adet (gönderilenin %1,7). Kollar kendilerini `U`'ya sığdırır
  (`U` 824.165 adet = Lumoda'nın fiilen gönderdiği); spec'teki 179 / 210 ölçümde 177'dir (R6).
- **Benzer ve LightGBM hedefi stoklu gün hızıyla sansür düzeltir** (R3): koşullu Poisson (Basit)
  düzeltmesi yok; stoksuz başlayan hücrelerde öngörü biraz düşük. LightGBM `ilk_alim`'ı özellik olarak
  kullanır (R13); model buyer'ın yanılgısını da öğrenir. İleri zamanlı tahmin düşük kalır.
- **Beden uyumsuzluğu ve tek paket.** Paket tek (1-2-2-1-1); aksesuar tek beden. Kırık çift ve beden
  kaybı pencere sonu fotoğraflarına bağlı ölçütlerdir.
- **Tutma online'ı da değiştirir.** Aynı depodan online satar; tutmanın bulunabilirlik kazancı fiziksel
  mağazalardadır, brüt kâr ve tam fiyat STR online'ı da içerir (`online_satis` ayrı sütun).
- Kayıtlı sapmalar için bkz. spec §12.1 (Ruling R1–R50).
