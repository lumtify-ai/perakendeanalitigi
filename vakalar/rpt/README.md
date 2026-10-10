# RPT — tekrar sipariş

Lumoda v4 sentetik verisi ve v4 motoru üstünde tedarikçiye tekrar sipariş (RPT)
vakası. Sitedeki `/rpt/tekrar-siparis/` dizisinin (6 yazı) bütün sayıları buradan,
`cikti/rapor.txt`'ten çıkar. Tasarım: `docs/superpowers/specs/2026-10-09-rpt-v4-design.md`
(`docs/` ayrı depodur); uygulamadaki sapmalar ve kararlar o belgenin §11'inde.

RPT burada **tedarikçiye verilen tekrar üretim siparişidir**; depodan mağazaya
tekrar sevkiyat (replenishment) değildir. Sezon başındaki ilk alım ve ilk
dağıtım veriden aynen alınır, bu vakanın konusu değildir.

## Kurulum

    cd vakalar/rpt
    python -m venv .venv
    .venv/Scripts/pip install -e ../ortak              # perakende_analitik (Basit, hakem, sayı denetimi)
    .venv/Scripts/pip install --no-deps -e ../../veri  # perakende_veri (v4 motoru; yalnız rpt/motor.py açar)
    .venv/Scripts/pip install -e ".[dev]"

Veri `veri/cikti/v4/perakende.duckdb` (ya da `PERAKENDE_V4_DB`); yoksa yayımlanan
`veri-v4` dosyasını indirin ya da `cd veri && python -m perakende_veri.v4.uret`.
Hakem önbelleği ortak paketin kendi ortamında kurulur (`vakalar/ortak/.venv`).

## Koşum

Bütün komutlar `vakalar/rpt` içinden, vakanın `.venv`'iyle.

- **Ortam:** Windows konsolunda `PYTHONIOENCODING=utf-8` (Türkçe karakter).
- **Sıralı:** koşu önbelleği eşzamanlı yazmaya güvenli değil. Aşağıdaki
  komutlardan ikisini (rapor ve testler dahil) aynı anda koşmayın.
- **Makine uyanık kalmalı:** oyun ve yollar saatler sürer; uyku koşuyu keser
  (kaldığı yerden sürer, ama yarım koşu baştan koşulur).
- **Kaynaklar:** tepe bellek ~10 GB (bir TAM koşu 7–10,3 GB), disk ~9 GB
  (`cikti/`: koşu önbelleği koşu başına ~150 MB; yol başına DuckDB + günlük tablo
  ~0,5 GB; günlük tablo 250 MB).

Sıra ve süreler:

    # 1. Ortak günlük tablo (~6,5 dk; eğri, katmanlar, aday ve öğrenme bunu okur)
    .venv/Scripts/python -m rpt.hazirla                  # cikti/gunluk.parquet

    # 2. Hakem önbelleği (yalnız rapor için: yayımlanan dünyanın gerçek talebi)
    cd ../ortak && .venv/Scripts/python -m perakende_analitik.hakem && cd ../rpt

    # 3. Oyun ve yollar (ikisi birlikte ~4,5 sa; 42 TAM koşu, koşu başına ~3–5 dk,
    #    yol başına öğrenme 7–11 dk; p > 0 yolları kendi DuckDB'sini ve günlük tablosunu kurar)
    .venv/Scripts/python -m rpt.oyun                     # yol 0: hazırlık, SS24 seçimi, 14 kol; cikti/oyun.json
    .venv/Scripts/python -m rpt.yollar                   # 5 talep yolu, yol başına 5 kol (Banu a ve b ile); cikti/yollar.json

    # 4. Rapor (~6–7 dk; 18 oyun koşusu önbellekten; stderr "18/18 koşu önbellekten okundu" demeli)
    .venv/Scripts/python rapor.py > cikti/rapor.txt

    # 5. Yazılardaki her sayı raporda mı (çıkış 0)
    cd ../ortak && .venv/Scripts/python -m perakende_analitik.sayi_denetimi \
        --yazi ../../site/src/content/yazi/rpt/tekrar-siparis --rapor ../rpt/cikti/rapor.txt

Rapor korunum denetimi tutmazsa stdout'a hiçbir şey basmaz (çıkış 1). Aynı girdiyle
iki koşu bayt bayt aynıdır. Biten her motor koşusu `cikti/ilerleme.jsonl`'a yazılır.

Testler: `.venv/Scripts/python -m pytest -q -m "not veri"` (~4 dk); `-m veri` gerçek
v4 dosyasını, günlük tabloyu ve koşu önbelleğini ister (eksikse kendisi koşar).

