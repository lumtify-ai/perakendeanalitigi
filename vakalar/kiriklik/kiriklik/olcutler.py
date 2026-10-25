"""Ölçütler ve korunum (tasarım §0 K1, K6, K11, K13): bir kolun koşusu yolunun Lumoda koşusuyla kıyaslanır.

    korunum(kol, lumoda, plan, karar)   dict[str, bool]   koşu geçerli mi (aynı dünya, aynı mal, plan kesilmedi)
    olc(kol, lumoda, plan, sezon)       dict              ölçüm (JSON'a döner: int, float, str, None)

`kol` ve `lumoda` `allocation.motor.KosuKaydi` (tembel, önbellekten) ya da `motor.Kosu`; `lumoda` aynı yolun Lumoda
koşusudur (enjekte yuvası yok), `plan` kolun `kiriklik.plan.Plan`'ı. Yapı gereği iki koşuda müşteri akışı (talep
tohumu), RPT siparişleri ve fiyat kararları aynıdır (K6; `simulasyon` modül notu); aradaki tek fark transferdir ve
`korunum` bunu sınar. Bütün sayılar rapordan yazılara gider: tanımlar burada tamdır.

Bu modül ölçüm tarafındadır (`simulasyon.KOSU_DISI`, `tests/test_sizinti.py` OLCUM): gizli gerçeğin yalnız koşunun
`gercek` tablosunu (`karsilanmayan`) okur; dünyaya ve onun gizli alanlarına dokunmaz. Boyut bilgisi (ürün, mağaza
tipi, sezon tarihleri) koşunun kendi `urun`, `magaza`, `sezon` tablolarından okunur. Büyük tablolar (satış, stok,
sevkiyat, gizli gerçek) DuckDB'de, tembel kayıtta doğrudan Parquet'ten toplanır.

**Doğrulama** (`ValueError`): `lumoda` Lumoda koşusu (`meta["turler"] == {}`); iki koşunun ölçeği, gün sayısı ve
yolu aynı; `plan.sezon == sezon` (test sezonu). Kol bir plan koşusuysa `meta["parametreler"]["sezon"] == sezon` ve
yuvanın plan kimliği (`meta["politikalar"]["elle_transfer"]["parametreler"]["plan"]`) `plan.kimlik`; kol Lumoda
koşusuysa plan boş olmalıdır (`olc(lumoda, lumoda, plan.bos(...), sezon)` taban çizgisinin kendine karşı ölçümüdür:
bütün farklar sıfır).

**Kapsam.** Sezon kapsamı = test sezonunun Collection SKU'ları, Standart beden seti hariç (`kaynak` ile aynı süzgeç).
Fiziksel mağaza = tip AVM ya da Cadde (`sabitler.FIZIKSEL_TIPLER`). Transfer edilen kapsam = planın option'ları
(bütün SKU'ları). Hücre = (mağaza, SKU); çift = (mağaza, option). Alıcı hücreler planın (alici, urun_id)'leri,
verici hücreler (verici, urun_id)'leri; alıcı ve verici çiftleri aynı biçimde (alici | verici, option_id).

**Tarihler.** Karar `sabitler.KARAR[sezon]` (pazartesi); indirim ve çıkış yayımlanan `sezon` tablosundan
(`kaynak.sezon_dates`). Pencereler (yarı açık): **tam** [karar, indirim), **indirim** [indirim, çıkış), **outlet**
[çıkış, çıkış + 84) (İndirim Takvimi'nin outlet penceresi; bu pencereye düşen iadeler de oradadır); **toplam** üçünün
birleşimi [karar, çıkış + 84). Karardan önce iki koşu birebir aynı olduğu için ölçüm karar gününde başlar.
**Kapsanma:** koşunun son günü `min(ISINMA_BASLANGIC + gun_sayisi − 1, BITIS)` (tam koşuda BITIS); bitişi bu
günü aşan pencere ve tarihi bunu aşan fotoğraf ölçülmez, alan `None` olur (kısa test koşuları; tam koşuda hepsi
kapsanır). Toplam, bir penceresi `None` ise `None`dur.

**Kırıklık** (K1, K11; `olcu.cift_tablosu` + `olcu.ozet`): dört pazartesi stok fotoğrafı (sabah, satıştan önce):
`karar` (karar sabahı), `varis_sonrasi` (karar + 7'den sonraki ilk pazartesi, dahil), `indirim_oncesi` (indirim
gününden önceki son pazartesi), `cikis_oncesi` (çıkış − 7'den önceki son pazartesi, dahil; v4'te çıkış − 7'nin
kendisi). Fiziksel mağazalar, sezon kapsamının SKU'ları. Kapsamlar: `transfer_edilen_alici` (planın alıcı çiftleri),
`transfer_edilen_verici` (verici çiftleri), `transfer_edilen` (ikisinin birleşimi), `butun` (sezon kapsamının bütün
çiftleri). Her biri için kolun ve Lumoda'nın `ozet`i ve mutlak sayıların farkı (kol − lumoda): `kirik_beden`,
`kirik_cift`, `stoklu_cift`, `eksik_adet`. Stoğu sıfıra inen çift paydadan çıkar (`olcu.ozet` notu); mutlak sayılar
bu yüzden oranların yanındadır.

**Satışa dönüş** (K11; satış = `satis` tablosu, `adet` net: iade satırı negatif):
- *Saha ölçüsü* (yalnız kol koşusu; sahada görülebilen tek ölçü): alıcı hücre başına `alinan` = planın o hücreye
  adet toplamı; `varis` = kolun karar günü `elle_transfer` sevkiyat satırlarından planın o hücreye satırlarının
  (kaynak = verici, hedef = alıcı, urun_id) en erken `varis_tarihi` (eşleşen satır yoksa hücre satış saymaz, paydada
  kalır). `saha_indirime` = Σ min(hücrenin [varis, indirim) brüt pozitif satışı, alinan) ÷ Σ alinan;
  `saha_cikisa` aynısı [varis, çıkış). Pay `indirime_satilan`, `cikisa_satilan`; payda `alinan_adet`. Satış
  hücrenin bütün stoğundandır (asortinin altındaki önceki stok dahil); min bu yüzden alınanla sınırlar.
- *Gerçek etki* (yalnız simülasyonda): `etki_adet[pencere]` = transfer edilen option'ların bütün mağazalarında ve
  kanallarında (fiziksel, Outlet, Online) net satış adedi, kol − lumoda; `etki_oran` = etki_adet[toplam] ÷ taşınan
  adet (Σ plan adedi). Bütün kanallar: transferin sezon içi kazancı çıkışta outlet'e kalan malı azaltır, bu
  pencere etkinin parçasıdır. `etki_adet_fiziksel` aynısı yalnız fiziksel mağazalarda.
- `vericide_kayip_adet` = Σ verici hücreler (kol − lumoda) net satış [karar, çıkış) (beklenen ≤ 0);
  `alicida_kazanc_adet` aynısı alıcı hücreler. Saha ile etki arasındaki fark sahanın vericiyi görmediğidir (S6).

**Para** (`satis.tutar` net TL, iade dahil; bütün mağazalar ve kanallar): `ciro[kapsam]` kolun, Lumoda'nın ve
farkın (kol − lumoda) pencere toplamları; kapsamlar `transfer_edilen` ve `sezon`. Arz kollar arasında aynıdır (K6:
aynı RPT, aynı ilk dağıtım), bu yüzden ciro farkı katkı farkıdır (İndirim Takvimi R4'ün tanımı: katkı = ciro − arz
alış; arz terimi farkta düşer). `brut_kar_farki[kapsam]` = ciro farkı[toplam] − Σ (alış fiyatı × net adet farkı)
[karar, çıkış + 84). `maliyet[paket]` (`sabitler.MALIYET_PAKETLERI`: düşük, orta, yüksek) = toplama × taşınan adet
+ kargo × rota + yıpranma × Σ (alış fiyatı × adet) planın satırları üzerinden; rota = tekil (verici, alıcı) mağaza
çifti bütün option'lar üzerinden (`plan.rotalar`, K19; aynı çift birçok option taşısa da bir kargo). `net[paket]` =
ciro farkı (sezon, toplam) − maliyet[paket].

**Stok** (kapsamlar `transfer_edilen`, `sezon`; kol, Lumoda, fark; İndirim Takvimi `option_tablosu` tanımları):
`cikista_kalan` çıkış − 7 fotoğrafında mağaza stoğu (`stok`, fotoğraftaki bütün mağazalar) ve depo stoğu
(`depo_stok`): `magaza_adet`, `depo_adet`, `adet`, `liste` (× liste fiyatı), `alis` (× alış fiyatı); yoldaki mal
girmez. `outlete_giden` `sevkiyat` tip `outlet_akisi` [karar, çıkış + 84): `adet`, `liste`, `alis`. `olu_stok`
depo stoğu çıkış + 120 gününde (iki koşuda aynı gün; depo fotoğrafı günlüktür): `adet`, `alis`. Koşu o günü
kapsamıyorsa `None`. İndirim Takvimi'nden tek sapma bu kapsanma kuralıdır: orada gün min(çıkış + 120, koşunun son
depo fotoğrafı) idi; kısa koşunun son fotoğrafı ölü stok sayılmaz, iki koşu farklı günlerde ölçülmez.

**Yan etki** [karar, çıkış + 84), kol − lumoda: `replenishment_adet_farki` (`sevkiyat` tip `replenishment`;
`sezon` kapsamı ve `tum` bütün SKU'lar); `elle_transfer_adet_farki` Lumoda'nın bölge müdürü transferi, planın kendi
satırları düşülerek: (kolun `elle_transfer` adedi − planın karar günü gerçekten sevk edilen adedi) − Lumoda'nınki
(`sezon`, `tum`; plan sezon kapsamındadır). Sevk edilen plan adedi (kaynak, hedef, urun_id) başına min(plan adedi,
kolun karar günü `elle_transfer` adedi): kesilen ya da atılan plan satırı Lumoda'nın transferi sayılmaz (geçerli
koşuda plan tam sevk edilir ve ikisi aynıdır); `gizli_kayip_farki` gizli gerçeğin `karsilanmayan`ı, sezon kapsamı ×
fiziksel mağazalar (`gizli_kayip_lumoda` Lumoda'nın düzeyi); `test_disi_ciro_farki` sezon kapsamı dışındaki bütün SKU'ların cirosu
(öteki sezonlar, Outlet line, Basic/NOS, Standart; `test_disi_ciro_lumoda`); `surekli_siparis_adet_farki` Basic/NOS
sürekli tedarik siparişlerinin adedi (`siparis` tip `surekli`, sipariş tarihi [karar, çıkış + 84)).

**Plan** (planın kendisinden): `hareket`, `adet` (taşınan), `rota`, `option`, `alici_cift`, `alici_magaza`,
`verici_cift`, `verici_magaza`; `tamamlanan_set` = karar sabahı stoğu + alınan ile her bedeni (asortinin beş bedeni)
≥ 1 olan alıcı çifti sayısı (varıştaki durum; yoldaki günlerin satışı düşülmez, gerçekleşen durum `varis_sonrasi`
kesitindedir); `alici_basina_verici_medyan` (alıcı çifti başına tekil verici sayısının medyanı),
`rota_basina_adet_medyan` (plan boşsa `None`); `cozucu` `plan.bilgi`'den `durum`, `gap`, `kaynak` (varsa).

**Korunum** (K6; hepsi True değilse koşu geçersizdir, ölçülmez):
- `oncesi_birebir`: `satis` (tarih < karar), `stok` ve `depo_stok` fotoğrafları (tarih ≤ karar: fotoğraf günün
  başındadır, karar günü transferden önce), `sevkiyat` (tarih < karar), gizli gerçek (tarih < karar) iki koşuda
  satır satır aynı (çoklu küme eşitliği; iki tembel kayıtta önce Parquet'lerin aynı sırada eşitliğine bakılır:
  hızlı yol).
- `rpt_birebir`: `kayitlar["rpt"]` bütün koşu boyunca Lumoda'nınkiyle aynı (kısa ya da başka koşudan kurulmuş takvim
  bunu bozar). `fiyat_birebir`: `kayitlar["markdown"]` ve yayımlanan `fiyat` tablosu bütün koşu boyunca aynı.
  `siparis_birebir`: ilk ve RPT siparişleri (`siparis`, tip `surekli` dışı) ve onların `kalite_kontrol` satırları
  bütün koşu boyunca aynı (toplam arz). İçerikle karşılaştırılır (çoklu küme, `siparis_id` dışında; kalite kontrol
  satırı siparişin sipariş düzeyindeki alanlarıyla eşlenir): `siparis_id` oluşma sırasının numarasıdır ve tepkili
  sürekli siparişler araya girince kayar. Basic/NOS sürekli tedarik (`tip == "surekli"`) motorun içinde zincir
  satışına tepki verir (yuva değildir, oynatılamaz; transfer ikameyle Basic/NOS satışını değiştirir): replenishment
  gibi tepkili sayılır, farkı yan etkidedir (`surekli_siparis_adet_farki`).
- `plan_kesilmedi`: karar gününün `elle_transfer` sevkiyat satırları (kaynak, hedef, urun_id, adet). Motor planı
  Lumoda'nın elle transferinden önce uygular (`politika` notu) ve Lumoda'nın o günkü kararı iki koşuda aynıdır
  (karar sabahına kadar dünya aynı). Bu yüzden kolun satırları = planın satırları (kesilmemişse) + Lumoda'nın
  satırları (planın tükettiği stok yüzünden kesilmiş ya da düşmüş olabilir; bu K6'nın izin verdiği tepkidir). Koşul:
  planın satırlarının çoklu kümesi kolun satırlarının içinde ve geri kalan her (kaynak, hedef, urun_id) satırının
  adedi Lumoda'nın aynı satırının adedini aşmıyor. Kesilen, atılan ya da başka hedefe giden her plan satırı bunu
  bozar (kesilen plan satırı kolda daha küçük adetle görünür, aynı kaynaktan sonraki Lumoda satırı sıfırlanır).
  Lumoda'nın satırları kesilmediğinde koşul "kol − Lumoda = plan" çoklu küme eşitliğidir.
"""

