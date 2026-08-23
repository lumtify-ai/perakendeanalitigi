// site/src/lib/dogrula.ts
import { yaziYolunuAyristir } from './yol'

export type YaziGirdi = {
  id: string
  body: string
  data: {
    baslik: string
    tip: 'hikaye' | 'anlatici' | 'teknik' | 'sonuc'
    sira: number
    yazar?: string
    durum?: string
  }
}

export type DiziGirdi = {
  id: string
  data: { alan: string }
}

/** Alan koleksiyonunun bir girdisi. Gövde, alan sayfası kuralları için okunur. */
export type AlanGirdi = {
  id: string
  body: string
}

const TERIM_DESENI = /<T\s+k=["']([^"']+)["']/g
const KOPRU_DESENI = /<Lumtify\b/
// ``` ya da ~~~ ile açılan çitli kod bloğu; satır başında olmalı.
const KOD_BLOGU_DESENI = /^[ \t]*(```|~~~)/m
// Yazar kimliği hâlâ açık bir soru (tasarım dokümanı §14.1); yer tutucu bu.
const YAZAR_YER_TUTUCU = 'TBD'

/** Her yazının alanı ve dizisi tanımlı mı? */
function yollariDogrula(
  yazilar: YaziGirdi[],
  diziler: DiziGirdi[],
  alanlar: AlanGirdi[],
): string[] {
  const alanIdleri = new Set(alanlar.map((a) => a.id))
  const diziIdleri = new Set(diziler.map((d) => d.id))
  const hatalar: string[] = []

  for (const yaziGirdi of yazilar) {
    let yol
    try {
      yol = yaziYolunuAyristir(yaziGirdi.id)
    } catch (hata) {
      hatalar.push((hata as Error).message)
      continue
    }

    if (!alanIdleri.has(yol.alan)) {
      hatalar.push(
        `"${yaziGirdi.id}" tanımsız bir alana ait: "${yol.alan}". ` +
          `src/content/alan/${yol.alan}.md dosyasını ekleyin.`,
      )
    }
    if (yol.dizi && !diziIdleri.has(`${yol.alan}/${yol.dizi}`)) {
      hatalar.push(
        `"${yaziGirdi.id}" tanımsız bir diziye ait: "${yol.dizi}". ` +
          `src/content/dizi/${yol.alan}/${yol.dizi}.md dosyasını ekleyin.`,
      )
    }
  }
  return hatalar
}

/**
 * Her dizinin `data.alan` değeri, bulunduğu klasörle aynı mı?
 *
 * Hiyerarşi dosya yolunda yaşar, üstveride değil — bu ilke yazılarda zaten
 * uygulanıyor (`yazi` şemasında `alan`/`dizi` alanı yok). Dizi koleksiyonu
 * ise `data.alan`'ı ayrıca taşıyor (bkz. `content.config.ts`), bu da yol ile
 * üstverinin ayrışmasına izin veriyor: `id` klasörden türetilir ama
 * `data.alan` frontmatter'dan gelir ve ikisi hiç karşılaştırılmazsa bir
 * dizinin `alan` alanını yanlış yazması build'i sessizce geçer, sadece
 * dizi kendi alan sayfasından düşer ve o alanın sayfası kırık bir bağlantı
 * basar.
 */
function diziAlanlariDogrula(diziler: DiziGirdi[]): string[] {
  const hatalar: string[] = []

  for (const dizi of diziler) {
    const [klasorAlani] = dizi.id.split('/')
    if (dizi.data.alan !== klasorAlani) {
      hatalar.push(
        `"${dizi.id}" dizisinin bulunduğu klasör "${klasorAlani}" alanını gösteriyor, ` +
          `ama frontmatter'daki "alan" değeri "${dizi.data.alan}". ` +
          `src/content/dizi/${dizi.id}.md içindeki "alan" alanını "${klasorAlani}" olarak düzeltin.`,
      )
    }
  }
  return hatalar
}

/** Aynı dizideki sıra değerleri benzersiz ve 1'den kesintisiz mi? */
function siralariDogrula(yazilar: YaziGirdi[]): string[] {
  const hatalar: string[] = []
  const gruplar = new Map<string, YaziGirdi[]>()

  for (const yaziGirdi of yazilar) {
    const yol = yaziYolunuAyristir(yaziGirdi.id)
    const anahtar = yol.dizi ? `${yol.alan}/${yol.dizi}` : yol.alan
    gruplar.set(anahtar, [...(gruplar.get(anahtar) ?? []), yaziGirdi])
  }

  for (const [anahtar, grup] of gruplar) {
    const siralar = grup.map((y) => y.data.sira).sort((a, b) => a - b)
    if (new Set(siralar).size !== siralar.length) {
      hatalar.push(`"${anahtar}" içinde aynı sıra numarası birden çok yazıda: ${siralar.join(', ')}`)
      continue
    }
    const beklenen = siralar.map((_, i) => i + 1)
    if (siralar.join(',') !== beklenen.join(',')) {
      hatalar.push(
        `"${anahtar}" içindeki sıra 1'den kesintisiz gitmiyor: ${siralar.join(', ')}`,
      )
    }
  }
  return hatalar
}

