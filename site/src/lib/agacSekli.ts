// site/src/lib/agacSekli.ts
//
// Sitenin merkezî iddiası "hiyerarşi dosya yolunda yaşar" olduğuna göre
// **dosya ağacının kendisi şemadır.** src/lib/dogrula.ts bulduğu dosyaların
// *içini* doğrular; burası *hangi dosyanın nerede durduğunu* doğrular.
//
// Bu ayrım keyfi değil: ağaç bozukken içerik kontrolleri yanıltıcı hata
// üretir (örneğin alan dosyası eksik bir dizinin yazıları "tanımsız alan"
// diye tek tek raporlanır, asıl eksik olan tek bir dosyadır). Bu yüzden
// çağıran taraf bu adımı `hepsiniDogrula`'nın önünde koşar ve ağaç bozuksa
// içerik kontrollerine hiç girmez (bkz. scripts/dogrula.ts).
//
// Yakalanan sessiz hatalar:
//   1. Alan dosyası olmayan bir klasörde duran dizi/yazı — bugün `dogrula`
//      "temiz" der, `astro build` getEntry(...)! üzerinde native abort ile
//      çöker ve kullanıcı `dist/.prerender/chunks/index_*.mjs:54` görür.
//   2. Koleksiyon klasöründe beklenmeyen uzantı — glob loader dosyayı hiç
//      yüklemez, sayfa sessizce yok olur.
//   3. İki farklı dosyanın aynı URL'ye çıkması — Astro sessiz bir [WARN]
//      basar ve sayfalardan biri üretilmez.
//   4. İki parçalı olmayan dizi id'si — sayfa yanlış URL'de üretilir.
//   5. Boş `tanim` — zod `z.string()` boş dizeyi geçirir.

/** Alan `tanim` alanının asgari uzunluğu. Bir tanım cümlesi bundan kısa olmaz. */
export const TANIM_ASGARI_UZUNLUK = 40

export type Koleksiyon = 'alan' | 'dizi' | 'yazi' | 'sozluk' | 'kadro'

/**
 * İçerik ağacındaki tek bir dosya.
 *
 * `goreliYol` koleksiyon kökünden itibaren, **uzantısıyla birlikte** ve her
 * platformda eğik çizgiyle (`/`) verilir; Windows'ta `path.relative`
 * çıktısının normalize edilmesi çağıranın işidir.
 */
export type AgacDosyasi = {
  koleksiyon: Koleksiyon
  goreliYol: string
  /** Frontmatter. Yalnızca `alan` için okunur; ayrıca dizinin `demo` alanı. */
  data?: Record<string, unknown>
}

const BEKLENEN_UZANTI: Record<Koleksiyon, string> = {
  alan: '.md',
  dizi: '.md',
  yazi: '.mdx',
  sozluk: '.md',
  kadro: '.md',
}

/** Koleksiyon kökünden itibaren kaç parçalı bir yol beklenir. */
const BEKLENEN_DERINLIK: Record<Koleksiyon, number[]> = {
  alan: [1],
  dizi: [2],
  yazi: [2, 3],
  sozluk: [1],
  kadro: [1],
}

const DERINLIK_SEKLI: Record<Koleksiyon, string> = {
  alan: '<alan>.md',
  dizi: '<alan>/<dizi>.md',
  yazi: '<alan>/<slug>.mdx veya <alan>/<dizi>/<slug>.mdx',
  sozluk: '<terim>.md',
  kadro: '<kisi>.md',
}

/** Koleksiyonlardan türemeyen, kodda sabit duran rotalar. */
const SABIT_ROTALAR: { adres: string; kaynak: string }[] = [
  { adres: '/', kaynak: 'src/pages/index.astro' },
  { adres: '/sozluk/', kaynak: 'src/pages/sozluk.astro' },
  { adres: '/kadro/', kaynak: 'src/pages/kadro.astro' },
  { adres: '/veri-seti/', kaynak: 'src/pages/veri-seti.astro' },
]

