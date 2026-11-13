/**
 * Every service the site sells, with its questions.
 *
 * Customers never see the numbers in this file. They are the basis for the
 * ESTIMATE shown after the questions: `quote()` in pricing.ts adds them up and
 * turns the result into a range. The owner then confirms the final price by hand.
 * The one exception is an option marked `fixed`: that is a flat price, shown and
 * paid right away. All amounts are in cents.
 *
 * LAUNCH PRICING. The amounts are tuned to these rules, which `npm test` enforces:
 *   1. every normal request estimates at or under 500 dollars
 *   2. bulk quantities and "very complex" jobs stay at or under 800 dollars
 *   3. only a full app or game, or a full book, may go above that
 * `SHOW_SPREAD=1 npx vitest run tests/estimate-spread.test.ts --disable-console-intercept`
 * prints the spread while you tune numbers here.
 */
import { FONTS, IMAGERY, PALETTES, TEMPLATES } from "./templates";

export interface Option {
  id: string;
  label: string;
  hint?: string;
  /** Added to the estimate basis */
  price?: number;
  /** Multiplies the whole basis, e.g. 1.15 for rush delivery */
  multiplier?: number;
  /** Picking this makes the whole order a flat price, paid right away with no estimate */
  fixed?: number;
}

interface QuestionBase {
  id: string;
  label: string;
  help?: string;
  /** Only ask this when an earlier choice question has one of these answers */
  showIf?: { id: string; in: string[] };
}

export type Question =
  | (QuestionBase & {
      kind: "choice";
      options: Option[];
      /** Draws the options as a visual picker from the look catalogue instead of plain cards */
      ui?: "template" | "palette" | "font" | "imagery";
    })
  | (QuestionBase & { kind: "multi"; options: Option[] })
  | (QuestionBase & {
      kind: "number";
      min: number;
      max: number;
      /** How many are already covered by the basis so far */
      included: number;
      /** Added for each one above `included` */
      unitPrice: number;
      unit: string;
    })
  | (QuestionBase & {
      kind: "text";
      placeholder: string;
      required: boolean;
      maxLength: number;
      /** Shortest accepted answer when required. Defaults to 10. */
      minLength?: number;
      long?: boolean;
    });

export interface Service {
  id: string;
  name: string;
  tagline: string;
  icon: "globe" | "pen" | "palette" | "code" | "sparkles";
  delivery: string;
  /** true: never estimated automatically, the owner sets the price by hand */
  quoteOnly?: boolean;
  examples: string[];
  questions: Question[];
}

const RUSH: Question = {
  id: "speed",
  kind: "choice",
  label: "How fast do you need it?",
  options: [
    { id: "standard", label: "Standard", hint: "Normal delivery time" },
    { id: "rush", label: "Rush", hint: "About twice as fast", multiplier: 1.15 },
  ],
};

/** How hard the job is. Used by services that have no other measure of size. */
const COMPLEXITY: Question = {
  id: "complexity",
  kind: "choice",
  label: "How complex is it?",
  help: "Your best guess is fine. We check it before confirming your price.",
  options: [
    { id: "simple", label: "Simple", hint: "One clear, small job" },
    { id: "medium", label: "Medium", hint: "A few connected parts", multiplier: 1.4 },
    { id: "complex", label: "Complex", hint: "Many parts, or tricky details", multiplier: 2 },
  ],
};

/** Software can get far bigger than a logo or a resume, so it has one more tier. */
const COMPLEXITY_SOFTWARE: Question = {
  ...COMPLEXITY,
  options: [
    ...(COMPLEXITY as Extract<Question, { kind: "choice" }>).options,
    { id: "huge", label: "Very complex", hint: "A full app, game or system", multiplier: 3.5 },
  ],
};

/** How far the work is taken. */
const LEVEL: Question = {
  id: "level",
  kind: "choice",
  label: "What level of finish do you want?",
  options: [
    { id: "basic", label: "Basic", hint: "Clean and working, no extras" },
    { id: "polished", label: "Polished", hint: "Extra care on the details", multiplier: 1.2 },
    { id: "premium", label: "Premium", hint: "Our best work, top to bottom", multiplier: 1.4 },
  ],
};

const REVISIONS: Question = {
  id: "revisions",
  kind: "number",
  label: "How many rounds of changes do you want?",
  help: "A round is one list of changes after you see the draft.",
  min: 1,
  max: 6,
  included: 1,
  unitPrice: 5_00,
  unit: "round",
};

