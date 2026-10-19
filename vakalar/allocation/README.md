# Allocation — ilk sevkiyat

Lumoda v4 sentetik verisi ve v4 motoru üstünde ilk sevkiyat (initial allocation) vakası:
yeni bir sezonun dalgası mağazalara ilk kez dağıtılırken, depoda ne kadarının tutulacağı ve
kalanın hangi mağazaya, hangi pakete gideceği. Tasarım:
`docs/superpowers/specs/2026-10-19-ilk-sevkiyat-design.md` (`docs/` ayrı depodur). Bu dosya
iskelettir; koşum sırası, süreler ve çıktılar vakanın son görevinde tamamlanır.

## Kurulum

    cd vakalar/allocation
    python -m venv .venv
    .venv/Scripts/pip install -e ../ortak              # perakende_analitik (kaynak, stok, sayı denetimi)
    .venv/Scripts/pip install --no-deps -e ../../veri  # perakende_veri (v4 motoru)
    .venv/Scripts/pip install -e ".[dev]"

Veri `veri/cikti/v4/perakende.duckdb` (ya da `PERAKENDE_V4_DB`); yoksa yayımlanan `veri-v4`
dosyasını indirin ya da `cd veri && python -m perakende_veri.v4.uret`.

`lightgbm` < 4.6 ve `scikit-learn` < 1.8 sabit (Windows çökmesi ve `force_all_finite`;
`pyproject.toml`'daki not).

## Koşum

Bütün komutlar `vakalar/allocation` içinden, vakanın `.venv`'iyle; Windows konsolunda
`PYTHONIOENCODING=utf-8`.

- **Sıralı koş:** v4 koşu önbelleği eşzamanlı yazmaya güvenli değil. Vakanın iki komutunu
  (testler dahil) aynı anda koşmayın; RPT ve DM vakalarının koşularıyla da aynı anda koşmayın
  (TAM bir koşu tepe ~8 GB bellek).
- Hızlı testler: `.venv/Scripts/python -m pytest -q -m "not veri"`. `veri` işaretli testler
  gerçek v4 dosyasını ve TAM dünyayı kurar (yavaş).

## Benzer ürün hiyerarşisi

`benzer` kolu yeni bir option'ın mağaza payını, ona benzeyen geçmiş Collection option'larının o
mağazadaki göreli hızından alır (`allocation/benzer.py`). Benzerlik açık öznitelik hiyerarşisiyle,
en özelden en genele (`benzer.HIYERARSI`):

| düzey | eşleşen öznitelikler |
|---|---|
| 0 | alt kategori × fiyat segmenti × kalıp |
| 1 | alt kategori × fiyat segmenti |
| 2 | alt kategori |
| 3 | üst kategori |
| 4 | mağazanın bütün geçmiş Collection'ı |

Seçilen düzey, yeni option'la bütün sütunlarında eşleşen en az `en_az` geçmiş option'ı olan ilk
düzeydir; o düzeyde gözlemi olmayan mağaza bir üst düzeye düşer. SS option'ları yalnız SS
sezonlarından öğrenir (`mevsim="SS"`). **Eşik `en_az = 80`** (kalibrasyonun seçimi, aşağıda; SS23'te 210
Collection option'ı var). Pay WAPE'si eşik büyüdükçe düşer ve 40'tan sonra düzleşir (0,2350 →
0,2347); seçim ızgaranın ucunda kaldı (Ruling R24).

## Kalibrasyon

    .venv/Scripts/python -m allocation.oyun kalibrasyon      # cikti/kalibrasyon.json (~20 dk)

SS24'te, oyun sezonuna (SS25) bakmadan (`allocation/kalibrasyon.py`, spec §4.1):

- **Koşusuz** (~1 dk): SS24'ün ilk karar gününde (2024-02-09) kapanmış tek Collection sezonu SS23'le
  öğrenilir, SS24 Collection'ın yayımlanan veriden ölçülen ilk 6 hafta payına karşı mağaza payı
  WAPE'si (ilk alım ağırlıklı) ile seçilir: `benzer`'in eşiği (`en_az` ∈ {3, 5, 10, 20, 40, 80} →
  80), LightGBM'in `num_leaves` ∈ {15, 31, 63, 127} × `min_child_samples` ∈ {20, 50, 100, 200}
  (→ 63, 100), belirsizlik ölçüsü (kaynağın option WAPE'siyle Spearman'ı en yüksek:
  `benzer_tahmin_ayrisma`, ρ ≈ 0,11; sinyal zayıf). Izgaralar R24 ile genişletildi: ilk
  ızgaranın seçimleri uçtaydı, uçta kalan yönde bir kez daha uzatıldı ve orada durdu.
- **Simülasyon** (7 TAM koşu + önbellekli `lumoda`, ~18 dk): `benzer` ve `tahmin` tavanlı /
  tavansız; en iyisi (sezon boyu bulunabilirlik, 0,3 puandan yakınsa daha az sezon sonu kalan)
  kapsama tavanını (açık) ve belirsizliğin tabanını (`tahmin`) verir; `belirsizlik` γ ∈ {0,5; 1; 2}
  → 2. Üç γ'nın bulunabilirliği 0,03 puan içinde (eşitlik bandı 0,3): γ sezon sonu kalanla seçildi,
  eğri dikliği SS24'te pratikte etkisiz.

Seçimler, WAPE'ler ve koşu ölçütleri `cikti/kalibrasyon.json`'da; oyun ızgarası değerleri oradan
okur. Kalibrasyonun iki ölçütü (bulunabilirlik, sezon sonu kalan) oyunun ölçütleriyle tek tanımdır
(`allocation/olcutler.py`).

## Oyun ızgarası

    .venv/Scripts/python -m allocation.oyun                      # bütün bloklar sırayla (cikti/oyun.json)
    .venv/Scripts/python -m allocation.oyun izgara --blok pay    # tek blok; --ad <koşu> yalnız o koşu
    .venv/Scripts/python -m allocation.yollar                    # 5 talep yolu (cikti/yollar.json)

Oyun sezonu SS25'in Collection option'ları (`allocation/oyun.py`, spec §4.5). Bloklar bu sırayla koşar,
çünkü sonrakiler pay bloğunun seçtiği "en iyi" kola bakar (`cikti/secim.json`): `esdegerlik`
(`lumoda`, yayımlanan v4'ün kendisi) → `pay` (esit, benzer ve tahmin tavanlı / tavansız, kahin; t =
0) → `sabit_takvim` (lumoda'nın RPT ve markdown kararlarıyla) → `tutma` (t ∈ {0; 0,15; 0,30; 0,45}
× {lumoda_tut, en iyi} × replenishment {Lumoda, hiz}) → `strateji` (belirsizlik, t̄ = %30) → `demo`.
Çözümü aynı iki koşu adı (ör. demo'daki en iyi kol ile tutma ekseninin aynı noktası) bir kez
koşulur. Koşular sıralı ve önbellekli (`cikti/kosular/`, koşu başına ~150 MB); yarıda kalan ızgara
aynı komutla kaldığı yerden sürer (`cikti/ilerleme.jsonl`), makine uyumaz. Yollar ızgaranın pay
bloğundan sonra koşulur (yol 0 onun koşularıdır).

**Ölçütlerin tanımları** `allocation/olcutler.py`'nin modül notunda: bulunabilirlik (sezon boyu ve ilk
4 hafta), kayıp, tam fiyat STR (v4 kalibrasyon tanımı), markdown tutarı, sezon sonu kalan, brüt
kâr, düzeltme yükü (replenishment, elle transfer, RPT), dağıtım isabeti (erken birincil talep
payına karşı WAPE, oturan ve hızlı biten hücre), beden ölçütleri (kırık çift, beden kaybı, depoda
kalan beden (depodaki stoğa ve ilk alıma göre) ve ilk tükenen beden) ve korunum. **Markdown tutarı** yalnız markdown kaynaklı indirimdir:
kampanyasız satış satırlarının `indirim_tutari`'sı, option'ın o hattaki haftalık markdown oranı
sıfırdan büyükken. Kampanya indirimi (kampanya oranı markdown'ı aşınca satır kampanyalıdır) ve
işlem indirimi (yalnız markdown ve kampanya 0 iken çıkar) girmez.

`hiz` replenishment'ı kapanış kararı verilmiş mağazaya kapanışa dek gönderir (Lumoda'nın kuralı
gibi; `allocation/politika.py`).

## Hikâye

    .venv/Scripts/python -m allocation.hikaye_sec                       # cikti/hikaye.json
    .venv/Scripts/python -m allocation.hikaye_sec --hikaye OPTION --adaylar

1. yazının sahnesi (spec §6): ızgaranın `lumoda` koşusundan ve en iyi kolun (`cikti/secim.json`)
koşusundan, önbellekten okunur (koşu yapmaz). Merdiven, gevşetme sırası ve tanımlar
`allocation/hikaye_sec.py`'nin modül notunda; seçilen basamak, gevşeyen ölçütler ve alternatif
sahne `cikti/hikaye.json`'da.