import contextlib
from collections import Counter
from datetime import date, timedelta

import duckdb
import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.compute as pc
import pyarrow.dataset as pads
from allocation import motor
from perakende_veri.v4 import sabitler as v4_sabitler

from kiriklik import kaynak, olcu, sabitler
from kiriklik.plan import Plan, rotalar

OUTLET_GUN = 84
OLU_STOK_GUN = 120
CIKIS_FOTO_GUN = 7
PENCERELER = ("tam", "indirim", "outlet")
KESITLER = ("karar", "varis_sonrasi", "indirim_oncesi", "cikis_oncesi")
KAPSAMLAR = ("transfer_edilen_alici", "transfer_edilen_verici", "transfer_edilen", "butun")
MUTLAK = ("kirik_beden", "kirik_cift", "stoklu_cift", "eksik_adet")
COZUCU_ALANLARI = ("durum", "gap", "kaynak")
KORUNUM_KOSULLARI = ("oncesi_birebir", "rpt_birebir", "fiyat_birebir", "siparis_birebir", "plan_kesilmedi")


# ---------------------------------------------------------------------------
# Yardımcılar
# ---------------------------------------------------------------------------


def _ts(d: date) -> pd.Timestamp:
    return pd.Timestamp(d)


def _iso(d: date | None) -> str | None:
    return None if d is None else d.isoformat()


