/** Bir yazının hiyerarşideki yeri. Dizi yoksa tekil alandadır. */
export type YaziYolu = {
  alan: string
  dizi: string | null
  slug: string
}

/**
 * Koleksiyon id'sini hiyerarşiye çevirir.
 *
 * Alan ve dizi frontmatter'da tutulmaz; dosyanın nerede durduğu tek
 * gerçektir. Böylece yol ile üstverinin birbirinden kayması mümkün olmaz.
 */
export function yaziYolunuAyristir(id: string): YaziYolu {
  const parcalar = id.split('/').filter(Boolean)

  if (parcalar.length === 2) {
    return { alan: parcalar[0], dizi: null, slug: parcalar[1] }
  }
  if (parcalar.length === 3) {
    return { alan: parcalar[0], dizi: parcalar[1], slug: parcalar[2] }
  }

  throw new Error(
    `Yazı yolu iki veya üç parçalı olmalı, "${id}" ${parcalar.length} parçalı. ` +
      'Beklenen: <alan>/<slug> veya <alan>/<dizi>/<slug>',
  )
}

/** Yazının mutlak adresi. Sıra adreste görünmez. */
export function yaziAdresi(yol: YaziYolu): string {
  const parcalar = yol.dizi
    ? [yol.alan, yol.dizi, yol.slug]
    : [yol.alan, yol.slug]
  return `/${parcalar.join('/')}/`
}
