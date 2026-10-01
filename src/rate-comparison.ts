export type ComparableRate = {
  id: string;
  otaId: string;
  stayDate: string;
  observedAt: string;
  total: number;
  nights: number;
  roomType: string;
  unitId?: string;
  guests: number;
  board: string;
  refund: string;
  audience: string;
  taxes: string;
  sourceUrl: string;
};

export type RateComparisonRow<T extends ComparableRate> = {
  quote: T;
  nightly: number;
  booking: T | null;
  bookingNightly: number | null;
  deltaPct: number | null;
};

const normalized = (value: string | undefined) => (value || "").trim().toLocaleLowerCase("it-IT");

/** Confronta solo la stessa unità fisica e condizioni dichiarate, non nomi simili. */
export function buildRateComparisonRows<T extends ComparableRate>(quotes: T[], today: string): RateComparisonRow<T>[] {
  const latest = new Map<string, T>();
  for (const quote of quotes) {
    if (!/^\d{4}-\d{2}-\d{2}$/.test(quote.stayDate) || quote.stayDate < today ||
        !Number.isFinite(quote.total) || quote.total <= 0 || !Number.isInteger(quote.nights) || quote.nights < 1) continue;
    const key = [quote.otaId, quote.stayDate, normalized(quote.unitId) || `non-verificata:${quote.id}`,
      quote.guests, quote.nights, normalized(quote.board), normalized(quote.refund),
      normalized(quote.audience), normalized(quote.taxes)].join("|");
    const previous = latest.get(key);
    if (!previous || previous.observedAt < quote.observedAt) latest.set(key, quote);
  }
  const values = [...latest.values()];
  return values.map((quote) => {
    const unit = normalized(quote.unitId);
    const booking = unit ? values.find((other) => other.otaId === "booking" &&
      normalized(other.unitId) === unit && other.stayDate === quote.stayDate &&
      other.observedAt.slice(0, 10) === quote.observedAt.slice(0, 10) &&
      other.guests === quote.guests && other.nights === quote.nights &&
      normalized(other.board) === normalized(quote.board) &&
      normalized(other.refund) === normalized(quote.refund) &&
      normalized(other.audience) === normalized(quote.audience) &&
      normalized(other.taxes) === normalized(quote.taxes)) || null : null;
    const nightly = quote.total / quote.nights;
    const bookingNightly = booking ? booking.total / booking.nights : null;
    return {
      quote, nightly, booking, bookingNightly,
      deltaPct: bookingNightly === null ? null : 100 * (nightly - bookingNightly) / bookingNightly,
    };
  }).sort((a, b) => a.quote.stayDate.localeCompare(b.quote.stayDate) ||
    normalized(a.quote.unitId).localeCompare(normalized(b.quote.unitId)) || a.quote.otaId.localeCompare(b.quote.otaId));
}