def _sayi(x):
    """JSON'a dönen sayı: tamsayı değerli tamsayı türleri int, öteki float; NaN/None → None."""
    if x is None:
        return None
    if isinstance(x, (bool, np.bool_)):
        return bool(x)
    if isinstance(x, (int, np.integer)):
        return int(x)
    x = float(x)
    return None if not np.isfinite(x) else x


def _jsonla(x):
    if isinstance(x, dict):
        return {str(k): _jsonla(v) for k, v in x.items()}
    if isinstance(x, (list, tuple)):
        return [_jsonla(v) for v in x]
    if isinstance(x, str) or x is None:
        return x
    return _sayi(x)


def _fark(a, b):
    """İç içe sözlüklerde kol − lumoda (None varsa None)."""
    if isinstance(a, dict):
        return {k: _fark(a[k], b[k]) for k in a}
    return None if a is None or b is None else a - b


def _sondaki_pazartesi(d: date) -> date:
    """d ya da ondan önceki son pazartesi."""
    return d - timedelta(days=d.weekday())


def _sonraki_pazartesi(d: date) -> date:
    """d ya da ondan sonraki ilk pazartesi."""
    return d + timedelta(days=(7 - d.weekday()) % 7)


def _son_gun(kosu) -> date:
    """Koşunun yayımlanan tablolarındaki son gün: min(ISINMA_BASLANGIC + gun_sayisi − 1, BITIS)."""
    g = kosu.meta.get("gun_sayisi")
    if g is None:
        return v4_sabitler.BITIS
    return min(v4_sabitler.BITIS, v4_sabitler.ISINMA_BASLANGIC + timedelta(days=int(g) - 1))


def _metin(df: pd.DataFrame) -> pd.DataFrame:
    """Kategorik sütunlar `string` türüne (DuckDB'ye kaydedilen iki koşunun türleri aynı olsun; eksik değer NULL)."""
    kat = [c for c in df.columns if isinstance(df[c].dtype, pd.CategoricalDtype)]
    return df.astype({c: "string" for c in kat}) if kat else df


class _Sql:
    """İki koşunun tabloları DuckDB görünümü olarak: `t("kol", "satis")` görünümün adını verir (ilk kullanımda kurulur;
    tembel kayıtta Parquet dosyası, bellekteki koşuda DataFrame). Küçük çerçeveler `kaydet` ile."""

    def __init__(self, **kosular):
        self.con = duckdb.connect(":memory:")
        self.kosular = kosular
        self._var: set[str] = set()

    def t(self, ad: str, tablo: str) -> str:
        v = f"{ad}_{tablo}"
        if v not in self._var:
            kosu = self.kosular[ad]
            if isinstance(kosu, motor.KosuKaydi):
                yol = str(kosu._yol(tablo)).replace("'", "''")
                self.con.execute(f"create view {v} as select * from read_parquet('{yol}')")
            else:
                self.con.register(v, _metin(kosu.tablo(tablo)))
            self._var.add(v)
        return v

    def kaydet(self, ad: str, df: pd.DataFrame) -> None:
        self.con.register(ad, df)

    def df(self, sql: str, *prm) -> pd.DataFrame:
        return self.con.execute(sql, list(prm)).df()

    def deger(self, sql: str, *prm):
        return self.con.execute(sql, list(prm)).fetchone()[0]

    def kapat(self) -> None:
        self.con.close()


@contextlib.contextmanager
def _sql(**kosular):
    s = _Sql(**kosular)
    try:
        yield s
    finally:
        s.kapat()


def _ayni_sirada(s: _Sql, tablo: str, op: str | None, t: pd.Timestamp | None) -> bool:
    """Hızlı yol: iki tembel kaydın Parquet'i (`tarih op t` süzgeciyle) aynı sırada, aynı şemayla birebir mi (Arrow
    `Table.equals`). Yalnız True kesindir; False çoklu küme karşılaştırmasına düşer (`_birebir`)."""
    kol, lum = s.kosular["kol"], s.kosular["lum"]
    if not (isinstance(kol, motor.KosuKaydi) and isinstance(lum, motor.KosuKaydi)):
        return False
    suzgec = None
    if op is not None:
        sinir = pa.scalar(t, pa.timestamp("ns"))
        suzgec = pc.field("tarih") < sinir if op == "<" else pc.field("tarih") <= sinir
    a = pads.dataset(str(kol._yol(tablo))).to_table(filter=suzgec)
    b = pads.dataset(str(lum._yol(tablo))).to_table(filter=suzgec)
    return a.num_rows == b.num_rows and a.equals(b)


def _birebir(s: _Sql, tablo: str, op: str | None = None, t: pd.Timestamp | None = None) -> bool:
    """`tablo` iki koşuda (kol, lum) satır satır aynı mı (`op` verilirse yalnız `tarih op t` satırları): çoklu küme
    eşitliği (sayılar eşit ve kol − lum boş, `except all`). Tembel kayıtlarda önce aynı sıradaki eşitliğe bakılır."""
    if op not in (None, "<", "<="):
        raise ValueError(f"op '<' ya da '<=' olmalı: {op!r}")
    if _ayni_sirada(s, tablo, op, t):
        return True
    a, b = s.t("kol", tablo), s.t("lum", tablo)
    w, prm = (f"where tarih {op} ?", [t]) if op else ("", [])
    na = s.deger(f"select count(*) from {a} {w}", *prm)
    nb = s.deger(f"select count(*) from {b} {w}", *prm)
    if na != nb:
        return False
    fark = s.deger(f"select count(*) from (select * from {a} {w} except all select * from {b} {w})", *prm, *prm)
    return fark == 0


def _kayit_esit(a: pd.DataFrame | None, b: pd.DataFrame | None) -> bool:
    if a is None or b is None:
        return False
    return list(a.columns) == list(b.columns) and a.reset_index(drop=True).equals(b.reset_index(drop=True))


