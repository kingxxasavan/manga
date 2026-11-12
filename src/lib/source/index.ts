import { demoSource } from "./demo";
import type { Source } from "./types";

/** The active content source. Swap this one line to change where content comes from. */
export const source: Source = demoSource;

export type { Source } from "./types";
export { GENRES } from "./demo-data";