const details = (label: string, placeholder: string, showIf?: Question["showIf"]): Question => ({
  id: "details",
  kind: "text",
  label,
  placeholder,
  required: true,
  maxLength: 2000,
  long: true,
  showIf,
});

const links = (showIf?: Question["showIf"]): Question => ({
  id: "links",
  kind: "text",
  label: "Any links or examples you like?",
  help: "Optional. Paste links to things that look or work the way you want.",
  placeholder: "https://",
  required: false,
  maxLength: 600,
  long: true,
  showIf,
});

// Writing: which document types each follow up question applies to.
const LONG_FORM = ["essay", "report", "other"];
const CITED = ["essay", "report", "book"];
const FORMATTED = ["essay", "report", "book", "script", "other", "resume", "cover", "both"];

// Something else: the two paths.
const IDEA = { id: "mode", in: ["idea"] };
const RANDOM = { id: "mode", in: ["random"] };

export const SERVICES: Service[] = [
  {
    id: "website",
    name: "Website",
    tagline: "Pick a look, see it live, and we build it",
    icon: "globe",
    delivery: "3 to 7 days",
    examples: ["Landing page", "Portfolio", "Small business site", "Online store"],
    questions: [
      {
        id: "type",
        kind: "choice",
        label: "What kind of website?",
        options: [
          { id: "landing", label: "One page", hint: "A single landing page", price: 45_00 },
          { id: "multi", label: "Multi page", hint: "Home plus inner pages", price: 90_00 },
          { id: "store", label: "Online store", hint: "Products, cart and checkout", price: 140_00 },
        ],
      },
      {
        id: "siteName",
        kind: "text",
        label: "What is it called?",
        help: "Your business, brand or project name. It shows up in the preview.",
        placeholder: "Sunny Side Bakery",
        required: true,
        minLength: 2,
        maxLength: 50,
      },
      {
        id: "template",
        kind: "choice",
        ui: "template",
        label: "Pick a starting layout",
        help: "This sets the structure. Colors, text and images come next.",
        options: TEMPLATES.map((t) => ({ id: t.id, label: t.name, hint: t.blurb })),
      },
      {
        id: "palette",
        kind: "choice",
        ui: "palette",
        label: "Choose your colors",
        options: PALETTES.map((p) => ({ id: p.id, label: p.name })),
      },
      {
        id: "font",
        kind: "choice",
        ui: "font",
        label: "Choose your text style",
        options: FONTS.map((f) => ({ id: f.id, label: f.name, hint: f.blurb })),
      },
      {
        id: "imagery",
        kind: "choice",
        ui: "imagery",
        label: "What kind of images?",
        options: IMAGERY.map((i) => ({ id: i.id, label: i.name, hint: i.blurb })),
      },
      {
        id: "pages",
        kind: "number",
        label: "How many pages?",
        help: "Count every separate page.",
        min: 2,
        max: 20,
        included: 3,
        unitPrice: 6_00,
        unit: "page",
        showIf: { id: "type", in: ["multi", "store"] },
      },
      {
        id: "features",
        kind: "multi",
        label: "Anything extra it should do?",
        help: "Pick as many as you need, or none.",
        options: [
          { id: "form", label: "Contact form", price: 5_00 },
          { id: "blog", label: "Blog", price: 15_00 },
          { id: "booking", label: "Booking or appointments", price: 25_00 },
          { id: "payments", label: "Take payments", price: 30_00 },
          { id: "copy", label: "Write the text for me", price: 15_00 },
        ],
      },
      LEVEL,
      details("Now tell us about it, like you would ask an AI", "What is the site for, who is it for, what should be on it, and what should visitors do? The more you say, the closer the first draft."),
      links(),
      REVISIONS,
      RUSH,
    ],
  },
  {
    id: "writing",
    name: "Writing",
    tagline: "Essays, reports, books, scripts, resumes and more",
    icon: "pen",
    delivery: "1 to 4 days",
    examples: ["Essay", "Report", "Book", "Script", "Resume", "Product descriptions"],
    questions: [
      {
        id: "type",
        kind: "choice",
        label: "What do you need written?",
        options: [
          { id: "essay", label: "Essay", price: 12_00 },
          { id: "report", label: "Report", hint: "Business, research or project report", price: 15_00 },
          { id: "book", label: "Book", hint: "Fiction, guide or memoir, start to finish", price: 40_00 },
          { id: "script", label: "Script", hint: "Video, film, podcast or stage", price: 15_00 },
          { id: "resume", label: "Resume", price: 15_00 },
          { id: "cover", label: "Cover letter", price: 10_00 },
          { id: "both", label: "Resume and cover letter", price: 22_00 },
          { id: "product", label: "Product descriptions", price: 12_00 },
          { id: "other", label: "Something else", price: 12_00 },
        ],
      },
      {
        id: "pages",
        kind: "number",
        label: "About how many pages?",
        help: "One page is roughly 300 words.",
        min: 1,
        max: 40,
        included: 3,
        unitPrice: 1_50,
        unit: "page",
        showIf: { id: "type", in: LONG_FORM },
      },
      {
        id: "bookPages",
        kind: "number",
        label: "About how many pages is the book?",
        help: "A short guide is around 30 pages. A novel is 200 or more.",
        min: 10,
        max: 300,
        included: 20,
        unitPrice: 1_00,
        unit: "page",
        showIf: { id: "type", in: ["book"] },
      },
      {
        id: "minutes",
        kind: "number",
        label: "How long should it run, in minutes?",
        help: "One minute of script is about one page.",
        min: 1,
        max: 120,
        included: 3,
        unitPrice: 1_50,
        unit: "minute",
        showIf: { id: "type", in: ["script"] },
      },
      {
        id: "scriptFor",
        kind: "choice",
        label: "What is the script for?",
        options: [
          { id: "video", label: "Online video", hint: "YouTube, TikTok, Reels" },
          { id: "film", label: "Short film" },
          { id: "podcast", label: "Podcast" },
          { id: "ad", label: "Ad or promo" },
          { id: "stage", label: "Stage or live event" },
        ],
        showIf: { id: "type", in: ["script"] },
      },
      {
        id: "items",
        kind: "number",
        label: "How many products?",
        min: 1,
        max: 100,
        included: 5,
        unitPrice: 1_50,
        unit: "product",
        showIf: { id: "type", in: ["product"] },
      },
      {
        id: "sources",
        kind: "text",
        label: "Any specific sources we should use?",
        help: "Optional. Paste links, book titles or articles. Leave it empty and we find our own.",
        placeholder: "Links, titles, authors",
        required: false,
        maxLength: 1500,
        long: true,
        showIf: { id: "type", in: CITED },
      },
      {
        id: "citation",
        kind: "choice",
        label: "Which citation style?",
        options: [
          { id: "none", label: "No citations" },
          { id: "apa", label: "APA" },
          { id: "mla", label: "MLA" },
          { id: "chicago", label: "Chicago" },
          { id: "harvard", label: "Harvard" },
        ],
        showIf: { id: "type", in: ["essay", "report"] },
      },
      {
        id: "tone",
        kind: "choice",
        label: "What writing style?",
        options: [
          { id: "professional", label: "Professional" },
          { id: "academic", label: "Academic", hint: "Formal and precise" },
          { id: "friendly", label: "Friendly", hint: "Warm and simple" },
          { id: "bold", label: "Bold and confident" },
          { id: "story", label: "Storytelling", hint: "Vivid, pulls the reader in" },
          { id: "funny", label: "Funny" },
        ],
      },
      {
        id: "font",
        kind: "choice",
        label: "Which font?",
        options: [
          { id: "times", label: "Times New Roman" },
          { id: "arial", label: "Arial" },
          { id: "calibri", label: "Calibri" },
          { id: "georgia", label: "Georgia" },
          { id: "any", label: "You pick for me" },
        ],
        showIf: { id: "type", in: FORMATTED },
      },
      {
        id: "fontSize",
        kind: "choice",
        label: "What text size?",
        options: [
          { id: "12", label: "12 point", hint: "The usual choice" },
          { id: "10", label: "10 point" },
          { id: "11", label: "11 point" },
          { id: "14", label: "14 point" },
        ],
        showIf: { id: "type", in: FORMATTED },
      },
      COMPLEXITY,
      LEVEL,
      details("Give us the details", "The topic, the point you want to make, who will read it, and anything it must include. For a resume, paste your experience."),
      REVISIONS,
      RUSH,
    ],
  },
  {
    id: "design",
    name: "Logos and thumbnails",
    tagline: "Graphics for channels, brands and shops",
    icon: "palette",
    delivery: "1 to 3 days",
    examples: ["Logo", "YouTube thumbnail", "Brand kit", "Channel banner"],
    questions: [
      {
        id: "type",
        kind: "choice",
        label: "What should we design?",
        options: [
          { id: "thumbnail", label: "Thumbnail", price: 8_00 },
          { id: "banner", label: "Channel banner", price: 15_00 },
          { id: "logo", label: "Logo", price: 25_00 },
          { id: "kit", label: "Logo and brand kit", hint: "Logo, colors and fonts", price: 45_00 },
        ],
      },
      {
        id: "quantity",
        kind: "number",
        label: "How many?",
        min: 1,
        max: 30,
        included: 1,
        unitPrice: 5_00,
        unit: "extra",
      },
      COMPLEXITY,
      LEVEL,
      details("Describe what you want", "Name, style, colors, and the feeling it should give."),
      links(),
      REVISIONS,
      RUSH,
    ],
  },
  {
    id: "scripts",
    name: "Apps, scripts and tools",
    tagline: "From a small script to a full app or game",
    icon: "code",
    delivery: "2 to 5 days",
    examples: ["Discord bot", "Python script", "Spreadsheet automation", "Simple app or game"],
    questions: [
      {
        id: "type",
        kind: "choice",
        label: "What kind of tool?",
        options: [
          { id: "script", label: "Small script", hint: "Does one job", price: 25_00 },
          { id: "sheet", label: "Spreadsheet automation", price: 30_00 },
          { id: "bot", label: "Chat bot", hint: "Discord, Telegram and similar", price: 50_00 },
          { id: "automation", label: "Automation between apps", price: 65_00 },
          { id: "app", label: "App or game", hint: "A full program people use or play", price: 150_00 },
        ],
      },
      COMPLEXITY_SOFTWARE,
      LEVEL,
      {
        id: "extras",
        kind: "multi",
        label: "Any extras?",
        options: [
          { id: "setup", label: "Set it up and run it for me", price: 20_00 },
          { id: "docs", label: "Written guide on how to use it", price: 10_00 },
        ],
      },
      details("What should it do?", "Describe the steps. What goes in, what should come out, and where it should run."),
      REVISIONS,
      RUSH,
    ],
  },
  {
    id: "custom",
    name: "Something else",
    tagline: "Bring any idea, or let us surprise you",
    icon: "sparkles",
    delivery: "Depends on the job",
    quoteOnly: true,
    examples: ["A slide deck", "A study guide", "A custom calculator", "Surprise me"],
    questions: [
      {
        id: "mode",
        kind: "choice",
        label: "What are we making?",
        options: [
          { id: "idea", label: "I have an idea", hint: "Describe it and we tell you what it takes" },
          {
            id: "random",
            label: "Surprise me",
            hint: "Something random made just for you. Could be a cursed image, could be a gloriously bad little game. Flat $15.",
            fixed: 15_00,
          },
        ],
      },
      details("What do you want built?", "Describe it like you would to a friend. What is it, who is it for, what does done look like?", IDEA),
      {
        id: "budget",
        kind: "choice",
        label: "What is your budget?",
        help: "This helps us suggest something that fits. It is not a commitment.",
        options: [
          { id: "under50", label: "Under $50" },
          { id: "50to200", label: "$50 to $200" },
          { id: "200to800", label: "$200 to $800" },
          { id: "800plus", label: "$800 to $2,000" },
          { id: "unsure", label: "Not sure yet" },
        ],
        showIf: IDEA,
      },
      {
        id: "deadline",
        kind: "choice",
        label: "When do you need it?",
        options: [
          { id: "flexible", label: "No rush" },
          { id: "week", label: "Within a week" },
          { id: "days", label: "In a few days" },
        ],
        showIf: IDEA,
      },
      links(IDEA),
      {
        id: "vibe",
        kind: "choice",
        label: "Pick a vibe",
        options: [
          { id: "funny", label: "Funny" },
          { id: "cursed", label: "Cursed", hint: "Weird in a way you cannot unsee" },
          { id: "wholesome", label: "Wholesome" },
          { id: "chaos", label: "Pure chaos", hint: "Maximum brain rot" },
        ],
        showIf: RANDOM,
      },
      {
        id: "form",
        kind: "choice",
        label: "What should it be?",
        options: [
          { id: "any", label: "You decide", hint: "The full gamble" },
          { id: "image", label: "A weird image" },
          { id: "game", label: "A tiny, terrible game" },
          { id: "story", label: "A short story" },
          { id: "song", label: "A song or poem" },
        ],
        showIf: RANDOM,
      },
      {
        id: "avoid",
        kind: "text",
        label: "Anything we should stay away from?",
        help: "Optional. Topics, words or themes you do not want.",
        placeholder: "Spiders. Absolutely no spiders.",
        required: false,
        maxLength: 300,
        long: true,
        showIf: RANDOM,
      },
    ],
  },
];

export function getService(id: string): Service | undefined {
  return SERVICES.find((s) => s.id === id);
}
