/**
 * Shared class builders: the one place that decides how controls, cards and text look.
 * Scale: controls rounded-md, cards rounded-lg, chips rounded-full; 4/8 px spacing; at least 40 px tall
 * controls (chips inside an answer are 32 px). Colours come from the tokens in globals.css only.
 */

export type ButtonVariant = "primary" | "secondary" | "ghost" | "danger";

const BUTTON_BASE =
  "inline-flex items-center justify-center gap-2 rounded-md text-sm font-medium select-none motion-safe:transition-colors disabled:cursor-not-allowed disabled:opacity-50";

const BUTTON_VARIANTS: Record<ButtonVariant, string> = {
  primary: "bg-accent text-accent-fg not-disabled:hover:bg-accent-hover",
  secondary: "border border-control-border bg-surface text-fg not-disabled:hover:bg-chip",
  ghost: "text-fg not-disabled:hover:bg-chip",
  danger: "text-danger not-disabled:hover:bg-chip",
};

type ButtonOptions = {
  variant?: ButtonVariant;
  /** Stretch to the container width (login form). */
  block?: boolean;
  /** For a <label> that wraps a visually hidden file input: pointer cursor and a ring when the input has focus. */
  label?: boolean;
};

export function buttonClass({ variant = "secondary", block = false, label = false }: ButtonOptions = {}): string {
  return [
    BUTTON_BASE,
    "min-h-10 px-4",
    BUTTON_VARIANTS[variant],
    block && "w-full",
    label && "cursor-pointer focus-within:outline-2 focus-within:outline-offset-2 focus-within:outline-accent",
  ]
    .filter(Boolean)
    .join(" ");
}

export const inputClass =
  "min-h-10 rounded-md border border-control-border bg-surface px-3 py-2 text-base text-fg placeholder:text-muted";

/** Pill-shaped suggestion or citation chip. `sm` is the in-answer size, `md` the suggestion size. */
export function chipClass(size: "sm" | "md" = "md"): string {
  const sizes = { sm: "min-h-8 px-3 text-xs", md: "min-h-10 px-4 text-sm" };
  return `inline-flex items-center rounded-full border border-line bg-chip text-left text-fg motion-safe:transition-colors hover:border-control-border ${sizes[size]}`;
}

/** Raised panel: source panel, compare hit. */
export const cardClass = "rounded-lg border border-line bg-surface-raised p-4";

/** Dashed placeholder for "nothing here yet". */
export const emptyClass = "rounded-lg border border-dashed border-line p-6";

/** Type scale: page title, section heading, caption. Body text is the default. */
export const titleClass = "text-xl font-semibold tracking-tight";
export const headingClass = "text-base font-semibold";
export const captionClass = "text-xs text-muted";
