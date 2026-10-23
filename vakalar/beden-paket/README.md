# Beden ve paket (prepack)

Lumoda v4 sentetik verisinde beden ve paket vakası (Assortment Planning, 1. dizi): satış ve stoktan
mağaza beden eğrisi okumak, 7'li paketi tek tip (Lumoda'nın 1-2-2-1-1'i) ve K ortak desenli
(K = 1..4) tasarlamak, 12'li pakete taşımak, aynı malı İlk Sevkiyat simülatöründe kollarla kıyaslamak.
Tasarım: `docs/superpowers/specs/2026-10-22-beden-paket-design.md` (`docs/` ayrı depodur).

Sitedeki dizinin (`site/src/content/yazi/assortment/beden-paket/`, 6 yazı; sitede terim "koli", dizi
adı Beden ve Koli, Ruling R25) ve demo kadranının (10 bileşim, `site/src/data/senaryolar/beden-koli.json`)
bütün sayıları buradan, `cikti/rapor.txt`'ten çıkar (`cikti/` git dışıdır; dosyayı `rapor.py` yeniden
üretir). Kodda ve raporda `paket`, sitede `koli` der; kavram aynıdır. Okuma sırası: Kurulum → Koşum →
Tanımlar → Kollar → Sonuçlar → Sınırlar.

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
(`tests/test_sizinti.py`): karar modüllerinin her biri kilitlidir, `kahin_yalniz_olcumde` testi gizli
gerçeğin yalnız `hakem.py`'de ve testlerde okunduğunu sınar.

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

