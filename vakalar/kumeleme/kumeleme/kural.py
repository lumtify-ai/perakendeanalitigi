"""Kural tabanlı gruplar: Lumoda'nın bugünkü işi (K1 bölge, K2 ciro sınıfı, K3 bölge × sınıf) ve
konum kuralı (K4).

Kural: bu bir karar modülüdür; yalnız yayımlanan tablolardan gelen `kapsam` ve `satis`
girdisini okur, gizli gerçeğe ve ölçüm modüllerine dokunmaz (AST kilidi, `tests/test_sizinti.py`).
Her fonksiyon `kapsam`taki **bütün** mağazalara (kümelenen ve yeni) etiket verir ve
`magaza_id` dizinli bir `Series` döndürür; `kapsam` satır sırası korunur.

**K1 `bolge`.** Yayımlanan `bolge` olduğu gibi.

**K2 `ciro_sinifi`.** Karar gününden önceki son 12 ayın (`karar_gunu - 1 yıl <= tarih <
karar_gunu`) net cirosu: satış eksi iade, yani `tutar` toplamı (iade satırı negatif tutardır;
indirimden sonraki tutar). Mağazalar kümelenen mağazalar arasında (`kumelenir`) büyükten küçüğe
sıralanır; eşit cirolu mağazalar `magaza_id` sırasıyla. n kümelenen mağaza için ilk
`round(CIRO_A · n)` mağaza A, sonraki `round(CIRO_B · n)` mağaza B, kalanı C'dir (yarım yukarı
yuvarlama; 67 mağazada 13 / 20 / 34, 10 mağazada 2 / 3 / 5).

*Yeni mağaza* (`yeni`, geçmiş eşiği `GECMIS_HAFTA_ESIGI` altında): sıralamaya girmez ve sınıf
**C** alır; ciro sıralaması için yeterli geçmişi yoktur, planlamada da yeni mağaza öncelikle en
temkinli sınıfa konur. Eşiği geçip de 12 ayı doldurmamış mağaza (26-51 hafta) sıralamaya girer,
ama cirosu **yıllıklandırılır**: ilk satış gününden karar gününe kadar `g` gün geçmişse ciro
`pencere_gun / g` ile çarpılır (günlük ciro hızı × pencere). Aksi halde kısa geçmişli mağaza
sırf eksik ay yüzünden C'ye düşerdi. Bedeli: kısa geçmiş tek bir mevsimi görür, yıllıklandırma
mevsimselliği düzeltmez (yaz açılan mağazanın yıllıklandırılmış cirosu şişkin, kış açılanınki
düşük çıkabilir). `net_ciro` bu yıllıklandırılmış ciroyu verir (rapor eşikleri buradan).
Yıllıklandırma `TAM_YIL_HAFTA` (52) altındaki **her** mağazaya uygulanır, yeni mağazaya da: yeni
mağazanın yıllıklandırılmış cirosu yalnız raporlama içindir (SS25'te M041: ham 45,4 M, yıllıklandırılmış
125,9 M); sınıfı sıralamaya girmediği için ne olursa olsun C kalır.

*Tekilleştirme.* Gerçek `satis`ta birebir aynı satırlar vardır: yayımlanan tablonun tümünde 200 çift,
SS25 karar gününden önceki 12 aylık ciro penceresinde 70 çift (her biri iki kopya). `net_ciro` pencere
satırlarındaki birebir yinelenenleri kendisi düşürür (ortak `perakende_analitik.kaynak.temiz_satis`
görünümünün `select distinct` kuralı), yani çağıranın tekilleştirmesine bağlı değildir. Kural **gelen
sütunların tümü** üstünden çalışır: ham satırı `urun_id`, `adet` … ile birlikte verin; yalnız
(`tarih, magaza_id, tutar`) verilirse aynı gün aynı tutarlı iki gerçek satış tek sayılır. Günlük toplam
verirseniz satırlar zaten tekildir.

**K3 `bolge_ciro`.** Lumoda'nın planlama ızgarası: etiket `bolge×sınıf` (örn. `Marmara×A`).
Hücreler sınıf sırasıyla A-B-C dizilir; her bölgede en az `K3_EN_AZ` mağazası olmayan hücre
**komşu sınıfın** hücresine birleşir (komşu: dizideki dolu, bitişik hücre; boş B varsa A ile C
bitişiktir). Birleşme kuralı, bölge içinde şu döngüdür (bölgede tek grup kalana ya da bütün
gruplar `K3_EN_AZ`'ye varana dek):

    1. mağaza sayısı en az olan grup seçilir (eşitlikte A tarafındaki);
    2. A ya da C tarafındaki grubun tek komşusu B'yi içeren gruptur: **B öncelikli**, yani küçük
       uç hücre B'ye (ya da B'yi içeren gruba) eklenir;
    3. ortadaki (B'yi içeren) grup küçükse iki komşusundan mağazası az olanla birleşir
       (eşitlikte A).

Birleşen grubun etiketi sınıfları sırayla yan yana yazar: `Marmara×AB`, `Marmara×ABC`. Bölgenin
tümü `K3_EN_AZ`'den azsa tek grup olarak (örn. `Ege×ABC`) kalır; bölgeler birleşmez. Yeni mağaza
C olarak sayılır.

**K4 `konum`.** Yayımlanan şehir alanından, vakada yazılı açık tabloyla (`kaynak.SEHIR_IKLIM`,
`kaynak.TURISTIK`, `kaynak.METROPOL`): metropolse `metropol`; değilse şehrin iklim sınıfı; turistik
tatil beldesiyse `sicak_sahil`. Tabloda olmayan şehir hata verir (sessizce atanmaz).
"""

