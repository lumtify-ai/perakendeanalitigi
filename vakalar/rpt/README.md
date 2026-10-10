# RPT — tekrar sipariş

Lumoda v3 sentetik verisi üstünde tedarikçiye tekrar sipariş (RPT) vakası.
Sitedeki `/rpt/tekrar-siparis/` dizisinin bütün sayıları buradan çıkar. Tasarım:
`docs/superpowers/specs/2026-09-26-veri-v3-ve-rpt-design.md`, bölüm 3.

RPT burada **tedarikçiye verilen tekrar üretim siparişidir**; depodan mağazaya
tekrar sevkiyat (replenishment) değildir. Sezon başındaki ilk alım ve ilk
dağıtım veriden aynen alınır, bu vakanın konusu değildir.

## Kurulum ve koşum

    cd vakalar/rpt
    python -m venv .venv
    .venv/Scripts/pip install -e ../ortak
    .venv/Scripts/pip install --no-deps -e ../../veri
    .venv/Scripts/pip install -e ".[dev]"
    .venv/Scripts/python -m pytest tests/test_kaynak.py -q   # `veri` işaretliler gerçek v4 ister (~1 dk)

Veri `veri/cikti/v4/perakende.duckdb` (ya da `PERAKENDE_V4_DB`); yoksa yayımlanan
`veri-v4` dosyasını indirin ya da `cd veri && python -m perakende_veri.v4.uret`.
v4 geçişi sürüyor (`docs` ayrı depoda: `2026-10-09-rpt-v4` tasarımı); henüz
v4'e taşınmamış modüllerin testleri `Görev N'de v4'e` nedeniyle atlanır.

Ortak günlük tabloyu kurmak (~6,5 dk, bir kez; eğri, katmanlar ve aday bunu okur):

    .venv/Scripts/python -m rpt.hazirla         # cikti/gunluk.parquet

Alternatif talep yollarını koşmak (10 yol, 4 süreç paralel, ~6 dk; önce bu):

    .venv/Scripts/python -m rpt.yollar          # cikti/yollar.json