/** Her dizide en az bir hikâye ve bir sonuç yazısı var mı? */
function diziIcerigiDogrula(yazilar: YaziGirdi[], diziler: DiziGirdi[]): string[] {
  const hatalar: string[] = []

  for (const dizi of diziler) {
    const uyeler = yazilar.filter((y) => y.id.startsWith(`${dizi.id}/`))
    if (uyeler.length === 0) continue

    const tipler = new Set(uyeler.map((y) => y.data.tip))
    if (!tipler.has('hikaye')) {
      hatalar.push(`"${dizi.id}" dizisinde hikaye tipinde yazı yok — dizinin giriş kapısı eksik.`)
    }
    if (!tipler.has('sonuc')) {
      hatalar.push(`"${dizi.id}" dizisinde sonuc tipinde yazı yok — dizinin çıkış kapısı eksik.`)
    }
  }
  return hatalar
}

/** Kullanılan her terim sözlükte var mı? */
function terimleriDogrula(yazilar: YaziGirdi[], terimler: string[]): string[] {
  const hatalar: string[] = []
  const bilinen = new Set(terimler)

  for (const yaziGirdi of yazilar) {
    for (const eslesme of yaziGirdi.body.matchAll(TERIM_DESENI)) {
      const anahtar = eslesme[1]
      if (!bilinen.has(anahtar)) {
        hatalar.push(
          `"${yaziGirdi.id}" sözlükte olmayan bir terime atıf yapıyor: "${anahtar}". ` +
            `src/content/sozluk/${anahtar}.md dosyasını ekleyin.`,
        )
      }
    }
  }
  return hatalar
}

/** Lumtify köprüsü yalnızca sonuc yazılarında geçebilir. */
function kopruleriDogrula(yazilar: YaziGirdi[]): string[] {
  return yazilar
    .filter((y) => y.data.tip !== 'sonuc' && KOPRU_DESENI.test(y.body))
    .map(
      (y) =>
        `"${y.id}" Lumtify köprüsü içeriyor ama tipi "${y.data.tip}". ` +
        'Tek geçiş noktası kuralı: köprü yalnızca sonuc yazısının sonunda bulunur.',
    )
}

/**
 * Yayına çıkan bir yazının yazarı isimli midir?
 *
 * Tasarım dokümanı §11: "Yazar her yazıda isimlidir." Yer tutucu `TBD` hem
 * görünür metne hem JSON-LD'ye giriyor; bugün hiçbir yazı `yayinda` değil,
 * yani bu kural bugün geçer ve ilk yayın gününde tutar.
 */
function yazarlariDogrula(yazilar: YaziGirdi[]): string[] {
  return yazilar
    .filter((y) => y.data.durum === 'yayinda' && y.data.yazar?.trim() === YAZAR_YER_TUTUCU)
    .map(
      (y) =>
        `"${y.id}" yayında ama yazarı hâlâ "${YAZAR_YER_TUTUCU}". ` +
        'Yazar her yazıda isimlidir (tasarım dokümanı §11); yer tutucu hem sayfada ' +
        "hem JSON-LD'nin author alanında görünür. Gerçek yazar adını yazın ya da " +
        'yazıyı "hazirlaniyor" durumunda bırakın.',
    )
}

/**
 * Alan sayfası kod içermez (tasarım dokümanı §3).
 *
 * Alan sayfası bir perakende problemini kavram düzeyinde tanımlar; kod dizi
 * ve yazı sayfalarına aittir. Şablon gövdeyi süzmez, süzemez de: süzülen kod
 * sessizce kaybolur. Kural burada, build'i kırarak zorlanır.
 */
function alanGovdeleriDogrula(alanlar: AlanGirdi[]): string[] {
  return alanlar
    .filter((alan) => KOD_BLOGU_DESENI.test(alan.body))
    .map(
      (alan) =>
        `"${alan.id}" alan sayfası kod bloğu içeriyor. ` +
        'Alan sayfası problemi kavram düzeyinde tanımlar ve kod içermez ' +
        '(tasarım dokümanı §3); kod dizinin teknik yazılarına aittir.',
    )
}

/** Bütün değişmezleri koşar. Boş dizi dönerse içerik geçerlidir. */
export function hepsiniDogrula(
  yazilar: YaziGirdi[],
  diziler: DiziGirdi[],
  alanlar: AlanGirdi[],
  terimler: string[],
): string[] {
  const yolHatalari = yollariDogrula(yazilar, diziler, alanlar)
  const diziAlanHatalari = diziAlanlariDogrula(diziler)
  // Yol bozuksa sıra ve dizi kontrolleri anlamsız çıktı üretir
  if (yolHatalari.length > 0 || diziAlanHatalari.length > 0) {
    return [...yolHatalari, ...diziAlanHatalari]
  }

  return [
    ...siralariDogrula(yazilar),
    ...diziIcerigiDogrula(yazilar, diziler),
    ...terimleriDogrula(yazilar, terimler),
    ...kopruleriDogrula(yazilar),
    ...yazarlariDogrula(yazilar),
    ...alanGovdeleriDogrula(alanlar),
  ]
}
