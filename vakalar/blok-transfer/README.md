# Blok Transfer — model katmanı

Tasarım: `docs/superpowers/specs/2026-08-25-blok-transfer-model-design.md`.
Bu paket Lumoda verisi üstünde Blok Transfer'i iki yöntemle çözer
(SQL skor + açgözlü eşleştirme, MIP + PuLP) ve demo JSON'unu üretir.

## Kurulum ve koşum

    cd vakalar/blok-transfer
    python -m venv .venv
    .venv/Scripts/pip install -e ".[dev]"
    .venv/Scripts/python -m pytest -q          # testler
    .venv/Scripts/python senaryolar.py         # demo JSON'unu üretir (elle)

Veri yoksa önce üret: `cd veri && .venv/Scripts/python -m perakende_veri.uret`

## Parametre gerekçeleri (spec §4)

- `adet_maliyeti_tl = 25`: elleçleme + yol; ortalama liste fiyatının (~1.700 TL)
  yüzde 1-2'si mertebesi.
- `rota_sabiti_tl = 500`: bir mağaza çiftine koli/kamyon kaldırmanın sabit bedeli.
- `min_koli = 6`: altı adedin altına kamyon kalkmaz.
- `soguma_hafta = 2`: yeni sevkiyat yerleşmeden ölçülen hız, hız değildir.
- `ufuk_hafta = 8` ve `hiz_penceresi_hafta = 8`: v1 veride sezon kodu yok;
  gerekçe spec §4 ve sınırı §10.
