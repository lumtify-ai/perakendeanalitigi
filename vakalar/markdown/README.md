# İndirim takvimi (markdown)

Lumoda v4 sentetik verisinde indirim (markdown) vakası (İndirim, promosyon ve kampanya aşaması, 1. dizi):
talebin indirime tepkisinden option başına haftalık indirim yolunu seçmek; serbest ana kolu, takvime bağlı
kontrolü, kapsama kuralını ve gerçek girdili kahini v4 motorunda aynı malla Lumoda'nın kuralıyla kıyaslamak.
Tasarım: `docs/superpowers/specs/2026-10-23-indirim-takvimi-design.md` (`docs/` ayrı depodur; uygulamadaki
sapmalar spec §12'de ve SDD kayıt defterinin Ruling'lerinde, R1–R32).

Sitedeki dizinin (`site/src/content/yazi/indirim/indirim-takvimi/`, 6 yazı: İki Lacivert Tulum, Bu Karar Nasıl
Verilir, Kural Tabanlı Yöntem, İndirim Ne Kadar Sattırır, Takvimi Kurmak, Başarı Nasıl Ölçülür) ve demo
kadranının (18 bileşim, `site/src/data/senaryolar/indirim-takvimi.json`) bütün sayıları buradan,
`cikti/rapor.txt`'ten çıkar (`cikti/` git dışıdır; dosyayı `rapor.py` yeniden üretir). Bu dosya sayı vermez:
sonuçlar rapordadır, aşağıda hangi bölümde olduklarıyla anılır. Okuma sırası: Kurulum → Koşum → Önbellek →
Tanımlar → Kollar → Sonuçlar → Sınırlar.

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

Kütüphane sürümleri İlk Sevkiyat vakasının `.venv`'iyle aynıdır ve koşu önbelleğinin anahtarındadır
(numpy, pandas, pyarrow, duckdb, lightgbm, scikit-learn; `allocation.motor.SURUM_PAKETLERI`): biri değişirse
bütün koşular yeniden simüle edilir ve rapor eski koşuları reddeder. `allocation` ve `kumeleme` `--no-deps`
kurulur; hiçbir sürüm değişmemelidir.

**Veri.** `veri/cikti/v4/perakende.duckdb` (ya da `PERAKENDE_V4_DB`). Yoksa yayımlanan `veri-v4`
dosyalarını indirin ya da `cd veri && python -m perakende_veri.v4.uret`. Dosyanın parmak izi (ad, boyut,
değişiklik zamanı) koşu anahtarındadır: dosyayı yeniden üretmek ya da kopyalamak bütün ızgarayı geçersiz kılar.

## Testler

Komutlar vakanın `.venv`'iyle, `vakalar/markdown` içinden; Windows konsolunda `PYTHONIOENCODING=utf-8`.

    .venv/Scripts/python -m pytest tests -q -m "not veri"     # hızlı takım: oyuncak fikstür ve KÜÇÜK dünya (~5 dk)
    .venv/Scripts/python -m pytest tests -q                   # hepsi (gerçek veri testleri dahil)

`veri` işaretli testler yayımlanan v4 verisini okur ve v4 dünyasını (`allocation.motor.dunya`, ~20 sn) kurar.
`test_esdegerlik_tam` (`tests/test_simulasyon.py`) yol 0 Lumoda koşusunu TAM'da koşar (önbellekte değilse ~3,5
dk, tepe ~7,2 GB) ve yayımlanan v4'le tablo tablo satır sayısı ve satış toplamıyla karşılaştırır.

## Koşum