# ---------------------------------------------------------------------------
# Doğrulama ve kapsam
# ---------------------------------------------------------------------------


def _lumoda_mi(kosu) -> bool:
    return kosu.meta.get("turler") == {}


def _dogrula(kol, lumoda, plan: Plan, sezon: str) -> None:
    if sezon not in sabitler.TEST_SEZONLARI:
        raise ValueError(f"test sezonu değil: {sezon!r} (geçerli: {sabitler.TEST_SEZONLARI})")
    if plan.sezon != sezon:
        raise ValueError(f"planın sezonu {plan.sezon!r}, ölçülen sezon {sezon!r}")
    if not _lumoda_mi(lumoda):
        raise ValueError(f"taban Lumoda koşusu olmalı (enjekte yuva yok): {sorted(lumoda.meta.get('turler') or {})}")
    for alan in ("olcek", "gun_sayisi"):
        if kol.meta.get(alan) != lumoda.meta.get(alan):
            raise ValueError(f"koşuların {alan} değeri farklı: {kol.meta.get(alan)!r} ↔ {lumoda.meta.get(alan)!r}")
    yol = [int((k.meta.get("parametreler") or {}).get("yol", 0)) for k in (kol, lumoda)]
    if yol[0] != yol[1]:
        raise ValueError(f"koşular farklı yolların: kol {yol[0]}, lumoda {yol[1]}")
    if _lumoda_mi(kol):
        if len(plan.hareketler):
            raise ValueError("kol bir Lumoda koşusu: plan boş olmalı (plan.bos)")
        return
    par = kol.meta.get("parametreler") or {}
    if par.get("sezon") != sezon:
        raise ValueError(f"kol koşusunun sezonu {par.get('sezon')!r}, ölçülen sezon {sezon!r}")
    kimlik = (((kol.meta.get("politikalar") or {}).get("elle_transfer") or {}).get("parametreler") or {}).get("plan")
    if kimlik != plan.kimlik:
        raise ValueError(f"kol koşusunun plan kimliği {str(kimlik)[:12]}…, verilen planınki {plan.kimlik[:12]}…")


class _Kapsam:
    """Sezon kapsamı, tarihler ve boyut bilgisi (koşunun kendi `urun`, `magaza`, `sezon` tablolarından)."""

    def __init__(self, kosu, sezon: str):
        urun = kosu.tablo("urun", ["urun_id", "option_id", "line", "sezon_kodu", "beden_seti", "beden_sira",
                                   "liste_fiyati", "alis_fiyati"])
        urun = urun.astype({"urun_id": str, "option_id": str, "line": str, "sezon_kodu": str, "beden_seti": str})
        self.urun = urun.set_index("urun_id")
        k = urun[(urun["sezon_kodu"] == sezon) & (urun["line"] == sabitler.LINE)
                 & (urun["beden_seti"] != sabitler.STANDART_BEDEN_SETI)]
        self.sku = pd.DataFrame({"urun_id": k["urun_id"].to_numpy(dtype=object),
                                 "option_id": k["option_id"].to_numpy(dtype=object),
                                 "beden_sira": k["beden_sira"].to_numpy(dtype=np.int64),
                                 "liste": k["liste_fiyati"].to_numpy(dtype=float),
                                 "alis": k["alis_fiyati"].to_numpy(dtype=float)})
        mag = kosu.tablo("magaza", ["magaza_id", "tip"]).astype({"magaza_id": str, "tip": str})
        self.mag = pd.DataFrame({"magaza_id": mag["magaza_id"].to_numpy(dtype=object),
                                 "tip": mag["tip"].to_numpy(dtype=object)})
        self.fiziksel = set(mag.loc[mag["tip"].isin(sabitler.FIZIKSEL_TIPLER), "magaza_id"])
        con = duckdb.connect(":memory:")
        try:
            con.register("sezon", kosu.tablo("sezon"))
            self.indirim, self.cikis = kaynak.sezon_dates(con, sezon)
        finally:
            con.close()
        self.sezon = sezon
        self.karar = sabitler.KARAR[sezon]
        self.outlet_sonu = self.cikis + timedelta(days=OUTLET_GUN)
        self.son = _son_gun(kosu)
        olu = self.cikis + timedelta(days=OLU_STOK_GUN)
        self.olu_gun = olu if self.kapsar_gun(olu) else None             # iki koşuda tek gün (modül notu "Stok")
        self.kesit = {"karar": self.karar,
                      "varis_sonrasi": _sonraki_pazartesi(self.karar + timedelta(days=7)),
                      "indirim_oncesi": _sondaki_pazartesi(self.indirim - timedelta(days=1)),
                      "cikis_oncesi": _sondaki_pazartesi(self.cikis - timedelta(days=CIKIS_FOTO_GUN))}
        self.pencere = {"tam": (self.karar, self.indirim), "indirim": (self.indirim, self.cikis),
                        "outlet": (self.cikis, self.outlet_sonu)}

    def kapsar_gun(self, d: date) -> bool:
        """`d` günü koşuda var mı (fotoğraf)."""
        return d <= self.son

    def kapsar(self, bit: date) -> bool:
        """[·, bit) penceresi koşuda tam mı."""
        return bit - timedelta(days=1) <= self.son

    def tarihler(self) -> dict:
        return {"karar": _iso(self.karar), "indirim": _iso(self.indirim), "cikis": _iso(self.cikis),
                "outlet_sonu": _iso(self.outlet_sonu), "son_gun": _iso(self.son)}


def _pencereli(degerler: dict, k: _Kapsam) -> dict:
    """{pencere: değer} + toplam; kapsanmayan pencere None."""
    d = {p: (degerler.get(p, 0) if k.kapsar(k.pencere[p][1]) else None) for p in PENCERELER}
    d["toplam"] = None if any(v is None for v in d.values()) else sum(d.values())
    return d


# ---------------------------------------------------------------------------
# Korunum
# ---------------------------------------------------------------------------


def _karar_gunu_elle(s: _Sql, ad: str, karar: date) -> pd.DataFrame:
    """Karar gününün `elle_transfer` sevkiyat satırları [kaynak, hedef, urun_id, adet, varis_tarihi]."""
    return s.df(f"""
        select cast(kaynak as varchar) as kaynak, cast(hedef as varchar) as hedef, cast(urun_id as varchar) as urun_id,
               cast(adet as bigint) as adet, varis_tarihi
        from {s.t(ad, "sevkiyat")} where tarih = ? and cast(tip as varchar) = 'elle_transfer'""", _ts(karar))


def _satirlar(df: pd.DataFrame, k="kaynak", h="hedef") -> Counter:
    return Counter(zip(df[k].astype(str), df[h].astype(str), df["urun_id"].astype(str),
                       df["adet"].astype(np.int64).tolist(), strict=True))


