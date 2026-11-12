"use client";

import { useCallback, useSyncExternalStore } from "react";
import { store } from "./storage";

function subscribe(listener: () => void) {
  const off = store.subscribe(listener);
  window.addEventListener("storage", listener);
  return () => {
    off();
    window.removeEventListener("storage", listener);
  };
}

/**
 * Reads a stored value and re-renders when it changes. `fallback` must be a
 * stable reference (a module constant) because it is also the server value.
 */
export function useStored<T>(key: string, fallback: T): [T, (value: T) => void] {
  const value = useSyncExternalStore(
    subscribe,
    () => store.read(key, fallback),
    () => fallback,
  );
  const set = useCallback((next: T) => store.write(key, next), [key]);
  return [value, set];
}

const noop = () => () => {};

/** false on the server and during hydration, true afterwards. */
export function useHydrated(): boolean {
  return useSyncExternalStore(noop, () => true, () => false);
}