Komutlar `vakalar/markdown` içinden, bu sırayla; Windows konsolunda `PYTHONIOENCODING=utf-8`. TAM koşular
sıralı ve arka planda koşar; yarıda kalan ızgara önbellekten sürer. Süreler bu makinede ölçülendir.

    # 0. eşdeğerlik: yol 0 Lumoda = yayımlanan v4 (~3,5 dk; koşu önbelleğe girer)
    .venv/Scripts/python -m pytest tests -q -m veri -k esdegerlik_tam
    # 1. kalibrasyon: 18 koşu (kural α 6 değer, tekdüze 3 oran × AW23, SS24), cikti/kalibrasyon.json (~45 dk)
    .venv/Scripts/python -m markdown.oyun kalibrasyon
    # 2. ızgara: yol 0 (lumoda + 8 kol × 2 sezon; ~40 dk), ablasyon (R24, 4 koşu; ~10 dk),
    #    yollar 1–4 (her yolda lumoda + 6 kol × 2 sezon = 52 koşu; yol başına öğrenme ~10–15 dk; ~3,5–4 sa)
    .venv/Scripts/python -m markdown.oyun izgara --blok yol0
    .venv/Scripts/python -m markdown.oyun izgara --blok ablasyon
    .venv/Scripts/python -m markdown.oyun izgara --blok yollar        # --yol P ile tek yol
    # 3. ölçüm: önbellekteki bütün koşuları bugünkü ölçüm koduyla yeniden ölçer, koşmaz
    #    (~10 sn/koşu, artı yol başına öğrenme ve kahin girdisi; tahminen 30–60 dk)
    .venv/Scripts/python -m markdown.oyun olc                         # --zorla: ölçüm kodu aynı olsa da
    # 4. koşusuz veri analizi (VERİ bölümü): cikti/analiz.json (~1 dk)
    .venv/Scripts/python analiz.py
    # 5. hikâye: iki tulum, gömlek, karar anı, pazartesi listesi; cikti/hikaye.json
    .venv/Scripts/python -m markdown.hikaye
    # 6. demo dosyası: site/src/data/senaryolar/indirim-takvimi.json
    .venv/Scripts/python senaryolar.py
    # 7. rapor: yazıların bütün sayıları
    .venv/Scripts/python rapor.py > cikti/rapor.txt

