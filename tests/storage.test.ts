import { describe, expect, it, vi } from "vitest";
import { createStore } from "@/lib/storage";

function fakeStorage() {
  const data = new Map<string, string>();
  return {
    data,
    getItem: (k: string) => data.get(k) ?? null,
    setItem: (k: string, v: string) => void data.set(k, v),
    removeItem: (k: string) => void data.delete(k),
  };
}

describe("store", () => {
  it("round trips values and notifies subscribers", () => {
    const storage = fakeStorage();
    const s = createStore(() => storage);
    const listener = vi.fn();
    const off = s.subscribe(listener);
    s.write("k", { a: 1 });
    expect(s.read("k", null)).toEqual({ a: 1 });
    expect(storage.data.get("k")).toBe('{"a":1}');
    expect(listener).toHaveBeenCalledTimes(1);
    off();
    s.write("k", { a: 2 });
    expect(listener).toHaveBeenCalledTimes(1);
  });
  it("returns the same reference until the value changes", () => {
    const s = createStore(() => fakeStorage());
    const fallback: string[] = [];
    expect(s.read("list", fallback)).toBe(fallback);
    s.write("list", ["x"]);
    expect(s.read("list", fallback)).toBe(s.read("list", fallback));
  });
  it("falls back on corrupt data", () => {
    const storage = fakeStorage();
    storage.data.set("k", "{not json");
    expect(createStore(() => storage).read("k", 7)).toBe(7);
  });
  it("keeps working in memory when storage throws", () => {
    const s = createStore(() => ({
      getItem: () => { throw new Error("blocked"); },
      setItem: () => { throw new Error("blocked"); },
      removeItem: () => { throw new Error("blocked"); },
    }));
    expect(s.read("k", "fallback")).toBe("fallback");
    s.write("k", "value");
    expect(s.read("k", "fallback")).toBe("value");
    s.remove("k");
    expect(s.read("k", "fallback")).toBe("fallback");
  });
  it("works with no storage at all", () => {
    const s = createStore(() => null);
    s.write("k", 1);
    expect(s.read("k", 0)).toBe(1);
  });
});