import math

import pandas as pd

from kumeleme import kaynak, sabitler

SINIFLAR = ("A", "B", "C")
AYIRAC = "×"
_YARIM = 1e-9


def _kimlikli(kapsam: pd.DataFrame, degerler) -> pd.Series:
    s = pd.Series(list(degerler), index=pd.Index(kapsam["magaza_id"].astype(str), name="magaza_id"),
                  dtype=object)
    return s


def _yarim_yukari(x: float) -> int:
    return int(math.floor(x + 0.5 + _YARIM))


def bolge(kapsam: pd.DataFrame) -> pd.Series:
    """K1: yayımlanan bölge."""
    return _kimlikli(kapsam, kapsam["bolge"].astype(str)).rename("k1")


def net_ciro(satis: pd.DataFrame, kapsam: pd.DataFrame, karar_gunu) -> pd.Series:
    """Son 12 ayın net cirosu (iade düşülmüş `tutar` toplamı); 12 aydan kısa geçmişli, geçmiş
    eşiğini geçen mağazanın cirosu yıllıklandırılmıştır (modül notu). `kapsam`taki her mağaza
    için bir değer (satışsız: 0). `satis`: en az `tarih, magaza_id, tutar` sütunları (ham satır ya da günlük
    toplam); birebir yinelenen satırlar düşer (modül notu); karar gününden sonrası okunmaz."""
    karar = pd.Timestamp(karar_gunu).normalize()
    bas = karar - pd.DateOffset(years=1)
    pencere_gun = (karar - bas).days
    s = satis.loc[(satis["tarih"] >= bas) & (satis["tarih"] < karar)].drop_duplicates()
    kimlik = s["magaza_id"].astype(str)
    ciro = s["tutar"].groupby(kimlik.to_numpy()).sum()
    ilk = s["tarih"].dt.normalize().groupby(kimlik.to_numpy()).min()
    ids = kapsam["magaza_id"].astype(str)
    c = ids.map(ciro).fillna(0.0).astype("float64")
    g = (karar - ids.map(ilk)).dt.days.astype("float64")              # satışsız: NaN
    kisa = (kapsam["gecmis_hafta"].to_numpy() < sabitler.TAM_YIL_HAFTA) & g.notna().to_numpy()
    carpan = (pencere_gun / g.clip(lower=1.0, upper=pencere_gun)).where(kisa, 1.0)
    return _kimlikli(kapsam, (c * carpan).to_numpy()).astype("float64").rename("net_ciro")


