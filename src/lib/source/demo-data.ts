import type { Chapter, Series, SeriesStatus, SeriesType } from "@/lib/types";
import { createRand } from "./rand";

export const GENRES = [
  "Action", "Adventure", "Comedy", "Drama", "Fantasy", "Historical", "Horror",
  "Isekai", "Martial Arts", "Mystery", "Psychological", "Romance", "School",
  "Sci-Fi", "Slice of Life", "Sports", "Supernatural", "Thriller",
] as const;

type Seed = [title: string, type: SeriesType, genres: string[], author: string, premise: string, alt?: string];

// Every title, author and premise below is invented for the demo.
const SEEDS: Seed[] = [
  ["Ashfall Courier", "manga", ["Action", "Adventure", "Sci-Fi"], "Renji Okabe", "A parcel runner crosses a continent buried in volcanic ash, carrying a box nobody will let her open.", "Hai no Haitatsunin"],
  ["The Lantern Clerk", "manga", ["Mystery", "Supernatural", "Slice of Life"], "Mio Hasegawa", "The night shift at a tiny ward office files paperwork for residents who died decades ago."],
  ["Paper Moon Dojo", "manga", ["Martial Arts", "Comedy", "School"], "Daichi Kuroe", "A calligraphy club discovers its founding scroll is a complete fighting style."],
  ["Salt and Thunder", "manga", ["Adventure", "Fantasy", "Drama"], "Aoi Tanabe", "Two rival fishing villages share one storm spirit and it has started playing favourites."],
  ["Second Bell", "manga", ["Romance", "School", "Slice of Life"], "Yuna Shirai", "Two students who only ever meet in the three minutes between classes try to stretch those minutes."],
  ["Hollow Orchard", "manga", ["Horror", "Psychological", "Mystery"], "Kaede Mori", "Every tree in the family orchard is labelled with a name and the newest label is hers."],
  ["Gearheart Sonata", "manga", ["Sci-Fi", "Drama", "Romance"], "Tomo Ishikura", "A piano tuner repairs a retired android and finds a melody locked in its memory."],
  ["Ninth Inning Ghost", "manga", ["Sports", "Supernatural", "Comedy"], "Haruto Senda", "A benchwarmer is coached by the spirit of a pitcher who never got to finish his last game."],
  ["Crownless", "manga", ["Fantasy", "Action", "Historical"], "Ren Asakura", "The palace burns and the only survivor of the royal line is the kitchen boy who lit the stoves."],
  ["Tidewalkers", "manga", ["Adventure", "Fantasy", "Slice of Life"], "Nagi Umeda", "Twice a day the sea pulls back and a road appears to an island that is not on any map."],
  ["Static Bloom", "manga", ["Psychological", "Thriller", "Sci-Fi"], "Sora Fujikawa", "A radio host starts receiving calls from tomorrow's listeners."],
  ["Bento for the End of the World", "manga", ["Slice of Life", "Comedy", "Sci-Fi"], "Hina Matsuo", "Civilisation has ended quietly and one cook is still open for lunch."],
  ["Wolf at the Loom", "manga", ["Historical", "Drama", "Supernatural"], "Kyo Takamine", "A weaver's apprentice in an old silk town can read the future in dropped threads."],
  ["Quiet Blade Kanna", "manga", ["Action", "Historical", "Martial Arts"], "Jin Sakaki", "A swordswoman who has taken a vow of silence is hired to guard a man who never stops talking."],
  ["Low Orbit Diner", "manga", ["Sci-Fi", "Slice of Life", "Comedy"], "Mei Ogawa", "The last greasy spoon on a cargo ring serves truckers, smugglers and one very lost prince."],
  ["Glass Summit", "manga", ["Sports", "Drama", "Adventure"], "Riku Hayama", "A climbing team attempts a peak that reflects the sky so well nobody has ever found the top."],

  ["Level Zero Landlord", "manhwa", ["Fantasy", "Action", "Comedy"], "Seo Minjae", "He inherited a run down apartment block. The basement turns out to be a dungeon and the tenants are monsters.", "Zero Level Building Owner"],
  ["The Villainess Keeps a Ledger", "manhwa", ["Romance", "Fantasy", "Isekai"], "Han Yerin", "Reborn as the doomed rival in a novel, she decides to survive with compound interest."],
  ["Midnight Convenience", "manhwa", ["Supernatural", "Slice of Life", "Mystery"], "Park Dohyun", "A corner shop that only gods and ghosts can find hires its first human cashier."],
  ["Return of the Iron Chef Knight", "manhwa", ["Fantasy", "Action", "Adventure"], "Kim Taeyang", "The kingdom's deadliest knight comes back from war and opens a noodle stall."],
  ["Overtime Hunter", "manhwa", ["Action", "Thriller", "Supernatural"], "Lee Jiwoo", "An office worker clears monster gates between meetings and expenses the damage."],
  ["Blue Hour Bakery", "manhwa", ["Romance", "Slice of Life", "Drama"], "Choi Sarang", "Two bakers on the same street compete for the one customer who shows up before sunrise."],
  ["Tower of Ten Thousand Stairs", "manhwa", ["Fantasy", "Adventure", "Action"], "Yoon Hajun", "Each floor grants a wish and takes a memory. He is on floor nine thousand and cannot remember why."],
  ["My Classmate Is the Final Boss", "manhwa", ["School", "Comedy", "Fantasy"], "Jang Eunbi", "The transfer student is clearly the last enemy in a game only one girl has played."],
  ["Seoul After Rain", "manhwa", ["Drama", "Romance", "Psychological"], "Moon Chaewon", "A photographer keeps finding the same stranger in pictures taken years apart."],
  ["Regressor's Second Shift", "manhwa", ["Action", "Fantasy", "Isekai"], "Kang Woojin", "He died saving the world and woke up on his first day of work, with the monthly reports still due."],
  ["Paws of the Dragon King", "manhwa", ["Fantasy", "Comedy", "Slice of Life"], "Shin Bora", "An ancient dragon is reincarnated as a rescue cat and has opinions about the food."],
  ["Deadline Girl", "manhwa", ["Thriller", "Mystery", "Psychological"], "Ahn Soyeon", "A webtoon artist notices that whatever she draws by Friday happens by Monday."],
  ["Rooftop Kingdom", "manhwa", ["School", "Action", "Drama"], "Baek Junho", "Every school in the district is ruled from its roof and a quiet freshman is climbing all of them."],
  ["Neon Shaman", "manhwa", ["Supernatural", "Action", "Mystery"], "Ryu Dawon", "A club DJ by night performs exorcisms through the sound system."],

  ["Jade Furnace Chronicle", "manhua", ["Martial Arts", "Fantasy", "Action"], "Lin Qingyu", "A failed alchemist's last furnace begins refining the people who stand near it.", "Yu Lu Ji"],
  ["Heavenly Clerk of the Mortal Court", "manhua", ["Fantasy", "Comedy", "Historical"], "Zhao Wenbo", "Demoted from the celestial bureaucracy, a minor god must clear a village's backlog of prayers."],
  ["Sword Saint's Lazy Disciple", "manhua", ["Martial Arts", "Comedy", "Adventure"], "Chen Moran", "The greatest sword master alive takes one student, who would much rather nap."],
  ["Nine Rivers Rising", "manhua", ["Historical", "Drama", "Action"], "Wu Haoran", "Nine river clans, one flood season and a boatman who has ferried them all."],
  ["The Apothecary of Cloud Lane", "manhua", ["Mystery", "Historical", "Romance"], "Su Lanxin", "A herb seller solves the capital's quiet poisonings one prescription at a time."],
  ["Immortal on Probation", "manhua", ["Fantasy", "Comedy", "Supernatural"], "Gao Yifan", "He reached immortality by accident and heaven has given him ninety days to prove he deserves it."],
  ["Phoenix Under the Ash Tree", "manhua", ["Romance", "Fantasy", "Drama"], "Bai Ruoxi", "A disgraced general and a caged phoenix make a deal that neither intends to keep."],
  ["Cultivation Cram School", "manhua", ["School", "Martial Arts", "Comedy"], "Tang Zihao", "Entrance exams for the immortal sects are brutal, so somebody opened a tutoring centre."],
  ["Spirit Beast Courier Co.", "manhua", ["Adventure", "Fantasy", "Slice of Life"], "Ye Mingxuan", "Parcels delivered anywhere in the three realms, provided the giant crane is in a good mood."],
  ["The Emperor's Shadow Plays Chess", "manhua", ["Psychological", "Historical", "Thriller"], "Qin Shuhan", "The body double of a dying emperor must win a game that has been running for thirty years."],
];

