/**
 * request-counter.ts
 *
 * In-memory per-IP request counter used for rate-limiting.
 * The store maps IP → { count, resetAt } where resetAt is the
 * Unix epoch (ms) at which the window expires.
 */

interface BucketEntry {
  count: number;
  resetAt: number;
}

const WINDOW_MS = 60_000; // 1-minute sliding window
const MAX_REQUESTS = 100;

// Global in-memory store — intentionally process-scoped (single Node.js instance).
const store = new Map<string, BucketEntry>();

/** Return current epoch in ms.  Wrapping makes unit-testing straightforward. */
function now(): number {
  return Date.now();
}

/**
 * Purge expired buckets to keep memory bounded.
 * Called synchronously — no yield point, so it is safe to run between
 * any two async operations without a race.
 */
function evictExpired(): void {
  const t = now();
  for (const [ip, entry] of store) {
    if (entry.resetAt <= t) {
      store.delete(ip);
    }
  }
}

/**
 * Look up the current count for an IP.
 * Returns 0 for unknown or expired IPs.
 *
 * NOTE: this is a benign synchronous read — no await between the
 * Map.get() and its return, so there is no race window here even
 * when called from async callers.
 */
export function getCount(ip: string): number {
  const entry = store.get(ip);
  if (!entry || entry.resetAt <= now()) {
    return 0;
  }
  return entry.count;
}

/**
 * Increment the request counter for an IP and check the limit.
 * Returns true when the request is allowed; false when the IP is
 * over the limit.
 *
 * All mutations happen synchronously — no await, so two concurrent
 * calls cannot interleave between the read and the write.
 */
export function incrementAndCheck(ip: string): boolean {
  evictExpired();

  const t = now();
  const entry = store.get(ip);

  if (!entry || entry.resetAt <= t) {
    // Fresh bucket for this IP.
    store.set(ip, { count: 1, resetAt: t + WINDOW_MS });
    return true;
  }

  if (entry.count >= MAX_REQUESTS) {
    return false; // limit already hit
  }

  entry.count += 1;
  return true;
}

/**
 * Reset the counter for an IP (used after a successful auth challenge).
 * Synchronous — safe to call from any context.
 */
export function resetCounter(ip: string): void {
  store.delete(ip);
}