**Bellek.** Bir TAM koşu ~8 GB; süreç tepesi yol p > 0'ın öğrenme adımında (yayımlanan biçimin kurulması ve
öğrenme) ~13 GB (`cikti/ilerleme.jsonl`'ın `y<p>_ogrenme_*` satırlarında `surec_tepe_gb`). Yol p'nin öğrenmesi o yolun Lumoda koşusunun yayımlanan biçimini
geçici bir DuckDB dosyasından okur (R19; `%TEMP%`'te ~1–2 GB, öğrenmeden sonra silinir; sert öldürülen süreç
bırakabilir). Disk: TAM koşu önbelleği (`cikti/kosular/`) 91 koşu için ~15 GB.

**Aynı önbelleğe iki süreç yazmaz.** `oyun`'un her koşusu `cikti/kosular/`'daki, kendi sürecinden önce kalmış
`.yaziliyor-*` dizinlerini siler (İlk Sevkiyat motoru): TAM ızgara yazarken aynı dizinde ikinci bir `oyun`
(ölçüm ya da KÜÇÜK ızgara dahil) yazılmakta olan koşuyu silebilir. KÜÇÜK denemeleri ayrı bir `onbellek`
(`oyun.Ortam(onbellek=...)`) ile ya da ızgara bittikten sonra koşun.

**KÜÇÜK ölçek** (geliştirme): `oyun kalibrasyon|izgara|olc --olcek KUCUK`, `analiz.py --olcek KUCUK`,
`python -m markdown.hikaye --olcek KUCUK`, `senaryolar.py --kucuk`, `rapor.py --kucuk` (çıktılar `cikti/kucuk/`;
rapor her zaman taslaktır, yazılara kaynak olamaz).

**Rapor** (`rapor.py`) veriyi okumaz, simülasyon koşmaz: `oyun.json`, `kalibrasyon.json`, `analiz.json`,
`hikaye.json` ve demo dosyasını basar. Bir girdi eksik ya da eskiyse ya da bir korunum denetimi bozulursa stdout
boş kalır, mesaj stderr'e gider, çıkış 1. Eski sayılan: ızgaranın bir koşusu oyun.json'da yok, bugünkü ölçüm
koduyla ya da yolunun bugünkü Lumoda koşusuyla ölçülmemiş; koşunun önbellek dizini yok ya da `meta.json`'u
bugünkü vaka kod özetiyle, İlk Sevkiyat kod özetiyle, v4 parmak iziyle, kütüphane sürümleriyle (R24 kollarında
`politika_ablasyon.KOD`'la) koşulmamış; `analiz.json` bu oyun.json'un yol 0 Lumoda'sından değil ya da
`analiz.json`, `hikaye.json`, `kalibrasyon.json` bugünkü kodla yazılmamış; demo dosyası `senaryolar.uret()`'le
aynı değil. Kısmi bir yeniden koşu böylece eski kodla koşulmuş kayıtları rapora sokamaz. `--taslak` eksik
girdiye dayanan bölümleri atlar (çıkış 2). `analiz.py`, `rapor.py`, `senaryolar.py` paket dışında, vaka
kökündedir: paketin içinde olsalardı sınıflandırma ve kilit testleri onları ölçüm modülü olarak isterdi.

Sayı denetimi (yazılar yazıldıktan sonra; çıkış 0 olmalı):

    .venv/Scripts/python -m perakende_analitik.sayi_denetimi --yazi ../../site/src/content/yazi/indirim/indirim-takvimi --rapor cikti/rapor.txt

## Simülasyon ve önbellek

**Koşu** (`markdown.simulasyon.kos`): İlk Sevkiyat'ın motor adımları, vakanın yuvalarıyla. Markdown yuvasına
kol, öteki yuvalar Lumoda'nın; kol test option'larının normal ve online oranını kendisi tutar, outlet hattını ve
test dışı option'ları Lumoda'nın kuralına bırakır (`politika.Sarmalayici`).

- **Aynı mal, RPT yeniden oynatma (R4).** Her kolda RPT yuvası aynı yolun Lumoda koşusunun kayıtlı RPT
  kararlarının yeniden oynatılmasıdır (`allocation.politika.TakvimRPT`, bütün option'lar; takvimin içerik
  kimliği kolun anahtarında). İndirim ikame yoluyla öteki option'ların satışını ve tepkili bir RPT'yi
  değiştirebilirdi; takvimle bütün kollarda RPT siparişleri ve arz birebir aynıdır, kollar arası katkı farkı ciro
  farkıdır. Korunum bunu sonuçla sınar (`olcutler.korunum`: `rpt_birebir`, `ilk_dagitim_birebir`,
  `arz_birebir`); tutmayan koşu geçersizdir, rapor reddeder. Bedel: Lumoda RPT'sinin indirime tepkisi ölçülmez.
- **Koşu başına tek test sezonu (R5).** Bir karar koşusu yalnız bir test sezonunun (AW24 ya da SS25) 210
  Collection option'ında karar verir, öteki sezon Lumoda'nındır; iki sezonun toplamı iki koşunun toplamıdır
  (`oyun.json` `toplamlar`). İki sezon kış sonunda aynı gruplarda ikame ve elle transfer yoluyla birbirine sızar;
  tek koşuda ikisini birlikte değiştirmek sezon farkını karıştırırdı.
- **Açık siparişler (R28).** Optimizasyon ve kahinin satılabilir stoğu raf + yolda + depo + planlanan teslimi
  çıkıştan önce olan açık siparişlerdir (gerçekleşmemiş RPT; depo gibi talep payıyla hücrelere bölünür). Kural
  da açık siparişi sayar (çıkıştan sonra planlananı da); kıyas aynı stok bilgisiyle kurulur.

**Koşu önbelleği** `cikti/kosular/<ad>_<anahtar[:20]>`. Anahtar (`simulasyon.hazirla`): ad, parametreler, yol,
enjekte edilen yuvaların türü ve kimliği (kolun `parametreler()`'i: kip, pencere, taban, ε kaynağı, α, tekdüze
oran, test option'ları, `Ogrenilen.kimlik()`, kahin girdisinin içerik kimliği; RPT takviminin kimliği),
tohumlar, ölçek, İlk Sevkiyat kod özeti, v4 parmak izi, kütüphane sürümleri ve `vaka`: bu paketin
`SIMULASYON_MODULLERI`'nin (`__init__`, `sabitler`, `kaynak`, `ogrenme`, `tahmin`, `model`, `politika`,
`simulasyon`) ve onların ortak paket kapanışının içerik özeti.

**Uyarı.** `SIMULASYON_MODULLERI`'ndeki bir dosyada tek bir bayt değişikliği (docstring ya da yorum dahil;
yalnız CRLF/LF farkı sayılmaz) bütün ızgaranın anahtarını değiştirir: 91 TAM koşu yeniden simüle edilir (~6 sa). Ölçümü, raporu ya da
hikâyeyi değiştiren düzeltmeler bu dosyalara girmez; `sabitler.py`'ye yalnız simülasyonu değiştiren sabit
konur, ölçüm ve ızgara sabitleri kendi modüllerindedir (ör. `oyun.KAL_DEGERLERI`, `oyun.OLCUM_SURUMU`).

**Anahtar sözleşmesinin tek istisnası (R24).** Kuralın ayrıştırma kolları (`kural_takvim`, `kural_deposuz`)
`markdown/politika_ablasyon.py`'dedir ve bu modül bilerek `SIMULASYON_MODULLERI`'nin dışındadır: TAM ızgarası
koşarken eklendi ve vaka kod özetine girseydi koşan ızgaranın bütün önbelleği geçersizleşirdi. Onun yerine her
ablasyon kolunun `parametreler()`'i `kod` alanında kendi kod özetini taşır (`politika_ablasyon.KOD`:
`politika_ablasyon.py`, `politika.py`, `model.py`, `tahmin.py`); bu dosyalardan biri değişince yalnız bu iki
kolun anahtarı değişir (testli). Bu asimetri bir hata değildir: modülü `SIMULASYON_MODULLERI`'ne eklemek
"düzeltme" gibi görünür ama 91 koşunun hepsini geçersiz kılar. Sınıflandırma testi modülü üçüncü kümede tutar
(`tests/test_sizinti.py` `ABLASYON_MODULLERI`); kilit karar modüllerininkiyle aynıdır.

