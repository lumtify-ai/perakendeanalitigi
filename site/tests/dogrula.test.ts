// site/tests/dogrula.test.ts
import { describe, expect, it } from 'vitest'
import {
  hepsiniDogrula,
  type AlanGirdi,
  type DiziGirdi,
  type YaziGirdi,
} from '../src/lib/dogrula'

function yazi(
  id: string,
  tip: YaziGirdi['data']['tip'],
  sira: number,
  body = '',
): YaziGirdi {
  return { id, body, data: { tip, sira, baslik: id } }
}

const DIZILER: DiziGirdi[] = [{ id: 'transfer/blok-transfer', data: { alan: 'transfer' } }]
const ALANLAR: AlanGirdi[] = [
  { id: 'transfer', body: 'Transfer bir kavramdir.' },
  { id: 'temeller', body: 'Temeller bir kavramdir.' },
]
const TERIMLER = ['cover', 'option']

function tamDizi(): YaziGirdi[] {
  return [
    yazi('transfer/blok-transfer/a', 'hikaye', 1),
    yazi('transfer/blok-transfer/b', 'teknik', 2),
    yazi('transfer/blok-transfer/c', 'sonuc', 3),
  ]
}

describe('hepsiniDogrula', () => {
  it('geçerli içerikte hata vermez', () => {
    expect(hepsiniDogrula(tamDizi(), DIZILER, ALANLAR, TERIMLER)).toEqual([])
  })

  it('tanımsız alanı yakalar', () => {
    const yazilar = [yazi('fiyatlama/bir-yazi', 'hikaye', 1)]
    const hatalar = hepsiniDogrula(yazilar, DIZILER, ALANLAR, TERIMLER)
    expect(hatalar.join('\n')).toMatch(/fiyatlama.*alan/i)
  })

  it('tanımsız diziyi yakalar', () => {
    const yazilar = [yazi('transfer/atil-tekleme/a', 'hikaye', 1)]
    const hatalar = hepsiniDogrula(yazilar, DIZILER, ALANLAR, TERIMLER)
    expect(hatalar.join('\n')).toMatch(/atil-tekleme.*dizi/i)
  })

  it('çift sıra numarasını yakalar', () => {
    const yazilar = tamDizi()
    yazilar[1].data.sira = 1
    const hatalar = hepsiniDogrula(yazilar, DIZILER, ALANLAR, TERIMLER)
    expect(hatalar.join('\n')).toMatch(/sıra/i)
  })

  it('sıradaki boşluğu yakalar', () => {
    const yazilar = tamDizi()
    yazilar[2].data.sira = 9
    const hatalar = hepsiniDogrula(yazilar, DIZILER, ALANLAR, TERIMLER)
    expect(hatalar.join('\n')).toMatch(/kesintisiz/i)
  })

  it('hikâyesi olmayan diziyi yakalar', () => {
    const yazilar = [
      yazi('transfer/blok-transfer/a', 'teknik', 1),
      yazi('transfer/blok-transfer/b', 'sonuc', 2),
    ]
    const hatalar = hepsiniDogrula(yazilar, DIZILER, ALANLAR, TERIMLER)
    expect(hatalar.join('\n')).toMatch(/hikaye/i)
  })

  it('sonucu olmayan diziyi yakalar', () => {
    const yazilar = [
      yazi('transfer/blok-transfer/a', 'hikaye', 1),
      yazi('transfer/blok-transfer/b', 'teknik', 2),
    ]
    const hatalar = hepsiniDogrula(yazilar, DIZILER, ALANLAR, TERIMLER)
    expect(hatalar.join('\n')).toMatch(/sonuc/i)
  })

  it('sözlükte olmayan terimi yakalar', () => {
    const yazilar = tamDizi()
    yazilar[0].body = 'Mağazanın <T k="raf-omru">raf ömrü</T> yüksekti.'
    const hatalar = hepsiniDogrula(yazilar, DIZILER, ALANLAR, TERIMLER)
    expect(hatalar.join('\n')).toMatch(/raf-omru/)
  })

  it('sözlükteki terimi kabul eder', () => {
    const yazilar = tamDizi()
    yazilar[0].body = 'Mağazanın <T k="cover">cover</T> değeri yüksekti.'
    expect(hepsiniDogrula(yazilar, DIZILER, ALANLAR, TERIMLER)).toEqual([])
  })

  it('sonuc dışındaki yazıda Lumtify köprüsünü yakalar', () => {
    const yazilar = tamDizi()
    yazilar[1].body = 'Bir şeyler.\n\n<Lumtify />'
    const hatalar = hepsiniDogrula(yazilar, DIZILER, ALANLAR, TERIMLER)
    expect(hatalar.join('\n')).toMatch(/Lumtify/)
  })

  it('sonuc yazısında Lumtify köprüsüne izin verir', () => {
    const yazilar = tamDizi()
    yazilar[2].body = 'Sonuçlar.\n\n<Lumtify />'
    expect(hepsiniDogrula(yazilar, DIZILER, ALANLAR, TERIMLER)).toEqual([])
  })

  it('dizinin klasörü ile data.alan uyuştuğunda hata vermez', () => {
    expect(hepsiniDogrula(tamDizi(), DIZILER, ALANLAR, TERIMLER)).toEqual([])
  })

  it('dizinin klasörü ile data.alan uyuşmadığında yakalar', () => {
    const diziler: DiziGirdi[] = [{ id: 'transfer/blok-transfer', data: { alan: 'temeller' } }]
    const hatalar = hepsiniDogrula(tamDizi(), diziler, ALANLAR, TERIMLER)
    expect(hatalar.join('\n')).toMatch(/blok-transfer/)
  })
})

