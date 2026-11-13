import { createHash, createHmac, timingSafeEqual } from "node:crypto";

/**
 * Owner login. One password from the ADMIN_PASSWORD environment variable.
 * A successful login sets a signed cookie holding only an expiry time; the
 * signature key is derived from the password, so changing the password logs
 * every session out.
 */

export const ADMIN_COOKIE = "craftline_admin";
export const SESSION_SECONDS = 60 * 60 * 24 * 7;
export const MIN_PASSWORD_LENGTH = 12;

const sha256 = (text: string) => createHash("sha256").update(text).digest();

export function adminPassword(): string | null {
  const password = process.env.ADMIN_PASSWORD ?? "";
  return password.length >= MIN_PASSWORD_LENGTH ? password : null;
}

/** Constant time comparison, so response timing says nothing about the password. */
export function passwordMatches(input: unknown, actual: string): boolean {
  if (typeof input !== "string") return false;
  return timingSafeEqual(sha256(input), sha256(actual));
}

const sign = (password: string, expires: number) =>
  createHmac("sha256", sha256(`admin-session:${password}`)).update(String(expires)).digest("base64url");

export function createSessionToken(password: string, nowMs: number): string {
  const expires = Math.floor(nowMs / 1000) + SESSION_SECONDS;
  return `${expires}.${sign(password, expires)}`;
}

export function isValidSessionToken(password: string, token: unknown, nowMs: number): boolean {
  if (typeof token !== "string") return false;
  const [expiresText, signature, ...rest] = token.split(".");
  if (rest.length > 0 || !signature || !/^\d{1,12}$/.test(expiresText)) return false;
  const expires = Number(expiresText);
  if (expires * 1000 <= nowMs) return false;
  const expected = Buffer.from(sign(password, expires));
  const given = Buffer.from(signature);
  return expected.length === given.length && timingSafeEqual(expected, given);
}
