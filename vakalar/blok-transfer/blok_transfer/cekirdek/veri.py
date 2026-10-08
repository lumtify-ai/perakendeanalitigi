"""v4 verisine bağlantı, karar anı ve evren (spec §3.1).

Bağlantı ve kirli kayıt ayıklayıcıları ortak pakette (`perakende_analitik.kaynak`);
bu modül vakanın üç işini yapar:

    baglan      yayımlanan v4 dosyasına salt okunur bağlanır
    karar_ani   sezonun indirim öncesi, ileri penceresi dolu son stok fotoğrafı
    gorunumler  `bt_*` geçici görünümleri: evren + temiz satış + hayalet süzülmüş stok

Görünümler TARİH SINIRI KOYMAZ: karar anından sonraki satır, varış ya da
fotoğraf da görünür. Karar sınırı her sorgunun kendi işidir (Görev 4).
"""
from datetime import date
from pathlib import Path

import duckdb
from perakende_analitik import kaynak


def baglan(yol: Path | None = None) -> duckdb.DuckDBPyConnection:
    """v4 DuckDB dosyasına salt okunur bağlanır (yol yoksa varsayılan; yoksa açık hata)."""
    return kaynak.baglan(yol)


def karar_ani(con: duckdb.DuckDBPyConnection, sezon_kodu: str = "AW25", olcum_hafta: int = 8) -> date:
    """Karar anı: `stok` fotoğraf tarihlerinden

    - `takvim.sezon_kodu = sezon_kodu` olan,
    - sezonun `indirim_baslangic`inden önce olan (üç dalganın indirimi aynı;
      herhangi birinden önce olması yeter ve en erkeni alınır),
    - `olcum_hafta` hafta sonrası de verinin son fotoğrafına (`max(stok.tarih)`)
      sığan

    en geç tarih. Yoksa `ValueError`."""
    sonuc = con.execute(
        """
        with foto as (select distinct tarih from stok),
        sinir as (select min(indirim_baslangic) as indirim from sezon where sezon_kodu = ?),
        son as (select max(tarih) as son_foto from stok)
        select max(f.tarih)
        from foto f
        join takvim k on k.tarih = f.tarih and k.sezon_kodu = ?
        cross join sinir cross join son
        where f.tarih < sinir.indirim
          and f.tarih + to_weeks(?::integer) <= son.son_foto
        """,
        [sezon_kodu, sezon_kodu, olcum_hafta],
    ).fetchone()[0]
    if sonuc is None:
        raise ValueError(
            f"{sezon_kodu} için karar anı yok: indirimden önce, {olcum_hafta} hafta ileri "
            "penceresi dolu bir stok fotoğrafı bulunamadı."
        )
    return sonuc.date() if hasattr(sonuc, "date") else sonuc


def gorunumler(con: duckdb.DuckDBPyConnection, karar: date) -> None:
    """`bt_magaza`, `bt_stok`, `bt_satis`, `bt_sevkiyat` geçici görünümlerini kurar.

    bt_magaza    fiziksel (ONL değil), `karar`da açık (açılışı geçmiş, kapanmamış)
                 ve tadilatta olmayan mağazalar; sütunlar `magaza_id`, `tip`
    bt_stok      `stok` ∩ çeşit hücreleri (hayalet stok düşer) ∩ `bt_magaza`
    bt_satis     mükerrersiz satış ∩ `bt_magaza`
    bt_sevkiyat  `tarih` = varış tarihi, `magaza_id` = hedef; yolda kalan
                 (varış tarihi boş) düşer; yalnız `bt_magaza`'ya gidenler
    """
    gun = f"timestamp '{karar.isoformat()}'"   # görünüm tanımı parametre almaz; tarih tipli, güvenli
    cesit = kaynak.cesit_hucreleri(con)
    temiz_satis = kaynak.temiz_satis(con)
    con.execute(
        f"""
        create or replace temp view bt_magaza as
        select m.magaza_id, m.tip from magaza m
        where m.magaza_id <> 'ONL'
          and m.acilis_tarihi <= {gun}
          and (m.kapanis_tarihi is null or m.kapanis_tarihi > {gun})
          and not exists (select 1 from magaza_olay o
                          where o.magaza_id = m.magaza_id and o.olay = 'tadilat'
                            and o.olay_tarihi <= {gun} and {gun} < o.bitis_tarihi)
        """
    )
    con.execute(
        f"""
        create or replace temp view bt_stok as
        select s.tarih, s.magaza_id, s.urun_id, s.adet
        from stok s
        join {cesit} c on c.magaza_id = s.magaza_id and c.urun_id = s.urun_id
        join bt_magaza m on m.magaza_id = s.magaza_id
        """
    )
    con.execute(
        f"""
        create or replace temp view bt_satis as
        select s.tarih, s.magaza_id, s.urun_id, s.adet
        from {temiz_satis} s
        join bt_magaza m on m.magaza_id = s.magaza_id
        """
    )
    con.execute(
        """
        create or replace temp view bt_sevkiyat as
        select v.varis_tarihi as tarih, v.hedef as magaza_id, v.urun_id, v.adet, v.tip
        from sevkiyat v
        join bt_magaza m on m.magaza_id = v.hedef
        where v.varis_tarihi is not null
        """
    )