**Ölçüm önbelleği** (Beden ve Koli R14/R18 kalıbı). Ölçüm koşu önbelleğinden yeniden hesaplanır; `oyun.json`
kaydı koşu anahtarı, Lumoda anahtarı ve ölçüm kodu (`oyun.OLCUM_OZETI`: `olcutler.py`, `hakem.py`, `oyun`'un
`OLCUM_FONKSIYONLARI`, `KOLLAR`, `OLCUM_SURUMU`) aynıysa yeniden ölçülmez. Ölçümü değiştiren bir düzeltme
koşuları yeniden simüle ettirmez, `oyun olc` ister. Bu kapsamın dışında ölçümü değiştiren bir düzeltmede
`OLCUM_SURUMU` bir artırılır. `analiz.json` ve `hikaye.json` kendi kod özetlerini taşır (`analiz.kod_ozeti`,
`hikaye.kod_ozeti`).

**Öğrenme önbelleği** `cikti/ogrenme/`: günlük tablo ve çarpanlar, kaynak kimliği (yol 0'da yayımlanan dosya,
yol p'de o yolun Lumoda koşusunun anahtarı), sezon, bitiş ve `ogrenme.py` ile içe aktardığı ortak modüllerin kod
özetiyle (R14).

## Gün ekseni

Dünyanın gün indisi 0 = 2022-07-04 (ısınma başı, pazartesi; `perakende_veri.v4.takvim.gun_indisi`).
Yayımlanan tablolar 2023-01-01'den başlar ama `optionlar`'ın `lansman_gun`, `indirim_gun`, `cikis_gun`
sütunları bu eksendedir; gün `d` pazartesidir <=> `d % 7 == 0` (`sabitler.GUN_SIFIRI`, R7). Motor markdown'ı
her pazartesi ve her sezonun indirim gününde çağırır; AW23'ün indirimi salı, AW24'ünkü perşembedir.

## Kaynak, karar penceresi, öğrenme ve tahmin

`kaynak.yayimlanan_tablolar(con, adlar, bitis=None)`: `gizli_*` tablosu reddedilir; `bitis` verilirse
gözlenen olay tabloları o günden önceye kesilir; kampanya, sezon, takvim gibi açık plan tablolarına dokunulmaz.
`kaynak.test_optionlari(optionlar, sezonlar)`: sezonların Collection option'ları. `kaynak.karar_penceresi`:
ilk indirim yapılabilecek en erken gün; serbest kipte `max(indirim_gun − 56, lansman_gun + 42)`'nin ilk
pazartesisi (R9), takvim kipinde `indirim_gun` (yuvarlamasız).

`ogrenme.ogren(con, test_sezonu, bitis, ...)` test sezonunun en erken karar pazartesisinden
(`sabitler.OGRENME_BITIS`) önceki yayımlanan satırlardan bir kez öğrenir: ortak paketin kampanya ve markdown
esnekliği (ε̂), hafta günü, özel gün ve beden payı; saf regresyon ε'si (yalnız rapor); aynı tip kapanmış
sezonlardan alt kategori × dalga yaşam eğrisi; kalıntı değeri; kanal başına iade ve işlem indirimi payı.
`tahmin.Tahminci` her pazartesi option başına hücre × hafta tam fiyat taban talebini, satılabilir stoğu ve
fiyat çarpanlarını yalnız `Gorunum`'den ve dünyanın açık alanlarından kurar. Son 28 günde satışı olmayan
mağaza-hücrenin talebi 0'dır (R13). `model.coz` haftalık dinamik programdır: durum (hafta, kademe, kalan stok
ızgarası), karar bir sonraki kademe (oran geri alınmaz), son değer kalıntı × liste × kalan; uygulanan yalnız ilk
haftanın basamağıdır (kayan ufuk). Tanımlar modül belgelerinde.

