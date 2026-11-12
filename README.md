# Inkwell

A manga, manhwa and manhua reading site. Next.js, TypeScript and Tailwind CSS.

It runs on built in demo content: 40 invented series with generated SVG covers and
pages. Nothing here is real or licensed material, it is placeholder content so the
whole site works out of the box.

## Run it

```bash
npm install
npm run dev      # http://localhost:3000
npm test         # unit tests
npm run lint
npm run build
```

## What is in it

- **Home**: spotlight banner, continue reading, popular (today, week, all time),
  recommendations, latest updates, genre shortcuts, a row per type
- **Browse**: search, filter by type, status and genres, four sort orders, all kept in the URL
- **Series page**: details, bookmark, chapter list with read markers, similar series
- **Reader**: long strip, single page and double page modes, reading direction,
  fit options, strip width and page gap, four backgrounds, keyboard, tap zones and
  swipe, auto hiding bars, page slider, auto continue, remembers your exact page
- **Library**: bookmarks and reading history
- Dark and light themes

Bookmarks, history and settings are stored in the browser (`localStorage`). There
are no accounts.

## Using real content

Everything the site shows comes through the `Source` interface in
`src/lib/source/types.ts`. To plug in a real catalogue:

1. Create a file in `src/lib/source/` that implements `Source`.
2. Export it as `source` from `src/lib/source/index.ts`.

Each `Series` carries its own `cover` URL and each `Page` its own `src`, so a new
source can point at any image host. The demo artwork routes under `src/app/api/`
can then be deleted.

## Renaming the site

Change `SITE_NAME` in `src/lib/site.ts`.

## Layout

```
src/app/                 routes
src/components/          UI
src/components/reader/   the reader
src/lib/source/          Source interface and the demo implementation
src/lib/reader/logic.ts  pure reader logic (page stepping, spreads, input mapping)
src/lib/recommend.ts     recommendation scoring
src/lib/storage.ts       safe localStorage wrapper
tests/                   unit tests
```
