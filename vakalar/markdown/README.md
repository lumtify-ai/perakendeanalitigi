# İndirim takvimi (markdown)

Lumoda v4 sentetik verisinde indirim (markdown) vakası (Fiyat ve Promosyon, 1. dizi): talebin indirime
tepkisinden option başına haftalık indirim yolunu seçmek, serbest ana kolu ve takvime bağlı kontrolü
v4 motorunda aynı malla Lumoda'nın kuralıyla kıyaslamak. Tasarım:
`docs/superpowers/specs/2026-10-23-indirim-takvimi-design.md` (`docs/` ayrı depodur).

Vaka adım adım kuruluyor; bu sürümde iskelet, sabitler, kaynak, sızıntı kilidi, haftalık dinamik
program, öğrenme ve tahmin var (`markdown.sabitler`, `markdown.kaynak`, `markdown.model`,
`markdown.ogrenme`, `markdown.tahmin`).

## Kurulum

    cd vakalar/markdown
    python -m venv .venv
    .venv/Scripts/pip install numpy==2.5.4 pandas==2.3.3 duckdb==1.5.6 pyarrow==26.0.0 \
        scikit-learn==1.7.2 scipy==1.18.1 lightgbm==4.5.0 threadpoolctl==3.7.0
    .venv/Scripts/pip install -e ../ortak              # perakende_analitik (kaynak, sayı denetimi)
    .venv/Scripts/pip install --no-deps -e ../../veri  # perakende_veri (yalnız hakem ve simülasyon)
    .venv/Scripts/pip install --no-deps -e ../allocation   # İlk Sevkiyat motoru ve yardımcıları
    .venv/Scripts/pip install --no-deps -e ../kumeleme
    .venv/Scripts/pip install -e ".[dev]"

Kütüphane sürümleri İlk Sevkiyat vakasının `.venv`'iyle aynıdır (koşu önbelleğinin anahtarındadır);
`allocation` ve `kumeleme` `--no-deps` kurulur, hiçbir sürüm değişmemelidir.

**Veri.** `veri/cikti/v4/perakende.duckdb` (ya da `PERAKENDE_V4_DB`). Yoksa yayımlanan `veri-v4`
dosyalarını indirin ya da `cd veri && python -m perakende_veri.v4.uret`.

## Testler

Komutlar vakanın `.venv`'iyle, `vakalar/markdown` içinden; Windows konsolunda `PYTHONIOENCODING=utf-8`.

    .venv/Scripts/python -m pytest tests -q                   # hepsi (gerçek veri testleri dahil)
    .venv/Scripts/python -m pytest tests -q -m "not veri"     # yalnız oyuncak fikstür

`veri` işaretli testler yayımlanan v4 verisini okur ve v4 dünyasını (`allocation.motor.dunya`, ~20 sn)
kurar.

## Gün ekseni

Dünyanın gün indisi 0 = 2022-07-04 (ısınma başı, pazartesi; `perakende_veri.v4.takvim.gun_indisi`).
Yayımlanan tablolar 2023-01-01'den başlar ama `optionlar`'ın `lansman_gun`, `indirim_gun`, `cikis_gun`
sütunları bu eksendedir; gün `d` pazartesidir <=> `d % 7 == 0` (`sabitler.GUN_SIFIRI`).

## Kaynak ve karar penceresi

`kaynak.yayimlanan_tablolar(con, adlar, bitis=None)`: `gizli_*` tablosu reddedilir; `bitis` verilirse
gözlenen olay tabloları (satış, stok, depo, sevkiyat, fiyat, sipariş, kalite kontrol) o günden önceye
kesilir; kampanya, sezon, takvim gibi açık plan tablolarına dokunulmaz.
`kaynak.test_optionlari(optionlar, sezonlar)`: sezonların Collection option'ları (satır konumu).
`kaynak.karar_penceresi(optionlar, idx, kol_tipi)`: ilk indirim yapılabilecek en erken gün; serbest kolda
`max(indirim_gun - 56, lansman_gun + 42)`'nin ilk pazartesisi, takvim kolunda `indirim_gun`.

## Öğrenme ve tahmin

`ogrenme.ogren(con, test_sezonu, bitis, onbellek=None, kaynak_kimligi=None)` test sezonunun en erken
karar pazartesisinden (`sabitler.OGRENME_BITIS`) önceki yayımlanan satırlardan bir kez öğrenir: ortak
paketin kampanya ve markdown esnekliği, hafta günü, özel gün ve beden payı; saf regresyon ε'si (yalnız
rapor); aynı tip kapanmış sezonlardan (SS25 ← SS23 + SS24, AW24 ← AW23) alt kategori × dalga yaşam eğrisi
(fiyat ve kampanya çarpanı çıkarılmış, eşleşmiş hücre zinciri; seyrekse üst kategori, sonra line),
kalıntı değeri (outlet penceresi cirosu ÷ çıkıştan bir hafta önceki stoğun liste değeri), kanal başına iade
ve işlem indirimi payı. Günlük tablo ve çarpanlar `cikti/ogrenme/`'de kaynak kimliği, sezon, bitiş ve kod
özetiyle önbelleklenir (ilk kurulum yol 0'da birkaç dakika). `tahmin.Tahminci(ogrenilen, optionlar)` her
pazartesi bir option için hücre × hafta tam fiyat taban talebi (`taban`), satılabilir stoğu (`satilabilir`)
ve fiyat çarpanlarını (`carpan`) yalnız `Gorunum`'den ve dünyanın açık alanlarından kurar; tanımlar modül
belgelerinde.

## Kilit

Karar modülleri (`sabitler`, `kaynak`, `ogrenme`, `tahmin`, `model`, `politika`) `perakende_veri`'yi,
`markdown.hakem`'i, `markdown.simulasyon`'u, `markdown.olcutler`'i ve `allocation.motor`'u (geçişli
olarak da) içe aktarmaz; `lam`, `esneklik`, `esneklik_hucre`, `gercek`, `ilk_siparisler`, `gizli_*` ve
`sapma_*` adlarını okumaz. AST kilidi `tests/test_sizinti.py`'dedir; henüz yazılmamış modüller
dosya eklendiği anda kendiliğinden kilitlenir.
