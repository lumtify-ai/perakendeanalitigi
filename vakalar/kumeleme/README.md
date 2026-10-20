# Kümeleme: mağaza grupları

Lumoda v4 sentetik verisinde mağaza kümeleme vakası: Lumoda'nın bugünkü kural tabanlı grupları
(bölge, ciro sınıfı, ikisinin çaprazı, konum) ile satış verisinden makine öğrenmesiyle bulunan
kümeleri aynı mağazalarda kıyaslamak; gizli segmente oturuşlarını, kararlılıklarını, yeni mağaza
atamasını ve en çok karar kalitesini (İlk Sevkiyat'ta küme kolları) ölçmek. Tasarım:
`docs/superpowers/specs/2026-10-20-magaza-kumeleme-design.md` (`docs/` ayrı depodur).

Bu dosya iskelet durumundadır (vaka iskeleti, sabitler, kaynak, kapsam). Özellikler, kümeler,
ölçütler, rapor ve koşum sonraki görevlerde eklenir; bu README onlarla birlikte genişler.

## Kurulum

    cd vakalar/kumeleme
    python -m venv .venv
    .venv/Scripts/pip install -e ../ortak              # perakende_analitik (kaynak, sayı denetimi)
    .venv/Scripts/pip install --no-deps -e ../../veri  # perakende_veri (yalnız hakem ve testler)
    .venv/Scripts/pip install -e ".[dev]"

Kütüphane sürümleri İlk Sevkiyat ile aynı bandadır (`pyproject.toml`): kurulu sürümler
scikit-learn 1.7.2, numpy 2.5.4, pandas 2.3.3, duckdb 1.5.6. `kumeleme` paketi İlk Sevkiyat
vakasının `.venv`'ine `--no-deps` kurulur; orada hiçbir kütüphane sürümü değişmemelidir (koşu
önbelleğinin anahtarındadır).

**Veri.** `veri/cikti/v4/perakende.duckdb` (ya da `PERAKENDE_V4_DB`). Yoksa yayımlanan
`veri-v4` dosyalarını indirin ya da `cd veri && python -m perakende_veri.v4.uret`.

## Testler

Komutlar vakanın `.venv`'iyle, `vakalar/kumeleme` içinden; Windows konsolunda
`PYTHONIOENCODING=utf-8`.

    .venv/Scripts/python -m pytest tests -q                   # hepsi (gerçek veri testleri dahil)
    .venv/Scripts/python -m pytest tests -q -m "not veri"     # yalnız oyuncak fikstür

`veri` işaretli testler yayımlanan v4 verisini ister. Oyuncak fikstür (`tests/conftest.py`) 12
mağazalı, v4 şemalı küçük tablolardır: 3 görünür bölge, 4 metropol mağazası (İstanbul, Ankara), 1
outlet, 1 online, 1 kapanmış, 1 yeni mağaza (10 haftalık geçmiş), iki sezon satışı. Gizli segment
sütunu yalnız `gizli` fikstüründedir.

## Kapsam

Karar günü SS25'in ilk Collection karar günüdür (`sabitler.KARAR_GUNU`, lansmandan önceki cuma).
Kümeler yalnız o güne kadarki yayımlanan veriyle kurulur. `kaynak.kapsam` kümelenecek mağazaları
verir ve İlk Sevkiyat'ın aday tanımıyla aynı koşulları uygular (`allocation.paylastir.aday_maskesi`):

