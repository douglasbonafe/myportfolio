// The site was written with root-absolute links ("/work/", "/assets/me.jpg").
// Astro prefixes its own bundles with `base`, but not hand-written paths.
// This rewrites them in the built output so the same source works at "/" and
// under a sub-path like GitHub Pages' /myportfolio/.
import { readdir, readFile, writeFile } from 'node:fs/promises';
import { join } from 'node:path';

const base = (process.env.BASE_PATH || '/').replace(/\/$/, '');
if (!base) process.exit(0);

const escaped = base.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
const attr = new RegExp(`((?:href|src|srcset|content)=["'])/(?!/|${escaped.slice(1)}/)`, 'g');
const css = new RegExp(`(url\\(\\s*["']?)/(?!/|${escaped.slice(1)}/)`, 'g');

async function* walk(dir) {
	for (const e of await readdir(dir, { withFileTypes: true })) {
		const p = join(dir, e.name);
		if (e.isDirectory()) yield* walk(p);
		else yield p;
	}
}

let changed = 0;
for await (const file of walk('dist')) {
	if (!/\.(html|css)$/.test(file)) continue;
	const src = await readFile(file, 'utf8');
	const out = src.replace(attr, `$1${base}/`).replace(css, `$1${base}/`);
	if (out !== src) {
		await writeFile(file, out);
		changed++;
	}
}
console.log(`rebased root-absolute paths under ${base}/ in ${changed} files`);