## Önbellek katmanları

| Katman | Yer | Anahtar | Değişince |
|---|---|---|---|
| Günlük tablo | `cikti/gunluk.parquet` + `kaynak.json` (her yolun dizininde de) | v4 dosyası (yol, boyut, mtime), pencere, `hazirla.kod_ozeti` (hazirla.py + ortak içe aktarma kapanışı) | `hazirla` çarpanları siler, tabloyu yanına yeniden kurar; içerik bayt bayt aynıysa eski dosya ve mtime'ı korunur (`gunluk_sha256`) |
| Karar anı çarpanları | `cikti/carpanlar_<kapanmış sezonlar>.pkl` | kapanmış sezon kümesi; günlük tablodan yeni olmalı | günlük tablo yeniden kurulunca silinir |
| Motor koşuları | `cikti/kosular/<ad>_<anahtar>` | ad, parametreler, politika kimliği (öğrenilenlerin içerik özeti dahil), tohumlar, ölçek, `motor.kod_ozeti` (`KOSU_MODULLERI` + ortak kapanışı + `perakende_veri/v4`), v4 parmak izi, kütüphane sürümleri | yeni anahtar, yeni koşu (eskisi diskte kalır) |
| Öğrenme | `cikti/yollar/yol<p>/ogrenme.pkl` | DuckDB ve günlük tablonun yol/boyut/mtime'ı, `motor.kod_ozeti`, hazirla.py'nin özeti, Lumoda koşusunun anahtarı | yeniden öğrenilir (7–11 dk); kimlik (`Ogrenilen.kimlik`) koşu anahtarına girer; aşağıdaki uyarıya bakın |
| Yol DuckDB'si | `cikti/yollar/yol<p>/perakende.duckdb` + `.kosu` | Lumoda koşusunun anahtarı | yeniden yazılır |
| Aday sınaması | `cikti/yollar/yol0/rpt_yok/sinama.parquet` + `.anahtar` | rpt_yok koşusunun anahtarı, öğrenilenlerin kimliği, `motor.kod_ozeti` | yeniden kurulur |
| Yollar | `cikti/yollar.json` | yol başına `yollar.kod_ozeti` (koşu kod özeti, v4 parmak izi, `olcutler`, `yollar`, `hazirla` kodu) + kullanılan koşuların anahtarları | kodu tutmayan yol yeniden hesaplanır (koşular önbellekten) |
| Oyun özeti | `cikti/oyun.json` | yok (her `rpt.oyun` yeniden yazar) | rapor seçilen kuralı onunla karşılaştırır |
| Hakem | `vakalar/ortak/cikti/hakem/` | ortak paketin kuralı | `perakende_analitik.hakem` |

**Koşu anahtarına girenler kasıtlı dar (Ruling R3):** `rapor*.py`, `olcutler`, `hikaye*`,
`yollar`, `hazirla` ve testler koşu kod özetinde değildir; bunları değiştirmek 4,5 saatlik
ızgarayı geçersiz kılmaz. `rpt/`'deki her modül iki listeden birindedir (`motor.KOSU_MODULLERI`
/ `motor.KOSU_DISI`; `tests/test_motor.py`). Politikanın davranışını değiştiren, nesnenin beyan
etmediği her parametre `parametreler`'e girmeli.

**Kod değişince elle silinecekler:**

- `KOSU_MODULLERI`'nden bir dosya, onların ortak kapanışı ya da `veri/` değişirse hiçbir şey
  silmeyin: bütün anahtarlar kendiliğinden değişir, ızgara baştan koşulur (~4,5 sa). Eski
  koşu dizinleri `cikti/kosular/`'da kalır; yer açmak için elle silinebilir.
- `hazirla.py` ya da ortak kapanışı değişirse günlük tablo ve çarpanlar kendiliğinden yenilenir;
  öğrenme de (anahtarında hazirla.py var). Bilinen açık: aday sınamasının anahtarında günlük
  tablonun ve hazirla kodunun izi yok (`oyun.sinama`; oyun.py koşu modülü olduğu için bu dalga
  değiştirmedi). `hazirla` "içerik değişti" dediyse `cikti/yollar/yol*/rpt_yok/sinama.anahtar`
  dosyalarını silin.