- fiziksel mağaza; **outlet ayrı gruptur** (başka line satar) ve **online dışarıdadır**;
- açılışı lansmana (karar gününden sonraki ilk pazartesi) kadar: karar gününde açık olanlar ve
  lansmana dek açılacaklar (SS25'te M027, lansman günü açılıyor);
- karar gününde kapanış kararı verilmemiş (`magaza_olay`) ve lansmana dek kapanmıyor
  (`magaza.kapanis_tarihi`).

SS25 karar gününde 69 aday mağaza vardır: AVM ve Cadde tipli 74 mağazadan dördü kapanmış
(M004, M005, M006, M077), biri lansmandan sonra açılıyor (M044); 10 outlet ve online baştan dışarıdadır. **Yeni mağaza:** karar gününe dek tamamlanmış ve satışlı hafta sayısı
(`gecmis_hafta`) `GECMIS_HAFTA_ESIGI` = 26'dan azsa mağaza kümelenmez, "yeni" sayılır: 67 mağaza
kümelenir, 2'si yenidir (M041 19 hafta, M027 geçmişsiz). Hafta, pazartesi-pazar takvim haftasıdır;
yalnız pazarı karar gününden önce kalan ve brüt (pozitif adetli) satış taşıyan haftalar sayılır;
iade ve karar gününden sonraki satış sayılmaz.

## Şehir → iklim tablosu

K4 konum kuralı (iklim sınıfı + metropol bayrağı) şehirden türetilir. `kaynak.SEHIR_IKLIM`
vakada yazılı, açık bir tablodur: 26 şehrin her biri dört sınıftan birine konur.

| Sınıf | Şehirler |
|---|---|
| `soguk` | Erzurum, Kars, Van, Sivas |
| `sicak_sahil` | Antalya, Alanya, Kemer, Fethiye, Bodrum, Mersin, Adana, İzmir |
| `ılıman` | İstanbul, Bursa, Kocaeli, Gebze, Samsun, Trabzon, Denizli |
| `karasal` | Ankara, Eskişehir, Konya, Kayseri, Malatya, Diyarbakır, Gaziantep |

`TURISTIK` = Antalya, Alanya, Kemer, Fethiye, Bodrum (tatil beldeleri; hepsi `sicak_sahil`).
`METROPOL` = İstanbul, Ankara, İzmir.

**Kaynak ve sınır.** Sınıflar genel coğrafya bilgisinden yazıldı (Türkiye'nin iklim bölgeleri ve
Köppen sınıflaması; yükseklik, kıyıya uzaklık); `perakende_veri` içe aktarılmadı ve karar
modüllerinde içe aktarılmaz. Yine de bu tablo simülatörden bağımsız bir ölçüm değildir: simülatörün
şehir iklim etiketleriyle 25 şehrin 24'ünde örtüşür (fark İzmir), çünkü sentetik zincir gerçek
coğrafya üstüne kurulmuştur. Bu yüzden K4 konum kuralının başarısı kısmen verinin nasıl
kurulduğunun bir özelliğidir; yazılar bunu söyler. Sınırdaki şehirler bir yargıdır: Denizli iç Ege
(ılıman nemli ile karasal arası) `ılıman`, İzmir kıyı Ege olduğundan `sicak_sahil`, Malatya,
Diyarbakır ve Gaziantep sıcak yazlı ve soğuk kışlı iç kesimler olduğundan `karasal` sayıldı.
`tests/test_kaynak.py::test_sehir_iklim_butun_sehirler` yayımlanan bütün şehirlerin tabloda
olduğunu sınar.

## Sızıntı kilidi

Gizli gerçek (`gizli_magaza.segment`, v4 üreteci) yalnız ölçümde okunur: `hakem.py` ve testler.
Karar modülleri (`sabitler`, `kaynak`, `ozellikler`, `kural`, `ogren`, `yeni_magaza`, `kume_payi`,
`hikaye_sec`) `perakende_veri`'yi, `perakende_analitik.hakem`'i ve `kumeleme.hakem`'i ne
doğrudan ne başka bir modül üstünden içe aktarır, gizli tablonun adını geçirmez, gizli alana
erişmez. Tarama AST'dir (`tests/test_sizinti.py`): `import`, `from X import Y`, göreli içe aktarma,
fonksiyon içi içe aktarma ve sabit dizgeli `importlib` dahil; henüz yazılmamış modüller atlanır.
Pakete eklenen her modül `KARAR_MODULLERI` ya da `IZINLI_MODULLER` listesinde olmalıdır.

## Dosyalar

    kumeleme/sabitler.py   karar günleri, eşikler, tohum
    kumeleme/kaynak.py     baglan, yayimlanan_tablolar, kapsam, SEHIR_IKLIM / TURISTIK / METROPOL
    tests/                 conftest (oyuncak fikstür), test_kaynak, test_sabitler, test_sizinti
