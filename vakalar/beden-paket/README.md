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

## Koşucu

İlk Sevkiyat'ın `motor.kos`'u paket seçimini açmadığı için vaka kendi simülasyonunu kurar
(`beden_paket.simulasyon`): yayımlanan dünyanın `paketler`'i ayrılmış kopyası (`politika.paket_ekle`;
yeni paketler standartların ardına), oyun option'larında (SS25 Collection) mağazanın deseni
(`PaketSecimi`) ve Lumoda'nın **giden** paket sayısı (`GidenIlkDagitim`, `kosucu.lumoda_giden`); öteki
her şey Lumoda'nın. Koşu önbelleği `cikti/kosular/` (İlk Sevkiyat motorunun düzeni ve anahtarı + vaka
kodu); İlk Sevkiyat'ın önbelleği yalnız salt okunur açılır. Anahtarın vaka kodu yalnız simülasyonu
değiştiren modüllerdir (`simulasyon.SIMULASYON_MODULLERI`: `simulasyon`, `politika`, `sabitler`,
`__init__`); ölçüm (`kosucu`), ızgara (`oyun`), eğri ve tasarım kodu değişince koşular önbellekten
okunur, yalnız ölçüm yeniden yapılır (`test_olcum_degisikligi_simulasyonu_bozmaz`). Ölçüt
`kosucu.olc`: İlk Sevkiyat'ın ölçütleri, kırpma pakete duyarlı, `paket_tipi` giden beden deseni sayısı;
ilk 4 hafta kırık set ve beden kaybı payı (`kirik_cift_pay_yuzde_ilk4`, `beden_kayip_payi_ilk4`; pencere
`bulunabilirlik_ilk4`'ünki, Ruling R19).

Doğrulama kolu standart paket ve Lumoda'nın kendi ilk dağıtımıyla İlk Sevkiyat'ın `lumoda` koşusunu
birebir üretir (KÜÇÜK'te `test_dogrulama_kucuk`; TAM'da, ~4–8 dk, ~8 GB). İlk Sevkiyat'ın önbelleği ya
da kayıtlı ölçütü yoksa komut başarısızdır (çıkış 1):

    .venv/Scripts/python -m beden_paket.kosucu dogrulama            # yol 0; --yol P ile yol P

## Oyun ızgarası

`beden_paket.oyun`: kollar (Ruling R10, R20, R21) yol 0'da `dogrulama`, `p1`, `p2`, `p1_12`, `p3_12`,
`pm_12`, `p2_12`, `l0_12` (ayrıştırma kontrolü: Lumoda paketinin 12'li karşılığı 2-3-3-2-2, tasarım
aranmaz), `p2_ham`; yollar 1–4'te `dogrulama`, `p1`, `p2`, `p3_12` (25 kayıt). Her yolda eğri, tasarım, `ns` ve
depo o yolun doğrulama koşusunun (yol 0 TAM'da yayımlanan verinin) tablolarından, karar günü bilgisiyle. Tasarımı
aynı yolda daha önceki bir kolunkiyle aynı olan kol koşulmaz, kaydı `ayni` ile bağlanır (TAM yol 0'da
pm_12 = p3_12, p2_ham = p2). Sonuç `cikti/oyun.json`, ilerleme `cikti/ilerleme.jsonl`:

    .venv/Scripts/python -m beden_paket.oyun izgara --blok ana       # yol 0: dogrulama … l0_12
    .venv/Scripts/python -m beden_paket.oyun izgara --blok ablasyon  # yol 0: p2_ham
    .venv/Scripts/python -m beden_paket.oyun izgara --blok yol       # yollar 1–4
    .venv/Scripts/python -m beden_paket.oyun izgara --olcek KUCUK    # KÜÇÜK dünya: cikti/kucuk/oyun.json

**Depo** (Ruling R16). Tasarımın depo kısıtı karar anında bilinenden kurulur: ilk siparişin beden
adedi (`YolGirdisi.siparis_deposu`). Kalite kontrol hatası düşülmüş depo (`YolGirdisi.depo`; motorun
ilk dağıtım anındaki deposu, hataların çoğu karar gününden sonraki teslimlerde) yalnız koşmadan option
başına sınamada (`on_denetim`) ve korunumda kullanılır. İki tanımla tasarımlar ve bağlar aynıdır
(`depo_tanimlari_ayni`, oyun.json `yollar.<p>.depo.tanimlar_ayni`).

**Kalibrasyon komutu yok** (Ruling R17): κ eğrinin içinde, yolun kendi tablolarıyla seçilir
(`egri.kappa_sec`); κ tablosu ve SS24 uyumu `YolGirdisi.egri_tanisi()` ve oyun.json
`yollar.<p>.egri_tanisi`'nde.

**Sabitler kuralı** (Ruling R18). `beden_paket/sabitler.py` simülasyon anahtarındadır
(`politika` onu içe aktarır): değişirse bütün koşular yeniden simüle edilir. TAM koşulduktan sonra
oraya yalnız simülasyonu değiştiren sabit girer; ölçüm, ızgara ve rapor sabitleri kendi modüllerinde
durur (ör. `oyun.OLCUM_SURUMU`, `oyun.OLCUM_FONKSIYONLARI`). Ölçüm kodu özeti (`oyun.OLCUM_OZETI`)
`kosucu.py`'yi, İlk Sevkiyat `olcutler.py`'yi ve `oyun`'un ölçüm tarafı işlevlerini kapsar; bunların
dışında ölçümü değiştiren bir düzeltmede `OLCUM_SURUMU` bir artırılır.

## Sınırlar

Bu iskelet yalnız okuma ve kapsamı içerir; ölçüm bulguları sonraki görevlerle gelir.