def ciro_sinifi(satis: pd.DataFrame, kapsam: pd.DataFrame, karar_gunu) -> pd.Series:
    """K2: A / B / C (modül notu). Yeni mağaza sıralamaya girmez ve C alır."""
    ciro = net_ciro(satis, kapsam, karar_gunu)
    kumelenir = pd.Series(kapsam["kumelenir"].to_numpy(dtype=bool), index=ciro.index)
    sirali = (pd.DataFrame({"ciro": ciro[kumelenir], "kimlik": ciro.index[kumelenir]})
              .sort_values(["ciro", "kimlik"], ascending=[False, True]))
    n = len(sirali)
    n_a = _yarim_yukari(sabitler.CIRO_A * n)
    n_b = _yarim_yukari(sabitler.CIRO_B * n)
    sinif = pd.Series("C", index=ciro.index, dtype=object, name="k2")
    sinif.loc[sirali["kimlik"].iloc[:n_a]] = "A"
    sinif.loc[sirali["kimlik"].iloc[n_a:n_a + n_b]] = "B"
    return sinif


def _birlestir(sayilar: dict[str, int]) -> dict[str, str]:
    """Bir bölgenin sınıf → mağaza sayısı tablosundan sınıf → grup sınıfları (`AB`, `ABC`)."""
    gruplar = [[s, n] for s, n in sayilar.items() if n > 0]     # A, B, C sırasıyla dolu hücreler
    while len(gruplar) > 1 and min(n for _, n in gruplar) < sabitler.K3_EN_AZ:
        i = min(range(len(gruplar)), key=lambda j: (gruplar[j][1], j))      # en küçük, eşitlikte A tarafı
        if i == 0:
            j = 1
        elif i == len(gruplar) - 1:
            j = i - 1
        else:                                                   # ortadaki: az mağazalı komşu, eşitlikte A
            j = i - 1 if gruplar[i - 1][1] <= gruplar[i + 1][1] else i + 1
        a, b = sorted((i, j))
        gruplar[a] = [gruplar[a][0] + gruplar[b][0], gruplar[a][1] + gruplar[b][1]]
        del gruplar[b]
    return {c: ad for ad, _ in gruplar for c in ad}


def bolge_ciro(kapsam: pd.DataFrame, ciro: pd.Series) -> pd.Series:
    """K3: `bolge×sınıf`, küçük hücreler birleşmiş (modül notu). `ciro`: K2 sınıfı (`magaza_id`
    dizinli)."""
    b = kapsam["bolge"].astype(str).to_numpy()
    sinif = ciro.reindex(kapsam["magaza_id"].astype(str)).to_numpy()
    df = pd.DataFrame({"bolge": b, "sinif": sinif})
    cikti = pd.Series(index=_kimlikli(kapsam, b).index, dtype=object, name="k3")
    for ad, alt in df.groupby("bolge", sort=True):
        sayim = alt["sinif"].value_counts()
        harita = _birlestir({c: int(sayim.get(c, 0)) for c in SINIFLAR})
        cikti.iloc[alt.index] = [f"{ad}{AYIRAC}{harita[c]}" for c in alt["sinif"]]
    return cikti


def konum(kapsam: pd.DataFrame) -> pd.Series:
    """K4: `metropol` ya da şehrin iklim sınıfı; turistik beldeler `sicak_sahil`."""
    bilinmeyen = sorted(set(kapsam["sehir"].astype(str)) - set(kaynak.SEHIR_IKLIM))
    if bilinmeyen:
        raise ValueError(f"şehir → iklim tablosunda olmayan şehir: {bilinmeyen}")

    def sinif(sehir: str) -> str:
        if sehir in kaynak.METROPOL:
            return "metropol"
        return "sicak_sahil" if sehir in kaynak.TURISTIK else kaynak.SEHIR_IKLIM[sehir]

    return _kimlikli(kapsam, [sinif(str(s)) for s in kapsam["sehir"]]).rename("k4")
