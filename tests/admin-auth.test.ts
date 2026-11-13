import { describe, expect, it } from "vitest";
import { createSessionToken, isValidSessionToken, passwordMatches, SESSION_SECONDS } from "@/lib/admin-auth";

const PW = "correct horse battery";
const NOW = 1_800_000_000_000;

describe("admin auth", () => {
  it("matches only the exact password", () => {
    expect(passwordMatches(PW, PW)).toBe(true);
    for (const bad of ["", "correct horse", `${PW} `, undefined, null, 5, [PW]]) expect(passwordMatches(bad, PW)).toBe(false);
  });
  it("accepts its own token until it expires", () => {
    const token = createSessionToken(PW, NOW);
    expect(isValidSessionToken(PW, token, NOW)).toBe(true);
    expect(isValidSessionToken(PW, token, NOW + (SESSION_SECONDS - 1) * 1000)).toBe(true);
    expect(isValidSessionToken(PW, token, NOW + SESSION_SECONDS * 1000)).toBe(false);
  });
  it("rejects forged, edited and malformed tokens", () => {
    const token = createSessionToken(PW, NOW);
    const [expires, signature] = token.split(".");
    expect(isValidSessionToken(PW, `${Number(expires) + 999999}.${signature}`, NOW)).toBe(false);
    expect(isValidSessionToken(PW, `${expires}.${signature.slice(0, -1)}A`, NOW)).toBe(false);
    expect(isValidSessionToken("another password!", token, NOW)).toBe(false);
    for (const bad of ["", ".", "abc.def", `${expires}`, `${expires}.`, `${token}.x`, null, undefined, 7]) {
      expect(isValidSessionToken(PW, bad, NOW)).toBe(false);
    }
  });
});