## Tanımlar

Ayrıntı modül notlarında (`markdown/olcutler.py`, `analiz.py`); burada raporda karşılaşılan adlar. Kapsam
koşunun test sezonunun Collection option'larıdır (TAM'da sezon başına 210); option için lansman L, indirim I,
çıkış C.

- **Sezon katkısı** (`katki`, ana ölçü): toplam net ciro (sezon L → C ve outlet penceresi C → C + 84; iade
  satırları negatif) − teslim edilmiş ilk + RPT arzın alış değeri. Arz kollar arasında aynı olduğu için (R4)
  kollar arası katkı farkı ciro farkıdır. Brüt kâr satılan malın alışını düşer; ikisi ayrı basılır.
- **Markdown TL (R21).** Yazıların ve raporun her bölümünün tek tanımı `olcutler`'inkidir: pozitif satış
  satırları (iadeden önce), kampanyasız, normal ya da online hat, satırın günlük markdown oranı > 0, L ≤ gün < C;
  Σ indirim tutarı. Kampanyalı satırlar kampanya TL'si, oranı 0 olan kampanyasız satırların indirimi işlem
  indirimi TL'sidir (motorun %8 olasılıklı işlem indirimi). Outlet indirimi: outlet hattı, C ≤ gün < C + 84.
  Spec §0'ın keşif sayıları iade düşülmüş, indirim dönemi penceresiyle ölçülmüştü; o tanım yalnız `analiz.json`'da
  durur, raporda basılmaz.
- **Günlük oran.** Yayımlanan `fiyat` haftalıktır (haftanın son günündeki oran). Pazartesi olmayan indirim
  günlü sezonda (AW23 salı, AW24 perşembe) indirim haftasının pazartesi → indirim günü arası günlerin oranı
  koşunun markdown kaydındaki pazartesi çağrısından kurulur (`olcutler` "Günlük oran"; son kod incelemesi I1).
  Haftalık oranla bu günlerin tam fiyat satışı, yalnız indirim gününde taban uygulayan kollarda (Lumoda,
  tekdüze, opt_takvim, opt_taban) markdown sayılıyordu.
