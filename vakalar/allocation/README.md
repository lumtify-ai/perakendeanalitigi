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

Seçimler, WAPE'ler ve koşu ölçütleri `cikti/kalibrasyon.json`'da; Görev 8'in ızgarası değerleri
oradan okur. Kalibrasyonun iki ölçütünün (bulunabilirlik, sezon sonu kalan) tanımı
`allocation/oyun.py`'nin modül notunda.
