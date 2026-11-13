"use client";

import { Moon, Sun } from "./icons";

export const THEME_KEY = "craftline:theme";

export function ThemeToggle() {
  const toggle = () => {
    const next = document.documentElement.dataset.theme === "dark" ? "light" : "dark";
    document.documentElement.dataset.theme = next;
    try {
      localStorage.setItem(THEME_KEY, next);
    } catch {
      // storage blocked: the choice just lasts for this page
    }
  };
  // Both icons render and CSS shows one, so server and browser markup always match.
  return (
    <button type="button" onClick={toggle} aria-label="Switch between light and dark theme" className="grid size-10 place-items-center rounded-full text-muted transition hover:bg-surface-2 hover:text-text">
      <Sun className="hidden [[data-theme=dark]_&]:block" />
      <Moon className="[[data-theme=dark]_&]:hidden" />
    </button>
  );
}
