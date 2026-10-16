/** Shared presentation helpers.
 *
 * The four clinical BAND colours are the only semantic colour scale in the
 * console, so every band-bearing string is mapped through here and anything
 * unrecognised (including NOT_ENOUGH_DATA) falls back to the neutral badge.
 */

const BANDS = ["GREEN", "YELLOW", "ORANGE", "RED"] as const;

/** Badge classes for a band value: "GREEN" and "band_GREEN" both work. */
export function bandClass(value: string): string {
  const upper = value.toUpperCase();
  const band = BANDS.find((candidate) => upper.includes(candidate));
  return band ? `badge badge-${band.toLowerCase()}` : "badge badge-neutral";
}
