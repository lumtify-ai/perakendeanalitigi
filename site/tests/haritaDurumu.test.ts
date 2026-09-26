// site/tests/haritaDurumu.test.ts

import { describe, expect, it } from 'vitest'
import { asamaBul } from '../src/data/harita'
import { algoritmaDurumu, asamaAktifMi, type DiziBagi } from '../src/lib/haritaDurumu'

const A: DiziBagi = {
  id: 'replenishment/otomatik-ikmal',
  baslik: 'Otomatik ikmal',
  adres: '/replenishment/otomatik-ikmal/',
  algoritmalar: ['otomatik-ikmal'],
  yayinda: true,
}

const B: DiziBagi = {
  id: 'indirim/markdown',
  baslik: 'Markdown taslağı',
  adres: '/indirim/markdown/',
  algoritmalar: ['markdown'],
  yayinda: false,
}

const C: DiziBagi = {
  id: 'is-zekasi/yok-satma',
  baslik: 'Yok satma',
  adres: '/is-zekasi/yok-satma/',
  algoritmalar: ['yok-satma'],
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
