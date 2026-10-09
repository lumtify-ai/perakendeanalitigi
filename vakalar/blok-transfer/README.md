# Blok Transfer — model katmanı

Tasarım: `docs/superpowers/specs/2026-10-07-blok-transfer-v4-design.md` (uygulamadaki
sapmalar §12'de); uygulama planı: `docs/superpowers/plans/2026-10-07-blok-transfer-v4.md`.
Bu paket Lumoda v4 verisi üstünde Blok Transfer'i iki yöntemle çözer (SQL skor + açgözlü
eşleştirme, MIP + PuLP), planın karardan sonraki 8 haftada ne kurtardığını ölçer
(`olcum`), iki demo JSON'unu ve dizinin bütün sayılarını (`rapor.py`) üretir.

## Kurulum

    cd vakalar/blok-transfer
    python -m venv .venv
    .venv/Scripts/pip install -e ../ortak                 # ortak paket (kaynak, kestirici, hakem)
    .venv/Scripts/pip install --no-deps -e ../../veri     # perakende-veri: yalnız hakem için (rapor.py)
    .venv/Scripts/pip install -e ".[dev]"                 # bu paket + pytest (PuLP 3.3.2 sabit)

`perakende-veri` PyPI'da yok; `perakende_analitik.hakem` onu modül düzeyinde içe aktarır,
bu yüzden `rapor.py` (ve `test_rapor`) onsuz içe aktarılamaz. `blok_transfer` paketi onu
hiç görmez (`tests/test_sizinti.py`).

Veri: v4 (`veri/cikti/v4/perakende.duckdb`; başka yol için `PERAKENDE_V4_DB`). Yoksa
yayımlanan dosyayı indirin ya da yerelde üretin:
`cd veri && .venv/Scripts/python -m perakende_veri.v4.uret`.

## Koşum sırası

Hepsi `vakalar/blok-transfer`'den, Türkçe çıktı için `PYTHONIOENCODING=utf-8` ile. Süreler
bu makinede ölçüldü (tek koşum).

| Adım | Komut | Süre |
|---|---|---|
| 1. ön hazırlık | `.venv/Scripts/python -m blok_transfer.hazirla` | ~7 dk |
| 2. hakem (ortak) | `cd ../ortak && .venv/Scripts/python -m perakende_analitik.hakem` | ~4 dk |
| 3. demo senaryoları | `.venv/Scripts/python senaryolar.py` | soğuk 2–3 saat, sıcak dakikalar |
| 4. getiri demosu | `.venv/Scripts/python getiri.py` | ~1 dk |
| 5. rapor | `.venv/Scripts/python rapor.py > cikti/rapor.txt` | ~7 dk (sıcak) |
| 6. sayı denetimi | `cd ../ortak && .venv/Scripts/python -m perakende_analitik.sayi_denetimi --yazi ../../site/src/content/yazi/transfer/blok-transfer --rapor ../blok-transfer/cikti/rapor.txt` | saniyeler |

İsteğe bağlı: `.venv/Scripts/python -m blok_transfer.hikaye_sec` (~40 sn) sahneyi ve
yan rolleri basar; varsayılan sahne kullanıcının seçimidir (`KULLANICI_SECIMI`).

Kurallar:

- **İki çözücüyü aynı anda koşmayın** (iki `senaryolar.py`, ya da `senaryolar.py` ile
  `rapor.py`/`getiri.py`/`hikaye_sec`): plan önbelleğinin geçici dosya adları sabit,
  aynı anahtara eşzamanlı yazım güvensiz; CPU paylaşımı da yayımlanan süreleri bozar.
- **Plan önbelleği** `cikti/planlar` (git dışı). Anahtar: karar anı, bütün parametreler,
  yöntem, değer terazisi, v4 dosyasının kimliği ve çözücüye giren kodun özeti
  (`cekirdek/`, `cozuculer/`, `degerlendirme.py`, ortak `kaynak.py`). Bu kod ya da veri
  değişince eski planlar okunmaz; yine de çözücü girdisini değiştirdikten sonra dizini
  boşaltın (bayat dosyalar birikmesin, soğuk süre ölçülsün).
- **Yayımlanan çözüm süreleri önbellekten gelir.** Soğuk yeniden çözümde süreler oynar
  (son soğuk koşumda referans MIP 37,8 sn → 54,7 sn, açgözlü 16,7 → 39,7 ms); düğüm
  sınırında duran MIP planları ise deterministiktir (32 plan hareket hareket aynı çıktı).
  Süre değişirse yazılardaki süre cümlelerini rapordan güncelleyin.
- `rapor.py` önbellekten bayt bayt yeniden üretilebilir (ölçülen süre basmaz); korunum
  tutmazsa stdout'a tek satır yazmaz, çıkış 1.