def _plan_kesilmedi(kol_satir: pd.DataFrame, lum_satir: pd.DataFrame, plan: Plan) -> bool:
    """Modül notu (`plan_kesilmedi`): plan ⊆ kol ve (kol − plan) her (kaynak, hedef, urun_id)'de Lumoda'yı aşmaz."""
    A, L = _satirlar(kol_satir), _satirlar(lum_satir)
    P = _satirlar(plan.hareketler, k="verici", h="alici")
    if any(A[x] < n for x, n in P.items()):
        return False
    kalan, lum = Counter(), Counter()
    for (k, h, u, a), n in (A - P).items():
        kalan[(k, h, u)] += a * n
    for (k, h, u, a), n in L.items():
        lum[(k, h, u)] += a * n
    return all(a <= lum[x] for x, a in kalan.items())


_SUREKLI = "surekli"


def _siparisler(s: _Sql, ad: str) -> str:
    """İlk ve RPT siparişlerinin satırları, `siparis_id` dışında (SQL alt sorgusu)."""
    return f"(select * exclude (siparis_id) from {s.t(ad, 'siparis')} where cast(tip as varchar) <> '{_SUREKLI}')"


def _kaliteler(s: _Sql, ad: str) -> str:
    """İlk ve RPT siparişlerinin kalite kontrol satırları, siparişin sipariş düzeyindeki alanlarıyla (`siparis_id`,
    `urun_id` ve `adet` dışında; SQL alt sorgusu)."""
    return f"""(select * exclude (siparis_id) from {s.t(ad, 'kalite_kontrol')}
                join (select distinct * exclude (urun_id, adet) from {s.t(ad, 'siparis')}
                      where cast(tip as varchar) <> '{_SUREKLI}') using (siparis_id))"""


def _coklu_esit(s: _Sql, a: str, b: str) -> bool:
    if s.deger(f"select count(*) from {a}") != s.deger(f"select count(*) from {b}"):
        return False
    return s.deger(f"select count(*) from (select * from {a} except all select * from {b})") == 0


def _arz_birebir(s: _Sql) -> bool:
    """`siparis_birebir` (modül notu "Korunum"): ilk ve RPT siparişleri ve kalite kontrolleri içerikle aynı."""
    return (_coklu_esit(s, _siparisler(s, "kol"), _siparisler(s, "lum"))
            and _coklu_esit(s, _kaliteler(s, "kol"), _kaliteler(s, "lum")))


def korunum(kol, lumoda, plan: Plan, karar: date) -> dict[str, bool]:
    """Koşunun geçerlilik koşulları (modül notu "Korunum"); `karar` planın sezonunun karar günü olmalı."""
    if karar != sabitler.KARAR.get(plan.sezon):
        raise ValueError(f"karar {karar} planın sezonunun ({plan.sezon}) karar günü değil")
    _dogrula(kol, lumoda, plan, plan.sezon)
    t = _ts(karar)
    with _sql(kol=kol, lum=lumoda) as s:
        oncesi = (_birebir(s, "satis", "<", t) and _birebir(s, "stok", "<=", t)
                  and _birebir(s, "depo_stok", "<=", t) and _birebir(s, "sevkiyat", "<", t)
                  and _birebir(s, "gercek", "<", t))
        fiyat = _kayit_esit(kol.kayitlar.get("markdown"), lumoda.kayitlar.get("markdown")) and _birebir(s, "fiyat")
        siparis = _arz_birebir(s)
        kesilmedi = _plan_kesilmedi(_karar_gunu_elle(s, "kol", karar), _karar_gunu_elle(s, "lum", karar), plan)
    rpt = _kayit_esit(kol.kayitlar.get("rpt"), lumoda.kayitlar.get("rpt"))
    return dict(zip(KORUNUM_KOSULLARI, map(bool, (oncesi, rpt, fiyat, siparis, kesilmedi)), strict=True))


# ---------------------------------------------------------------------------
# Ölçüm parçaları (koşu başına toplamlar)
# ---------------------------------------------------------------------------


def _satis_option(s: _Sql, ad: str, k: _Kapsam) -> pd.DataFrame:
    """Sezon kapsamının satışı [karar, çıkış + 84): option × pencere × mağaza tipi → adet, tutar, alış × adet."""
    return s.df(f"""
        select s.option_id,
               case when t.tarih < ? then 'tam' when t.tarih < ? then 'indirim' else 'outlet' end as pencere,
               coalesce(m.tip, '?') as tip,
               sum(t.adet)::bigint as adet, sum(t.tutar) as tutar, sum(t.adet * s.alis) as alis_tutar
        from {s.t(ad, "satis")} t
        join sku s on cast(t.urun_id as varchar) = s.urun_id
        left join mag m on cast(t.magaza_id as varchar) = m.magaza_id
        where t.tarih >= ? and t.tarih < ?
        group by 1, 2, 3""", _ts(k.indirim), _ts(k.cikis), _ts(k.karar), _ts(k.outlet_sonu))


def _toplam_ciro(s: _Sql, ad: str, k: _Kapsam) -> float:
    """Bütün SKU'ların cirosu [karar, çıkış + 84)."""
    return float(s.deger(f"select coalesce(sum(tutar), 0) from {s.t(ad, 'satis')} where tarih >= ? and tarih < ?",
                         _ts(k.karar), _ts(k.outlet_sonu)))


def _hucre_satis(s: _Sql, ad: str, k: _Kapsam, hucre: pd.DataFrame) -> pd.DataFrame:
    """`hucre` [magaza_id, urun_id, varis] satırları için: `net` [karar, çıkış) net adet; `poz_indirime`,
    `poz_cikisa` varıştan [indirim | çıkış)'a brüt pozitif adet. Satışı olmayan hücre 0."""
    s.kaydet("hucre", hucre)
    t = s.df(f"""
        select h.magaza_id, h.urun_id,
               sum(case when t.tarih < ? then t.adet else 0 end)::bigint as net,
               sum(case when t.adet > 0 and h.varis is not null and t.tarih >= h.varis and t.tarih < ?
                        then t.adet else 0 end)::bigint as poz_indirime,
               sum(case when t.adet > 0 and h.varis is not null and t.tarih >= h.varis and t.tarih < ?
                        then t.adet else 0 end)::bigint as poz_cikisa
        from hucre h join {s.t(ad, "satis")} t
          on cast(t.magaza_id as varchar) = h.magaza_id and cast(t.urun_id as varchar) = h.urun_id
        where t.tarih >= ? and t.tarih < ?
        group by 1, 2""", _ts(k.cikis), _ts(k.indirim), _ts(k.cikis), _ts(k.karar), _ts(k.cikis))
    out = hucre[["magaza_id", "urun_id"]].merge(t, on=["magaza_id", "urun_id"], how="left")
    return out.fillna({"net": 0, "poz_indirime": 0, "poz_cikisa": 0}).astype(
        {"net": np.int64, "poz_indirime": np.int64, "poz_cikisa": np.int64})


def _fotograflar(s: _Sql, ad: str, gunler: list[date]) -> pd.DataFrame:
    """Sezon kapsamının `stok` satırları verilen pazartesilerde [tarih, magaza_id, urun_id, adet]."""
    if not gunler:
        return pd.DataFrame({"tarih": [], "magaza_id": [], "urun_id": [], "adet": []})
    yer = ", ".join("?" for _ in gunler)
    df = s.df(f"""
        select t.tarih, cast(t.magaza_id as varchar) as magaza_id, cast(t.urun_id as varchar) as urun_id,
               cast(t.adet as bigint) as adet
        from {s.t(ad, "stok")} t join sku s on cast(t.urun_id as varchar) = s.urun_id
        where t.tarih in ({yer})""", *[_ts(g) for g in gunler])
    df["tarih"] = pd.to_datetime(df["tarih"]).dt.date
    return df


