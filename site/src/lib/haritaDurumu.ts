// site/src/lib/haritaDurumu.ts
//
// Bir algoritmanın veya aşamanın "durumu" haritada sabit değil — hangi
// dizilerin yayında olduğuna göre türer. Bu türetme her sayfa isteğinde
// yeniden hesaplanır ki bir dizi taslaktan yayına geçtiğinde harita sayfaları
// elle güncellenmeden doğru rengi göstersin. Kural kasıtlı olarak katmanlı:
// önce kapsama (algoritmalar) bakılır, ancak o boşsa değinme (deginir)
// devreye girer — bir yazı bir algoritmayı yalnızca geçerken anmışsa bu,
// o algoritmanın kendi dizisi olduğu izlenimini vermemeli, ama tamamen
// solukmuş gibi de görünmemeli.

import type { Asama } from '../data/harita'

/** Bir dizinin haritayla bağı. `id` koleksiyon id'si: 'rpt/tekrar-siparis'. */
export type DiziBagi = {
  id: string
  baslik: string
  adres: string // '/rpt/tekrar-siparis/'
  algoritmalar: string[]
  deginir: string[]
  yayinda: boolean // en az bir `durum: yayinda` yazısı var
}

/** Bir diziye geri bağlantı için yeterli olan alanlar; DiziBagi'nin geri kalanı görüntülemeyle ilgisiz. */
export type DiziAtfi = { baslik: string; adres: string }

export type AlgoritmaDurumu =
  | { tur: 'aktif'; diziler: DiziAtfi[] }
  | { tur: 'deginilmis'; diziler: DiziAtfi[] }
  | { tur: 'soluk' }

function atfaCevir(dizi: DiziBagi): DiziAtfi {
  return { baslik: dizi.baslik, adres: dizi.adres }
}

/**
 * Bir algoritmanın durumunu türetir. Yalnızca `yayinda: true` diziler sayılır
 * — taslak bir dizi ne kapsıyor ne de değiniyor sayılmaz, aksi halde henüz
 * yayımlanmamış bir yazı harita sayfasında zaten "ele alınmış" görünürdü.
 * Kapsama (algoritmalar) değinmeyi (deginir) her zaman yener: bir algoritma
 * hem bir dizide kapsanıp hem başka bir dizide anılıyorsa yalnızca kapsayan
 * dizi(ler) gösterilir.
 */
export function algoritmaDurumu(algoritmaId: string, diziler: DiziBagi[]): AlgoritmaDurumu {
  const yayindakiler = diziler.filter((dizi) => dizi.yayinda)

  const kapsayanlar = yayindakiler.filter((dizi) => dizi.algoritmalar.includes(algoritmaId))
  if (kapsayanlar.length > 0) {
    return { tur: 'aktif', diziler: kapsayanlar.map(atfaCevir) }
  }

  const deginenler = yayindakiler.filter((dizi) => dizi.deginir.includes(algoritmaId))
  if (deginenler.length > 0) {
    return { tur: 'deginilmis', diziler: deginenler.map(atfaCevir) }
  }

  return { tur: 'soluk' }
}

/** Aşamanın algoritmalarından en az biri aktifse aşama da aktiftir. */
export function asamaAktifMi(asama: Asama, diziler: DiziBagi[]): boolean {
  return asama.algoritmalar.some(
    (algoritma) => algoritmaDurumu(algoritma.id, diziler).tur === 'aktif',
  )
}
