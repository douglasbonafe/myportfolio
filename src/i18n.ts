import type { CollectionEntry } from 'astro:content';

export type Lang = 'en' | 'pt' | 'es';
export const LANGS: Lang[] = ['en', 'pt', 'es'];

export const ui = {
	en: { name: 'English', short: 'EN', locale: 'en-US', back: 'Blog', source: 'Source code', readIn: 'Read in' },
	pt: { name: 'Português', short: 'PT', locale: 'pt-BR', back: 'Blog', source: 'Código-fonte', readIn: 'Ler em' },
	es: { name: 'Español', short: 'ES', locale: 'es', back: 'Blog', source: 'Código fuente', readIn: 'Leer en' },
} as const;

export const postKey = (p: CollectionEntry<'blog'>) => p.data.key ?? p.slug;
export const postUrl = (p: CollectionEntry<'blog'>) => `/blog/${p.slug}/`;

/** Every translation of a post, in LANGS order. */
export function translations(all: CollectionEntry<'blog'>[], post: CollectionEntry<'blog'>) {
	const k = postKey(post);
	return LANGS.map((l) => all.find((p) => postKey(p) === k && p.data.lang === l)).filter(
		(p): p is CollectionEntry<'blog'> => Boolean(p)
	);
}

export function formatDate(d: Date, lang: Lang, month: 'long' | 'short' = 'long') {
	return d.toLocaleDateString(ui[lang].locale, { year: 'numeric', month, day: 'numeric', timeZone: 'UTC' });
}