## Testler

    .venv/Scripts/python -m pytest -q -m "not veri"   # hızlı: v4 şemalı küçük fikstür (~1,5 dk)
    .venv/Scripts/python -m pytest -q                  # hepsi; `veri` işaretliler gerçek v4,
                                                       # hazirla çıktısı, plan ve hakem önbelleği ister

## Ön hazırlık (`hazirla`)

`cikti/`ya (git dışı) üç adım yazar: `gunluk.parquet` (2023-01-01..2025-12-31),
`carpanlar.pkl` (öğrenme 2023–2024), `kayip_basit.parquet` (Basit kestiricinin kaybı,
yalnız ölçüm penceresi `[karar, karar + 7·olcum_hafta gün)` içindeki `bos`/`tukenen`
satırları; `blok_transfer.hazirla.pencere` tanımı). Eğitim havuzu ve çarpanlar
yok-satma vakasıyla aynıdır, yani pencere içindeki `kayip` değerleri yok-satma'nın
`kayip_basit.parquet`'indekiyle aynıdır. Dosyası olan adım atlanır; `--yeniden`
hepsini kurar. `kaynak.json` (v4 dosyası parmak izi, karar anı, ölçüm haftası)
değişirse çıktılar silinip baştan kurulur. Süre ve satır sayıları `cikti/sure.json`'da.

Ölçülen süre (tepe bellek ölçülmedi): `gunluk` 319 sn (69.380.499 satır), `carpanlar`
36 sn (38.484.293 öğrenme satırı), `basit` 44 sn (havuz 56.748.777 satır, pencerede
832.051 stoksuz gün-hücresi); toplam yaklaşık 7 dk. Karar anı 2025-11-03, ölçüm
penceresi 2025-11-03..2025-12-28.

Veri katmanı (`blok_transfer/cekirdek/veri.py`): `karar_ani` (AW25 indirimden önceki,
8 hafta ileri penceresi dolu son stok fotoğrafı) ve `gorunumler` (`bt_magaza`,
`bt_stok`, `bt_satis`, `bt_sevkiyat`: online, kapalı, açılmamış ve tadilattaki
mağazalar dışarıda; mükerrer satış ve hayalet stok düşük). Görünümler tarih sınırı
koymaz; karar sınırı her sorgunun işidir (hız ve STR'nin satışı `< karar`, soğuma ve
STR'nin varışı `≤ karar`).

## Rapor (`rapor.py`)

Yazılardaki her sayının tek kaynağı `cikti/rapor.txt`'tir (git dışı). Girdiler: `hazirla`
çıktıları, plan önbelleği (`senaryolar.py` doldurur; kâr-ağırlıklı iki planı rapor
kendisi çözer, ilk koşum ~9 dk) ve hakem önbelleği. Hakemi yalnız rapor okur. Eksik
girdide hangi komutun koşulacağını söyleyip 1 ile çıkar. `--hikaye OPTION:ALICI:VERICI`
sahneyi geçersiz kılar.

## Parametre gerekçeleri (spec §3)

- `adet_maliyeti_tl = 25`: elleçleme + yol; ortalama liste fiyatının yüzde 1-2'si
  mertebesi.
- `rota_sabiti_tl = 500`: bir mağaza çiftine koli/kamyon kaldırmanın sabit bedeli.
- `min_koli = 6`: altı adedin altına kamyon kalkmaz.
- `soguma_hafta = 2`: yeni sevkiyat yerleşmeden ölçülen hız, hız değildir; varış
  tarihine bakılır, bütün sevkiyat türleri sayılır.
- `ufuk_hafta = 8`, `hiz_penceresi_hafta = 8`, `olcum_hafta = 8`: karar anı AW25'in
  indirim öncesi son 8 haftalık penceresi; hız son 8 haftadaki stoklu haftalardan,
  ölçüm karardan sonraki 8 haftada.
- `tepe_hafta = 52`: alıcı kapasitesi = son 52 haftanın tepe stoku − karar günü stoku
  (nominal kapasite sütunu v4'te büyük ölçüde aşılıyor).
- `verici_cover_esigi = 6`, `alici_cover_tavani = 0` (kapalı), `min_satis = 1`:
  referans senaryo; kadranlar 6/14/18/26 ve kapalı/3/6/14.
- MIP: `mip_bosluk_orani = 5e-3`, `mip_dugum_limiti = 10.000`, `mip_zaman_limiti_sn =
  3600`, CBC seri. Durum `optimal` = tolerans içinde durdu (kanıtlı optimum değil),
  `limit` = sınırda olurlu çözümle durdu; açgözlünün durumu `sezgisel`.