function uzantisiniAl(yol: string): string {
  const nokta = yol.lastIndexOf('.')
  const egik = yol.lastIndexOf('/')
  return nokta > egik ? yol.slice(nokta) : ''
}

function uzantisiniAt(yol: string): string {
  const uzanti = uzantisiniAl(yol)
  return uzanti ? yol.slice(0, -uzanti.length) : yol
}

function kaynakYolu(dosya: AgacDosyasi): string {
  return `src/content/${dosya.koleksiyon}/${dosya.goreliYol}`
}

/** Uzantı, koleksiyonun glob desenine uyuyor mu? */
function uzantilariDogrula(dosyalar: AgacDosyasi[]): string[] {
  return dosyalar
    .filter((dosya) => uzantisiniAl(dosya.goreliYol) !== BEKLENEN_UZANTI[dosya.koleksiyon])
    .map((dosya) => {
      const bulunan = uzantisiniAl(dosya.goreliYol) || '(uzantısız)'
      const beklenen = BEKLENEN_UZANTI[dosya.koleksiyon]
      return (
        `${kaynakYolu(dosya)} beklenmeyen uzantı taşıyor: "${bulunan}". ` +
        `"${dosya.koleksiyon}" koleksiyonu yalnızca "${beklenen}" dosyalarını yükler. ` +
        `Bu dosya build sırasında sessizce yok sayılır — sayfası hiç üretilmez, ` +
        `hata da uyarı da çıkmaz. Uzantıyı "${beklenen}" yapın ya da dosyayı ` +
        'içerik ağacının dışına taşıyın.'
      )
    })
}

/** Dosya, koleksiyonun beklediği derinlikte mi duruyor? */
function derinlikleriDogrula(dosyalar: AgacDosyasi[]): string[] {
  return dosyalar
    .filter((dosya) => {
      const parcalar = uzantisiniAt(dosya.goreliYol).split('/').filter(Boolean)
      return !BEKLENEN_DERINLIK[dosya.koleksiyon].includes(parcalar.length)
    })
    .map((dosya) => {
      const parcalar = uzantisiniAt(dosya.goreliYol).split('/').filter(Boolean)
      return (
        `${kaynakYolu(dosya)} yanlış derinlikte: ${parcalar.length} parçalı. ` +
        `"${dosya.koleksiyon}" koleksiyonunda beklenen şekil: ` +
        `${DERINLIK_SEKLI[dosya.koleksiyon]}. ` +
        'Hiyerarşi dosya yolunda yaşar; yanlış derinlikteki dosya yanlış URL üretir.'
      )
    })
}

/** Her dizinin ve her yazının bulunduğu klasörün bir alan dosyası var mı? */
function alanVarligiDogrula(dosyalar: AgacDosyasi[]): string[] {
  const alanIdleri = new Set(
    dosyalar
      .filter((dosya) => dosya.koleksiyon === 'alan')
      .map((dosya) => uzantisiniAt(dosya.goreliYol)),
  )

  return dosyalar
    .filter((dosya) => dosya.koleksiyon === 'dizi' || dosya.koleksiyon === 'yazi')
    .filter((dosya) => !alanIdleri.has(uzantisiniAt(dosya.goreliYol).split('/')[0]))
    .map((dosya) => {
      const alan = uzantisiniAt(dosya.goreliYol).split('/')[0]
      const ne = dosya.koleksiyon === 'dizi' ? 'dizisi' : 'yazısı'
      return (
        `${kaynakYolu(dosya)} ${ne} "${alan}" alanının altında duruyor ama ` +
        `src/content/alan/${alan}.md yok. ` +
        'Alan dosyasını ekleyin ya da dosyayı tanımlı bir alanın klasörüne taşıyın. ' +
        'Bu dosya eksikken build, alan girdisi tanımsız olduğu için sayfa üretirken ' +
        'çöker; hata mesajı derlenmiş bir chunk dosyasını gösterir ve eksik alan ' +
        'dosyasına işaret etmez.'
      )
    })
}

