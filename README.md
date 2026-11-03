# Douglas Bonafé: Blog

Notes on QA, test automation and AI engineering. Each post comes with code you can run.

Live at https://douglasbonafe.github.io/myportfolio/

## Writing a post

Add a Markdown file to `src/content/blog/`:

```yaml
---
title: "Post title"
description: "One or two sentences for the list page and link previews."
publishDate: 2026-11-03
tags: [QA, Python]
repo: https://github.com/douglasbonafe/some-poc   # optional
cover: /assets/blog/some-cover.jpg                # optional, lives in public/
cover_alt: "What the cover shows"
---
```

Push to `master` and the GitHub Pages workflow builds and deploys it.

## Commands

| Command           | Action                                  |
| :---------------- | :-------------------------------------- |
| `npm install`     | Install dependencies                    |
| `npm run dev`     | Dev server at `localhost:3000`          |
| `npm run build`   | Build to `./dist/`                      |
| `npm run preview` | Preview the build locally               |

The site is built with Astro. GitHub Pages serves it under `/myportfolio/`, so the deploy sets `BASE_PATH` and runs `scripts/rebase-paths.mjs` after the build. Local and root-domain builds need neither.
