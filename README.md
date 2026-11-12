# Inkwell

A manga, manhwa and manhua reading site. Next.js, TypeScript and Tailwind CSS.

By default it shows real series information and cover thumbnails from the public
[MangaDex API](https://api.mangadex.org/docs/): titles, covers, descriptions, genres
and scores for the most followed manga, manhwa and manhua.

It does **not** host or fetch any chapters. The reader opens generated placeholder
pages so every reading mode can be tried, and series pages link out to the official
release when MangaDex lists one.

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

## Content source

Set the `CONTENT_SOURCE` environment variable:

| Value | What you get |
|---|---|
| `mangadex` (default) | Real catalogue and covers from MangaDex, refreshed about once an hour |
| `demo` | 40 invented series with generated covers, no network needed |

If MangaDex cannot be reached the site serves the demo catalogue instead of breaking.

When using MangaDex data, keep to their API rules: credit MangaDex (the footer does),
and do not run ads or charge for a site built on it. Covers are loaded through
`/api/md-cover` because MangaDex asks sites not to hotlink its image host.

To use a different catalogue, implement the `Source` interface from
`src/lib/source/types.ts` (or reuse `catalogueSource` in `mangadex.ts` with your own
loader) and export it from `src/lib/source/index.ts`.

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
