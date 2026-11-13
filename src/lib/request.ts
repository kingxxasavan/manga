import "server-only";
import { headers } from "next/headers";

/** Public address of the site, used for the links Stripe sends people back to. */
export async function getBaseUrl(): Promise<string> {
  const fixed = process.env.SITE_URL;
  if (fixed && /^https?:\/\/[^/\s]+$/.test(fixed)) return fixed;
  const h = await headers();
  const host = h.get("x-forwarded-host") ?? h.get("host") ?? "localhost:3000";
  const local = host.startsWith("localhost") || host.startsWith("127.0.0.1");
  const proto = h.get("x-forwarded-proto")?.split(",")[0] ?? (local ? "http" : "https");
  return `${proto}://${host}`;
}

export async function getClientIp(): Promise<string> {
  const h = await headers();
  return h.get("x-forwarded-for")?.split(",")[0]?.trim() || h.get("x-real-ip") || "unknown";
}

/**
 * Best effort limiter kept in memory. On serverless hosting each instance has
 * its own memory, so this slows abuse down rather than stopping it outright.
 */
const hits = new Map<string, number[]>();
export function allow(key: string, limit: number, windowMs: number, now = Date.now()): boolean {
  const recent = (hits.get(key) ?? []).filter((t) => now - t < windowMs);
  if (recent.length >= limit) {
    hits.set(key, recent);
    return false;
  }
  recent.push(now);
  hits.set(key, recent);
  if (hits.size > 5000) for (const k of hits.keys()) if (hits.size > 2500) hits.delete(k);
  return true;
}