def _depo(s: _Sql, ad: str, gunler: list[date]) -> pd.DataFrame:
    """Sezon kapsamının `depo_stok` satırları verilen günlerde [tarih, urun_id, adet]."""
    if not gunler:
        return pd.DataFrame({"tarih": [], "urun_id": [], "adet": []})
    yer = ", ".join("?" for _ in gunler)
    df = s.df(f"""
        select t.tarih, cast(t.urun_id as varchar) as urun_id, cast(t.adet as bigint) as adet
        from {s.t(ad, "depo_stok")} t join sku s on cast(t.urun_id as varchar) = s.urun_id
        where t.tarih in ({yer})""", *[_ts(g) for g in gunler])
    df["tarih"] = pd.to_datetime(df["tarih"]).dt.date
    return df


def _sevk_tip(s: _Sql, ad: str, k: _Kapsam) -> pd.DataFrame:
    """[karar, çıkış + 84) sevkiyat: tip × kapsam (sezon kapsamı SKU'su mu) × option → adet, liste ve alış değeri."""
    return s.df(f"""
        select cast(t.tip as varchar) as tip, s.urun_id is not null as kapsam, s.option_id,
               sum(t.adet)::bigint as adet, sum(t.adet * coalesce(s.liste, 0)) as liste,
               sum(t.adet * coalesce(s.alis, 0)) as alis
        from {s.t(ad, "sevkiyat")} t left join sku s on cast(t.urun_id as varchar) = s.urun_id
        where t.tarih >= ? and t.tarih < ?
        group by 1, 2, 3""", _ts(k.karar), _ts(k.outlet_sonu))


def _surekli_adet(s: _Sql, ad: str, k: _Kapsam) -> int:
    """Basic/NOS sürekli tedarik siparişlerinin adedi, sipariş tarihi [karar, çıkış + 84)."""
    return int(s.deger(f"""
        select coalesce(sum(adet), 0)::bigint from {s.t(ad, "siparis")}
        where cast(tip as varchar) = '{_SUREKLI}' and siparis_tarihi >= ? and siparis_tarihi < ?""",
                       _ts(k.karar), _ts(k.outlet_sonu)))


def _gizli_kayip(s: _Sql, ad: str, k: _Kapsam) -> int:
    """Gizli gerçeğin karşılanmayan talebi: sezon kapsamı × fiziksel mağazalar, [karar, çıkış + 84)."""
    return int(s.deger(f"""
        select coalesce(sum(g.karsilanmayan), 0)::bigint
        from {s.t(ad, "gercek")} g
        join sku s on cast(g.urun_id as varchar) = s.urun_id
        join mag m on cast(g.magaza_id as varchar) = m.magaza_id
        where m.fiziksel and g.tarih >= ? and g.tarih < ?""", _ts(k.karar), _ts(k.outlet_sonu)))


class _Toplamlar:
    """Bir koşunun ölçüm toplamları (kol ve Lumoda için aynı sorgular)."""

    def __init__(self, s: _Sql, ad: str, k: _Kapsam, hucre: pd.DataFrame):
        self.satis = _satis_option(s, ad, k)
        self.toplam_ciro = _toplam_ciro(s, ad, k) if k.kapsar(k.outlet_sonu) else None
        self.hucre = _hucre_satis(s, ad, k, hucre)
        gunler = [g for g in (*k.kesit.values(),) if k.kapsar_gun(g)]
        self.foto = _fotograflar(s, ad, sorted(set(gunler)))
        self.depo = _depo(s, ad, sorted({g for g in (k.kesit["cikis_oncesi"], k.olu_gun) if g is not None
                                         and k.kapsar_gun(g)}))
        self.sevk = _sevk_tip(s, ad, k)
        self.gizli_kayip = _gizli_kayip(s, ad, k)
        self.surekli = _surekli_adet(s, ad, k)


# ---------------------------------------------------------------------------
# Bölümler
# ---------------------------------------------------------------------------


def _ciftler(h: pd.DataFrame, rol: str) -> set[tuple[str, str]]:
    return set(zip(h[rol].astype(str), h["option_id"].astype(str), strict=True))


def _kiriklik(k: _Kapsam, kt: _Toplamlar, lt: _Toplamlar, h: pd.DataFrame) -> dict:
    alici, verici = _ciftler(h, "alici"), _ciftler(h, "verici")
    kapsam_ciftleri = {"transfer_edilen_alici": alici, "transfer_edilen_verici": verici,
                       "transfer_edilen": alici | verici, "butun": None}

    def ozetler(foto: pd.DataFrame, gun: date) -> dict:
        f = foto[(foto["tarih"] == gun) & foto["magaza_id"].isin(k.fiziksel)]
        f = f.merge(k.sku[["urun_id", "option_id", "beden_sira"]], on="urun_id")
        hucre = pd.DataFrame({"magaza_id": f["magaza_id"], "option_id": f["option_id"],
                              "beden_sira": f["beden_sira"].astype(np.int64), "stok": f["adet"].astype(np.int64)})
        cift = olcu.cift_tablosu(hucre)
        anahtar = pd.Series(list(zip(cift["magaza_id"].astype(str), cift["option_id"].astype(str), strict=True)),
                            dtype=object)
        sonuc = {}
        for ad, ciftler in kapsam_ciftleri.items():
            c = cift if ciftler is None else cift[anahtar.isin(ciftler).to_numpy()]
            sonuc[ad] = olcu.ozet(c)
        return sonuc

    bolum = {}
    for ad, gun in k.kesit.items():
        if not k.kapsar_gun(gun):
            bolum[ad] = {"tarih": _iso(gun), "kapsamlar": None}
            continue
        ko, lo = ozetler(kt.foto, gun), ozetler(lt.foto, gun)
        bolum[ad] = {"tarih": _iso(gun), "kapsamlar": {
            kap: {"kol": ko[kap], "lumoda": lo[kap], "fark": {m: ko[kap][m] - lo[kap][m] for m in MUTLAK}}
            for kap in KAPSAMLAR}}
    return bolum


def _varislar(h: pd.DataFrame, kol_elle: pd.DataFrame) -> pd.DataFrame:
    """Alıcı hücreler [magaza_id, urun_id, alinan, varis]: planın satırlarının kolun karar günü elle_transfer
    satırlarındaki en erken varışı (modül notu)."""
    e = kol_elle.rename(columns={"kaynak": "verici", "hedef": "alici"})[["verici", "alici", "urun_id", "varis_tarihi"]]
    m = h[["verici", "alici", "urun_id", "adet"]].astype({"verici": str, "alici": str, "urun_id": str}).merge(
        e.groupby(["verici", "alici", "urun_id"], as_index=False)["varis_tarihi"].min(),
        on=["verici", "alici", "urun_id"], how="left")
    g = m.groupby(["alici", "urun_id"], as_index=False).agg(alinan=("adet", "sum"), varis=("varis_tarihi", "min"))
    return pd.DataFrame({"magaza_id": g["alici"].astype(object), "urun_id": g["urun_id"].astype(object),
                         "alinan": g["alinan"].astype(np.int64), "varis": pd.to_datetime(g["varis"])})


