/** Small deterministic PRNG so demo content is identical on every render. */
export function hash(text: string): number {
  let h = 2166136261;
  for (let i = 0; i < text.length; i++) {
    h ^= text.charCodeAt(i);
    h = Math.imul(h, 16777619);
  }
  return h >>> 0;
}

export interface Rand {
  (): number;
  int(min: number, max: number): number;
  pick<T>(items: readonly T[]): T;
}

export function createRand(seed: string): Rand {
  let a = hash(seed) || 1;
  const next = () => {
    a = (a + 0x6d2b79f5) | 0;
    let t = Math.imul(a ^ (a >>> 15), 1 | a);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
  const rand = next as Rand;
  rand.int = (min, max) => min + Math.floor(next() * (max - min + 1));
  rand.pick = (items) => items[Math.floor(next() * items.length)];
  return rand;
}
