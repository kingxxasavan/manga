/**
 * Typed wrapper around localStorage. Reads and writes never throw: when
 * storage is blocked (private mode, quota) values live in memory for the
 * session instead.
 */

export const KEYS = {
  settings: "inkwell:reader-settings",
  progress: "inkwell:progress",
  read: "inkwell:read-chapters",
  bookmarks: "inkwell:bookmarks",
  theme: "inkwell:theme",
} as const;

export interface Progress {
  chapter: number;
  page: number;
  total: number;
  updatedAt: number;
}
export type ProgressMap = Record<string, Progress>;
export type ReadMap = Record<string, number[]>;

type StorageLike = Pick<Storage, "getItem" | "setItem" | "removeItem">;

export interface Store {
  read<T>(key: string, fallback: T): T;
  write<T>(key: string, value: T): void;
  remove(key: string): void;
  subscribe(listener: () => void): () => void;
}

export function createStore(getStorage: () => StorageLike | null): Store {
  const memory = new Map<string, string>();
  const cache = new Map<string, { raw: string | null; value: unknown }>();
  const listeners = new Set<() => void>();

  const rawGet = (key: string): string | null => {
    if (memory.has(key)) return memory.get(key)!;
    try {
      return getStorage()?.getItem(key) ?? null;
    } catch {
      return null;
    }
  };
  const notify = () => listeners.forEach((l) => l());

  return {
    read<T>(key: string, fallback: T): T {
      const raw = rawGet(key);
      if (raw === null) return fallback;
      const hit = cache.get(key);
      if (hit && hit.raw === raw) return hit.value as T;
      let value: T;
      try {
        value = JSON.parse(raw) as T;
      } catch {
        return fallback;
      }
      if (value === null || value === undefined) return fallback;
      cache.set(key, { raw, value });
      return value;
    },
    write<T>(key: string, value: T) {
      const raw = JSON.stringify(value);
      try {
        const storage = getStorage();
        if (!storage) throw new Error("no storage");
        storage.setItem(key, raw);
        memory.delete(key);
      } catch {
        memory.set(key, raw);
      }
      notify();
    },
    remove(key: string) {
      memory.delete(key);
      cache.delete(key);
      try {
        getStorage()?.removeItem(key);
      } catch {
        // nothing to remove
      }
      notify();
    },
    subscribe(listener: () => void) {
      listeners.add(listener);
      return () => {
        listeners.delete(listener);
      };
    },
  };
}

export const store = createStore(() => (typeof window === "undefined" ? null : window.localStorage));