Yazıların alıntıladığı bütün sayıları basmak (~2 dk; yol 0'ı baştan koşar):

    .venv/Scripts/python rapor.py > cikti/rapor.txt

Windows konsolunda Türkçe karakter için `PYTHONIOENCODING=utf-8`.

## Durum

**Faz A:** veri paneli, yaşam eğrisi, sansürlü talep kestirimi ve ilk üç
yazının sayıları. **Faz B:** aday modeli, newsvendor miktarı, dağıtım
kuralları, kollar ve alternatif talep yolları (4.–6. yazılar). Motor
yazılmaz: aynı talep v3'ün `simule_et(dunya, talep, rpt_politikasi=...,
dagitim_politikasi=...)`'i ile farklı politikalarla yeniden oynatılır
(bir koşu ~3 sn).

## Modüller

| Modül | İşi |
|---|---|
| `kaynak.py` | v4 DuckDB tablolarını ortak paketin görünümleriyle (temiz satış, hayaletsiz çeşit) okur; hücre-hafta (mağaza × SKU × lansmandan beri hafta) ve option-hafta panelleri (online satış STR'ye girer, depo stoğu pazartesi süzülür); `tarihten_once` ile karar sabahına kırpma; `gecmis_sezonlar` |
| `motor.py` | Üretecin tek kapısı: vakada `perakende_veri`'yi yalnız bu modül içe aktarır. `dunya()`, `politika_gorunumu(dunya)` (Lumoda'nın gördüğü plan, ilk alım, tedarikçi alanları; karar modüllerine bu verilir), `kos(rpt, replenishment, ad=, parametreler=)` → `Kosu` (temiz 18 tablo + hücre-gün gizli gerçek, hakem tanımıyla). Koşular `cikti/kosular/`'da anahtarlı önbellekte (ad, parametreler, tohumlar, yalnız koşuyu etkileyen kaynakların kod özeti, v4 parmak izi); **politikanın davranışını değiştiren her parametre `parametreler`'e girmeli**. Karar modülleri bu modülü içe aktarmaz (`tests/test_sizinti.py`) |
| `bilgi.py` | `PolitikaBilgisi` veri tipi (tarafsız; karar modülleri tipi buradan alır, nesneyi `motor.politika_gorunumu` doldurur) |
| `hazirla.py` | `python -m rpt.hazirla`: `cikti/gunluk.parquet` (ortak günlük tablo, 2023–2025, durum stoklu / tükenen / boş; ~6,5 dk, bir kez, v4 parmak izli); `havuz_gunlugu` (karar havuzunun satırları + Basit özellikleri), `carpanlar` (karar anı çarpanları, kapanmış sezon kümesi başına önbellekli) |
| `egri.py` | Yaşam eğrisinin **şekli** (birikimli pay k_h), geçmiş sezonlardan: çıplak (sansürlü satış), düzeltilmiş (satış + ortak Basit kaybı, karar anı = oyunun ilk lansman sabahı), gerçek (yalnız argüman olarak verilen gerçek tabloyla, kıyas) |
| `sansur.py` | `karar_ani_talep(gunluk, t, carpanlar, havuz)`: karar anı Basit'iyle hücre-gün talebi (saf; tablo yolunda ve motor içinde aynı); sezon talebi kestirimi, dört katman (a çıplak · b stoklu gün hızı · c FRR eğri ölçeği · d b+c); gerçek talebe (argüman) karşı hata |
| `hikaye.py` | "Bitti" haftası, hikâye adayları, mağaza tablosu, Lumoda'nın RPT'lerinin akıbeti |
| `anlik.py` | Motor içi ikiz: `gunluk_gorunumden(g, havuz)` Görünüm'den (motor `gecmis_kaydi`yla) ortak günlük tabloyu + Basit özelliklerini kurar; tablo yoluyla aynı girdide aynı kestirim (R5, testli, birebir). `durum_gorunumden`: karar sabahı STR, stok, açık sipariş |
| `dagitim.py` | `KURALLAR` a/b/c/d: v4 replenishment kancası (a Lumoda · b stoklu gün hızı · c yeniden lansman · d c + %30 depoda tutma); RPT'nin varışı açık siparişin düşmesinden ve depodan anlaşılır |
| `miktar.py` | Banu %50 · FRR · newsvendor (MOQ kapısı). Belirsizlik (μ, σ) geçmiş sezonlarda log(Basit'le doldurulmuş talep / karar anı kestirimi) — gerçek talep okunmaz; indirim beklentisi geçmiş sezonların yayımlanan `fiyat`ından (dalga × hafta) |
| `aday.py` | Karar satırı (`karar_kaydi`: karar anı x, D + karar sabahı durumu, tablo yolunda `durum_tablodan`; Banu'nun STR'si yayımlanan RPT'leri birebir üretir), saf özellikler, sonradan-bakış etiketi (talep argüman: gerçek ya da Basit'le doldurulmuş), kural / lojistik / LightGBM (yalnız geçmiş sezonlarla), TL değerlendirme |
| `politika.py` | `KOLLAR`: `rpt_yok`, `mevcut` (v4 `LumodaRPT`), `frr`, `oneri` (her karar pazartesisi kendi dünyasının geçmişinden karar anı kestirimi + aday modeli + newsvendor). Çevrimdışı öğrenilenler `Ogrenilen` (veri; özetleri `parametreler()` ile koşu anahtarına) |
| `kahin.py` | `Kahin(gercek_talep, …)`: koşunun talebini bilen kol; `politika` onu içe aktarmaz |
| `oyun.py` | Hazırlık (yolun gerçekleşen tarihi + öğrenme), dağıtım kuralı seçimi (SS24), kol koşuları |
| `olcutler.py` | Spec 3.4 ölçütleri, option düzeyinde, rpt_yok tabanına göre |
| `yollar.py` | 10 alternatif talep yolu, paralel, JSON |
| `rapor.py`, `rapor_b.py` | Yayımlanacak her sayı (HİKÂYE · KARAR · SANSÜR · ADAY · MİKTAR · SONUÇ) |

## İlkeler

- **Bilgi bu sezondan.** RPT kararının seviyesi (ürün ne kadar tutuyor) içinde
  bulunulan sezonun erken haftalarından gelir; geçmiş sezonlardan yalnız
  eğrinin **şekli** öğrenilir (kullanıcının "RPT geçmişe değil bu sezona
  bakar" cümlesi).
- **Sızıntı yok.** Oyun sezonları AW24 ve SS25. Eğri yalnız oyun sezonundan
  önce kapanmış sezonlardan (AW24 ← SS23, AW23, SS24; SS25 ← + AW24) ve oyunun
  ilk lansman sabahından önceki satırlardan öğrenilir; Basit'in kaybı o sabahın
  karar anı moduyla (Ruling R4). Karar pazartesisi `t`'nin kestirimi `t`'den
  sonraki satırı okumaz. Testle kilitli (`test_oyun_egrisi_gelecegi_gormez`,
  `test_karar_ani_katmanlari_gelecegi_gormez`, `test_gercek_veri_kirpilmis_tabloyla_ayni`).
- **Kayıp satış yalnız doğruluk ölçüsüdür.** v4'te kayıp satış yayımlanmaz;
  gerçek talep hakemden yalnız raporda kurulur (`olcutler.gercek_gunluk`) ve
  kestirim modüllerine yalnız argüman olarak girer; hiçbir kestirim onu okumaz
  (`test_kayip_okunmaz_*`).
- **Sezon talebi = lansman → indirim başı** (FRR'nin "sezon"u). Çıkışa kadarki
  talep de ayrıca raporlanır (RPT'nin indirimde satacağı kısım için).
- **Plan gizli değildir.** Buyer planı (`plan_sezon`) tablolarda yok, dünyadan
  okunur; ama ilk alım ondan hesaplandı, zincir bu sayıyı bilir. Sürpriz ve
  gerçek beklenen talep okunmaz.

## Faz B'nin kurulumu

- **Kollar yalnız oyun sezonlarının (AW24, SS25) Collection option'larına
  dokunur**; öteki bütün option'larda Banu'nun kuralı ve bugünkü dağıtım
  işler. Dağıtım kuralları yalnız RPT'si GELMİŞ option'lara uygulanır: RPT'siz
  kolda b/c/d bugünkü kuralla birebir aynıdır (testli). Fark RPT'nin kendisinden
  gelir.
- **Kollar arası gürültü yok.** v3'ün iade ve işlem indirimi rastgeleliği (gün,
  hücre) başına tohumlanır ve politikadan bağımsızdır (`simule_et(...,
  operasyon_tohumu=42)`): RPT'si olmayan bir option her kolda birebir aynı
  sonuçlanır (testli). Alternatif yollar kendi operasyon tohumunu kullanır.
- **`mevcut` kolu v3'ün kendisidir**: dışa aktarılan tablolar birebir
  (`test_esdegerlik.py`).
- **Öğrenme** (eğri, belirsizlik, aday modeli) her yolun "gerçekleşen tarihi"nden
  (Banu'nun kuralı + bugünkü dağıtım), oyun sezonunun ilk lansman sabahına
  kırpılarak, yalnız önceki sezonlardan. **Dağıtım kuralı** oyundan önce SS24'te
  seçilir (Banu'nun RPT'leriyle, en yüksek SS24 kârı).
- **Değerleme:** gelir − (ilk alım + RPT) × alış; sezon sonunda kalan stok 0 TL
  (alt sınır). Taban `rpt_yok`.
- **Kâhin üst sınır değildir:** gerçek talebi ve teslim gecikmesini bilir ama
  zincir düzeyinde düşünür; mağazalar arası sıkışmayı ve dağıtımı bilmez. Kâr
  ölçütü indirimde satışı da içerdiği için tam fiyattan MOQ/2 satamayan ama
  kârlı siparişler verebilir (ölçütte "yanlış alarm" sayılır).
- **Sızıntı kalkanları (testli):** kâhin dışındaki kollar sonraki talebi
  bozunca aynı RPT'leri verir (kâhin vermez); kalibrasyon ve eğri oyun
  başlangıcından sonraki veri bozulunca değişmez; aday eğitimi yalnız önceki
  sezonlardan.

## Tanımlar

- **Hafta h:** lansmandan itibaren [lansman + 7h, lansman + 7h + 7). h.
  haftanın stoklu günü (h+1). pazartesinin fotoğrafındadır.
- **Tutan (hit):** gerçek talep / plan ≥ 1,5 (spec 2.12).
- **Bitti:** pazartesi sabahı depo ≤ ilk alımın %2'si ve depo + mağaza ≤ %20'si.
- **RPT akıbeti:** depo partiyi ayırt etmez; çıkışta depoda kalan (en fazla RPT
  kadar) RPT'den kalmış sayılır (FIFO). RPT'yi olduğundan iyi gösteren atama.

## Bilinen sınırlar ve veriden çıkan sürprizler

- **Üçüncü haftada biten tutan ürün yok.** SS25'in 16 tutan option'ından
  hiçbiri 3. hafta pazartesisine kadar "bitmiyor"; en erken biten (MDL190-HAK,
  yerli, planın 3,6 katı) 4. hafta pazartesisi biter, çoğu 6.–7. haftada.
  3. hafta pazartesisi, Lumoda'nın kuralının tetiklendiği gündür: depo o sabah
  son partiyi mağazalara gönderir. Hikâyenin haftası buna göre seçilmeli
  (rapor iki pazartesiyi de basar).
- **Stoklu gün düzeltmesi gün içi tükenmeyi göremez.** Hızlı satan hücre güne
  birkaç adetle açılır, öğleden sonra biter; o gün "stoklu" sayılır. Tutan
  ürünlerde düzeltme gerçek kaybın yarısı kadarını geri kazanır.
- **AW24'ün eğrisi yalnız bir bahar sezonundan** (SS24) öğrenilir; kış
  mevsimselliği farklıdır. AW24 hataları SS25'ten büyüktür.
- **Eğri gruplaması:** üst kategori × dalga, yalnız dalgadan kötü (grup başına
  birkaç option; gürültü). Seçilen: yalnız dalga.
- **Çıkış hedefli eğri** (`hedef="cikis"`), geçmiş sezonun çıkışı oyun
  başlangıcından sonraysa o sezonun son haftalarını göremez (AW24 için SS24'ün
  son haftası, SS25 için AW24'ün son iki haftası).
- İkame (stoksuz ürünün talebinin başka ürüne kayması) ve sergi etkisi v3'te
  modellenmez.
- **SS25'in öğrenmesi AW24'ün gerçekleşen (Banu'lu) tarihinden**; bir kol
  AW24'te başka RPT verseydi SS25'e giden geçmiş biraz farklı olurdu.
- **Belirsizlik (σ) kısmen örneklem içi**: SS23'ün öncesi olmadığı için SS23
  kestirimleri oyun sezonunun eğrisiyle yapılır. SS23'ün karar anlarında
  kapanmış sezon yoktur (AW22 pencereye yarım girer): Basit nötr çarpanlarla
  çalışır (`hazirla.carpan_bulucu`).
- **Kalibrasyonun hedefi Basit'tir** (R4: oyunun ilk lansman sabahında
  doldurulmuş talep), gerçek değil: μ Basit'in kendi yanlılığını içermez; gerçeğe
  karşı yanlılık yalnız raporda ölçülür.
- **Aday modeli üç (AW24) ya da dört (SS25) geçmiş sezondan** eğitilir (SS23,
  AW23, SS24 [, AW24]); satır ve pozitif sayıları raporda.
- **Uzak Doğu da aday olabilir** (v3'te olamıyordu): v4 sezonları uzun, 12–15
  haftalık tedarikle bile bazı satırların etiketi pozitif; oranı raporda.
- Aday etiketi ve newsvendor zincir düzeyinde stok akışı varsayar (mağazalar
  arası sıkışma yok): RPT lehine iyimser.
- İade oranı newsvendor'da yok sayılır; motor iadeyi satışla orantılı üretir.
