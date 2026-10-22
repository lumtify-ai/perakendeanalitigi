# Kümeleme: mağaza grupları

Lumoda v4 sentetik verisinde mağaza kümeleme vakası: Lumoda'nın bugünkü kural tabanlı grupları
(bölge, ciro sınıfı, ikisinin çaprazı, konum) ile satış verisinden makine öğrenmesiyle bulunan
kümeleri aynı mağazalarda kıyaslamak; gizli segmente oturuşlarını, kararlılıklarını, yeni mağaza
atamasını ve en çok karar kalitesini (İlk Sevkiyat'ta küme kolları) ölçmek. Tasarım:
`docs/superpowers/specs/2026-10-20-magaza-kumeleme-design.md` (`docs/` ayrı depodur).

Sitedeki Mağaza Kümeleme dizisinin (`site/src/content/yazi/magaza-kumeleme/magaza-gruplama/`, 6 yazı)
ve demo kadranının (15 bileşim) bütün sayıları buradan, `cikti/rapor.txt`'ten çıkar
(`cikti/` git dışıdır; dosyayı `rapor.py` yeniden üretir). Küme kollarının İlk Sevkiyat sonuçları
`vakalar/allocation/cikti/rapor.txt`'in KÜME bölümündedir; bu vaka ona yalnız girdisini
(`kumeler.json`, `kume_payi`) verir. Okuma sırası: Kurulum → Koşum → Sonuçlar → Sınırlar.

## Kurulum

    cd vakalar/kumeleme
    python -m venv .venv
    .venv/Scripts/pip install -e ../ortak              # perakende_analitik (kaynak, sayı denetimi)
    .venv/Scripts/pip install --no-deps -e ../../veri  # perakende_veri (yalnız hakem ve testler)
    .venv/Scripts/pip install -e ".[dev]"

Kütüphane sürümleri İlk Sevkiyat ile aynı bandadır (`pyproject.toml`): kurulu sürümler
scikit-learn 1.7.2, numpy 2.5.4, pandas 2.3.3, duckdb 1.5.6. `kumeleme` paketi İlk Sevkiyat
vakasının `.venv`'ine `--no-deps` kurulur; orada hiçbir kütüphane sürümü değişmemelidir (koşu
önbelleğinin anahtarındadır):

    cd vakalar/allocation
    .venv/Scripts/pip install --no-deps -e ../kumeleme

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

## Tanımlar

Ayrıntı modül notlarında (`kumeleme/*.py`); burada okuyucunun raporda karşılaşacağı adlar.

- **Aday, kümelenen, yeni.** Aday = karar gününde açık fiziksel outlet olmayan mağaza (SS25: 69);
  kümelenen = geçmişi `GECMIS_HAFTA_ESIGI` = 26 haftayı geçen aday (67); yeni = geri kalan (2: M041
  19 hafta, M027 geçmişsiz). Segmentle ölçüm yalnız kümelenenlerde yapılır; kural grupları (K1-K4)
  ve küme kolları 69 adayı kapsar.
- **K1 bölge** (yayımlanan bölge, 7 grup). **K2 ciro sınıfı** (son 12 ayın net cirosuna göre sıralı:
  A ilk %20, B sonraki %30, C kalan; Lumoda'nın planlama grubu, anlatı varsayımı olarak konmuştur;
  12 aydan kısa geçmiş yıllıklaştırılır, yeni mağaza sıralamaya girmez ve C alır, Ruling R8).
  **K3 bölge × ciro sınıfı** (3 mağazadan küçük hücre komşu sınıfla birleşir). **K4 konum**
  (metropol, değilse şehrin iklim sınıfı; turistik belde `sicak_sahil`).
- **S1, S2, S4, S5.** Mağaza özellik aileleri (yukarıda). Öneri S1'dir (satış karışımı); S2 beden
  eğrisi ve mevsimselliği, S4 çeşitten arındırılmış S2'yi, S5 ölçeği ekler.
- **Siluet.** Standartlanmış özellik uzayında mağazanın kendi kümesine ortalama uzaklığı ile en yakın
  başka kümeye uzaklığından türeyen, kümelerin ayrıklığını ölçen iç ölçüt (hakemsiz); `bos_siluet`
  sütunları karıştırılmış yapısız veride aynı ölçüdür.
