/**
 * The website look catalogue: templates, color sets, text styles and image styles.
 *
 * This file is the "database" the website builder reads from. Customers pick one
 * of each and see a live preview. To offer more choice, add entries here: the
 * build flow, the preview and the order pages all pick them up automatically.
 * (A template also needs a layout in components/site-preview.tsx.)
 */

export interface Template {
  id: string;
  name: string;
  blurb: string;
  /** Which kinds of website (the first question) this template suits best */
  goodFor: string[];
  /** Button text used in the preview */
  cta: string;
}

export const TEMPLATES: Template[] = [
  { id: "business", name: "Business", blurb: "Clear and trustworthy, for services and companies", goodFor: ["multi", "landing"], cta: "Get in touch" },
  { id: "storefront", name: "Storefront", blurb: "Products up front with a shop grid", goodFor: ["store"], cta: "Shop now" },
  { id: "portfolio", name: "Portfolio", blurb: "Big visuals to show off your work", goodFor: ["multi", "landing"], cta: "See my work" },
  { id: "restaurant", name: "Food and venue", blurb: "Menu, hours and a booking button", goodFor: ["multi", "landing"], cta: "Book a table" },
  { id: "launch", name: "Launch page", blurb: "One strong message and one button", goodFor: ["landing"], cta: "Get started" },
  { id: "blog", name: "Blog and stories", blurb: "Made for reading, posts first", goodFor: ["multi"], cta: "Read more" },
];

export interface Palette {
  id: string;
  name: string;
  bg: string;
  surface: string;
  text: string;
  muted: string;
  accent: string;
  accentInk: string;
}

export const PALETTES: Palette[] = [
  { id: "midnight", name: "Midnight", bg: "#0b1020", surface: "#151c33", text: "#f3f6ff", muted: "#9aa6c4", accent: "#5d87ff", accentInk: "#050814" },
  { id: "paper", name: "Paper", bg: "#faf6ef", surface: "#ffffff", text: "#1f1b16", muted: "#756c60", accent: "#c8553d", accentInk: "#ffffff" },
  { id: "forest", name: "Forest", bg: "#10241c", surface: "#193329", text: "#f1f5ee", muted: "#a3b8a9", accent: "#e0b354", accentInk: "#1a1405" },
  { id: "ocean", name: "Ocean", bg: "#f4fafc", surface: "#ffffff", text: "#0c2733", muted: "#55707c", accent: "#0e8fa8", accentInk: "#ffffff" },
  { id: "sunset", name: "Sunset", bg: "#fff6f1", surface: "#ffffff", text: "#3a1730", muted: "#8a6478", accent: "#f0603c", accentInk: "#ffffff" },
  { id: "mono", name: "Mono", bg: "#ffffff", surface: "#f3f3f3", text: "#0d0d0d", muted: "#6b6b6b", accent: "#0d0d0d", accentInk: "#ffffff" },
  { id: "candy", name: "Candy", bg: "#fff3fa", surface: "#ffffff", text: "#35123d", muted: "#8a6692", accent: "#d63ea8", accentInk: "#ffffff" },
  { id: "sand", name: "Sand", bg: "#f2ebdd", surface: "#fbf7ee", text: "#3b2f20", muted: "#7c6e5a", accent: "#6f7f3a", accentInk: "#ffffff" },
];

export interface FontStyle {
  id: string;
  name: string;
  blurb: string;
  /** CSS font-family for headings and for body text. Only fonts that need no download. */
  heading: string;
  body: string;
  headingWeight: number;
  /** letter-spacing for headings, in em */
  tracking: number;
}

const SANS = '"Inter Variable", ui-sans-serif, system-ui, sans-serif';

export const FONTS: FontStyle[] = [
  { id: "modern", name: "Modern", blurb: "Clean and neutral", heading: SANS, body: SANS, headingWeight: 700, tracking: -0.02 },
  { id: "bold", name: "Bold", blurb: "Loud headlines with character", heading: '"Bricolage Grotesque Variable", ' + SANS, body: SANS, headingWeight: 800, tracking: -0.03 },
  { id: "classic", name: "Classic", blurb: "Elegant serif, feels established", heading: 'Georgia, "Times New Roman", serif', body: 'Georgia, "Times New Roman", serif', headingWeight: 700, tracking: -0.01 },
  { id: "friendly", name: "Friendly", blurb: "Soft and rounded, easy going", heading: 'ui-rounded, "Arial Rounded MT Bold", "Nunito", ' + SANS, body: SANS, headingWeight: 700, tracking: -0.01 },
  { id: "tech", name: "Tech", blurb: "Monospace, for builders and gamers", heading: 'ui-monospace, "SF Mono", Menlo, Consolas, monospace', body: SANS, headingWeight: 700, tracking: -0.04 },
];

export interface Imagery {
  id: string;
  name: string;
  blurb: string;
}

export const IMAGERY: Imagery[] = [
  { id: "photo", name: "Photos", blurb: "Real photos of your work, place or products" },
  { id: "illustration", name: "Illustrations", blurb: "Drawn shapes and characters" },
  { id: "abstract", name: "Abstract", blurb: "Gradients and soft color washes" },
  { id: "none", name: "No images", blurb: "Text first, very minimal" },
];

export interface Look {
  template: Template;
  palette: Palette;
  font: FontStyle;
  imagery: Imagery;
}

const pick = <T extends { id: string }>(list: T[], id: unknown): T => list.find((item) => item.id === id) ?? list[0];

/** Resolves stored answer ids into a full look. Unknown or missing ids fall back to the first entry. */
export function resolveLook(answers: Record<string, unknown>): Look {
  return {
    template: pick(TEMPLATES, answers.template),
    palette: pick(PALETTES, answers.palette),
    font: pick(FONTS, answers.font),
    imagery: pick(IMAGERY, answers.imagery),
  };
}