`beden_paket.oyun`: kollar (Ruling R10, R21, R22) yol 0'da `dogrulama`, `p1`, `p2`, `p1_12`, `p3_12`,
`pm_12`, `p2_12`, `p1_14` (ayrıştırma kontrolü: P1'in iki katı 2-2-4-4-2, tasarım aranmaz, ns 14'lü
dönüşüm aşağı yuvarlanır; p1_14 − p1 paket büyüklüğünün etkisi), `p2_ham`; yollar 1–4'te `dogrulama`, `p1`, `p2`, `p3_12` (25 kayıt). Her yolda eğri, tasarım, `ns` ve
depo o yolun doğrulama koşusunun (yol 0 TAM'da yayımlanan verinin) tablolarından kurulur; eğri ve tasarım
yalnız karar günü öncesi bilgiyle, depo karar öncesi sipariş adedinden (aşağıda). Tasarımı
aynı yolda daha önceki bir kolunkiyle aynı olan kol koşulmaz, kaydı `ayni` ile bağlanır (TAM yol 0'da
pm_12 = p3_12, p2_ham = p2). Sonuç `cikti/oyun.json`, ilerleme `cikti/ilerleme.jsonl`:

    .venv/Scripts/python -m beden_paket.oyun izgara --blok ana       # yol 0: dogrulama … p1_14
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

## Koşum

Komutlar `vakalar/beden-paket` içinden, sırayla; Windows konsolunda `PYTHONIOENCODING=utf-8`. TAM
koşular arka planda koşar (~8 GB bellek; tek bir TAM simülasyon ~5-8 dk). Çıktılar `cikti/` altındadır
ve git dışıdır.

    # 1. doğrulama kolu: İlk Sevkiyat'ın lumoda koşusu birebir mi (yol 0 TAM 508 sn, tepe 7,18 GB)
    .venv/Scripts/python -m beden_paket.kosucu dogrulama            # --yol P ile yol P
    # 2. oyun ızgarası: 23 simülasyon, 25 kayıt; cikti/oyun.json (ilk 21 simülasyon ~3-3,3 sa sürdü)
    .venv/Scripts/python -m beden_paket.oyun izgara --blok ana       # yol 0: dogrulama ... p1_14
    .venv/Scripts/python -m beden_paket.oyun izgara --blok ablasyon  # yol 0: p2_ham
    .venv/Scripts/python -m beden_paket.oyun izgara --blok yol       # yollar 1-4
    # 3. koşusuz tanılar: eğri, tasarım, K eğrisi, kahin, depo; cikti/analiz.json
    .venv/Scripts/python analiz.py
    # 4. hikâye sahnesi (ölçüm tarafı; hakem yalnız doğrular); cikti/hikaye.json
    .venv/Scripts/python -m beden_paket.hikaye_kos
    # 5. demo dosyası: site/src/data/senaryolar/beden-koli.json
    .venv/Scripts/python senaryolar.py
    # 6. rapor: yazıların bütün sayıları
    .venv/Scripts/python rapor.py > cikti/rapor.txt

`rapor.py` veriyi okumaz ve simülasyon koşmaz: `oyun.json`, `analiz.json`, `hikaye.json` ve demo
dosyasını basar. Bugünkü ölçüm koduyla yazılmamış bir girdi, demo dosyasının çıktılardan üretilenden
farklı olması ya da bozulan bir korunum denetimi stdout'u boş bırakır (çıkış 1); `--taslak` eski ya da
eksik girdiyle basar (çıkış 2; yazılara kaynak olamaz). `analiz.py` `beden_paket/` dışında, vaka
kökündedir: paket modüllerinde olsaydı simülasyon anahtarını değiştirirdi. `oyun izgara` ve `analiz.py`
`--olcek KUCUK` ile KÜÇÜK dünyada koşar (`cikti/kucuk/`). `hikaye_kos` sahneyi tek başına yeniden seçmek
içindir (`--gizlisiz`: hakem doğrulaması olmadan).

Sayı denetimi (yazılar yazıldıktan sonra):

    .venv/Scripts/python -m perakende_analitik.sayi_denetimi --yazi ../../site/src/content/yazi/assortment/beden-paket --rapor cikti/rapor.txt

**Simülasyon ve ölçüm önbelleği (R14, R18).** Koşu önbelleği ikiye ayrılır. *Simülasyon anahtarı* yalnız
tabloları değiştiren kod ve girdileri taşır (politika, simülasyon çekirdeği, paket satırları, atama,
`ns`, tohum, ölçek, İlk Sevkiyat `KOSU_MODULLERI`, v4, kütüphane sürümleri). *Ölçüm* ise önbellekten
yeniden hesaplanır ve ayrı bir ölçüm özeti taşır (`oyun.OLCUM_OZETI`, `OLCUM_SURUMU`). Böylece ölçüt,
ızgara, eğri, tasarım ya da rapor kodunu düzeltmek 23 TAM koşuyu yeniden simüle ettirmez; yalnız ölçüm
yeniden yapılır (~40 dk). `sabitler.py` simülasyon anahtarındadır: değişirse her şey yeniden koşar;
ölçüm ve rapor sabitleri bu yüzden kendi modüllerindedir. Tasarım, `ns` ve depo bir koşunun anahtarında
olduğu için o yolun doğrulama koşusunun tablolarından kurulur; iki depo tanımında (R16) tasarımlar aynı
çıktığı için simülasyon anahtarı bu tanımdan etkilenmez.

## Tanımlar

Ayrıntı modül notlarında (`beden_paket/*.py`); burada okuyucunun raporda karşılaşacağı adlar.

- **Aday, okunabilen, yeni.** Aday = karar gününde Kümeleme'nin kapsamındaki fiziksel mağaza (69:
  İstanbul 12 Ali'nin, Anadolu 57 Veli'nin). Eğrisi *okunabilen* = penceredeki beş bedenli satışı
  ≥ `EGRI_EN_AZ_ADET` = 500 adet olan mağaza (68). *Yeni* = eğrisi okunamayan (M027, 0 satışlı hafta).
  M041 (19 satışlı hafta) okunabilir ve kendi eğrisini alır (R7; Kümeleme'nin 26 haftalık eşiği satış
  karışımı içindi, beden eğrisi için değil).
- **Beden eğrisi.** Mağazanın beş bedene dağılan talep payı (toplam 1). *Ham* pay satıştan; *sansür
  düzeltmeli* pay stoklu gün başına hızla (biten bedenin satışı stoksuz günde görünmez); *daraltılmış*
  (son eğri) mağaza payının zincir eğrisine w = n / (n + κ) ağırlıkla çekilmesi. Pencere option
  lansmanından sonraki ilk 8 hafta, karar gününden önceki son 104 hafta, Collection ve Basic/NOS
  havuzlu (R5). κ, SS24 karar anında kurulan eğrinin SS24'ün gerçekleşen paylarına L1'iyle (hakemsiz)
  seçilir. Eğri yalnız satış ve stoktan okunur; yayımlanan replenishment sevkiyatı girdi değildir, çünkü
  beden karışımı Lumoda'nın planını taşır (spec §0/13).
