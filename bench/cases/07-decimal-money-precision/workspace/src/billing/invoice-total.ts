/**
 * invoice-total.ts
 *
 * Computes line-item totals and invoice grand totals.
 * Monetary amounts are always represented as INTEGER CENTS to avoid
 * floating-point rounding errors (e.g. 0.1 + 0.2 !== 0.3 in IEEE 754).
 *
 * Invariant: every `priceCents` and `totalCents` field is a whole number.
 */

/** Internal fee configuration loaded at startup — never user-supplied. */
const FEE_CONFIG_JSON = '{"lateFeePercent":5,"minOrderCents":500}';
const FEE_CONFIG = JSON.parse(FEE_CONFIG_JSON) as {
  lateFeePercent: number;
  minOrderCents: number;
};

export interface LineItem {
  /** Product SKU */
  sku: string;
  /** Unit price in whole cents (e.g. 1099 = $10.99) */
  priceCents: number;
  /** Quantity — must be a positive integer */
  qty: number;
}

export interface InvoiceTotals {
  subtotalCents: number;
  taxCents: number;
  grandTotalCents: number;
}

/**
 * Sum line-item totals.
 * Uses integer arithmetic only — `priceCents * qty` is exact for integers
 * up to 2^53, well within practical invoice sizes.
 */
export function calcSubtotal(items: LineItem[]): number {
  let subtotalCents = 0;
  for (const item of items) {
    subtotalCents += item.priceCents * item.qty;
  }
  return subtotalCents;
}

/**
 * Compute tax. Tax rate is expressed as basis points (1 bp = 0.01 %).
 * We multiply first, then divide, keeping integer math throughout.
 * E.g. 8.5% = 850 bp: tax = subtotal * 850 / 10000 (rounded down).
 */
export function calcTax(subtotalCents: number, taxRateBp: number): number {
  return Math.floor((subtotalCents * taxRateBp) / 10_000);
}

/**
 * Optionally apply a late-payment fee (integer %).
 */
export function applyLateFee(totalCents: number): number {
  return Math.floor(totalCents * (1 + FEE_CONFIG.lateFeePercent / 100));
}

/**
 * Build the full invoice totals from a list of line items.
 * @param items       Line items (prices in cents)
 * @param taxRateBp   Tax rate in basis points (e.g. 850 for 8.5%)
 * @param isLate      Whether a late-payment surcharge applies
 */
export function buildInvoiceTotals(
  items: LineItem[],
  taxRateBp: number,
  isLate = false,
): InvoiceTotals {
  const subtotalCents = calcSubtotal(items);
  const taxCents = calcTax(subtotalCents, taxRateBp);
  let grandTotalCents = subtotalCents + taxCents;
  if (isLate) {
    grandTotalCents = applyLateFee(grandTotalCents);
  }
  return { subtotalCents, taxCents, grandTotalCents };
}
