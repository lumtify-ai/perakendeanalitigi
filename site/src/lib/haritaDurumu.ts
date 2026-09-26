// site/src/lib/haritaDurumu.ts
//
// Bir algoritmanın veya aşamanın "durumu" haritada sabit değil — hangi
// dizilerin yayında olduğuna göre türer. Bu türetme her sayfa isteğinde
// yeniden hesaplanır ki bir dizi taslaktan yayına geçtiğinde harita sayfaları
// elle güncellenmeden doğru rengi göstersin. İki durum var: algoritmayı
// kapsayan yayında bir dizi varsa aktif, yoksa soluk. Bir dizinin başka bir
// algoritmadan yalnızca söz etmesi haritada iz bırakmaz (spec §0.1 madde 7:
// "değinme" kavramı okurda karışıklık yarattığı için kaldırıldı).

import type { Asama } from '../data/harita'

/** Bir dizinin haritayla bağı. `id` koleksiyon id'si: 'rpt/tekrar-siparis'. */
export type DiziBagi = {
  id: string
  baslik: string
  adres: string // '/rpt/tekrar-siparis/'
  algoritmalar: string[]
  yayinda: boolean // en az bir `durum: yayinda` yazısı var
}

/** Bir diziye geri bağlantı için yeterli olan alanlar; DiziBagi'nin geri kalanı görüntülemeyle ilgisiz. */
export type DiziAtfi = { baslik: string; adres: string }

export type AlgoritmaDurumu =
  | { tur: 'aktif'; diziler: DiziAtfi[] }
  | { tur: 'soluk' }

function atfaCevir(dizi: DiziBagi): DiziAtfi {
  return { baslik: dizi.baslik, adres: dizi.adres }
}

/**
 * Bir algoritmanın durumunu türetir. Yalnızca `yayinda: true` diziler sayılır
 * — taslak bir dizi kapsıyor sayılmaz, aksi halde henüz yayımlanmamış bir
 * yazı harita sayfasında zaten "ele alınmış" görünürdü.
 */
export function algoritmaDurumu(algoritmaId: string, diziler: DiziBagi[]): AlgoritmaDurumu {
  const yayindakiler = diziler.filter((dizi) => dizi.yayinda)

  const kapsayanlar = yayindakiler.filter((dizi) => dizi.algoritmalar.includes(algoritmaId))
  if (kapsayanlar.length > 0) {
    return { tur: 'aktif', diziler: kapsayanlar.map(atfaCevir) }
  }

  return { tur: 'soluk' }
}

/** Aşamanın algoritmalarından en az biri aktifse aşama da aktiftir. */
export function asamaAktifMi(asama: Asama, diziler: DiziBagi[]): boolean {
  return asama.algoritmalar.some(
    (algoritma) => algoritmaDurumu(algoritma.id, diziler).tur === 'aktif',
  )
}
