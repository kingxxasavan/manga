import "server-only";

/**
 * Tiny Postgres layer.
 *
 * With DATABASE_URL set (production) it talks to that Postgres database.
 * Without it, in development and tests only, it runs PGlite, a real Postgres
 * engine inside Node, so the exact same SQL is exercised with nothing to install.
 * Production never falls back to PGlite: orders would vanish on every restart.
 */

export class DatabaseNotConfigured extends Error {
  constructor() {
    super("DATABASE_URL is not set. Add a Postgres database to the project.");
    this.name = "DatabaseNotConfigured";
  }
}

type Runner = (sql: string, params: unknown[]) => Promise<Record<string, unknown>[]>;

const SCHEMA = `
CREATE TABLE IF NOT EXISTS orders (
  id                    text PRIMARY KEY,
  created_at            timestamptz NOT NULL DEFAULT now(),
  updated_at            timestamptz NOT NULL DEFAULT now(),
  service_id            text NOT NULL,
  service_name          text NOT NULL,
  email                 text NOT NULL,
  name                  text NOT NULL,
  answers               jsonb NOT NULL,
  lines                 jsonb NOT NULL,
  amount_cents          integer,
  status                text NOT NULL,
  paid_at               timestamptz,
  stripe_session_id     text,
  stripe_payment_intent text,
  customer_note         text,
  delivery_url          text,
  payment_alert         text
);
CREATE INDEX IF NOT EXISTS orders_created_at ON orders (created_at DESC);
ALTER TABLE orders ADD COLUMN IF NOT EXISTS estimate_low_cents integer;
ALTER TABLE orders ADD COLUMN IF NOT EXISTS estimate_high_cents integer;
`;

interface Holder {
  runner?: Promise<Runner>;
}
// Kept on globalThis so dev hot reloads reuse one connection instead of opening many.
const holder = globalThis as unknown as { __craftlineDb?: Holder };
holder.__craftlineDb ??= {};

async function connect(): Promise<Runner> {
  const url = process.env.DATABASE_URL ?? process.env.POSTGRES_URL;
  let run: Runner;
  if (url) {
    const { Pool } = await import("pg");
    const pool = new Pool({ connectionString: url, max: 3 });
    run = async (sql, params) => (await pool.query(sql, params)).rows;
  } else {
    if (process.env.NODE_ENV === "production" && process.env.ALLOW_LOCAL_DB !== "1") throw new DatabaseNotConfigured();
    const { PGlite } = await import("@electric-sql/pglite");
    const dir = process.env.PGLITE_DIR ?? (process.env.NODE_ENV === "test" ? undefined : ".data/pglite");
    const db = new PGlite(dir);
    run = async (sql, params) => (await db.query(sql, params)).rows as Record<string, unknown>[];
    await db.exec(SCHEMA);
    return run;
  }
  for (const statement of SCHEMA.split(";").map((s) => s.trim()).filter(Boolean)) await run(statement, []);
  return run;
}

export async function query(sql: string, params: unknown[] = []): Promise<Record<string, unknown>[]> {
  const state = holder.__craftlineDb!;
  state.runner ??= connect().catch((error) => {
    state.runner = undefined; // let the next request try again
    throw error;
  });
  return (await state.runner)(sql, params);
}