- **ARI, AMI** (hakemli): bir bölmenin gizli segmentle uyumu; 1 kusursuz, 0 rastgele düzeyi. ARI
  etiket adlarından bağımsızdır. **Saflık**: bir grubun (ya da segmentin) çoğunluk eşleşmesindeki
  payı.
- **Kararlılık** (hakemsiz): yıllar arası (iki ayrı 52 haftalık pencerenin bölmeleri arası ARI),
  önyükleme (iadeli 50 çekiliş; ARI ve mağaza başına değişme sıklığı), alt örneklem (%80 × 50).
- **Bırakbir isabeti.** Mağaza yeniymiş gibi, kümeler o mağaza hariç kurulur; mağaza yalnız
  statikleriyle atanır; isabet, atanan kümenin kendi satış kümesi ya da (mağaza hariç) çoğunluk
  gizli segmenti olmasıdır. Tabanlar: herkese en büyük küme, herkese en sık segment.
- **Küme kolları** (İlk Sevkiyat; `kume_k2`, `kume_k1`, `kume_k3`, `kume_ml`, `kume_gizli`): küme payı
  (`kume_payi`) benzer ürün endeksinin küme düzeyindeki hâli; aynı mal (t = 0, tavansız, ⌊U⌋) kime
  gideceği değişir. Ölçüt bulunabilirliktir (tanım: `vakalar/allocation/README.md`, Tanımlar).
  Kayıttaki kol adı `kahin`'dir (Ruling R2), rapor ve yazılar koşu adıyla adlandırır. `kume_k3`
  Lumoda'nın gruplarıdır (K3 ızgarası, 12 grup; R21, yollarda R23). İlk Sevkiyat'ın Lumoda kolu
  (`lumoda`, plan payı) bir gruplama değil, Lumoda'nın yayımlanan mağaza mağaza planıdır (R22).

## Sonuçlar

SS25 karar günü (karar günü ve ölçüm koşulları yukarıda). Sayılar `cikti/rapor.txt`'ten ve
İlk Sevkiyat raporundan (`vakalar/allocation/cikti/rapor.txt`, KÜME bölümü) aynı biçimde kopyalanmıştır.

**Gizli segmente oturuş** (67 kümelenen; `ARI / AMI / saflık`):

| Gruplama | Grup | ARI | AMI | Saflık |
|---|---|---|---|---|
| K1 bölge | 7 | 0,209 | 0,334 | %70,1 |
| K2 ciro sınıfı | 3 | 0,035 | 0,012 | %47,8 |
| K3 bölge × ciro | 12 | 0,104 | 0,256 | %71,6 |
| K4 konum | 5 | 0,432 | 0,679 | %79,1 |
| Öneri (S1 k-means k = 5) | 5 | 1,000 | 1,000 | %100,0 |

K4 metropol dışında (46 mağaza) ARI 0,664, metropolde (21 mağaza, 3 segment) tek grup (ARI 0,000);
öneri iki yerde de 1,000. Önerinin kümeleri 32 / 14 / 7 / 7 / 7 mağaza. S2 (beden eğrisi ve mevsim
eklenmiş) k-means k = 3 seçer, hakem ARI'si 0,055; S4 de 0,055 (hakemsiz k ile, k-means).

**Kararlılık.** Öneri yıllar arası ARI 0,642 (65 mağaza), önyüklemede ARI 0,803, mağaza başına
değişme %12,0 (hiç değişmeyen 22/67, %32,8); alt örneklemde 0,851. K2 ciro sınıfı yıllar arası ARI
0,834 (sınıfı değişen 4/65, %6,2), K3 0,910.

**Ablasyon** (k = 5, hakem ARI). S1 1,000 → S1 + ölçek 0,106; S2 0,137 → S5 0,028 (ölçek karışımın
yapısını bozar, bölmeyi ciro sınıfına yaklaştırır: K2 ile ARI S1 0,035 → S1 + ölçek 0,322). Çeşitten
arındırılmış karışım: hakemsiz k ile k-means k = 4 ARI 0,948, Ward k = 5 ARI 1,000; k = 5'te
k-means 0,682 yerel bir optimum (Ward aynı ailede 1,000), "çeşit atılınca bölme bozuldu" denmez.
Ağırlık ablasyonu (sütun orantılı, R7): S1 1,000 → 1,000, S2 0,137 → 0,091.

