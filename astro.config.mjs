import { defineConfig } from 'astro/config';

// Netlify serves the site from the domain root, GitHub Pages from /myportfolio.
// The Pages workflow sets SITE_URL and BASE_PATH; local and Netlify builds don't.
export default defineConfig({
	site: process.env.SITE_URL || undefined,
	base: process.env.BASE_PATH || '/',
});
