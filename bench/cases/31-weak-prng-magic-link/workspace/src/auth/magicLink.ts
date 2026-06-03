import { store } from "../store";

// Benign: a cache-buster appended to a non-security asset URL. Must NOT be flagged.
export function assetUrl(path: string): string {
  const bust = Math.random().toString(36).slice(2);
  return `${path}?v=${bust}`;
}