**Yeni mağaza** (bırakbir, 67 mağaza). En yakın 5 komşu: kendi satış kümesine isabet 55/67 (%82,1);
metropolde 10/21 (%47,6), metropol dışında 45/46 (%97,8); taban (herkese en büyük küme) 32/67
(%47,8). En yakın küme merkezi 47/67 (%70,1). İki gerçek yeni mağaza: M041 Kocaeli 1 doğru
(anadolu_aile), M027 İzmir 2 yanlış (metropol_genc kümesine, gerçeği anadolu_aile).

**Hikâye sahnesi.** M013 İstanbul 13 komşusu M010'dan ayrılıyor (karışım uzaklığı 1,759, üst %25
eşiği 1,661; gizli anadolu_aile / metropol_genc) ve Eskişehir 2 (M055) gibi satıyor (uzaklık 0,601,
alt %25 eşiği 1,040; ikisi anadolu_aile); gevşeme yok. Alternatif: M049 Konya 3 – M075 Sivas 1 /
M049 – M008 İstanbul 8 (3 gevşetme). Kalemler ve eşikler `cikti/rapor.txt` HİKÂYE bölümünde.

**Küme kolları İlk Sevkiyat'ta** (yol 0, aynı mal, t = 0, tavansız; bulunabilirlik): Lumoda'nın
mağaza planı (`lumoda`) %68,98 · ciro sınıfı (K2) %69,19 · bölge (K1) %69,35 · Lumoda'nın grupları
(K3) %69,35 · ML önerisi %69,53 · gizli segment %69,51 · benzer (mağaza geçmişi) %69,51 · tahmin
(LightGBM) %70,41. Yol 0'da `kume_ml − kume_k3` bulunabilirlik +0,18, brüt kâr +1.251.940 TL, kalan
−0,43, WAPE −0,008; `kume_k3 − lumoda` bulunabilirlik +0,37, brüt kâr −868.933 TL, kalan +0,31.
Beş yolda (R23): `kume_ml − kume_k3` bulunabilirlik 5/5 yolda önde (bir ondalık +0,2 · +0,2 · +0,4 ·
+0,3 · +0,1, medyan +0,2), kalan 5/5 (medyan −0,43), pay WAPE 5/5 (medyan −0,007); `kume_k3 − lumoda`
bulunabilirlik 5/5 (medyan +0,4), kalan 1/5, pay WAPE 0/5; ML bulunabilirlikte benzerden 3/5 (medyan
0,0), tahminden 0/5, Lumoda'dan 5/5 yolda önde; gizli segment ML'den 2/5 yolda önde (medyan 0,0).
İlk Sevkiyat raporundaki `KÜME SORU 7` satırı bunları tek satırda özetler (bu vakanın SORU 7'si
cevabı oraya yönlendirir).

Yani ML kümesine göre plan Lumoda'nın gruplarını da mağaza planını da geçiyor, mağazanın kendi
geçmişine yetişiyor ama onu geçmiyor, kusursuz segment bile geçmiyor, LightGBM önde. Bölmenin hakem
uyumu (ARI 1,000) karar kalitesine çevrilmiyor: ML kümesi ile gizli segment yol 0'da yalnız M027'de
ayrışır. Kalibrasyon: ızgarada ilk düzey ve en az örnek eşiği SS24'te pay WAPE'siyle seçildi (k2
0,238, k1 0,235, k3 0,237, ml 0,237, gizli 0,237; aynı sezonda benzer 0,235, tahmin 0,197). Seçilen
ayarlar (ilk düzey / en az örnek): k2 0 / 80, k1 3 / 3, k3 3 / 3, ml 0 / 40, gizli 3 / 20. Kalibrasyon
geçmiş sezonda kaba düzeye denk gelen yüksek bir örnek eşiği seçti; ince düzey ancak çok örnek
olduğunda kullanılıyor. Aynı ayarın oyun sezonunda option'lara dağılımı: ml alt_kategori 68 ·
ust_kategori 109 · genel 33; k2 ust_kategori 143 · genel 67; k1, k3 ve gizli ust_kategori 210.
"Kümede ince benzerlik" hipotezi desteklenmedi.