def _hucre_net(t: pd.DataFrame, hucreler: pd.DataFrame) -> int:
    m = t.merge(hucreler[["magaza_id", "urun_id"]].drop_duplicates(), on=["magaza_id", "urun_id"])
    return int(m["net"].sum())


def _satisa_donus(k: _Kapsam, kt: _Toplamlar, lt: _Toplamlar, h: pd.DataFrame, alici_h: pd.DataFrame,
                  verici_h: pd.DataFrame) -> dict:
    tasinan = int(h["adet"].sum())
    r = alici_h.merge(kt.hucre, on=["magaza_id", "urun_id"], how="left")
    alinan = int(r["alinan"].sum())
    ind = int(np.minimum(r["poz_indirime"], r["alinan"]).sum())
    cik = int(np.minimum(r["poz_cikisa"], r["alinan"]).sum())
    opt = set(h["option_id"].astype(str))

    def etki(fiziksel: bool) -> dict:
        def topla(t):
            x = t.satis[t.satis["option_id"].isin(opt)]
            if fiziksel:
                x = x[x["tip"].isin(sabitler.FIZIKSEL_TIPLER)]
            return {p: int(x.loc[x["pencere"] == p, "adet"].sum()) for p in PENCERELER}
        a, b = topla(kt), topla(lt)
        return _pencereli({p: a[p] - b[p] for p in PENCERELER}, k)

    e = etki(False)
    sezon_ici = k.kapsar(k.cikis)
    return {
        "alinan_adet": alinan, "indirime_satilan": ind if k.kapsar(k.indirim) else None,
        "cikisa_satilan": cik if k.kapsar(k.cikis) else None,
        "saha_indirime": ind / alinan if alinan and k.kapsar(k.indirim) else None,
        "saha_cikisa": cik / alinan if alinan and k.kapsar(k.cikis) else None,
        "etki_adet": e, "etki_adet_fiziksel": etki(True),
        "etki_oran": e["toplam"] / tasinan if tasinan and e["toplam"] is not None else None,
        "vericide_kayip_adet": (_hucre_net(kt.hucre, verici_h) - _hucre_net(lt.hucre, verici_h)) if sezon_ici else None,
        "alicida_kazanc_adet": (_hucre_net(kt.hucre, alici_h) - _hucre_net(lt.hucre, alici_h)) if sezon_ici else None,
    }


def _ciro(t: _Toplamlar, opt: set | None) -> tuple[dict, float]:
    x = t.satis if opt is None else t.satis[t.satis["option_id"].isin(opt)]
    return ({p: float(x.loc[x["pencere"] == p, "tutar"].sum()) for p in PENCERELER},
            float(x["tutar"].sum() - x["alis_tutar"].sum()))


def _para(k: _Kapsam, kt: _Toplamlar, lt: _Toplamlar, h: pd.DataFrame) -> dict:
    kapsamlar = {"transfer_edilen": set(h["option_id"].astype(str)), "sezon": None}
    ciro, brut = {}, {}
    for ad, opt in kapsamlar.items():
        (ck, bk), (cl, bl) = _ciro(kt, opt), _ciro(lt, opt)
        a, b = _pencereli(ck, k), _pencereli(cl, k)
        ciro[ad] = {"kol": a, "lumoda": b, "fark": _fark(a, b)}
        brut[ad] = bk - bl if k.kapsar(k.outlet_sonu) else None
    adet = h["adet"].to_numpy(dtype=np.int64)
    alis = float((k.urun.loc[h["urun_id"].astype(str), "alis_fiyati"].to_numpy(dtype=float) * adet).sum()) \
        if len(h) else 0.0
    n_rota = len(rotalar(h))
    maliyet, net = {}, {}
    fark = ciro["sezon"]["fark"]["toplam"]
    for ad, p in sabitler.MALIYET_PAKETLERI.items():
        m = {"toplama": p.toplama_birim_tl * int(adet.sum()), "kargo": p.kargo_rota_tl * n_rota,
             "yipranma": p.yipranma_orani * alis}
        m["toplam"] = m["toplama"] + m["kargo"] + m["yipranma"]
        maliyet[ad] = m
        net[ad] = None if fark is None else fark - m["toplam"]
    return {"ciro": ciro, "brut_kar_farki": brut, "tasinan_alis": alis, "maliyet": maliyet, "net": net}


def _stok(k: _Kapsam, kt: _Toplamlar, lt: _Toplamlar, h: pd.DataFrame) -> dict:
    fiyat = k.sku.set_index("urun_id")[["option_id", "liste", "alis"]]
    kapsamlar = {"transfer_edilen": set(h["option_id"].astype(str)), "sezon": None}
    foto = k.kesit["cikis_oncesi"]

    def deger(df: pd.DataFrame, opt) -> pd.DataFrame:
        x = df.join(fiyat, on="urun_id")
        return x if opt is None else x[x["option_id"].isin(opt)]

    def cikista(t: _Toplamlar, opt) -> dict | None:
        if not k.kapsar_gun(foto):
            return None
        m = deger(t.foto[t.foto["tarih"] == foto], opt)
        d = deger(t.depo[t.depo["tarih"] == foto], opt)
        ma, da = int(m["adet"].sum()), int(d["adet"].sum())
        return {"magaza_adet": ma, "depo_adet": da, "adet": ma + da,
                "liste": float((m["adet"] * m["liste"]).sum() + (d["adet"] * d["liste"]).sum()),
                "alis": float((m["adet"] * m["alis"]).sum() + (d["adet"] * d["alis"]).sum())}

    def outlete(t: _Toplamlar, opt) -> dict | None:
        if not k.kapsar(k.outlet_sonu):
            return None
        x = t.sevk[(t.sevk["tip"] == "outlet_akisi") & t.sevk["kapsam"]]
        x = x if opt is None else x[x["option_id"].isin(opt)]
        return {"adet": int(x["adet"].sum()), "liste": float(x["liste"].sum()), "alis": float(x["alis"].sum())}

    def olu(t: _Toplamlar, opt) -> dict | None:
        if k.olu_gun is None:
            return None
        d = deger(t.depo[t.depo["tarih"] == k.olu_gun], opt)
        return {"adet": int(d["adet"].sum()), "alis": float((d["adet"] * d["alis"]).sum())}

    def uc(f, opt):
        a, b = f(kt, opt), f(lt, opt)
        if a is None or b is None:
            return None
        return {"kol": a, "lumoda": b, "fark": _fark(a, b)}

    bolum = {ad: {"cikista_kalan": uc(cikista, opt), "outlete_giden": uc(outlete, opt), "olu_stok": uc(olu, opt)}
             for ad, opt in kapsamlar.items()}
    bolum["tarihler"] = {"cikis_fotografi": _iso(foto) if k.kapsar_gun(foto) else None, "olu_stok": _iso(k.olu_gun)}
    return bolum