const HOOKS = [
  "What starts as a small favour turns into the longest season of their life.",
  "Old debts, new allies and a secret that refuses to stay buried.",
  "Funny when it wants to be and sharp when it needs to be.",
  "A slow burn that rewards patience with chapters you will reread.",
  "Each arc raises the stakes without losing the quiet moments.",
  "Come for the premise, stay for a cast that feels like friends.",
];

const CHAPTER_WORDS = [
  "Arrival", "The Offer", "Smoke", "A Small Lie", "Crossing", "The Name", "Rain", "First Blood",
  "Homecoming", "The Door", "Echo", "Ledger", "Night Market", "The Promise", "Ash", "Tide",
  "Old Friends", "The Trial", "Lantern", "Summit", "Silence", "The Letter", "Dawn", "Rival",
];

const BASE_TIME = Date.UTC(2026, 10, 10);
const DAY = 86_400_000;

export function slugify(title: string): string {
  return title.toLowerCase().replace(/'/g, "").replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "");
}

function build(seed: Seed): Series {
  const [title, type, genres, author, premise, alt] = seed;
  const slug = slugify(title);
  const rand = createRand(slug);
  const statusRoll = rand();
  const status: SeriesStatus = statusRoll < 0.68 ? "ongoing" : statusRoll < 0.92 ? "completed" : "hiatus";
  const all = rand.int(120_000, 9_800_000);
  const week = Math.round(all * (0.004 + rand() * 0.05));
  const today = Math.round(week * (0.05 + rand() * 0.35));
  const daysAgo = status === "ongoing" ? rand.int(0, 13) : rand.int(40, 400);
  return {
    slug,
    title,
    cover: `/api/cover/${slug}`,
    altTitles: alt ? [alt] : [],
    author,
    type,
    status,
    genres,
    synopsis: `${premise} ${rand.pick(HOOKS)}`,
    rating: Math.round((6.6 + rand() * 3.1) * 10) / 10,
    views: { today, week, all },
    year: rand.int(2015, 2026),
    chapterCount: rand.int(8, 96),
    updatedAt: new Date(BASE_TIME - daysAgo * DAY).toISOString(),
  };
}

export const DEMO_SERIES: Series[] = SEEDS.map(build);

const BY_SLUG = new Map(DEMO_SERIES.map((s) => [s.slug, s]));

export function findSeries(slug: string): Series | undefined {
  return BY_SLUG.get(slug);
}

/** Strips (manhwa, manhua) use a few tall pages, manga uses many book pages. */
export function pageCountFor(series: Series, chapter: number): number {
  const rand = createRand(`${series.slug}/${chapter}/count`);
  return series.type === "manga" ? rand.int(14, 20) : rand.int(7, 11);
}

export function pageSizeFor(series: Series): { width: number; height: number } {
  return series.type === "manga" ? { width: 800, height: 1200 } : { width: 800, height: 1800 };
}

export function buildChapters(series: Series): Chapter[] {
  const rand = createRand(`${series.slug}/chapters`);
  const last = new Date(series.updatedAt).getTime();
  const chapters: Chapter[] = [];
  for (let n = 1; n <= series.chapterCount; n++) {
    chapters.push({
      number: n,
      title: rand.pick(CHAPTER_WORDS),
      publishedAt: new Date(last - (series.chapterCount - n) * 7 * DAY).toISOString(),
      pageCount: pageCountFor(series, n),
    });
  }
  return chapters;
}