- **Tam fiyat STR**: 100 × kampanyasız pozitif satış, satırın hattının günlük oranının ilk kez > 0 olduğu günden
  önce ve C'den önce ÷ arz (v4 kalibrasyon tanımı, gün düzeyinde). **Son STR**: 100 × pozitif satış (gün < C) ÷
  arz. **İndirim başı STR**: 100 × pozitif satış (gün < I) ÷ arz, option başına; çeyreklerin ölçüsü.
- **Çeyrek.** Option'lar aynı yolun Lumoda koşusunun indirim başı STR'sine göre dörde bölünür (1 en düşük;
  eşitlikte option_id; `ceil(4 · sıra ÷ n)`); kolların kazancı çeyrek başına toplanır.
- **Çıkışta kalan**: C − 7 pazartesisinin mağaza (fiziksel) ve depo fotoğrafı (adet, liste ve alış değeri;
  yoldaki girmez). **Ölü stok**: outlet penceresinden sonra, min(C + 120, son depo fotoğrafı) günü depoda kalan
  adet ve alış değeri.
- **Kalıntı değeri** (DP'nin son değeri, `Ogrenilen.kalinti`): aynı tip kapanmış sezonlarda outlet penceresi
  cirosu ÷ çıkıştan bir hafta önceki stoğun liste değeri (yalnız Outlet mağazaları); ölçülür, ayarlanmaz.
- **İndirim davranışı**: indirilen option, ilk indirim haftası (I'nın haftasına göre, medyan), ortalama en derin
  oran, hiç indirilmeyenlerin indirim başı STR'si (haftalık `fiyat`'tan).
- **VERİ'nin "indirim gününden önce oranı olan" sayısı**: yol 0 Lumoda koşusunun günlük oranından (`olcutler`
  option tablosunun `ilk_md_gun`'ü); kademe dağılımı yayımlanan haftalık `fiyat`'tan.
- **Bulunabilirlik ve kayıp** (gizli gerçekten, fiziksel mağazalar, serbest pencere → C): talepli hücre-günlerin
  kendi satışı olan payı; karşılanmayan ÷ talep. Yalnız yan etki ölçüsüdür.
- **Tahmin isabeti**: kolun pazartesi kaydındaki tahmini satış (ufuk → C) ile gerçekleşen; WAPE ve yanlılık.
- **Yan etki**: test dışı option'ların (öteki sezonlar, Outlet line, Basic, NOS) ciro farkı Lumoda'ya göre,
  test option'larının ikameyle aldığı satış, elle transfer farkı.
- **Yol.** İlk Sevkiyat'ın 5 talep yolu: yol 0 yayımlanan dünya, yol 1–4 aynı dünyada başka müşteri akışı
  (`talep_tohumu`); her yolda öğrenme o yolun Lumoda koşusunun yayımlanan biçiminden yeniden yapılır.
- **Fark kuralı.** Farklar basılan değerlerden; tek ondalıklı her fark iki ondalıklı farkın bir kez
  yuvarlanmışıdır (yarım yukarı). "k/n yolda önde" yol başına farkın işaretidir.

## Kollar ve kipler

Kip (`politika.KIPLER`) karar penceresini ve indirim günü tabanını belirler; korunum kolu kipiyle sınar
(`oyun.KOLLAR`).

| Kip | Pencere | Taban |
|---|---|---|
| `serbest` | `max(I − 56, L + 42)`'nin pazartesisi | yok |
| `takvim` | I | I'dan çıkışa ≥ %30 |
| `erken_yok` | I | yok |
| `taban` | serbest | I'dan çıkışa ≥ %30 |

| Kol | Kip | Ne | Yol |
|---|---|---|---|
| `lumoda` | — | v4 `LumodaMarkdown` (kaydediciyle; yol 0 = yayımlanan) | 0–4 |
| `tekduze` | takvim | herkese aynı oran I'dan çıkışa (oran kalibrasyondan) | 0–4 |
| `kural` | serbest | kapsama kuralı: satılabilir stok ÷ son 14 günün stoklu gün hızı, kalan güne oranı α'yı aşarsa bir kademe (α kalibrasyondan; R6 tek eşik) | 0–4 |
| `opt_tuzak` | serbest | optimizasyon, ε̂ markdown'dan (esneklik tuzağı) | 0–4 |
| `opt` | serbest | optimizasyon, ε̂ kampanyadan (ana öneri) | 0–4 |
| `opt_takvim` | takvim | aynı optimizasyon, takvime bağlı (kontrol) | 0–4 |
| `opt_erken_yok` | erken_yok | ayrışım: "kime" | 0 |
| `opt_taban` | taban | ayrışım: "ne zaman" | 0 |
| `kahin` | serbest | `opt`'un gerçek taban talep ve hücre esnekliği girdili hâli (`hakem.kahin_girdisi`) | 0–4 |
| `kural_takvim` | erken_yok | R24 ablasyonu: kuralın penceresi I (erken başlamanın değeri) | 0 |
| `kural_deposuz` | serbest | R24 ablasyonu: stok yalnız raf + yolda (depoyu görmenin değeri) | 0 |

Izgara (`oyun.izgara_listesi`): kalibrasyon 18 (kural α ∈ {0,6; 0,8; 1,0; 1,25; 1,5; 2,0}, R20 ile bir kez
aşağı genişletildi; tekdüze {%30, 40, 50}; AW23 ve SS24; seçim iki sezonun katkı toplamı) + yol 0 17 + yollar
52 + ablasyon 4 = 91 TAM koşu. Kahinin girdileri gizli gerçekten yalnız `hakem.py`'de ölçülür ve kola dizi
olarak gelir.

## Sonuçlar

Sayılar `cikti/rapor.txt`'tedir; bölümler spec §5'in sırasıyla. Başlık soruları (spec §4.6) raporda tek
satırdır (`SORU n · …`): SORU 1, 3, 6 YOL 0'da; SORU 2 ve 5 AYRIŞIM'da; SORU 4 ESNEKLİK'te; SORU 7 ÇEYREK'te;
SORU 8 HİKÂYE'de. Yazıların omurgası R30'dur: iyi kurulmuş kapsama kuralı optimizasyonla başa baş; kazanç
zamanlamada (erken başlamak) ve depoyu görmekte; yazılar "optimizasyon kazandı" demez. Kahinin bir sezonda
opt'un altında kalması bir bulgudur, hata değil (R29; aşağıda Sınırlar). Yollar bölümü beş yolda farkın
işaretini ve medyanını, YAN ETKİ test dışı ciro farkını basar (R31: sezon katkısının dışındaki bu etki küçük
değildir).

## Kilit

Karar modülleri (`sabitler`, `kaynak`, `ogrenme`, `tahmin`, `model`, `politika`) ve ablasyon modülü
(`politika_ablasyon`) `perakende_veri`'yi, `markdown.hakem`'i, `markdown.simulasyon`'u, `markdown.olcutler`'i,
`oyun`'u, `hikaye`'yi ve `allocation.motor`'u (geçişli olarak da) içe aktarmaz; `lam`, `esneklik`,
`esneklik_hucre`, `gercek`, `ilk_siparisler`, `gizli_*` ve `sapma_*` adlarını okumaz. Ölçüm modüllerinden
dünyanın gizli alanlarına yalnız `hakem` ve `simulasyon` dokunur; öteki ölçüm modülleri koşunun `gercek`
tablosunu okuyabilir; vaka kökünün betikleri hiçbirini okumaz. AST kilidi ve modül sınıflandırması
`tests/test_sizinti.py`'dedir.

## Sınırlar

- **Bu dünyada olmayanlar.** Müşteri indirimi beklemez (erken indirim gelecek talebi çalmaz); referans fiyat,
  indirim yorgunluğu ve ürünler arası doğrudan fiyat etkisi yoktur (spec §0). Erken ve derin indirimin gerçek
  bir zincirdeki bedelinin bir kısmı bu yüzden ölçülmez.
- **Zincir fiyatı.** Fiyat option × hat düzeyinde, zincir genelindedir; mağazaya göre indirim yoktur. Mağaza stok
  dengesizliği yalnız replenishment ve elle transferle çözülür; indirim onu hedefleyemez.
- **İkame yan etkisi (R31).** İndirim, test option'larına ikameyle talep çekerek test dışı option'ların cirosunu
  değiştirir; bu etki sezon katkısının dışında, YAN ETKİ bölümünde ayrı basılır ve küçük değildir. Kollar
  arasındaki sıralama yalnız sezon katkısıyla okunmamalıdır.
- **RPT sabit (R4).** Bütün kollar Lumoda'nın RPT'sini yeniden oynatır; daha iyi bir indirim takviminin RPT
  kararını da değiştirmesi ölçülmez.
- **Stok modeli iyimser.** DP'nin akış modeli stoğu karar anındaki hücre paylarıyla (`w`; depo ve açık sipariş
  talep payıyla bölünmüş) ufuk boyunca sabit tutar ve hücre başına `min(X · w, d · m)` satar; replenishment'ın,
  transferin ve hücreler arası tükenmenin zamanlamasını görmez. Kahin tanısına göre derin indirimde satışı
  gerçekleşenden fazla tahmin eder; raporun TAHMİN İSABETİ bölümü kolların genel isabetini basar.