- **Öğrenmeyi temiz bir süreçte kurun.** `Ogrenilen.kimlik` eğitilmiş modelleri pickle
  baytlarından da özetler (`politika.ozet_hash`); pickle'ın nesne paylaşımı süreçte daha önce
  ne yüklendiğine bağlı. Son düzeltme dalgasında rapor içinden yeniden öğrenmek aynı içerikle
  başka bir kimlik verdi ve öneri / kâhin kolunun 5 koşusu (çıktıları bayt bayt aynı) yeni
  anahtarla yeniden koşuldu; aynı öğrenme temiz bir süreçte özgün kimliği verdi ve 18 koşu yine
  önbellekten geldi. Öğrenmenin anahtarı değiştiyse (hazirla.py, v4 dosyası, koşu kodu) raporu
  koşmadan önce `.venv/Scripts/python -c "from rpt import oyun; oyun.hazirlik(0, ilerleme=None)"`
  (ya da `python -m rpt.oyun`) koşun. Kalıcı çare (modellerin içerik özeti) koşu modüllerini
  değiştirir; ızgara yeniden koşulacağı bir değişikliğe bırakıldı.
- `olcutler.py` ya da `yollar.py` değişirse `yollar.json`'ın yolları kendiliğinden yeniden
  hesaplanır (`python -m rpt.yollar`; koşular önbellekten). Bu alandan (`kod`, `anahtarlar`)
  önce yazılmış bir `yollar.json` ilk `rpt.yollar`da baştan hesaplanır; rapor eski kaydı okur
  ve yol 0'ı ölçütleriyle denetler.
- `rapor.py`, `rapor_b.py`, `hikaye*.py` değişirse yalnız raporu yeniden koşun.

## Sahneler

`hikaye_sec` iki sahneyi bir merdivenle seçer (spec §6; rapor HİKÂYE bölümü huniyi basar):

- **Hit (1.–5. yazı):** MDL0548-LCV Süet Ceket Lacivert (Çorlu Giyim, yerli, RPT 5 hafta,
  MOQ 300; ilkbahar-yazın üçüncü dalgası). Merdivenin ilk adayı, gevşetme yok.
- **Geç gelen (5.–6. yazı):** MDL0579-SYH Örgü Kemer Siyah (Tiruppur Ganga Textiles,
  Hindistan, RPT 14 hafta, MOQ 600). Ruling R9: Banu'nun RPT'si o option'da RPT
  vermemekten zararlı olmalı; gevşeyen ölçüt yalnız Banu'nun tetik haftası (4. pazartesi).
  Veride model adı "Örgü Kemer Kemer"; rapor yinelenen kelimeyi bir kez basar.

Alternatifler (okuma kapısında sunuldu; seçilirse rapor `--hikaye` ile yeniden koşulur ve
yazıların sahne sayıları yenilenir):

    .venv/Scripts/python rapor.py --hikaye MDL0560-BEJ:MDL0579-SYH > cikti/rapor.txt   # hit: Midi Etek Bej
    .venv/Scripts/python rapor.py --hikaye MDL0548-LCV:MDL0609-LCV > cikti/rapor.txt   # geç gelen: Sırt Çantası Lacivert

Midi Etek daha dramatik stoksuzluk gösterir ama "üç haftada ≥ 3 stoksuz günü olan en az üç
mağaza" şartını bir mağazayla kaçırır. Sırt Çantası aynı kalıpta (Banu 4. pazartesi); Banu'nun
RPT'si orada daha zararlı (RPT yoka göre −46.965 TL).

## Kararlar (özet; ayrıntı spec §11 ve `.superpowers/sdd/2026-10-09-rpt-v4/progress.md`)

- **R1/R2:** v3 modüllerinin testleri yenilenene dek test düzeyinde atlandı (hepsi kalktı);
  ilk alım ile plan ilişkisi (~%93) motorun politika görünümünden sınanır.
- **R3, R-T4f:** koşu kod özeti yalnız koşuyu etkileyen kaynakları kapsar; ölçüm sonucu
  politikaya yalnız `parametreler` üstünden girer.
- **R4/R5:** vakadaki bütün Basit kullanımları karar anı modunda; karar anı kestirimi saf bir
  fonksiyon (`sansur.karar_ani_talep`), tablo yolu ile motor içi yol birebir aynı (testli).
- **R6:** v4 motoruna isteğe bağlı geçmiş kaydı (`gecmis_kaydi`, varsayılan kapalı; yayımlanan
  veri bayt bayt aynı).
- **R7:** kâhin aynı tohumlu `rpt_yok` koşusunun talebini ve tedarikçinin gerçek gecikmesini
  bilir; üst sınır değildir.
