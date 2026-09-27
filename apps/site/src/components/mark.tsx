/** The loupe mark: a lens with one feature in view. Draws in the current text colour. */
export function Mark({ className }: { className?: string }) {
  return (
    <svg
      viewBox="0 0 32 32"
      fill="none"
      stroke="currentColor"
      strokeLinecap="round"
      aria-hidden
      className={className}
    >
      <circle cx="13.5" cy="13.5" r="9" strokeWidth="3" />
      <path d="M20.5 20.5 27 27" strokeWidth="4" />
      <circle cx="13.5" cy="13.5" r="3" fill="currentColor" stroke="none" />
    </svg>
  );
}