// Tasarım dokümanı §11: "Yazar her yazıda isimlidir." Yer tutucu `TBD` hem
// görünür metne hem JSON-LD'nin author alanına giriyordu ve hiçbir şey
// yayına çıkmasını engellemiyordu. Bugün hiçbir yazı yayında değil; kural
// ilk yayın gününde tutar.
describe('yazar kuralı', () => {
  function yazarli(durum: string, yazar: string): YaziGirdi[] {
    const yazilar = tamDizi()
    yazilar[0].data.durum = durum
    yazilar[0].data.yazar = yazar
    return yazilar
  }

  it('yayındaki yazıda TBD yazarını yakalar', () => {
    const hatalar = hepsiniDogrula(yazarli('yayinda', 'TBD'), DIZILER, ALANLAR, TERIMLER)
    expect(hatalar.join('\n')).toMatch(/TBD/)
    expect(hatalar.join('\n')).toMatch(/transfer\/blok-transfer\/a/)
  })

  it('hazırlanıyor yazıda TBD yazarına izin verir', () => {
    expect(hepsiniDogrula(yazarli('hazirlaniyor', 'TBD'), DIZILER, ALANLAR, TERIMLER)).toEqual([])
  })

  it('yayındaki yazıda isimli yazara izin verir', () => {
    expect(hepsiniDogrula(yazarli('yayinda', 'Pelin'), DIZILER, ALANLAR, TERIMLER)).toEqual([])
  })
})

// Tasarım dokümanı §3: alan sayfası problemi kavram düzeyinde tanımlar ve
// **kod içermez**. Şablon gövdeyi süzmez, süzmemeli de: süzülen kod sessizce
// kaybolurdu. Kural build'i kırarak zorlanır.
describe('alan sayfası kod içermez', () => {
  it('alan gövdesindeki çitli kod bloğunu yakalar', () => {
    const alanlar: AlanGirdi[] = [
      { id: 'transfer', body: 'Giris.\n\n```sql\nSELECT 1\n```\n' },
      { id: 'temeller', body: 'Zemin.' },
    ]
    const hatalar = hepsiniDogrula(tamDizi(), DIZILER, alanlar, TERIMLER)
    expect(hatalar.join('\n')).toMatch(/transfer.*kod/is)
  })

  it('tilde ile açılan kod bloğunu da yakalar', () => {
    const alanlar: AlanGirdi[] = [
      { id: 'transfer', body: '~~~python\nx = 1\n~~~\n' },
      { id: 'temeller', body: 'Zemin.' },
    ]
    expect(hepsiniDogrula(tamDizi(), DIZILER, alanlar, TERIMLER)).not.toEqual([])
  })

  it('kodsuz alan gövdesine dokunmaz', () => {
    expect(hepsiniDogrula(tamDizi(), DIZILER, ALANLAR, TERIMLER)).toEqual([])
  })
})
