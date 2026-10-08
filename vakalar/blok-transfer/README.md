# Blok Transfer — model katmanı

Tasarım: `docs/superpowers/specs/2026-08-25-blok-transfer-model-design.md`.
Bu paket Lumoda verisi üstünde Blok Transfer'i iki yöntemle çözer
(SQL skor + açgözlü eşleştirme, MIP + PuLP) ve demo JSON'unu üretir.

## Kurulum ve koşum

    cd vakalar/blok-transfer
    python -m venv .venv
    .venv/Scripts/pip install -e ../ortak -e ".[dev]"    # önce ortak paket (perakende-analitik)
    .venv/Scripts/python -m pytest -q                    # testler (gerçek veri testleri `veri` işaretli)
    .venv/Scripts/python senaryolar.py                   # demo JSON'unu üretir (elle)

Veri: v4 (`veri/cikti/v4/perakende.duckdb`; başka yol için `PERAKENDE_V4_DB`).
Yoksa yayımlanan dosyayı indirin ya da yerelde üretin:
`cd veri && .venv/Scripts/python -m perakende_veri.v4.uret`.

Veri katmanı (`blok_transfer/cekirdek/veri.py`): `karar_ani` (AW25 indirimden önceki,
8 hafta ileri penceresi dolu son stok fotoğrafı) ve `gorunumler` (`bt_magaza`,
`bt_stok`, `bt_satis`, `bt_sevkiyat`: online, kapalı, açılmamış ve tadilattaki
mağazalar dışarıda; mükerrer satış ve hayalet stok düşük). Görünümler tarih sınırı
koymaz; karar sınırı her sorgunun işidir.

## Parametre gerekçeleri (spec §4)

- `adet_maliyeti_tl = 25`: elleçleme + yol; ortalama liste fiyatının (~1.700 TL)
  yüzde 1-2'si mertebesi.
- `rota_sabiti_tl = 500`: bir mağaza çiftine koli/kamyon kaldırmanın sabit bedeli.
- `min_koli = 6`: altı adedin altına kamyon kalkmaz.
- `soguma_hafta = 2`: yeni sevkiyat yerleşmeden ölçülen hız, hız değildir.
- `ufuk_hafta = 8` ve `hiz_penceresi_hafta = 8`: v1 veride sezon kodu yok;
  gerekçe spec §4 ve sınırı §10.