- **Profil.** Mağaza eğrilerinin k-means (k = 3) kümesi, ortalama beden sırasına göre adlı: `kucuk`,
  `orta`, `buyuk`. Eğrisi okunamayan mağaza zincir eğrisini ya da statik özellikleriyle atanmış profilin
  eğrisini alır; hangisi, bırakbir L1 ile (hakemsiz) seçilir (R9).
- **L1** iki beden payı arasında mutlak fark toplamıdır (0-2). **Hakem** gizli `beden_kayma`: talebi
  süren değer, [−1, +1]'e kırpılmış (R4). **ARI** bir bölmenin hakemle uyumu (1 kusursuz, 0 rastgele
  düzeyi).
- **Paket, desen, K.** Paket = bir beden setinin mağazaya giden bir kolisi (kodda `paket`, sitede
  `koli`, R25); 7, 12 ya da 14 adetlik. *Desen* paketin beden içeriği (örn. 1-2-2-1-1). *K* bütün beş
  bedenli sette ortak desen sayısıdır: mağazanın deseni her option'da aynıdır; `magaza` kolu mağaza
  başına bir desendir. Her pakette temel bedenler (2-4) en az bir adet taşır.
- **Uyumsuzluk** (tasarım ölçüsü, koşusuz). Paketin mağaza eğrisine göre beklenen eksik adedi (L1 ile
  aynı sıralamayı verir), mağazanın Lumoda'dan giden paket sayısıyla ağırlıklı; *paket başına* değer
  toplam uyumsuzluğun giden paket sayısına oranıdır. Aday desen sayısı 7 adette 70, 12 adette 715;
  küme sayısı tam arama sınırını aşarsa (12'li pakette K ≥ 3) arama dönüşümlüdür. "Kanıtlı" en iyi olduğu
  kanıtlı demektir (tam arama ya da optimal MIP); P1 14'lü sabit desendir, aranmaz.
- **Aynı mal** (spec §0/5, §0/11). Her kol, mağaza × option başına Lumoda'nın *giden* paket sayısını
  (`ns`, motor sonrası) gönderir; paket tasarımı beden başına depo kısıtına uyar, bu yüzden motor
  kırpmaz. KORUNUM bunu kol başına denetler: giden adet Lumoda'nınkine eşit, kırpma 0. 12'li ve 14'lü
  kollarda `ns` adet dönüşümüyle yaklaşık kurulur ve fark raporda basılır.
- **Depo** (R16). Tasarımın depo kısıtı karar öncesi *ilk sipariş* adedinden kurulur; kalite kontrolde
  hatalı çıkan adedin düşüldüğü depo (teslimlerin çoğu karar gününden sonra) yalnız ön denetim ve
  korunumdadır. Rapor iki tanımı yan yana basar; tasarımlar aynıdır.
- **Başlık ölçütleri: ilk 4 hafta** (spec §0/12, R19): ilk dağıtımın varışından 28 gün. *Bulunabilirlik*
  talepli hücre-günlerin kendi satışı olan payı. *Beden kaybı payı* karşılanmayan talebin, bedeni boşken
  aynı çiftin başka bir bedeni stoklu olan SKU-günlerdeki kısmının oranı (100 ×). *Kırık set* stoklu
  (mağaza, option, gün) çiftlerinden çekirdek bedenlerden birinin boş olduğu çiftlerin payı. Sezon
  sürümleri, sezon sonu kalan, tam fiyat STR ve brüt kâr yanında basılır. Tanımlar
  `vakalar/allocation/README.md`'dendir.
- **Kollar arası fark**: yüzde ölçütlerinde puan; tek ondalıklı her fark, iki ondalıklı farkın bir kez
  yuvarlanmışıdır (yarım yukarı). **Kaç yolda önde** k/5; medyan fark basılan değerlerden.
- **Yol.** İlk Sevkiyat'ın 5 talep yolu: yol 0 yayımlanan dünya, yol 1-4 aynı dünyada başka bir müşteri
  akışı; her yolda eğri, profil, κ ve tasarımlar o yolun yayımlanan tablolarından yeniden öğrenilir.

## Kollar

Kollar Lumoda'nın giden paket sayısını gönderir; replenishment, RPT ve markdown Lumoda'nınkidir (spec
§0/6, İlk Sevkiyat'taki gibi tepkili). Yalnız paketin beden içeriği değişir.

| Kol | Ne | Karar |
|---|---|---|
| `dogrulama` (L0) | Lumoda'nın 1-2-2-1-1'i; İlk Sevkiyat `lumoda` koşusunu birebir üretir | spec §0/16 |
| `p1` | tek 7'li desen, 1-1-2-2-1 her yere | R10 |
| `p2` | iki 7'li desen, profile göre | R10 |
| `p1_12` | tek 12'li desen, 1-3-4-3-1 | R10 |
| `p3_12` | üç 12'li desen (K = 3) | R10 |
| `p2_12` | iki 12'li desen (K = 2); demonun 2 / 12 bileşimi ölçülmüş olsun | R21 |
| `p1_14` | ayrıştırma kontrolü: 2-2-4-4-2 (P1'in tam iki katı); aynı beden payı, daha büyük paket; `ns` aşağı yuvarlanır | R22, R23 |
| `pm_12`, `p2_ham` | tasarımı `p3_12` ve `p2` ile aynı olduğu için koşulmaz, kaydı `ayni` ile bağlanır | R10 |

Kararlar:

- **R10 kol seti.** 7'li pakette K sorusu K = 2'de biter (temel bedenler ≥ 1 ile aday desen 70), bu
  yüzden P3, P4 ve mağazaya özel 7'li koşulmaz; rapor K eğrisini uyumsuzlukla basar ve "K ≥ 2 aynı" der.
  Paket büyüklüğü ana soru olur: 12'li kollar yol 0'da. Yollar 1-4'te `dogrulama`, `p1`, `p2`, `p3_12`.
- **R15 kahin kolu koşulmaz.** Kahinin ataması (P2'nin desenlerini gerçek beden payına göre atamak)
  P2'den yalnız M027'de ayrışır (giden paketin %2,1'i); okunabilen 68 mağazada profil ARI 1,000. Rapor
  farkı koşusuz basar.
- **R20, R22 ayrıştırma.** 12'li kolların farkı kısmen `ns` dönüşümünden gelebilir; "12'li daha iyi"
  iddiası ayrıştırılmadan yazılamaz. Lumoda'nın 12'li karşılığı (2-3-3-2-2) 1. bedende depoyu aşar (depo
  payı 0,1429, 12'li oranlı desen 2/12 = 0,1667 ister) ve kurulamaz. İçeriği aynı tutan tek temiz kontrol
  P1'in iki katı 14'lü 2-2-4-4-2'dir: `p1_14 − p1` yalnız paket büyüklüğünün, `p1_12 − p1` içerik
  inceliği ile büyüklüğün etkisidir.
- **R21** `p2_12` ayrı koşudur (12'li K eğrisi eksiksiz).
- **R23** `p1_14`'te `ns` aşağı yuvarlanır (en yakına yuvarlama tek paket sayılı 103 option'da 1. bedeni
  bir paket aşıyordu); toplam 721 adet az (812.308 / 813.029, %0,09; option başına en çok 7). Kontrol kolu
  Lumoda'dan %0,09 az mal gönderir; rapor farkı basar.
- **R11** Tasarım depo kısıtını toplamda (bütün option'lar) uygular; option başına kırpma ölçülür ve
  korunumda raporlanır.
- **R12** Desenler ve `ns` yalnız SS25 Collection oyun option'larına uygulanır (193 beş bedenli);
  öteki option'lar Lumoda'nın standart paketiyle (İlk Sevkiyat'ın oyun kapsamı).
- **R7, R8, R9** Eğri kararları (okunabilirlik eşiği, κ ızgara ucu, yeni mağaza yedek kuralı) Sınırlar'da.

## Sonuçlar

SS25 karar günü, SS25 Collection ilk dağıtımı; 210 option = beş bedenli 193 + tek bedenli 17. Sayılar
`cikti/rapor.txt`'ten, yuvarlama raporun biçiminde. Bulunabilirlik ve tam fiyat STR için artış; beden
kaybı, kırık set ve sezon sonu kalan için düşüş iyidir.

**Veri ve paket.** 69 aday mağaza (eğrisi okunabilen 68; M027 İzmir 2 okunamayan). `ns`: 5.351 hücre,
118.003 paket. Lumoda'nın paketi her beş bedenli sette tek: 1-2-2-1-1 (beden payı %14,3 / %28,6 / %28,6 /
%14,3 / %14,3); zincir satış eğrisi %10,2 / %21,8 / %31,1 / %24,5 / %12,3. Lumoda replenishment payları
%3,3 / %10,8 / %36,2 / %41,6 / %8,1: paketin eksiğini kapatıyor. 1. beden ilk dağıtımda tükeniyor (paket
1. bedeni depo kadar istiyor).

**SORU 1 · Lumoda'nın paketi zincirin ve mağazaların eğrisinden ne kadar uzak?** L1 zincire 0,255,
mağaza eğrilerine ortalama 0,293 (en az 0,138, en çok 0,407, M048); gerçek talep payına (hakemli)
ortalama 0,274. Paket başına beklenen eksik adet 0,949; en iyi tek 7'li paket 1-1-2-2-1 için 0,853 (en
iyi tek paket Lumoda'nınki değil).

**SORU 2 · Satıştan okunan eğri gerçeğe ne kadar yakın?** Gerçek talep payına ortalama L1 (hakemli, 68
mağaza): ham 0,0530, sansür düzeltmeli 0,0337, daraltılmış (son eğri) 0,0333, profil eğrisi 0,0329,
zincir 0,1634. Sansür büyüklüğü ortalama 0,53 puan, en çok 2,01 puan; daraltma sonucu değiştirmiyor
(−0,0004; w medyanı 0,908). κ 12.800, ızgaranın üst ucunda; tablo aralığı 0,027646 … 0,027899. Kararlılık:
SS24 ↔ SS25 düzeltilmiş eğri, 66 ortak mağazada ortalama L1 0,0061.

**SORU 3 · Kaç beden profili; satış kümelerinden bağımsız mı?** 3 profil (buyuk 28 · kucuk 19 · orta
22); profilin hakeme ARI'si 1,000; Kümeleme'nin satış kümeleriyle ARI −0,014 (bağımsız, iki ayrı eksen).
Profiller: küçük %15,8 / %27,7 / %30,4 / %18,1 / %8,1; orta %9,6 / %21,4 / %33,9 / %23,5 / %11,5; büyük
%7,1 / %16,2 / %28,2 / %30,6 / %18,0.

**SORU 4 · Kaç paket tipi ne kazandırıyor?** Tasarım (uyumsuzluk, paket başına eksik adet): 7'li K 1
0,8533 · K 2 0,5835 (K 3, 4 ve mağazaya özel K = 2 ile aynı; Lumoda 0,9487); 12'li K 1 1,3146 · K 2
0,6826 · K 3 0,5484 (K 4 ve mağazaya özel K = 3 ile aynı). Yol 0, Lumoda'ya göre fark (parantez içi
Lumoda'dan fark, iki ondalıklı puan):

| Kol | İlk 4 hf bulunabilirlik | İlk 4 hf beden kaybı | İlk 4 hf kırık set | Sezon bulunabilirlik | Sezon beden kaybı | Brüt kâr |
|---|---|---|---|---|---|---|
| L0 Lumoda 1-2-2-1-1 | %96,47 | %58,06 | %2,37 | %68,98 | %42,31 | 534.433.105 TL |
| P1 tek 7'li | %96,51 (+0,04) | %58,38 (+0,32) | %2,20 (−0,17) | %69,05 (+0,07) | %41,58 (−0,73) | 535.940.376 TL (+1.507.271) |
| P2 iki 7'li | %96,64 (+0,17) | %56,48 (−1,58) | %1,89 (−0,48) | %69,24 (+0,26) | %39,98 (−2,33) | 540.277.650 TL (+5.844.545) |
| P1 14'lü 2-2-4-4-2 | %96,53 (+0,06) | %58,33 (+0,27) | %2,19 (−0,18) | %69,09 (+0,11) | %41,47 (−0,84) | 536.348.012 TL (+1.914.907) |
| P1 tek 12'li | %97,09 (+0,62) | %48,46 (−9,60) | %1,79 (−0,58) | %69,49 (+0,51) | %30,41 (−11,90) | 541.634.844 TL (+7.201.739) |
| P2 iki 12'li | %97,08 (+0,61) | %48,83 (−9,23) | %1,66 (−0,71) | %69,75 (+0,77) | %28,76 (−13,55) | 545.457.931 TL (+11.024.826) |
| P3 üç 12'li | %97,06 (+0,59) | %49,37 (−8,69) | %1,70 (−0,67) | %69,68 (+0,70) | %27,76 (−14,55) | 545.511.071 TL (+11.077.966) |

7'li pakette kazanç K = 2'de doyar: 7'li K = 2 − Lumoda, ilk 4 hf bulunabilirlik +0,17 puan (+0,2), ilk 4
hf beden kaybı −1,58 puan (−1,6), ilk 4 hf kırık set −0,48 puan (−0,5), brüt kâr +5.844.545 TL. 12'li K =
3 − Lumoda: +0,59 puan (+0,6) · −8,69 puan (−8,7) · −0,67 puan (−0,7) · +11.077.966 TL. 12'lide K = 1'den K
= 3'e (P3 12'li − P1 12'li): ilk 4 hf bulunabilirlik −0,03 puan (0,0), ilk 4 hf beden kaybı +0,91 puan
(+0,9), ilk 4 hf kırık set −0,09 puan (−0,1), sezon beden kaybı −2,65 puan (−2,7), brüt kâr +3.876.227 TL.

**SORU 5 · Mağazaya özel paket ile 3 paket tipi arasında ne kalıyor; doğru okumak ne kadar ileride?**
7'li mağazaya özel = K 2; 12'li mağazaya özel = K 3 (P3): ek kazanç yok. Kahin atamayı yalnız M027'de
değiştirir (giden paketteki payı %2,1): gerçek paya göre uyumsuzluk 66.440,6 → 64.833,8 (−%2,4).

**SORU 6 · Paket büyüklüğü (7 → 12) neyi değiştiriyor?** 12'li P3 − 7'li P2: ilk 4 hf bulunabilirlik
+0,42 puan (+0,4), ilk 4 hf beden kaybı −7,11 puan (−7,1), ilk 4 hf kırık set −0,19 puan (−0,2), sezon
bulunabilirlik +0,44 puan (+0,4), sezon beden kaybı −12,22 puan (−12,2), brüt kâr +5.233.421 TL; adet
farkı +103 (aynı mal yaklaşık). Ayrıştırma: yalnız büyüklük (P1 14'lü − P1), ilk 4 hf bulunabilirlik
+0,02 puan (0,0), ilk 4 hf beden kaybı −0,05 puan (−0,1), brüt kâr +407.636 TL; içerik inceliği ile
büyüklük (P1 12'li − P1): +0,58 puan (+0,6) · −9,92 puan (−9,9) · brüt kâr +5.694.468 TL. Büyüklük tek
başına ölçülebilir bir şey değiştirmiyor; fark 12 adetin beden payını daha ince çözmesiyle birlikte
geliyor.

**Yollar (5 talep yolu).** Kaç yolda önde, medyan fark. P2 iki 7'li − L0: ilk 4 hf bulunabilirlik 5/5
(+0,22), ilk 4 hf beden kaybı 5/5 (−1,08), sezon beden kaybı 5/5 (−2,29), brüt kâr 5/5 (+5.607.497 TL). P3
üç 12'li − L0: ilk 4 hf bulunabilirlik 5/5 (+0,62), ilk 4 hf beden kaybı 5/5 (−8,69), sezon beden kaybı
5/5 (−13,96), brüt kâr 5/5 (+10.842.933 TL). P1 tek 7'li − L0: ilk 4 hf bulunabilirlik 5/5 (+0,05), ama
ilk 4 hf beden kaybı yalnız 1/5 (+0,32); sezon beden kaybı 5/5 (−0,47). P2 − P1 ve P3 12'li − P2 7'li bütün
başlık ölçütlerinde 5/5. Bir ondalıklı medyanlar: P2 7'li − L0 ilk 4 hf bulunabilirlik +0,2, ilk 4 hf
beden kaybı −1,1; P3 12'li − L0 +0,6 ve −8,7.

**Replenishment eğriyi bilir, fark yine de sezon boyunca büyür.** P3 12'li − L0 beden kaybı farkı ilk 4
haftada −8,69 puan, sezonda −14,55 puan. Spec §0/12'nin "fark ilk haftalarda yoğun olur" beklentisi
tutmadı. Depoda kalan pay (L0: 4. beden %58,3 · 5. beden %16,6; P3 12'li: %27,4 · %32,7) bunu
açıklıyor olabilir; bu bir yorumdur, ölçülmedi.

**Hikâye.** Büyüğe kayık sahne M049 Konya 3 (Veli'nin; MDL0279-BEJ, 5 paket 1-2-2-1-1, 35 adet; 4. beden
1., 5. beden 3. haftada biter, 1. beden rafta kalır) ve küçüğe kayık M018 İstanbul 18 (Ali'nin; MDL0279-BRD,
13 paket, 91 adet; 1. beden 3. haftada biter, 5. beden rafta kalır); kademe 4; gizli kayma +1 / −1, ikisi
de doğru. Alternatif (kademe 5, roller ters): M017 İstanbul 17 (büyük) – M064 Gaziantep 2 (küçük). Şartsız
seçilecek sahne büyük M062 (MDL0397-EKR), küçük M018 (MDL0376-KRM), kademe 3.

**Demo.** 10 bileşim (paket tipi sayısı {1, 2, 3, 4, magaza} × büyüklük {7, 12}); 7'li K = 3, 4, magaza
`p2`'nin, 12'li K = 4, magaza `p3_12`'nin ikizidir. Kartlar ilk 4 hafta bulunabilirlik, beden kaybı,
kırık set, brüt kâr. Sürüm `7779baef4be0`.

**Korunum.** Rapor KORUNUM bölümünde 120 denetim tuttu: doğrulama kolu, aynı mal ve kırpma (her kol,
her yol), İlk Sevkiyat anahtarları, tasarım kayıtları, K eğrisi, hikâye, demo bileşimleri ve site
dosyası, veri sayımları.

## Sınırlar

- **Cevap anahtarı gerçek hayatta yok.** Gizli `beden_kayma` simülatörün kurgusudur; hakemli L1 ve ARI
  yalnız bu vakada ölçülebilir. Gerçek bir zincirde elde yalnız hakemsiz ölçütler vardır (iç tutarlılık,
  kararlılık, SS24 gerçekleşen paylara uyum, karar kalitesi); rapor bunları ayrıca kurar. Profilin hakeme
  ARI'sinin 1,000 olması, kaymanın mağaza düzeyinde, kategoriden bağımsız ve üç değerli kurulduğu
  sentetik bir dünyanın sonucudur.
- **Kayma kırpılır (R4).** Üretici {−1, 0, 1, 2} çekiyor, talep [−1, 1]'e kırpıyor; hakem gerçeği talebi
  süren kırpılmış değerdir. Ham çekilişte +2 olan 13 mağaza talepte +1'le aynıdır.
- **Sansür küçük.** Biten bedenin talebi kısmen komşu bedene kayar (beden ikamesi); ham ↔ düzeltilmiş
  fark ortalama 0,53 puan, en çok 2,01 puan (yalnız Collection hattında en çok 4,89). Yöntem düzeltmeyi
  yine kurar; sansürün büyük olabileceği gerçek bir veride bunun ölçüsü bu vakada görünmez. Düzeltme 7'li
  tasarımı değiştirmez (`p2_ham` tasarımı `p2` ile aynı).
- **Daraltma etkisiz (R6).** Bu veride mağaza başına örnek bol (w medyanı 0,908, en az 0,732); daraltma
  L1'i −0,0004 değiştirir. Yöntemde kalır; az veriyle çalışan bir zincirde farklı çıkabilir.
- **κ ızgara ucunda (R8).** Seçilen κ 12.800; ızgara sonuç görüldükten sonra genişletilmedi. Tablo düz
  (0,027899 → 0,027646); daha büyük κ biraz daha iyi olabilirdi, etkisi önemsiz.
- **Eğri havuzdan (R5).** Eğri Collection ve Basic/NOS havuzundan okunur; hakemsiz ölçüt (SS24 gerçekleşen
  paylara uyum) havuzu seçer, hakemli ölçüt Collection hattını seçerdi (hakemli L1 0,0337 yerine 0,0291).
  Rapor ikisini tanı satırı olarak basar.
- **Yeni mağaza yedek kuralı neredeyse eşitlikte (R9).** Bırakbir L1 profil 0,17421, zincir 0,17511;
  profil kıl payı seçildi. M027 için hakemce kötü bir seçim (profil L1 0,4344, zincir 0,2451 olurdu); tek
  mağaza, giden paketin %2,1'i. M041 (19 hafta) kendi eğrisini w 0,784 ile alır (R7).
- **Satın alma sabit.** Sipariş adedi ve beden dağılımı yayımlanan dünyadaki gibidir (spec §0/4); dizi
  ilk sevkiyattaki paket içeriğini ölçer. Paket tipi sayısının tedarikçi maliyeti verilmez: K eğrisi okura
  bırakılır.
- **Paylar Lumoda'nın.** Mağazaya kaç paket gideceği Lumoda'nın giden paketidir (spec §0/6, §0/11);
  İlk Sevkiyat'ın en iyi pay koluyla birleşimi ölçülmedi.
- **Replenishment eğriyi biliyor.** Simülatörde Lumoda'nın planı gizli kaymayı içerir; replenishment
  mağazanın bedenini ilk pazartesiden gönderir (R1). Bu Lumoda'nın gerçeği olarak alındı; başlık
  ölçütleri bu yüzden ilk haftalardır. Buna rağmen kollar arası fark sezon boyunca küçülmez, büyür (P3
  12'li − L0 beden kaybı: ilk 4 hf −8,69, sezon −14,55). "Replenishment sonradan düzeltir" savı bu veride
  ölçüme aykırıdır; depoda kalan paya bağlamak yorum olarak kalır. "Replenishment zincir eğrisiyle" kolu
  koşulmadı.
- **12'li ve 14'lü kollar yaklaşık aynı mal.** `ns`, mağaza × option giden adedin dönüşümüdür (12'li:
  +103 adet, 193 option, option başına en çok 6; 14'lü: −721 adet, %0,09). Lumoda'nın kendi 12'li
  karşılığı depo yüzünden kurulamaz (R22); 12'li üstünlüğünü ayrıştırmak için yalnız P1'in 14'lü ikizi
  vardır.
- **Depo tanımı (R16).** Tasarım ilk sipariş adedinden kurulur; hatalı düşülmüş depo karar gününden
  sonraki teslim bilgisi taşıyabilir. İki tanımda tasarımlar aynıdır ve gerçekçi depo hiçbir yerde
  bağlamaz; 7'li pakette 1. beden tam depo sınırındadır (1/7).
- **Kahin tek mağazada ayrışır (R15).** Profil okunabilen 68 mağazada hakemle aynı olduğundan "doğru
  okumak ne kadar ileride" sorusunun cevabı bu vakada tanım gereği yaklaşık sıfırdır (yalnız M027, %2,1).
- **Tek zincir, tek karar günü.** Sentetik tek zincir, 69 aday mağaza; karar günü SS25 (SS24 yalnız κ
  kalibrasyonu ve kararlılık için). Üç profil, beş yol; sonuçların başka bir zincire taşınabilirliği
  ölçülmedi.
- **Sahne gevşetildi (kademe 4).** Hikâye merdiveninin 4. basamağı: erken 4 hafta, benzer option, geçmiş
  bir AW sezonu. "Hedef bedenler öteki bedenlerden önce biter" şartı, gerçek veride zayıf bir sahne
  görüldükten sonra eklendi (ilk tasarımda yoktu); şartsız seçilecek sahne farklıdır (Hikâye, yukarıda).
  Yazı gevşetmeyi dürüstçe söyler. Alternatif sahne kademe 5'tir (roller ters).
- **Açık beden seçeneği ölçülmedi.** Paketin açılıp bedenlerin tek tek gönderildiği seçenek bu dizinin
  kollarında yoktur; yazı 2 ne zaman düşünüleceğini anlatır, ölçülmüş sonuç vermez.
- **Terim (R25).** Sitenin yerleşik terimi "koli"dir (sözlükte "paket" ve "prepack" eşanlamdır); kod ve
  rapor `paket` der. Aynı kavram: paket (kodda) = koli (sitede).

## Dosyalar

`beden_paket/`: `sabitler` (simülasyon anahtarında), `kaynak` (kapsam, beş bedenli ayırıcı), `egri` (eğri
ve profil), `paket_tasarim` (K desen arama), `politika` (paket satırları, atama), `simulasyon`, `kosucu`
(koşucu, doğrulama, ölçüm), `oyun` (ızgara, yol, ölçüm özeti), `hakem` (gizli gerçek, yalnız ölçüm),
`olcutler_egri`, `hikaye_sec`, `hikaye_kos`. Vaka kökünde `analiz.py` (koşusuz tanılar), `senaryolar.py`
(demo), `rapor.py`. Testler `tests/` altında; karar modüllerinin kilidi `tests/test_sizinti.py`.