- **Kahin tanısı (R29).** Kahin talebi ve esnekliği bilir ama aynı stok modelini kullanır; bu yüzden opt'u her
  sezonda geçmesi gerekmez. Salt okunur tanıda (`kahin-tani.md`, SDD klasörü) kod hatası çıkmadı: girdi gerçek
  talebi verir, tahmin hatasının çoğu akış modelinden gelir. Yazı bunu "talebi bilmek yetmiyor, malın nerede
  durduğu" diye söyler; rapor ayrışımı basmaz, isabet ölçüsüyle yetinir.
- **opt_tuzak iki yerden yanlış (son kod incelemesi M12).** `opt_tuzak` velocity'yi ε̂_markdown'la fiyattan
  arındırır ve DP'de ε̂_markdown kullanır, ama yaşam eğrisi öğrenmede ε̂_kampanya ile arındırılmıştır: "yanlış
  esneklik" ε'nin girdiği üç yerin ikisini değiştirir.
- **Satışsız hücre (R13).** Son 28 günde satışı olmayan mağaza-hücrenin talebi 0 sayılır; stoğu kalıntı gibi
  değerlenir. Transfer olmadan erimeyecek stok indirimi biraz bastırır.
- **AW24'ün perşembe indirimi (R17).** Tabanlı kiplerde DP indirim haftasını serbest planlar, %30 tabanı
  perşembe çağrısında sarmalayıcı uygular; o haftanın beklenen satışı biraz yanlış planlanır, uygulanan oran
  kurala uygundur.
- **Kalibrasyon ve öğrenme yayımlanan veriden.** α ve tekdüze oran kalibrasyon sezonlarında (AW23, SS24) yol
  0'da seçilir ve beş yolda aynıdır; öğrenme her yolda yeniden yapılır.
- **Tek zincir.** Sentetik tek zincir, iki test sezonu, beş yol; sonuçların başka bir zincire taşınabilirliği
  ölçülmedi. Gerçek bir zincirde hakem yoktur: kahin ve gizli gerçeğe dayanan ölçüler yalnız bu vakada vardır.

## Dosyalar

`markdown/`: `sabitler`, `kaynak` (yayımlanan tablolar, karar penceresi), `ogrenme`, `tahmin`, `model`
(haftalık DP), `politika` (kollar), `politika_ablasyon` (R24 kolları; anahtar istisnası), `simulasyon`
(koşu, önbellek, RPT takvimi), `hakem` (gizli gerçek, kahin girdisi), `olcutler`, `oyun` (kalibrasyon, ızgara,
ölçüm), `hikaye`. Vaka kökünde `analiz.py` (koşusuz VERİ), `senaryolar.py` (demo), `rapor.py`. Testler
`tests/`; sahte rapor girdileri `tests/sahte_rapor.py`.
