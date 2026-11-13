/**
 * Every service the site sells, with its questions and prices.
 * All prices are in cents. To add a service, add an entry to SERVICES.
 * The price shown to customers and the price charged both come from this file
 * through `quote()` in pricing.ts, so they can never disagree.
 */

export interface Option {
  id: string;
  label: string;
  hint?: string;
  /** Added to the price */
  price?: number;
  /** Multiplies the whole price, e.g. 1.3 for rush delivery */
  multiplier?: number;
}

interface QuestionBase {
  id: string;
  label: string;
  help?: string;
}

export type Question =
  | (QuestionBase & { kind: "choice"; options: Option[] })
  | (QuestionBase & { kind: "multi"; options: Option[] })
  | (QuestionBase & {
      kind: "number";
      min: number;
      max: number;
      /** How many are already covered by the price so far */
      included: number;
      /** Price for each one above `included` */
      unitPrice: number;
      unit: string;
    })
  | (QuestionBase & { kind: "text"; placeholder: string; required: boolean; maxLength: number; long?: boolean });

export interface Service {
  id: string;
  name: string;
  tagline: string;
  icon: "globe" | "pen" | "palette" | "code" | "sparkles";
  /** Shown on cards as "from". Must be the cheapest price the questions can produce. */
  startingAt: number;
  delivery: string;
  /** true: never priced automatically, the owner sets the price by hand */
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
    { id: "rush", label: "Rush", hint: "About twice as fast", multiplier: 1.3 },
  ],
};

const REVISIONS: Question = {
  id: "revisions",
  kind: "number",
  label: "How many rounds of changes do you want?",
  help: "One round is included. A round is one list of changes after you see the draft.",
  min: 1,
  max: 6,
  included: 1,
  unitPrice: 12_00,
  unit: "round",
};

const details = (label: string, placeholder: string): Question => ({
  id: "details",
  kind: "text",
  label,
  placeholder,
  required: true,
  maxLength: 2000,
  long: true,
});

const LINKS: Question = {
  id: "links",
  kind: "text",
  label: "Any links or examples you like?",
  help: "Optional. Paste links to things that look or work the way you want.",
  placeholder: "https://",
  required: false,
  maxLength: 600,
  long: true,
};

