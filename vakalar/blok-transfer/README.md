# Blok Transfer — model katmanı

Tasarım: `docs/superpowers/specs/2026-08-25-blok-transfer-model-design.md`.
Bu paket Lumoda verisi üstünde Blok Transfer'i iki yöntemle çözer
(SQL skor + açgözlü eşleştirme, MIP + PuLP) ve demo JSON'unu üretir.

## Kurulum ve koşum

    cd vakalar/blok-transfer
    python -m venv .venv
    .venv/Scripts/pip install -e ../ortak -e ../../veri -e ".[dev]"    # ortak paket + perakende-veri
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

## Ön hazırlık (`hazirla`)

    cd vakalar/blok-transfer
    PYTHONIOENCODING=utf-8 .venv/Scripts/python -m blok_transfer.hazirla    # önce bu
    # ölçüm ve senaryo komutları ondan sonra (hazirla çıktısı yoksa ya da başka bir
    # karar anı / v4 dosyası için kurulmuşsa hata verip bu komutu söylerler)

`cikti/`ya (git dışı) üç adım yazar: `gunluk.parquet` (2023-01-01..2025-12-31),
`carpanlar.pkl` (öğrenme 2023–2024), `kayip_basit.parquet` (Basit kestiricinin kaybı,
yalnız ölçüm penceresi `[karar, karar + 7·olcum_hafta gün)` içindeki `bos`/`tukenen`
satırları; `blok_transfer.hazirla.pencere` tanımı). Eğitim havuzu ve çarpanlar
yok-satma vakasıyla aynıdır, yani pencere içindeki `kayip` değerleri yok-satma'nın
`kayip_basit.parquet`'indekiyle aynıdır. Dosyası olan adım atlanır; `--yeniden`
hepsini kurar. `kaynak.json` (v4 dosyası parmak izi, karar anı, ölçüm haftası)
değişirse çıktılar silinip baştan kurulur. Süre ve satır sayıları `cikti/sure.json`'da.

Gerçek v4 verisinde ölçülen süre (tek koşum, tepe bellek ölçülmedi): `gunluk` 319 sn
(69.380.499 satır), `carpanlar` 36 sn (38.484.293 öğrenme satırı), `basit` 44 sn
(havuz 56.748.777 satır, pencerede 832.051 stoksuz gün-hücresi); toplam yaklaşık 7 dk.
Karar anı 2025-11-03, ölçüm penceresi 2025-11-03..2025-12-28; penceredeki toplam
Basit kaybı 527.475 adet.

## Rapor (`rapor.py`)

    cd vakalar/blok-transfer
    PYTHONIOENCODING=utf-8 .venv/Scripts/python rapor.py > cikti/rapor.txt

Yazılardaki her sayının tek kaynağı `cikti/rapor.txt`'tir (git dışı). Girdiler: `hazirla`
çıktıları, plan önbelleği (`cikti/planlar`; `senaryolar.py` doldurur) ve hakem önbelleği
(`cd ../ortak && .venv/Scripts/python -m perakende_analitik.hakem`). Hakemi yalnız rapor
okur; bu yüzden `../../veri` (`perakende-veri`, PyPI'da yok) yalnız rapor için kurulur.
Eksik girdide hangi komutun koşulacağını söyleyip 1 ile çıkar. `--hikaye OPTION:ALICI:VERICI`
sahneyi geçersiz kılar.

## Parametre gerekçeleri (spec §4)

- `adet_maliyeti_tl = 25`: elleçleme + yol; ortalama liste fiyatının (~1.700 TL)
  yüzde 1-2'si mertebesi.
- `rota_sabiti_tl = 500`: bir mağaza çiftine koli/kamyon kaldırmanın sabit bedeli.
- `min_koli = 6`: altı adedin altına kamyon kalkmaz.
- `soguma_hafta = 2`: yeni sevkiyat yerleşmeden ölçülen hız, hız değildir.
- `ufuk_hafta = 8` ve `hiz_penceresi_hafta = 8`: v1 veride sezon kodu yok;
  gerekçe spec §4 ve sınırı §10.
