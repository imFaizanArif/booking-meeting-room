/**
 * Lightweight inline SVG illustrations in the unDraw / Storyset flat style,
 * tinted with the Kodifly palette via CSS variables.
 */

export function MeetingIllustration({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 400 300" fill="none" className={className} aria-hidden="true">
      <ellipse cx="200" cy="262" rx="160" ry="18" fill="currentColor" opacity="0.06" />
      <rect x="70" y="80" width="260" height="150" rx="20" fill="currentColor" opacity="0.08" />
      <rect x="90" y="100" width="220" height="110" rx="12" fill="var(--primary)" opacity="0.14" />
      <rect x="105" y="115" width="90" height="10" rx="5" fill="var(--primary)" opacity="0.6" />
      <rect x="105" y="135" width="140" height="8" rx="4" fill="currentColor" opacity="0.25" />
      <rect x="105" y="151" width="120" height="8" rx="4" fill="currentColor" opacity="0.18" />
      <circle cx="278" cy="140" r="24" fill="var(--accent)" opacity="0.85" />
      <path
        d="M270 140l6 6 12-12"
        stroke="white"
        strokeWidth="4"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
      <circle cx="135" cy="245" r="16" fill="var(--primary)" />
      <rect x="123" y="225" width="24" height="14" rx="7" fill="var(--primary)" opacity="0.7" />
      <circle cx="200" cy="245" r="16" fill="var(--accent)" />
      <rect x="188" y="225" width="24" height="14" rx="7" fill="var(--accent)" opacity="0.7" />
      <circle cx="265" cy="245" r="16" fill="var(--secondary)" opacity="0.8" />
      <rect x="253" y="225" width="24" height="14" rx="7" fill="var(--secondary)" opacity="0.5" />
      <rect x="160" y="40" width="80" height="26" rx="13" fill="var(--primary)" />
      <circle cx="176" cy="53" r="5" fill="white" opacity="0.9" />
      <rect x="188" y="49" width="40" height="8" rx="4" fill="white" opacity="0.8" />
    </svg>
  );
}

export function EmptyStateIllustration({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 300 220" fill="none" className={className} aria-hidden="true">
      <ellipse cx="150" cy="196" rx="110" ry="12" fill="currentColor" opacity="0.06" />
      <rect x="75" y="40" width="150" height="130" rx="18" fill="currentColor" opacity="0.07" />
      <rect x="92" y="58" width="116" height="14" rx="7" fill="var(--primary)" opacity="0.3" />
      <rect x="92" y="84" width="86" height="10" rx="5" fill="currentColor" opacity="0.18" />
      <rect x="92" y="104" width="100" height="10" rx="5" fill="currentColor" opacity="0.12" />
      <circle cx="150" cy="146" r="17" fill="var(--accent)" opacity="0.2" />
      <path
        d="M150 138v10m0 0v0m-5-5h10"
        stroke="var(--accent)"
        strokeWidth="3.5"
        strokeLinecap="round"
      />
      <circle cx="226" cy="48" r="11" fill="var(--accent)" opacity="0.45" />
      <circle cx="71" cy="150" r="8" fill="var(--primary)" opacity="0.35" />
    </svg>
  );
}

export function AuthIllustration({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 400 400" fill="none" className={className} aria-hidden="true">
      <circle cx="200" cy="200" r="160" fill="white" opacity="0.06" />
      <circle cx="200" cy="200" r="120" fill="white" opacity="0.07" />
      <rect x="120" y="110" width="160" height="200" rx="24" fill="white" opacity="0.12" />
      <rect x="140" y="140" width="120" height="12" rx="6" fill="white" opacity="0.65" />
      <rect x="140" y="168" width="80" height="10" rx="5" fill="white" opacity="0.4" />
      <rect x="140" y="200" width="120" height="34" rx="12" fill="white" opacity="0.22" />
      <rect x="140" y="244" width="120" height="34" rx="12" fill="white" opacity="0.22" />
      <circle cx="200" cy="80" r="26" fill="var(--accent)" />
      <path
        d="M190 80l7 7 14-14"
        stroke="white"
        strokeWidth="4.5"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
      <circle cx="310" cy="150" r="10" fill="var(--accent)" opacity="0.8" />
      <circle cx="92" cy="260" r="14" fill="white" opacity="0.18" />
      <circle cx="320" cy="290" r="8" fill="white" opacity="0.25" />
    </svg>
  );
}
