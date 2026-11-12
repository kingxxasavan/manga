"use client";

import { KEYS, store } from "@/lib/storage";
import { MoonIcon, SunIcon } from "./icons";

export function ThemeToggle() {
  const toggle = () => {
    const next = document.documentElement.dataset.theme === "light" ? "dark" : "light";
    document.documentElement.dataset.theme = next;
    store.write(KEYS.theme, next);
  };
  // Both icons render and CSS picks one, so there is nothing to mismatch on hydration.
  return (
    <button
      type="button" onClick={toggle} aria-label="Switch between light and dark theme"
      className="grid size-10 place-items-center rounded-full text-muted transition hover:bg-surface-2 hover:text-text"
    >
      <SunIcon className="hidden [[data-theme=dark]_&]:block" />
      <MoonIcon className="hidden [[data-theme=light]_&]:block" />
    </button>
  );
}