/** Bir dosyanın (ve varsa demo sayfasının) ürettiği adresler. */
function adresleriUret(dosya: AgacDosyasi): string[] {
  const parcalar = uzantisiniAt(dosya.goreliYol).split('/').filter(Boolean)

  if (dosya.koleksiyon === 'alan' || dosya.koleksiyon === 'yazi') {
    return [`/${parcalar.join('/')}/`]
  }
  if (dosya.koleksiyon === 'dizi') {
    const kapak = `/${parcalar.join('/')}/`
    return dosya.data?.demo === true ? [kapak, `${kapak}demo/`] : [kapak]
  }
  return []
}

/** İki farklı dosya aynı URL'ye mi çıkıyor? */
function adresCakismalariDogrula(dosyalar: AgacDosyasi[]): string[] {
  const sahipler = new Map<string, string[]>()

  for (const { adres, kaynak } of SABIT_ROTALAR) {
    sahipler.set(adres, [kaynak])
  }

  for (const dosya of dosyalar) {
    for (const adres of adresleriUret(dosya)) {
      const kaynak =
        adres.endsWith('/demo/') && dosya.koleksiyon === 'dizi'
          ? `${kaynakYolu(dosya)} (demo: true)`
          : kaynakYolu(dosya)
      sahipler.set(adres, [...(sahipler.get(adres) ?? []), kaynak])
    }
  }

  return [...sahipler]
    .filter(([, kaynaklar]) => kaynaklar.length > 1)
    .map(
      ([adres, kaynaklar]) =>
        `"${adres}" adresini ${kaynaklar.length} kaynak birden üretiyor: ` +
        `${kaynaklar.join(', ')}. ` +
        'Astro çakışan rotada yalnızca bir [WARN] basar ve sayfalardan birini hiç ' +
        'üretmez; hangisinin düştüğü rota önceliğine bağlıdır. Kaynaklardan birini ' +
        'yeniden adlandırın.',
    )
}

/** Alan dosyasının `tanim` alanı gerçekten dolu mu? */
function tanimlariDogrula(dosyalar: AgacDosyasi[]): string[] {
  return dosyalar
    .filter((dosya) => dosya.koleksiyon === 'alan')
    .map((dosya) => {
      const ham = dosya.data?.tanim
      const tanim = typeof ham === 'string' ? ham.trim() : ''
      if (tanim.length >= TANIM_ASGARI_UZUNLUK) return null
      return (
        `${kaynakYolu(dosya)} içindeki "tanim" alanı ${tanim.length} karakter; ` +
        `en az ${TANIM_ASGARI_UZUNLUK} olmalı. ` +
        'Alan sayfasının ilk paragrafı doğrudan tanımla açılır (tasarım dokümanı §3); ' +
        'yapay zekâ araçlarının alıntıladığı cümle budur, boş geçilemez.'
      )
    })
    .filter((hata): hata is string => hata !== null)
}

/**
 * İçerik ağacının şeklini doğrular. Boş dizi dönerse ağaç sağlamdır.
 *
 * Adımlar birbirine bağımlıdır: uzantısı ya da derinliği yanlış bir dosyanın
 * adresi de alanı da anlamsızdır, o yüzden o dosya sonraki adımlara girmez.
 */
export function agacSekliniDogrula(dosyalar: AgacDosyasi[]): string[] {
  const uzantiHatalari = uzantilariDogrula(dosyalar)
  const uzantisiSaglam = dosyalar.filter(
    (dosya) => uzantisiniAl(dosya.goreliYol) === BEKLENEN_UZANTI[dosya.koleksiyon],
  )

  const derinlikHatalari = derinlikleriDogrula(uzantisiSaglam)
  const sekliSaglam = uzantisiSaglam.filter((dosya) => {
    const parcalar = uzantisiniAt(dosya.goreliYol).split('/').filter(Boolean)
    return BEKLENEN_DERINLIK[dosya.koleksiyon].includes(parcalar.length)
  })

  return [
    ...uzantiHatalari,
    ...derinlikHatalari,
    ...alanVarligiDogrula(sekliSaglam),
    ...adresCakismalariDogrula(sekliSaglam),
    ...tanimlariDogrula(sekliSaglam),
  ]
}
