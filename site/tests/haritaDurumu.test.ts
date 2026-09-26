// site/tests/haritaDurumu.test.ts

import { describe, expect, it } from 'vitest'
import { asamaBul } from '../src/data/harita'
import { algoritmaDurumu, asamaAktifMi, type DiziBagi } from '../src/lib/haritaDurumu'

const A: DiziBagi = {
  id: 'replenishment/otomatik-ikmal',
  baslik: 'Otomatik ikmal',
  adres: '/replenishment/otomatik-ikmal/',
  algoritmalar: ['otomatik-ikmal'],
  deginir: ['yok-satma'],
  yayinda: true,
}

const B: DiziBagi = {
  id: 'indirim/markdown',
  baslik: 'Markdown taslağı',
  adres: '/indirim/markdown/',
  algoritmalar: ['markdown'],
  deginir: ['yasam-egrisi'],
  yayinda: false,
}

const C: DiziBagi = {
  id: 'is-zekasi/yok-satma',
  baslik: 'Yok satma',
  adres: '/is-zekasi/yok-satma/',
  algoritmalar: ['yok-satma'],
  deginir: [],
  yayinda: true,
}

describe('algoritmaDurumu', () => {
  it('kapsayan yayındaki dizi algoritmayı aktif yapar', () => {
    expect(algoritmaDurumu('otomatik-ikmal', [A])).toEqual({
      tur: 'aktif',
      diziler: [{ baslik: A.baslik, adres: A.adres }],
    })
  })

  it('yalnızca taslak dizi durumu değiştirmez', () => {
    expect(algoritmaDurumu('markdown', [B])).toEqual({ tur: 'soluk' })
    expect(algoritmaDurumu('yasam-egrisi', [B])).toEqual({ tur: 'soluk' })
  })

  it('değinme soluk başlığa not ekler', () => {
    expect(algoritmaDurumu('yok-satma', [A])).toEqual({
      tur: 'deginilmis',
      diziler: [{ baslik: A.baslik, adres: A.adres }],
    })
  })

  it('kapsama değinmeyi yener', () => {
    expect(algoritmaDurumu('yok-satma', [A, C])).toEqual({
      tur: 'aktif',
      diziler: [{ baslik: C.baslik, adres: C.adres }],
    })
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