## Koşum, rapor, demo

Komutlar `vakalar/kumeleme` içinden, sırayla:

    PYTHONIOENCODING=utf-8 .venv/Scripts/python -m kumeleme.oyun           # ~3-4 dk: cikti/sonuc.json, cikti/hikaye.json, kumeler.json
    PYTHONIOENCODING=utf-8 .venv/Scripts/python senaryolar.py              # site/src/data/senaryolar/magaza-gruplama.json
    PYTHONIOENCODING=utf-8 .venv/Scripts/python rapor.py > cikti/rapor.txt # yazıların bütün sayıları
    PYTHONIOENCODING=utf-8 .venv/Scripts/python -m kumeleme.hikaye_kos     # isteğe bağlı: yalnız sahneyi yeniden seçer (cikti/hikaye.json)

`rapor.py` demo dosyasını da denetler (`senaryolar.uret(sonuc)` ile aynı değilse stdout boş kalır),
bu yüzden `senaryolar.py` rapordan önce koşar. `hikaye_kos` zorunlu adım değildir: `oyun` sahneyi
zaten aynı işlevle seçip `sonuc.json`'a ve `hikaye.json`'a yazar; ayrı CLI sahneyi tek başına
yeniden seçmek ya da elle çift denemek içindir (`--gizlisiz`: hakem doğrulaması olmadan; `--zorla
M1,M2,M3,M4`). Rapor sahneyi `sonuc.json`'dan okur; sahneyi değiştirmek için `oyun` yeniden koşar.