export const SERVICES: Service[] = [
  {
    id: "website",
    name: "Website",
    tagline: "A clean site for you or your business",
    icon: "globe",
    startingAt: 149_00,
    delivery: "3 to 7 days",
    examples: ["Landing page", "Portfolio", "Small business site", "Online store"],
    questions: [
      {
        id: "type",
        kind: "choice",
        label: "What kind of website?",
        options: [
          { id: "landing", label: "One page", hint: "A single landing page", price: 149_00 },
          { id: "multi", label: "Multi page", hint: "Home plus inner pages", price: 299_00 },
          { id: "store", label: "Online store", hint: "Products, cart and checkout", price: 649_00 },
        ],
      },
      {
        id: "pages",
        kind: "number",
        label: "How many pages?",
        help: "Three pages are included with multi page and store sites. One page sites stay at 1.",
        min: 1,
        max: 20,
        included: 3,
        unitPrice: 35_00,
        unit: "page",
      },
      {
        id: "features",
        kind: "multi",
        label: "Anything extra it should do?",
        help: "Pick as many as you need, or none.",
        options: [
          { id: "form", label: "Contact form", price: 20_00 },
          { id: "blog", label: "Blog", price: 60_00 },
          { id: "booking", label: "Booking or appointments", price: 90_00 },
          { id: "payments", label: "Take payments", price: 120_00 },
          { id: "copy", label: "Write the text for me", price: 60_00 },
        ],
      },
      details("Tell us about it", "What is the site for, who is it for, and what should visitors do on it?"),
      LINKS,
      REVISIONS,
      RUSH,
    ],
  },
  {
    id: "writing",
    name: "Writing",
    tagline: "Resumes, cover letters and product text",
    icon: "pen",
    startingAt: 19_00,
    delivery: "1 to 2 days",
    examples: ["Resume", "Cover letter", "Product descriptions", "About page"],
    questions: [
      {
        id: "type",
        kind: "choice",
        label: "What do you need written?",
        options: [
          { id: "cover", label: "Cover letter", price: 19_00 },
          { id: "resume", label: "Resume", price: 29_00 },
          { id: "both", label: "Resume and cover letter", price: 42_00 },
          { id: "product", label: "Product descriptions", hint: "Up to 5 products included", price: 25_00 },
          { id: "other", label: "Something else", hint: "Up to 500 words", price: 25_00 },
        ],
      },
      {
        id: "items",
        kind: "number",
        label: "How many items?",
        help: "For product descriptions this is the number of products (5 included). For everything else leave it at 5.",
        min: 5,
        max: 100,
        included: 5,
        unitPrice: 4_00,
        unit: "item",
      },
      details("Give us the details", "Paste your experience, the job you want, or the products. The more you give, the better it reads."),
      {
        id: "tone",
        kind: "choice",
        label: "What tone?",
        options: [
          { id: "professional", label: "Professional" },
          { id: "friendly", label: "Friendly" },
          { id: "bold", label: "Bold and confident" },
        ],
      },
      REVISIONS,
      RUSH,
    ],
  },
  {
    id: "design",
    name: "Logos and thumbnails",
    tagline: "Graphics for channels, brands and shops",
    icon: "palette",
    startingAt: 12_00,
    delivery: "1 to 3 days",
    examples: ["Logo", "YouTube thumbnail", "Brand kit", "Channel banner"],
    questions: [
      {
        id: "type",
        kind: "choice",
        label: "What should we design?",
        options: [
          { id: "thumbnail", label: "Thumbnail", hint: "Price is for each one", price: 12_00 },
          { id: "banner", label: "Channel banner", price: 25_00 },
          { id: "logo", label: "Logo", price: 39_00 },
          { id: "kit", label: "Logo and brand kit", hint: "Logo, colors and fonts", price: 79_00 },
        ],
      },
      {
        id: "quantity",
        kind: "number",
        label: "How many?",
        help: "Extra ones cost less than the first.",
        min: 1,
        max: 30,
        included: 1,
        unitPrice: 9_00,
        unit: "extra",
      },
      details("Describe what you want", "Name, style, colors, and the feeling it should give."),
      LINKS,
      REVISIONS,
      RUSH,
    ],
  },
  {
    id: "scripts",
    name: "Scripts and automations",
    tagline: "Small tools that save you time",
    icon: "code",
    startingAt: 49_00,
    delivery: "2 to 5 days",
    examples: ["Discord bot", "Python script", "Spreadsheet automation", "Web scraper for your own data"],
    questions: [
      {
        id: "type",
        kind: "choice",
        label: "What kind of tool?",
        options: [
          { id: "script", label: "Small script", hint: "Does one job", price: 49_00 },
          { id: "sheet", label: "Spreadsheet automation", price: 59_00 },
          { id: "bot", label: "Chat bot", hint: "Discord, Telegram and similar", price: 99_00 },
          { id: "automation", label: "Automation between apps", price: 129_00 },
        ],
      },
      {
        id: "size",
        kind: "choice",
        label: "How big is the job?",
        options: [
          { id: "small", label: "Small", hint: "One clear task" },
          { id: "medium", label: "Medium", hint: "A few connected tasks", multiplier: 1.6 },
          { id: "large", label: "Large", hint: "Many steps or moving parts", multiplier: 2.4 },
        ],
      },
      {
        id: "extras",
        kind: "multi",
        label: "Any extras?",
        options: [
          { id: "setup", label: "Set it up and run it for me", price: 40_00 },
          { id: "docs", label: "Written guide on how to use it", price: 20_00 },
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
    tagline: "Describe any idea and we will price it for you",
    icon: "sparkles",
    startingAt: 0,
    delivery: "Depends on the job",
    quoteOnly: true,
    examples: ["A slide deck", "A study guide", "A custom calculator", "Anything you can describe"],
    questions: [
      details("What do you want built?", "Describe it like you would to a friend. What is it, who is it for, what does done look like?"),
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
        ],
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
      },
      LINKS,
    ],
  },
];

export function getService(id: string): Service | undefined {
  return SERVICES.find((s) => s.id === id);
}
