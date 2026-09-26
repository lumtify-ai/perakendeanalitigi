// site/src/lib/haritaDurumu.ts
//
// Bir algoritmanın veya aşamanın "durumu" haritada sabit değil — hangi
// dizilerin yayında olduğuna göre türer. Bu türetme her sayfa isteğinde
// yeniden hesaplanır ki bir dizi taslaktan yayına geçtiğinde harita sayfaları
// elle güncellenmeden doğru rengi göstersin. İki durum var: algoritmayı
// kapsayan yayında bir dizi varsa aktif, yoksa soluk. Bir dizinin başka bir
// algoritmadan yalnızca söz etmesi haritada iz bırakmaz (spec §0.1 madde 7:
// "değinme" kavramı okurda karışıklık yarattığı için kaldırıldı).

import type { Asama, Faz } from '../data/harita'

/** Bir dizinin haritayla bağı. `id` koleksiyon id'si: 'rpt/tekrar-siparis'. */
export type DiziBagi = {
  id: string
  baslik: string
  adres: string // '/rpt/tekrar-siparis/'
  algoritmalar: string[]
  yayinda: boolean // en az bir `durum: yayinda` yazısı var
  yaziSayisi: number // yayındaki yazı sayısı — DiziEtiketi "· N yazı" basar
}

/** Bir diziye geri bağlantı için yeterli olan alanlar; DiziBagi'nin geri kalanı görüntülemeyle ilgisiz. */
export type DiziAtfi = { baslik: string; adres: string; yaziSayisi: number }

export type AlgoritmaDurumu =
  | { tur: 'aktif'; diziler: DiziAtfi[] }
  | { tur: 'soluk' }

/** Bir aşamanın ya da fazın ilerlemesi: kaç algoritması aktif, kaç tanesi var. */
export type Ilerleme = { aktif: number; toplam: number }

function atfaCevir(dizi: DiziBagi): DiziAtfi {
  return { baslik: dizi.baslik, adres: dizi.adres, yaziSayisi: dizi.yaziSayisi }
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

/** Bir aşamanın ilerlemesi: kaç algoritması aktif, aşamanın toplam algoritma sayısı. */
export function asamaIlerlemesi(asama: Asama, diziler: DiziBagi[]): Ilerleme {
  const aktif = asama.algoritmalar.filter(
    (algoritma) => algoritmaDurumu(algoritma.id, diziler).tur === 'aktif',
  ).length
  return { aktif, toplam: asama.algoritmalar.length }
}

/** Bir fazın ilerlemesi: bütün aşamalarının ilerlemesinin toplamı. */
export function fazIlerlemesi(faz: Faz, diziler: DiziBagi[]): Ilerleme {
  return faz.asamalar.reduce(
    (toplam, asama) => {
      const ilerleme = asamaIlerlemesi(asama, diziler)
      return { aktif: toplam.aktif + ilerleme.aktif, toplam: toplam.toplam + ilerleme.toplam }
    },
    { aktif: 0, toplam: 0 },
  )
}