**İlk Sevkiyat bu vakayı tüketir.** `vakalar/allocation` `kumeler.json`'u (yol 0) ve
`kumeleme.kume_payi`'nı (küme payı: benzer ürün endeksinin küme düzeyindeki hâli) kullanır; sıra o
vakanın README'sindedir (`allocation.oyun kume_kalibrasyon`, `izgara --blok kume`, `yollar`, rapor).
`kume_payi` allocation'ı içe aktarmaz; bağımlılık tek yönlüdür (allocation'ın koşu dışı `oyun.py`'si
kumeleme'yi çağırır). İki ayrı değişiklik iki ayrı bedel getirir: kümeleme paketinin kodu değişirse
(kod özeti `allocation.yollar`'ın önbellek anahtarındadır) yalnız yolların ölçümü önbellekten yeniden
yapılır (yeni simülasyon yok; İlk Sevkiyat'ta yollar 3.403 sn koştu); kümelerin ya da pay
sözlüklerinin içeriği değişirse küme kollarının koşu anahtarı değişir ve TAM koşular yeniden
koşar (kume bloğu 1.439 sn). Bu yüzden kümeleme düzeltmeleri İlk Sevkiyat ızgarasından ÖNCE yapılır.

- `kumeleme/oyun.py` (ölçüm yanı) bütün hesabı tek koşuda yapar: kapsam, K1-K4, S1/S2/S4/S5 özellikleri,
  önerinin aday tablosu (hakem ARI sonradan eklenir), boş siluet, hakem (ARI/AMI, çapraz tablo, saflık),
  kararlılık (yıllar arası, önyükleme; K2/K3 yıllar arası), bırakbir (5-NN ve merkez) ve iki gerçek yeni
  mağaza, ablasyon (S1, S2, S4, S5, S1 + ölçek, S1 stoklu; sütun orantılı ağırlık), hikâye ve 15 demo
  bileşimi. `sonuc.json` paket kodunun özetini ve v4 dosyasının parmak izini taşır.
- `kumeler.json` (git'te; İlk Sevkiyat yol 0 okur): karar günü eşlemeleri. K1-K4 kapsamın 69 mağazasında,
  önerinin kümeleri 67 kümelenen mağazada, yeni mağazaların 5-NN ataması, kimlikler; gizli segment ayrı bir
  `olcum_gizli_segment` alanında, yalnız ölçüm için (kahin küme kolu). Karar kodu o alanı okumaz.
- `rapor.py` veriyi okumaz, kümelemeyi koşmaz: `sonuc.json`'u basar; KORUNUM bölümünde 54 denetim. Bugünkü kodla ya da v4 dosyasıyla
  yazılmamış `sonuc.json`, `kumeler.json` ya da demo dosyasının `sonuc.json`'dan üretilenden farklı olması,
  ya da bozulan bir korunum denetimi stdout'u boş bırakır (çıkış 1). `--taslak` eski girdiyle basar
  (çıkış 2; yazılara kaynak olamaz). Aynı girdiyle iki koşu bayt bayt aynıdır.
- `senaryolar.py`: özellik seti {S1, S2, S4} × k {4..8} (k-means); kartlar hakem ARI, kararlılık, en küçük
  küme, siluet; `satirlar` kümeler ve en ayırt edici özellikleri. `surum` içeriğin özetidir.

Sayı denetimi (yazılar yazıldıktan sonra):

    .venv/Scripts/python -m perakende_analitik.sayi_denetimi --yazi ../../site/src/content/yazi/magaza-kumeleme/magaza-gruplama --rapor cikti/rapor.txt

## Sınırlar

- **Cevap anahtarı gerçek hayatta yok.** Gizli segment (`gizli_magaza.segment`) simülatörün
  kurgusudur; ARI, AMI ve saflık yalnız bu vakada ölçülebilir. Gerçek bir zincirde elde yalnız
  hakemsiz ölçütler (siluet, kararlılık, karar kalitesi) vardır; rapor bunları ayrıca kurar.
  Önerinin ARI 1,000'i, segmentin satış karışımı üstünden kurulmuş sentetik bir dünyanın sonucudur,
  gerçek veride beklenmez.
- **Konum tablosu bağımsız değil (Ruling R5).** Şehir → iklim tablosu genel coğrafya bilgisiyle yazıldı;
  simülatörün iklim etiketleriyle 25 şehrin 24'ünde örtüşür (fark İzmir), çünkü sentetik zincir
  gerçek coğrafya üstüne kuruldu. Tabloda 26 şehir var, kıyas 25 şehirdir (Gebze simülatörde yok).
  K4'ün başarısı kısmen verinin kurgusudur; Köppen gibi kamuya açık bir iklim verisinden türetme
  bu oturumda kaynak doğrulanamadığı için yapılmadı.
- **Seçim kuralı hakem görüldükten sonra son hâlini aldı.** Önerinin kuralı (Ruling R9) önce
  siluet, eşitlikte kararlılıktır; uygulayıcının ilk taslağı kararlılığı birincil yapıyordu ve S2
  k-means k = 3'ü (hakem ARI 0,055) seçiyordu. Kural hakem sonucu görüldükten sonra denetleyicinin
  önceden yazdığı biçime döndü. Yeni mağaza kuralının 5-NN olması (Ruling R10) da sonuçlar görüldükten
  sonra seçildi (komşu sayısı 5 önceden yazılmıştı; ölçüt hakemsiz, iki yöntem de basılır). Ağırlıkta
  blok içi alt blok eşitliği (Ruling R7) ilke olarak yazıldı, ama keşifte yalnız alt kategori
  bloğunun ARI'sinin 0,915 çıktığı görüldü. Seçimin hakemden tamamen bağımsız olduğu söylenemez.
- **Çeşit sabit.** v4'te hangi mağazanın hangi option'ı taşıdığı dünyada gizli segmente göre kurulmuş
  ve sabittir. Kümeyi çeşide uygulamak Assortment (05) aşamasının işidir; bu vaka kümeyi plana ve
  ilk sevkiyata bağlar.
- **CRM yok (Ruling R1).** Müşteri özellikleri kullanılmaz: v4'te müşteri yaşı gizli segmente göre
  çekilmiş bir arketip karışımından gelir, yaş payıyla tek başına KMeans(5) ARI 0,958 verir; cinsiyet
  payı bütün pencere satışından türediği için karar sonrası sızıntıdır. Müşteri verisini ölçmek
  yanıltıcı olurdu.
- **Tek zincir, tek karar günü.** Sentetik tek zincir, 67 kümelenen mağaza; karar günü SS25 (SS24
  yalnız kalibrasyon ve yıllar arası kararlılık için). Segment sayısı beş; sonuçların başka bir zincire
  taşınabilirliği ölçülmedi.
- **Yol 0'da ML kümesi gizli segmentin aynısıdır.** Bu yüzden küme kollarının ML ve gizli kolları
  yalnız M027'de ayrışır; "gizli segment ne kadar ileride" sorusunun cevabı bu vakada tanım gereği
  yaklaşık sıfırdır (yollarda kümeler yeniden kurulur; gizli segment ML'den 2/5 yolda önde, medyan
  fark 0,0 puan).
- **Küme payı ve çeşit.** Kümeye göre plan ilk sevkiyatın yalnız payını değiştirir (toplam mal aynı,
  ⌊U⌋); çeşidi, replenishment'ı ve markdown'ı değiştirmez.
- **Bırakbirin bedeli (Ruling R6).** Özellikler bir kez kurulur; dışarıda bırakılan mağazanın kendi
  7 hücre dolgusu ötekilerin medyanına küçük bir bilgi taşır (S1'de doldurma yok).
- **Yeni mağaza kuralı** statik özelliklerle çalışır (bölge, metropol, iklim, tip, m², enlem);
  metropolde aynı semtteki mağazaların müşterisini göremez (isabet 10/21, %47,6).

## Sızıntı kilidi

Gizli gerçek (`gizli_magaza.segment`, v4 üreteci) yalnız ölçümde okunur: `hakem.py` ve testler.
Karar modülleri (`sabitler`, `kaynak`, `ozellikler`, `kural`, `ogren`, `yeni_magaza`, `kume_payi`,
`hikaye_sec`) `perakende_veri`'yi, `perakende_analitik.hakem`'i ve `kumeleme.hakem`'i ne
doğrudan ne başka bir modül üstünden içe aktarır, gizli tablonun adını geçirmez, gizli alana
erişmez. Tarama AST'dir (`tests/test_sizinti.py`): `import`, `from X import Y`, göreli içe aktarma,
fonksiyon içi içe aktarma ve sabit dizgeli `importlib` dahil; henüz yazılmamış modüller atlanır.
Pakete eklenen her modül `KARAR_MODULLERI` ya da `IZINLI_MODULLER` listesinde olmalıdır
(`test_her_modul_siniflandirilmis`); tarayıcının ihlali yakaladığı bozma testleriyle sınanır
(`test_tarayici_*`).

**Veri tarafı.** `kumeler.json` karar günü eşlemelerini taşır; gizli segment ayrı bir
`olcum_gizli_segment` alanındadır ve yalnız ölçüm kolu (`kume_gizli`) okur, karar kodu okumaz.
Kümeleme ile İlk Sevkiyat arasındaki bağımlılık tek yönlüdür: `kume_payi` allocation'ı içe
aktarmaz (allocation'ın koşu dışı `oyun.py`'si onu çağırır), İlk Sevkiyat'ın `KOSU_MODULLERI`'ne
dokunulmaz ve mevcut koşuların önbellek anahtarı değişmez
(`vakalar/allocation/tests/test_oyun.py::test_mevcut_kosular_onbellekten`). `veri/` ve
`vakalar/ortak/` salt okunurdur.

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
    kumeleme/kume_payi.py  KumeEndeksi: küme payı (İlk Sevkiyat'ın küme kolları; karar modülü)
    kumeleme/hikaye_sec.py sec (hikâye merdiveni); hikaye_kos.py: ölçüm yanı CLI
    kumeleme/oyun.py       kos, kumeler_kaydi, kod_ozeti (ölçüm yanı koşum)
    rapor.py               cikti/rapor.txt (yazıların sayıları)
    senaryolar.py          demo JSON
    kumeler.json           karar günü eşlemeleri (git'te; İlk Sevkiyat okur)
    tests/                 conftest (oyuncak fikstür), test_kaynak, test_ozellikler, test_sabitler,
                           test_kural, test_ogren, test_olcutler, test_yeni_magaza, test_sizinti,
                           test_hikaye_sec, test_hikaye_kos, test_kume_payi, test_oyun, test_rapor,
                           test_senaryolar (sahte_sonuc)