- **R8:** plan raporda `motor.politika_gorunumu`'ndan okunur, CSV'den değil.
- **R9:** geç gelen sahnesinde Banu'nun RPT'si zararlı olmalı (sahne kemer oldu).
- **R10:** sayfada takvim tarihi ve yıl yok; mevsime göre ifadeler ve süreler serbest.
- Uygulayıcı kararları: kapsam mağaza + online; öğrenilenlerin kimliği içerikten
  (`Ogrenilen.sabitle`); dağıtım kuralı SS24'te bir kez seçilir (b), yollarda yeniden seçilmez;
  kâr = satış tutarı − alış × depoya giren; kalan stok 0 TL; FIFO akıbeti.

## Modüller

| Modül | İşi |
|---|---|
| `kaynak.py` | v4 DuckDB tablolarını ortak paketin görünümleriyle (temiz satış, hayaletsiz çeşit) okur; hücre-hafta ve option-hafta panelleri (online satış STR'ye girer, depo stoğu pazartesi süzülür); `tarihten_once` ile karar sabahına kırpma; `gecmis_sezonlar` |
| `motor.py` | Üretecin tek kapısı: vakada `perakende_veri`'yi yalnız bu modül içe aktarır. `dunya()`, `politika_gorunumu(dunya)` (Lumoda'nın gördüğü plan, ilk alım, tedarikçi alanları), `kos(...)` → `Kosu` / `KosuKaydi` (temiz 18 tablo + hücre-gün gizli gerçek; `tembel=True` tabloları diskten süzerek okur). Koşu önbelleği (yukarıdaki tablo). Karar modülleri bu modülü içe aktarmaz (`tests/test_sizinti.py`) |
| `bilgi.py` | `PolitikaBilgisi` veri tipi (karar modülleri tipi buradan alır, nesneyi `motor.politika_gorunumu` doldurur) |
| `hazirla.py` | `python -m rpt.hazirla`: `cikti/gunluk.parquet` (2023–2025 günlük tablo, durum stoklu / tükenen / boş); `havuz_gunlugu` (karar havuzunun satırları + Basit özellikleri); `carpanlar` (karar anı çarpanları, kapanmış sezon kümesi başına önbellekli); `kod_ozeti` |
| `egri.py` | Yaşam eğrisinin şekli (birikimli pay), geçmiş sezonlardan: çıplak, düzeltilmiş (satış + karar anı Basit kaybı), gerçek (yalnız kıyas) |
| `sansur.py` | `karar_ani_talep(gunluk, t, carpanlar, havuz)`: karar anı Basit'iyle hücre-gün talebi (saf; tablo yolunda ve motor içinde aynı); sezon talebi kestirimi, dört katman (a çıplak · b stoklu gün hızı · c FRR eğri ölçeği · d b+c). Raporun katman adları `rapor.KATMAN_ADI`'dadır; `sansur.KATMAN_ADI` v3'ten kalma ve kullanılmıyor, ama sansur.py koşu modülü olduğu için silinmedi |
| `hikaye.py`, `hikaye_sec.py` | Mağaza tabloları, RPT akıbeti (FIFO); sahne merdiveni (`--hikaye` ile zorlanabilir) |
| `anlik.py` | Motor içi ikiz: `Gorunum`'den (geçmiş kaydıyla) ortak günlük tabloyu ve karar sabahı durumunu kurar; tablo yoluyla aynı girdide aynı kestirim (R5) |
| `dagitim.py` | `KURALLAR` a/b/c/d: v4 replenishment kancası (a Lumoda · b stoklu gün hızı · c yeniden lansman · d c + %30 depoda tutma); yalnız RPT'si gelmiş oyun option'larına dokunur |
| `miktar.py` | Banu %50 · FRR · newsvendor (MOQ kapısı); belirsizlik (μ, σ) geçmiş sezonlarda Basit'le doldurulmuş talebe karşı; indirim beklentisi geçmiş sezonların fiyatından |
| `aday.py` | Karar satırı, özellikler, iki etiket ((i) gerçek talep, (ii) Basit'le doldurulmuş), kural / lojistik / LightGBM (yalnız geçmiş sezonlarla), TL değerlendirme |
| `politika.py` | `KOLLAR`: `rpt_yok`, `mevcut` (v4 `LumodaRPT`), `frr`, `oneri`; çevrimdışı öğrenilenler `Ogrenilen` (kimliği içerikten) |
| `kahin.py` | `Kahin`: koşunun talebini bilen kol (R7); `politika` onu içe aktarmaz |
| `oyun.py` | `hazirlik(yol)` (gerçekleşen tarih + öğrenme), `dagitim_secimi` (SS24), `tum_kollar`, `ozet_tablosu`, `sinama` |
| `olcutler.py` | Option düzeyinde ölçütler: kâr, kurtarılan kayıp (kalıcı / ikame), boşa giden RPT, yanlış alarm; `gercek_gunluk` |
| `yollar.py` | 5 talep yolu (yol 0 yayımlanan), her yolda öğrenme + kollar; `cikti/yollar.json` |
| `rapor.py`, `rapor_b.py` | Yayımlanacak her sayı (HİKÂYE · KARAR · SANSÜR · ADAY · MİKTAR · SONUÇ · YOLLAR · ANLATI VARSAYIMLARI · KORUNUM); hakem yalnız burada |

## İlkeler

- **Bilgi bu sezondan.** RPT kararının seviyesi içinde bulunulan sezonun erken haftalarından
  gelir; geçmiş sezonlardan eğrinin şekli, belirsizlik ve aday modeli öğrenilir.
- **Sızıntı yok.** Oyun sezonları AW24 ve SS25. Öğrenme yalnız oyun sezonundan önce kapanmış
  sezonlardan (AW24 ← SS23, AW23, SS24; SS25 ← + AW24) ve oyunun ilk lansman sabahından önceki
  satırlardan; karar pazartesisi `t`'nin kestirimi `t`'den sonraki satırı okumaz (testli:
  `test_karar_ani_gelecegi_gormez`, `test_karar_ani_katmanlari_gelecegi_gormez`).
- **Kestirim girdi, gizli gerçek ölçü.** v4'te kayıp satış yayımlanmaz; gerçek talep hakemden
  (yayımlanan dünya) ya da koşunun kendi gizli gerçeğinden (oyun) yalnız ölçümde kurulur.
- **Plan gizli değildir.** Buyer planı tablolarda yok, motorun politika görünümünden okunur;
  ilk alım ondan hesaplandı (planın ~%93'ü).

## Oyunun kurulumu

- **Kollar yalnız oyun sezonlarının (AW24, SS25) Collection option'larına dokunur**; öteki
  option'larda Banu'nun kuralı ve bugünkü dağıtım işler.
- **Kollar arası gürültü yok.** Talep, iade, ikame ve işlem indirimi rastgeleliği anahtarlı
  sayaçlardan; aynı tohumda koşu birebir tekrarlanır. v4'te ikame ve fiyat içsel olduğundan
  RPT'siz bir option da kola göre biraz değişebilir. Alternatif yollar yalnız talep tohumunu
  değiştirir.
- **`mevcut` kolu + kural a, yayımlanan v4'ü üreten koşudur** (`test_esdegerlik.py`).
  `y0_rpt_yok_d` ve `y0_mevcut_a` koşuları bu eşdeğerlik testlerinden gelir (rapor okumaz).
- **Dağıtım kuralı** oyundan önce SS24'te Banu'nun RPT'leriyle seçilir (b); yollarda yeniden
  seçilmez.
- **Değerleme:** gerçekleşen satış tutarı − (ilk alım + RPT − kalite reddi) × alış; pencere
  sonunda kalan stok 0 TL. Taban `rpt_yok`.
- **Kâhin üst sınır değildir:** talebi ve teslim gecikmesini bilir, zincir düzeyinde düşünür;
  mağazalar arası sıkışmayı ve dağıtımı bilmez.

## Tanımlar

- **Hafta h:** lansmandan itibaren [lansman + 7h, lansman + 7h + 7).
- **Tutan (hit):** gerçek talep / plan ≥ 1,5.
- **RPT akıbeti:** depo partiyi ayırt etmez; çıkışta depoda kalan (en fazla RPT kadar) RPT'den
  kalmış sayılır (FIFO). RPT'yi olduğundan iyi gösteren atama.

## Bilinen sınırlar

- Aday etiketi ve newsvendor zincir düzeyinde stok akışı varsayar (mağazalar arası sıkışma
  yok): RPT lehine iyimser. İade oranı newsvendor'da yok sayılır.
- SS25'in öğrenmesi AW24'ün gerçekleşen (Banu'lu) tarihinden; bir kol AW24'te başka RPT
  verseydi SS25'e giden geçmiş biraz farklı olurdu.
- SS23'ün karar anlarında kapanmış sezon yoktur: Basit nötr çarpanlarla çalışır
  (`hazirla.carpan_bulucu`).
- Kalibrasyonun hedefi Basit'tir (gerçek değil); gerçeğe karşı yanlılık yalnız raporda ölçülür.
- Dağıtım kuralı seçiminin yol belirsizliği ölçülmez (yollarda yeniden seçilmez).
- p > 0 yollarında yeniden kurulan DuckDB'nin yayımlananla eşitliği ayrıca denetlenmez (yol 0
  eşdeğerlik testiyle kilitli).
