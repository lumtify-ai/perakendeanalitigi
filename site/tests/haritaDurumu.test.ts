// site/tests/haritaDurumu.test.ts

import { describe, expect, it } from 'vitest'
import { asamaBul, HARITA } from '../src/data/harita'
import {
  algoritmaDurumu,
  asamaAktifMi,
  asamaIlerlemesi,
  fazIlerlemesi,
  type DiziBagi,
} from '../src/lib/haritaDurumu'

const A: DiziBagi = {
  id: 'replenishment/otomatik-ikmal',
  baslik: 'Otomatik ikmal',
  adres: '/replenishment/otomatik-ikmal/',
  algoritmalar: ['otomatik-ikmal'],
  yayinda: true,
  yaziSayisi: 6,
}

const B: DiziBagi = {
  id: 'indirim/markdown',
  baslik: 'Markdown taslağı',
  adres: '/indirim/markdown/',
  algoritmalar: ['markdown'],
  yayinda: false,
  yaziSayisi: 0,
}

const C: DiziBagi = {
  id: 'is-zekasi/yok-satma',
  baslik: 'Yok satma',
  adres: '/is-zekasi/yok-satma/',
  algoritmalar: ['yok-satma'],
  yayinda: true,
  yaziSayisi: 2,
}

const BLOK_TRANSFER: DiziBagi = {
  id: 'transfer/blok-transfer',
  baslik: 'Blok Transfer',
  adres: '/transfer/blok-transfer/',
  algoritmalar: ['blok-transfer'],
  yayinda: true,
  yaziSayisi: 7,
}

const RPT: DiziBagi = {
  id: 'rpt/tekrar-siparis',
  baslik: 'Tekrar Sipariş',
  adres: '/rpt/tekrar-siparis/',
  algoritmalar: ['rpt-gereksinim-adet'],
  yayinda: true,
  yaziSayisi: 6,
}

describe('algoritmaDurumu', () => {
  it('kapsayan yayındaki dizi algoritmayı aktif yapar', () => {
    expect(algoritmaDurumu('otomatik-ikmal', [A])).toEqual({
      tur: 'aktif',
      diziler: [{ baslik: A.baslik, adres: A.adres, yaziSayisi: A.yaziSayisi }],
    })
  })

  it('yalnızca taslak dizi durumu değiştirmez', () => {
    expect(algoritmaDurumu('markdown', [B])).toEqual({ tur: 'soluk' })
    expect(algoritmaDurumu('yasam-egrisi', [B])).toEqual({ tur: 'soluk' })
  })

  it('algoritmayı kapsamayan yayındaki dizi onu soluk bırakır', () => {
    // Değinme kavramı kalktı (spec §0.1 madde 7): bir dizinin başka bir
    // algoritmadan söz etmesi haritada hiçbir iz bırakmaz.
    expect(algoritmaDurumu('yok-satma', [A])).toEqual({ tur: 'soluk' })
  })

  it('yalnızca iki durum var: aktif ve soluk', () => {
    const turler = new Set(
      ['otomatik-ikmal', 'yok-satma', 'markdown', 'rota'].map(
        (id) => algoritmaDurumu(id, [A, B, C]).tur,
      ),
    )
    expect([...turler].sort()).toEqual(['aktif', 'soluk'])
  })

  it('hiçbiri yoksa soluk', () => {
    expect(algoritmaDurumu('rota', [A, B, C])).toEqual({ tur: 'soluk' })
  })
})

describe('asamaAktifMi', () => {
  it('aşama bir algoritması aktifse aktif', () => {
    expect(asamaAktifMi(asamaBul('replenishment')!.asama, [A])).toBe(true)
    expect(asamaAktifMi(asamaBul('indirim')!.asama, [B])).toBe(false)
  })
})

describe('asamaIlerlemesi', () => {
  it('aktif algoritma sayısını aşamanın toplamına göre verir', () => {
    // transfer aşamasının üç algoritması var: blok-transfer, tekleme-transfer,
    // acma-kapama-transferi. Yalnızca blok-transfer yayında.
    expect(asamaIlerlemesi(asamaBul('transfer')!.asama, [BLOK_TRANSFER])).toEqual({
      aktif: 1,
      toplam: 3,
    })
  })

  it('taslak dizi aktif sayılmaz', () => {
    expect(asamaIlerlemesi(asamaBul('indirim')!.asama, [B])).toEqual({ aktif: 0, toplam: 2 })
  })

  it('hiçbir dizi kapsamıyorsa aktif sıfırdır', () => {
    expect(asamaIlerlemesi(asamaBul('mfp')!.asama, [])).toEqual({ aktif: 0, toplam: 1 })
  })
})

describe('fazIlerlemesi', () => {
  it('fazın bütün aşamalarının ilerlemesini toplar', () => {
    // Sezon İçi: allocation(2) + replenishment(1) + rpt(1) + transfer(3) +
    // indirim(2) = 9 algoritma. A, BLOK_TRANSFER, RPT ile üç tanesi aktif.
    const sezonIci = HARITA.find((faz) => faz.slug === 'sezon-ici')!
    expect(fazIlerlemesi(sezonIci, [A, BLOK_TRANSFER, RPT])).toEqual({ aktif: 3, toplam: 9 })
  })

  it('hiçbir dizi yoksa hepsi soluktur ama toplam değişmez', () => {
    const sezonIci = HARITA.find((faz) => faz.slug === 'sezon-ici')!
    expect(fazIlerlemesi(sezonIci, [])).toEqual({ aktif: 0, toplam: 9 })
  })
})
