# Inkwell: manga reading site design

Date: 2026-11-12
Status: awaiting review

## Goal

An original manga / manhwa / manhua reading site with the same kind of features as
popular reader sites, but with a better interface, better colour, richer discovery
(popular, recommended, diverse browsing) and a noticeably better reading page.

It is for readers on phone and desktop. Success means: a visitor can land on the
home page, find something through popular / recommended / browse, open a series,
read chapters comfortably in the mode they prefer, and come back later to exactly
where they stopped.

The site uses its own name, logo and visual design. It does not copy another
site's branding or scrape another site's content.

## Decisions already made

| Topic | Decision |
|---|---|
| Content | Built in demo data behind a swappable source interface |
| Stack | Next.js (App Router) + TypeScript + Tailwind CSS, deployable on Vercel |
| Persistence | Browser `localStorage` only, no accounts |
| Working name | Inkwell (one constant, easy to rename) |

## Out of scope

User accounts, comments, an upload tool, and any real content source. Each can be
added later without restructuring.

## Visual design

- Dark first, with a light mode toggle stored in `localStorage` and defaulting to
  the system preference.
- Deep ink background, warm coral / amber accent, neutral greys for text. Colours
  are CSS variables so both themes share every component.
- Large cover art, soft rounded cards, generous spacing, visible focus rings.
- Responsive from 360px wide phones to wide desktop. No horizontal page scroll.
- Motion is subtle and respects `prefers-reduced-motion`.

## Pages and routes

| Route | Purpose |
|---|---|
| `/` | Home: spotlight banner, Continue Reading, Popular, Recommended, Latest Updates, rows per type |
| `/browse` | Search plus filters and sort |
| `/series/[slug]` | Series detail and chapter list |
| `/read/[slug]/[chapter]` | Reader |
| `/library` | Bookmarks and reading history |

### Home

1. Spotlight: rotating banner of featured series, pauses on hover and focus, has
   manual controls.
2. Continue Reading: only shown when history exists.
3. Popular: tabs for Today, This Week, All Time, shown as a ranked list.
4. Recommended For You: see Recommendations below.
5. Latest Updates: series ordered by most recent chapter date.
6. One row each for Manga, Manhwa and Manhua.

### Browse

- Text search over title, alternative titles and author.
- Filters: genre (multi select), type, status.
- Sort: popular, rating, newest, A to Z.
- Filter state lives in the URL query string so results are shareable and the back
  button works.
- Empty state with a clear filters action.

### Series page

- Cover, title, author, type, status, rating, genres, synopsis.
- Start Reading or Continue (chapter N) button, bookmark toggle.
- Chapter list, newest first with a sort toggle, read chapters marked.
- "You may also like" row based on shared genres.

### Reader

- Modes: long strip, single page, double page spread.
- Direction: right to left or left to right (affects paged modes and tap zones).
- Fit: width, height, original, plus zoom in long strip.
- Input: arrow keys, space, tap zones (previous / menu / next), swipe on touch.
- Top and bottom bars auto hide while reading and return on tap or mouse move.
- Progress bar with page jump, previous / next chapter, chapter picker.
- At the end of a chapter: a next chapter card, with optional auto continue.
- Background choice: black, dark grey, sepia, white. Page gap setting for long strip.
- Settings panel persists every choice. Exact page is saved per series.
- Neighbouring pages are preloaded. A failed page shows a retry button.

### Library

Two tabs: Bookmarks and History. History shows last chapter and page with a resume
link, and can be cleared.

## Architecture

```
src/
  app/                 routes (server components by default)
  components/          presentational UI (cards, rows, header, spotlight)
  components/reader/   reader client components
  lib/source/          Source interface + demo implementation
  lib/recommend.ts     pure recommendation logic
  lib/reader/          pure reader state logic (reducer, page math)
  lib/storage.ts       typed localStorage wrapper
```

### Source interface

All content access goes through one interface. Pages never import demo data
directly.

```ts
interface Source {
  getSpotlight(): Promise<Series[]>
  getPopular(range: 'today' | 'week' | 'all'): Promise<Series[]>
  getLatest(): Promise<Series[]>
  getByType(type: SeriesType): Promise<Series[]>
  search(query: BrowseQuery): Promise<Series[]>
  getSeries(slug: string): Promise<Series | null>
  getChapters(slug: string): Promise<Chapter[]>
  getChapterPages(slug: string, chapter: string): Promise<Page[]>
  getAll(): Promise<Series[]>
}
```

`lib/source/index.ts` exports the active source. Replacing the demo source with a
real one means writing one new file that implements this interface.

### Demo source

- About 40 invented series across the three types with varied genres, statuses,
  ratings, view counts and chapter counts. Titles and synopses are made up.
- Covers and pages are generated SVG (deterministic from the series slug), served
  from route handlers, so there are no binary assets and no third party images.
- Manhwa and manhua pages are tall strips, manga pages use a standard page ratio,
  so every reader mode has realistic material.

### Recommendations

Pure function `recommend(all, history, bookmarks)`:

1. Build genre weights from read and bookmarked series (bookmarks count more).
2. Score unread series by summed genre weight, with rating as a tie breaker.
3. With no history, fall back to top rated.

Runs on the client because the inputs live in `localStorage`.

### Client state

`lib/storage.ts` wraps `localStorage` with typed keys for reader settings, reading
progress, bookmarks and theme. Every read and write is guarded so the site still
works when storage is unavailable (private mode). Components that depend on it
render a neutral state on the server and fill in after mount, to avoid hydration
mismatch.

## Error handling

- Unknown series or chapter: Next.js not found page with a link home.
- Page image fails: inline retry, the rest of the chapter stays readable.
- Storage unavailable: features degrade to session only, nothing throws.

## Testing

- Unit tests (Vitest): recommendation scoring and fallback, reader reducer (page
  stepping, direction, double page pairing, chapter boundaries), storage wrapper
  fallbacks, demo source query filtering and sorting.
- Browser check with Playwright: load every route, read through a chapter in each
  mode, confirm progress restores after reload, check phone and desktop widths.
- `next build` and lint must pass.
