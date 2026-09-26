// site/tests/haritaGirdisi.test.ts

import { describe, expect, it } from 'vitest'
import { diziBaglari, fazAl, fazBasamagi } from '../src/lib/haritaGirdisi'

function yazi(id: string, durum: string) {
  return { id, data: { baslik: id, tip: 'hikaye', sira: 1, durum, ozet: '' } }
}

const DIZILER = [
  { id: 'rpt/tekrar-siparis', data: { baslik: 'Tekrar Sipariş', algoritmalar: ['rpt-adet'], deginir: ['yok-satma'] } },
  { id: 'indirim/markdown', data: { baslik: 'Markdown', algoritmalar: ['markdown'], deginir: [] } },
]

describe('diziBaglari', () => {
  it('adresi koleksiyon id’sinden kurar ve listeleri taşır', () => {
    const [rpt] = diziBaglari(DIZILER, [])
    expect(rpt).toMatchObject({
      id: 'rpt/tekrar-siparis',
      baslik: 'Tekrar Sipariş',
      adres: '/rpt/tekrar-siparis/',
      algoritmalar: ['rpt-adet'],
      deginir: ['yok-satma'],
    })
  })

  it('en az bir yayındaki yazısı olan dizi yayındadır; yalnız taslağı olan değildir', () => {
    const baglar = diziBaglari(DIZILER, [
      yazi('rpt/tekrar-siparis/a', 'hazirlaniyor'),
      yazi('rpt/tekrar-siparis/b', 'yayinda'),
      yazi('indirim/markdown/a', 'hazirlaniyor'),
    ])
    expect(baglar.map((b) => b.yayinda)).toEqual([true, false])
  })

  it('yazısı olmayan dizi yayında değildir', () => {
    expect(diziBaglari(DIZILER, []).every((b) => !b.yayinda)).toBe(true)
  })
})

describe('fazBasamagi', () => {
  it('aşamanın fazını verir', () => {
    expect(fazBasamagi('replenishment')).toEqual([{ ad: 'Sezon İçi', adres: '/sezon-ici/' }])
    expect(fazBasamagi('range-plan')).toEqual([{ ad: 'Sezon Öncesi', adres: '/sezon-oncesi/' }])
  })

  it('Temeller için boştur', () => {
    expect(fazBasamagi('temeller')).toEqual([])
  })
})

describe('fazAl', () => {
  it('slug’a göre fazı döndürür', () => {
    expect(fazAl('sezon-ici').asamalar).toHaveLength(8)
  })
})
