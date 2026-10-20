# Kümeleme: mağaza grupları

Lumoda v4 sentetik verisinde mağaza kümeleme vakası: Lumoda'nın bugünkü kural tabanlı grupları
(bölge, ciro sınıfı, ikisinin çaprazı, konum) ile satış verisinden makine öğrenmesiyle bulunan
kümeleri aynı mağazalarda kıyaslamak; gizli segmente oturuşlarını, kararlılıklarını, yeni mağaza
atamasını ve en çok karar kalitesini (İlk Sevkiyat'ta küme kolları) ölçmek. Tasarım:
`docs/superpowers/specs/2026-10-20-magaza-kumeleme-design.md` (`docs/` ayrı depodur).

Bu dosya yapım hâlindedir (vaka iskeleti, sabitler, kaynak, kapsam, mağaza özellikleri, kural
grupları, makine öğrenmesi kümeleri, ölçütler, yeni mağaza). Rapor ve koşum sonraki görevlerde
eklenir; bu README onlarla birlikte genişler.

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
outlet, 1 online, 1 kapanmış, 1 yeni mağaza (10 haftalık geçmiş), 7 SKU (Collection, Basic, NOS),
iki sezon satışı (iadeli) ve pazartesi stok fotoğrafları. Gizli segment sütunu yalnız `gizli`
fikstüründedir.

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

## Mağaza özellikleri

`ozellikler.ozellik_tablosu(tablolar, magazalar, urunler, karar_gunu, aile)` mağaza × özellik
tablosu verir; tanımların tamamı modül notundadır (`kumeleme/ozellikler.py`). Kısaca:

- **Pencere:** karar gününden önceki son 104 tamamlanmış pazartesi-pazar haftası (`OZELLIK_HAFTA`;
  SS25'te karar haftasının ilk günleri de dışarıda). Stok fotoğrafı önceki haftayı anlattığı için
  aynı 104 hafta okunur.
- **Satış:** brüt adet (iade düşülmez), mükerrer satır tek; Outlet line'ı dışarıda. Line grupları
  `Collection` ve `Basic+NOS`: her grubun içinde ayrı paylar, yan yana.
- **Bloklar:** `karisim` (alt kategori, fiyat segmenti, kalıp payları), `beden` (beden sırası 1-5
  payı, her beden setinin içinde, setler eşit ağırlıkla ortalanır; tek bedenli set dışarıda),
  `mevsim` (12 ayın satışlı gün başına satıştan payı), `olcek` (log günlük net ciro, log m², log
  kapasite).
- **Çeşitten arındırma** (`*_stoklu`): aynı paylar, ham adet yerine stoklu gün başına satış
  hızından (karışım ve mevsim için stoklu option-gün, beden için stoklu SKU-gün; yayımlanan `stok`
  fotoğraflarının `stoklu_gun`'ünden). Hayalet stok pencere içinde ayıklanır. Mağazanın hiç
  taşımadığı kategori 0 sayılmaz, nötr doldurulur (kategorinin medyan hızı × mağazanın düzeyi).

| Aile | Bloklar | SS25, 67 mağaza |
|---|---|---|
| S1 | karisim | 45 sütun |
| S2 | karisim, beden, mevsim | 62 |
| S4 | karisim_stoklu, beden_stoklu, mevsim_stoklu | 62 (7 hücre nötr doldurulur) |
| S5 | karisim, beden, mevsim, olcek | 65 |

`standartla(X, aile)` her sütunu z-skora çevirir ve sabit sütunu düşürür. Ağırlık iki katmanlıdır:
**bloklar eşit** (her bloğun toplam varyansı 1; karışım, beden, mevsim, ölçek aynı ağırlıkta) ve
**blok içinde alt bloklar eşit**. Karışımın alt blokları (line grubu, nitelik) çiftleridir: 2 grup ×
alt kategori, fiyat segmenti, kalıp = 6 alt blok, her biri karışımın varyansının 1/6'sı; alt
kategorinin ~17 sütunu fiyat segmentinin 3 sütununu ezmez. Beden, mevsim ve ölçek tek alt bloktur.
`agirlik="sutun"` ablasyonu blok içinde sütunları eşit tutar (alt kategori karışımın varyansının
sütun sayısı oranında payını alır); rapor iki ağırlığı yan yana gösterebilir.
`ozellik_kimligi(X)` satır ve sütun sırasından bağımsız içerik özetidir (SHA-256). Ölçek karışımla
aynı bloğa konmaz; S5 bir ablasyondur.

Satışlı gün (mevsim, ölçek) ve ciro mağazanın bütün satışından sayılır; paylardaki adet yalnız
Collection, Basic ve NOS'un satışıdır. Arındırılmış bloklarda stoklu günü 0 olan hücrenin satışı
hıza girmez; `attrs["dusen_satis"]` alt blok başına bu adedi tutar (SS25, 67 mağaza: 0).

## Makine öğrenmesi kümeleri

`ogren` (kurallar modül notunda, `kumeleme/ogren.py`): `kume(X_std, "kmeans"|"ward", k)` mağaza →
küme numarası verir. k-means `n_init` = 50, tohum `TOHUM`, tek iş parçacığıyla; Ward Öklid. Etiketler
kanoniktir: küme 0 en küçük `magaza_id`'yi taşır, numaralar kümelerin en küçük kimliklerinin
sırasıyla. `bolme_kimligi` etiket adlarından bağımsız bölme özetidir (SHA-256).

- **k seçimi** (`k_sec`, hakemsiz): `K_ARALIK` = 3…10; en küçük kümesi 3 mağazadan az olan k elenir
  (`EN_KUCUK_KUME`), kalanlarda siluet en yüksek olana 0,01 yakın k'lardan en küçüğü seçilir.
  Dirsek için küme içi kareler (`w`) tabloda; kurala girmez.
- **Kararlılık** (`kararlilik`): mağazaların %80'i 50 kez iadesiz çekilip yeniden kümelenir;
  tam bölmeyle çekilen mağazalardaki ortalama ARI. Özellikler yeniden kurulmaz (Ruling R6).
- **Öneri** (`oneri`, Ruling R9): önce her (aile, yöntem) çifti kendi k'sını `k_sec` ile seçer
  (S1 ve S2 × kmeans ve Ward: en çok dört aday); sonra bu adaylar arasında siluet en yüksek olana
  0,01 yakın adaylardan bölme kararlılığı en yüksek olan (0,02 içinde eşitse küçük k, sonra S1,
  sonra kmeans). Bölme kararlılığı aynı bölmeyi veren adayların kararlılık ortalamasıdır: aynı
  bölmeyi veren iki yöntem eşittir, yöntem sırası belirler. İki kademenin payları birikir:
  önerilen satırın silueti uygun bütün ızgaranın en iyisinden ~0,02'ye kadar düşük olabilir. `bos_siluet` sütunları karıştırılmış yapısız veride ortalama
  silueti verir: aileler arasında siluetin karşılaştırılabilirliğinin denetimi. Bütün aday tablosu
  `Oneri.tablo`'dadır.
- **Yorum** (`yorum`): kümenin ortalama z'si |z| büyükten küçüğe en ayırt edici 3 özellik.

SS25 karar günü, 67 mağaza: öneri S1 (satış karışımı), k = 5, küme büyüklükleri 32, 14, 7, 7, 7
(siluet 0,308). k-means ve Ward aynı bölmeyi verir; yöntem sırasıyla k-means adı yazılır. S2'de k-means k = 3 seçilir (siluet 0,278); S2'nin
bölmesini beden eğrisi sürükler.

## Ölçütler ve yeni mağaza

**Hakem** (`hakem.py`, yalnız ölçüm): gizli segment (`gizli_segment`) v4 dünyasından okunur
(`dunya_kur(Olcek.TAM)`, yayımlanan veriyle aynı tohum; simülasyon koşulmaz, süreç içinde bir kez
kurulur, ~20-35 sn). `perakende_veri` paketin yalnız burada içe aktarılır.

**Hakemli ölçütler** (`olcutler.py`): ARI ve AMI (`ari_ami`), küme × segment çapraz tablosu
(`capraz`), segment başına saflık (`saflik`: segmentin en çok düştüğü küme, oradaki payı, kümenin o
segmentten payı) ve klasik toplam saflık (`toplam_saflik`). Ölçülen mağazalarda outlet ya da
online segmenti varsa hata verirler (outlet hariç ölçülür). Kararlılıkta dönem penceresi karar günü
penceresinden sonra bitemez (kalibrasyon gününde ileriye bakmayı önler).

**Kararlılık** (`olcutler.kararlilik`, hakemsiz): (1) yıllar arası, aynı kümeleme işleviyle iki
dönemin yalnız kendi 52 haftalık penceresinden kurulan özelliklerle bulunan bölmeler arası ARI.
"2023" = 2024-01-01'de biten 52 hafta (2023-01-02 … 2023-12-31; veri 2023-01-01 pazar başlar),
"2024" = SS25 karar gününde biten 52 hafta (2024-02-05 … 2025-02-02); pencereler örtüşmez. Her iki
pencerede en az 26 satışlı haftası olan kümelenen mağazalar karşılaştırılır (SS25'te M021 ve M037
dışarıda: 2023'te 19 hafta ve hiç). (2) Önyükleme: karar günü özellik tablosu bir kez kurulur
(Ruling R6), mağazalar 50 kez iadeli çekilip kümelenir, çekiliş kümeleri tam kümelerle Macar
eşlemesiyle eşlenir; mağaza başına değişme sıklığı = değiştiği çekiliş / girdiği çekiliş. Etiket
adları ölçüte girmez. (`ogren.kararlilik` ayrı bir ölçüttür: %80 iadesiz alt örneklemde ARI,
önerinin eşitlik bozucusu.)

**Yeni mağaza** (`yeni_magaza.py`, karar modülü): satış görmeden, yalnız statiklerle (bölge,
metropol, iklim sınıfı, tip, log m², enlem) atama; her statik eşit ağırlıklı bir blok (kümelenmiş
mağazalarda toplam varyans 1), istatistikler yalnız kümelenmiş mağazalardan. Kural en yakın 5
kümelenmiş mağazanın çoğunluk kümesi (`ata`, `yontem="knn"`, varsayılan; `"merkez"` en yakın küme
merkezi karşılaştırma için: satış kümeleri statik uzayda dışbükey değil, bırakbirde kendi satış
kümesine isabet SS25'te knn 0,82, merkez 0,70). Bırakbir ölçümü (`birakbir`,
spec §0/11): kümelenen her mağaza için kümeler o mağaza hariç aynı özellik tablosundan yeniden
kurulur (özellikler yeniden kurulmaz, Ruling R6; bedeli: oran bloklu ailelerde nötr doldurulan
hücreler dışarıda bırakılan mağazanın satırını da içeren medyandan gelir; S1'de doldurma yok), mağaza yalnız statikleriyle atanır, bırakbir kümesi tam
bölmenin etiketine Macar eşlemesiyle (birebir, önyüklemeyle aynı) çevrilir. `atanan_segment` (atanan
kümenin çoğunluk segmenti) tam bölmenin üyelerinden, mağazanın kendisi hariç sayılır; çoğunlukta
eşitlik ıskadır. Doğruluk `olcutler.birakbir_dogruluk`'ta:
kendi satış kümesine karşı ve gizli segmente karşı (atanan kümenin, mağaza hariç çoğunluk
segmenti), metropol / metropol dışı ayrı; iki taban (herkese en büyük küme, herkese en sık segment).

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
    kumeleme/ozellikler.py pencere, ozellik_tablosu, AILELER, standartla, ozellik_kimligi
    kumeleme/kural.py      K1 bölge, K2 ciro sınıfı, K3 bölge × sınıf, K4 konum
    kumeleme/ogren.py      kume, kanonik, bolme_kimligi, siluet, k_sec, kararlilik, bos_siluet,
                           yorum, oneri
    kumeleme/hakem.py      gizli_segment (yalnız ölçüm; v4 dünyası)
    kumeleme/olcutler.py   ari_ami, capraz, saflik, toplam_saflik, kararlilik, birakbir_dogruluk
    kumeleme/yeni_magaza.py statik_tablo, ata, birakbir
    tests/                 conftest (oyuncak fikstür), test_kaynak, test_ozellikler, test_sabitler,
                           test_kural, test_ogren, test_olcutler, test_yeni_magaza, test_sizinti