def _sevk_edilen_plan_adedi(h: pd.DataFrame, kol_elle: pd.DataFrame) -> int:
    """Planın karar günü gerçekten sevk edilen adedi: (verici, alıcı, urun_id) başına min(plan adedi, kolun karar günü
    `elle_transfer` adedi) (modül notu "Yan etki")."""
    anahtar = ["kaynak", "hedef", "urun_id"]
    p = (h.rename(columns={"verici": "kaynak", "alici": "hedef"})[anahtar + ["adet"]]
         .groupby(anahtar, as_index=False)["adet"].sum())
    e = kol_elle[anahtar + ["adet"]].groupby(anahtar, as_index=False)["adet"].sum().rename(columns={"adet": "sevk"})
    m = p.merge(e, on=anahtar, how="left").fillna({"sevk": 0})
    return int(np.minimum(m["adet"].to_numpy(dtype=np.int64), m["sevk"].to_numpy(dtype=np.int64)).sum())


def _yan_etki(k: _Kapsam, kt: _Toplamlar, lt: _Toplamlar, h: pd.DataFrame, kol_elle: pd.DataFrame) -> dict:
    tam = k.kapsar(k.outlet_sonu)
    plan_adet = _sevk_edilen_plan_adedi(h, kol_elle)

    def sevk(t: _Toplamlar, tip: str, kapsam: bool) -> int:
        x = t.sevk[t.sevk["tip"] == tip]
        return int((x[x["kapsam"]] if kapsam else x)["adet"].sum())

    def iki(tip: str, plan_dus: int) -> dict:
        if not tam:
            return {"sezon": None, "tum": None}
        return {"sezon": sevk(kt, tip, True) - plan_dus - sevk(lt, tip, True),
                "tum": sevk(kt, tip, False) - plan_dus - sevk(lt, tip, False)}

    sezon_k = float(kt.satis["tutar"].sum()), float(lt.satis["tutar"].sum())
    test_disi = None if not tam else ((kt.toplam_ciro - sezon_k[0]), (lt.toplam_ciro - sezon_k[1]))
    return {
        "replenishment_adet_farki": iki("replenishment", 0),
        "elle_transfer_adet_farki": iki("elle_transfer", plan_adet),
        "gizli_kayip_farki": kt.gizli_kayip - lt.gizli_kayip if tam else None,
        "gizli_kayip_lumoda": lt.gizli_kayip if tam else None,
        "test_disi_ciro_farki": None if test_disi is None else test_disi[0] - test_disi[1],
        "test_disi_ciro_lumoda": None if test_disi is None else test_disi[1],
        "surekli_siparis_adet_farki": kt.surekli - lt.surekli if tam else None,
    }


def _plan_ozeti(k: _Kapsam, kt: _Toplamlar, plan: Plan) -> dict:
    h = plan.hareketler.astype({"option_id": str, "urun_id": str, "verici": str, "alici": str})
    r = rotalar(h)
    alicilar = h.groupby(["alici", "option_id"])["verici"].nunique()
    # tamamlanan set: karar sabahı stoğu + alınan, asortinin her bedeni ≥ 1
    foto = kt.foto[kt.foto["tarih"] == k.karar]
    ciftler = alicilar.index.to_frame(index=False).rename(columns={"alici": "magaza_id"})
    skular = ciftler.merge(k.sku[["urun_id", "option_id", "beden_sira"]], on="option_id")
    st = skular.merge(foto[["magaza_id", "urun_id", "adet"]], on=["magaza_id", "urun_id"], how="left")
    al = h.groupby(["alici", "urun_id"], as_index=False)["adet"].sum().rename(
        columns={"alici": "magaza_id", "adet": "alinan"})
    st = st.merge(al, on=["magaza_id", "urun_id"], how="left").fillna({"adet": 0, "alinan": 0})
    st["sonra"] = st["adet"] + st["alinan"]
    tam_mi = st.groupby(["magaza_id", "option_id"]).agg(
        beden=("beden_sira", "nunique"), dolu=("sonra", lambda x: int((x >= 1).sum())))
    tamamlanan = int(((tam_mi["dolu"] == len(sabitler.ASORTI)) & (tam_mi["beden"] == len(sabitler.ASORTI))).sum())
    return {
        "hareket": len(h), "adet": int(h["adet"].sum()), "rota": len(r),
        "option": int(h["option_id"].nunique()),
        "alici_cift": len(alicilar), "alici_magaza": int(h["alici"].nunique()),
        "verici_cift": int(h[["verici", "option_id"]].drop_duplicates().shape[0]),
        "verici_magaza": int(h["verici"].nunique()),
        "tamamlanan_set": tamamlanan,
        "alici_basina_verici_medyan": float(np.median(alicilar.to_numpy())) if len(alicilar) else None,
        "rota_basina_adet_medyan": float(np.median(r["adet"].to_numpy())) if len(r) else None,
        "cozucu": {a: plan.bilgi[a] for a in COZUCU_ALANLARI if a in plan.bilgi},
    }


# ---------------------------------------------------------------------------
# Ölçüm
# ---------------------------------------------------------------------------


def olc(kol, lumoda, plan: Plan, sezon: str) -> dict:
    """Kolun `sezon` ölçümü, yolun Lumoda koşusuna göre (modül notu). Bölümler: `sezon`, `tarihler`, `kiriklik`,
    `satisa_donus`, `para`, `stok`, `yan_etki`, `plan`. Değerler JSON'a döner; kapsanmayan alan `None`."""
    _dogrula(kol, lumoda, plan, sezon)
    k = _Kapsam(kol, sezon)
    h = plan.hareketler.astype({"option_id": str, "urun_id": str, "verici": str, "alici": str})
    with _sql(kol=kol, lum=lumoda) as s:
        s.kaydet("sku", k.sku)
        s.kaydet("mag", k.mag.assign(fiziksel=k.mag["tip"].isin(sabitler.FIZIKSEL_TIPLER)))
        kol_elle = _karar_gunu_elle(s, "kol", k.karar)
        alici_h = _varislar(h, kol_elle)
        verici_h = pd.DataFrame({"magaza_id": h["verici"].astype(object), "urun_id": h["urun_id"].astype(object)}
                                ).drop_duplicates().reset_index(drop=True)
        hucre = pd.concat([alici_h[["magaza_id", "urun_id", "varis"]],
                           verici_h.assign(varis=pd.NaT)], ignore_index=True)
        hucre = hucre.groupby(["magaza_id", "urun_id"], as_index=False)["varis"].min()
        hucre["varis"] = pd.to_datetime(hucre["varis"])
        kt = _Toplamlar(s, "kol", k, hucre)
        lt = _Toplamlar(s, "lum", k, hucre)
    sonuc = {
        "sezon": sezon,
        "tarihler": k.tarihler(),
        "kiriklik": _kiriklik(k, kt, lt, h),
        "satisa_donus": _satisa_donus(k, kt, lt, h, alici_h, verici_h),
        "para": _para(k, kt, lt, h),
        "stok": _stok(k, kt, lt, h),
        "yan_etki": _yan_etki(k, kt, lt, h, kol_elle),
        "plan": _plan_ozeti(k, kt, plan),
    }
    return _jsonla(sonuc)
