# Beden ve paket (prepack)

Lumoda v4 sentetik verisinde beden ve paket vakası (Assortment Planning, 1. dizi): satış ve stoktan
mağaza beden eğrisi okumak, 7'li paketi tek tip (Lumoda'nın 1-2-2-1-1'i) ve K ortak desenli
(K = 1..4) tasarlamak, aynı malı İlk Sevkiyat simülatöründe kollarla kıyaslamak. Tasarım:
`docs/superpowers/specs/2026-10-22-beden-paket-design.md` (`docs/` ayrı depodur).

Durum: iskelet (kaynak, sabitler, sızıntı kilidi). Eğri, paket tasarımı, koşucu, rapor ve yazılar
sonraki görevlerde eklenir; bu belge onlarla genişler. Okuma sırası: Kurulum → Testler → Sınırlar.

## Kurulum

    cd vakalar/beden-paket
    python -m venv .venv
    .venv/Scripts/pip install numpy==2.5.4 pandas==2.3.3 duckdb==1.5.6 pyarrow==26.0.0 \
        scikit-learn==1.7.2 scipy==1.18.1 lightgbm==4.5.0 threadpoolctl==3.7.0
    .venv/Scripts/pip install -e ../ortak              # perakende_analitik (kaynak, sayı denetimi)
    .venv/Scripts/pip install --no-deps -e ../../veri  # perakende_veri (yalnız hakem ve koşucu)
    .venv/Scripts/pip install --no-deps -e ../allocation   # İlk Sevkiyat motoru ve ölçütleri
    .venv/Scripts/pip install --no-deps -e ../kumeleme     # kapsam (aynı 69 mağaza)
    .venv/Scripts/pip install -e ".[dev]"

Kütüphane sürümleri İlk Sevkiyat vakasının `.venv`'iyle aynıdır (`pip list` karşılaştırması
numpy, pandas, duckdb, pyarrow, scikit-learn, scipy, lightgbm, threadpoolctl için aynı çıkar):
koşu önbelleğinin anahtarındadır. `allocation` ve `kumeleme` `--no-deps` kurulur; hiçbir sürüm
değişmemelidir.

**Veri.** `veri/cikti/v4/perakende.duckdb` (ya da `PERAKENDE_V4_DB`). Yoksa yayımlanan `veri-v4`
dosyalarını indirin ya da `cd veri && python -m perakende_veri.v4.uret`.

## Testler

Komutlar vakanın `.venv`'iyle, `vakalar/beden-paket` içinden; Windows konsolunda
`PYTHONIOENCODING=utf-8`.

    .venv/Scripts/python -m pytest tests -q                   # hepsi (gerçek veri testleri dahil)
    .venv/Scripts/python -m pytest tests -q -m "not veri"     # yalnız oyuncak fikstür

`veri` işaretli testler yayımlanan v4 verisini okur.

## Kapsam ve kilit

`beden_paket.kaynak.kapsam`, Kümeleme'nin kapsamını (`kumeleme.kaynak.kapsam`) sarar: karar
gününde aynı 69 aday mağaza, aynı sıra (`test_kapsam_kumeleme_ile_ayni`). `bes_bedenli` aksesuarı
ve tek bedenli setleri ayırır.

Karar modülleri (`sabitler`, `kaynak`, `egri`, `paket_tasarim`, `politika`, `hikaye_sec`)
`perakende_veri`'yi, hakemi ve ölçüm modüllerini içe aktarmaz; gizli `beden_kayma` yalnız `hakem.py`'ye
ve testlere aittir. `egri` yayımlanan `sevkiyat` tablosunu istemez: replenishment sevkiyatının beden
karışımı gizli gerçeği bilen Lumoda'nın planını taşır. İkisi de AST kilidiyle sınanır
(`tests/test_sizinti.py`); henüz yazılmamış modüllerin kontrolü atlanır, modül gelince devreye girer.

## Sınırlar

Bu iskelet yalnız okuma ve kapsamı içerir; ölçüm bulguları sonraki görevlerle gelir.
