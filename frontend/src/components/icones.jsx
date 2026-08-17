import React from 'react';

export function IconeTableau({ taille = 20, ...props }) {
  return (
    <svg width={taille} height={taille} viewBox="0 0 24 24" fill="none" aria-hidden="true" {...props}>
      <rect x="3" y="3" width="8" height="8" rx="2" fill="currentColor" opacity="0.9" />
      <rect x="13" y="3" width="8" height="8" rx="2" fill="currentColor" opacity="0.45" />
      <rect x="3" y="13" width="8" height="8" rx="2" fill="currentColor" opacity="0.45" />
      <rect x="13" y="13" width="8" height="8" rx="2" fill="currentColor" opacity="0.9" />
    </svg>
  );
}

export function IconeTrajets({ taille = 20, ...props }) {
  return (
    <svg width={taille} height={taille} viewBox="0 0 24 24" fill="none" aria-hidden="true" {...props}>
      <rect x="2" y="8" width="20" height="10" rx="3" stroke="currentColor" strokeWidth="2" />
      <circle cx="7" cy="19" r="2" fill="currentColor" />
      <circle cx="17" cy="19" r="2" fill="currentColor" />
      <path d="M2 12h20" stroke="currentColor" strokeWidth="1.5" />
      <path d="M8 8V6a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2" stroke="currentColor" strokeWidth="2" />
    </svg>
  );
}

export function IconeAssistant({ taille = 20, ...props }) {
  return (
    <svg width={taille} height={taille} viewBox="0 0 24 24" fill="none" aria-hidden="true" {...props}>
      <path
        d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"
        stroke="currentColor"
        strokeWidth="2"
        strokeLinejoin="round"
      />
      <circle cx="9" cy="11" r="1" fill="currentColor" />
      <circle cx="12" cy="11" r="1" fill="currentColor" />
      <circle cx="15" cy="11" r="1" fill="currentColor" />
    </svg>
  );
}

export function IconeEnvoyer({ taille = 20, ...props }) {
  return (
    <svg width={taille} height={taille} viewBox="0 0 24 24" fill="none" aria-hidden="true" {...props}>
      <path d="M22 2 11 13" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
      <path
        d="M22 2 15 22 11 13 2 9l20-7z"
        stroke="currentColor"
        strokeWidth="2"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}

export function IconeEffacer({ taille = 20, ...props }) {
  return (
    <svg width={taille} height={taille} viewBox="0 0 24 24" fill="none" aria-hidden="true" {...props}>
      <path d="M3 6h18" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
      <path d="M8 6V4h8v2" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
      <rect x="5" y="7" width="14" height="13" rx="2" stroke="currentColor" strokeWidth="2" />
      <path d="M10 11v5M14 11v5" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
    </svg>
  );
}

export function IconeCloseChip({ taille = 14, ...props }) {
  return (
    <svg width={taille} height={taille} viewBox="0 0 14 14" fill="none" aria-hidden="true" {...props}>
      <path d="M10.5 3.5 7 7m0 0L3.5 10.5M7 7l3.5 3.5M7 7 3.5 3.5"
            stroke="currentColor" strokeWidth="1.75" strokeLinecap="round" />
    </svg>
  );
}

export function IconeFiltres({ taille = 20, ...props }) {
  return (
    <svg width={taille} height={taille} viewBox="0 0 24 24" fill="none" aria-hidden="true" {...props}>
      <path d="M3 6h18M7 12h10M11 18h2" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
    </svg>
  );
}

export function IconeDeconnexion({ taille = 20, ...props }) {
  return (
    <svg width={taille} height={taille} viewBox="0 0 24 24" fill="none" aria-hidden="true" {...props}>
      <path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
      <polyline points="16 17 21 12 16 7" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
      <line x1="21" y1="12" x2="9" y2="12" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
    </svg>
  );
}

export function IconeAnalyses({ taille = 20, ...props }) {
  return (
    <svg width={taille} height={taille} viewBox="0 0 24 24" fill="none" aria-hidden="true" {...props}>
      <rect x="2" y="3" width="20" height="14" rx="2" stroke="currentColor" strokeWidth="2"/>
      <path d="M8 21h8M12 17v4" stroke="currentColor" strokeWidth="2" strokeLinecap="round"/>
      <path d="M7 8l3 3-3 3M13 13h4" stroke="currentColor" strokeWidth="1.75" strokeLinecap="round" strokeLinejoin="round"/>
    </svg>
  );
}

export function IconeCadenas({ taille = 20, ...props }) {
  return (
    <svg width={taille} height={taille} viewBox="0 0 24 24" fill="none" aria-hidden="true" {...props}>
      <rect x="5" y="11" width="14" height="10" rx="2" stroke="currentColor" strokeWidth="2" />
      <path d="M8 11V7a4 4 0 0 1 8 0v4" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
      <circle cx="12" cy="16" r="1.5" fill="currentColor" />
    </svg>
  );
}

export function IconeLocalisation({ taille = 20, ...props }) {
  return (
    <svg width={taille} height={taille} viewBox="0 0 24 24" fill="none" aria-hidden="true" {...props}>
      <path d="M12 2C8.686 2 6 4.686 6 8c0 5.25 6 14 6 14s6-8.75 6-14c0-3.314-2.686-6-6-6z"
        stroke="currentColor" strokeWidth="2" strokeLinejoin="round" />
      <circle cx="12" cy="8" r="2" stroke="currentColor" strokeWidth="1.5" />
    </svg>
  );
}

export function IconeTrainElec({ taille = 20, ...props }) {
  return (
    <svg width={taille} height={taille} viewBox="0 0 24 24" fill="none" aria-hidden="true" {...props}>
      <rect x="3" y="5" width="18" height="11" rx="2.5" stroke="currentColor" strokeWidth="1.8"/>
      <path d="M3 12h18M9 5v7m6-7v7" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round"/>
      <circle cx="7.5" cy="20" r="1.5" stroke="currentColor" strokeWidth="1.5"/>
      <circle cx="16.5" cy="20" r="1.5" stroke="currentColor" strokeWidth="1.5"/>
      <path d="M6 16l-1.5 4m15-4l1.5 4" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round"/>
      <path d="M12 1l-1.5 3h3L12 1z" fill="currentColor"/>
    </svg>
  );
}
export function IconeTrainDiesel({ taille = 20, ...props }) {
  return (
    <svg width={taille} height={taille} viewBox="0 0 24 24" fill="none" aria-hidden="true" {...props}>
      <rect x="3" y="5" width="18" height="11" rx="2.5" stroke="currentColor" strokeWidth="1.8"/>
      <path d="M3 12h18M9 5v7m6-7v7" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round"/>
      <circle cx="7.5" cy="20" r="1.5" stroke="currentColor" strokeWidth="1.5"/>
      <circle cx="16.5" cy="20" r="1.5" stroke="currentColor" strokeWidth="1.5"/>
      <path d="M6 16l-1.5 4m15-4l1.5 4" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round"/>
      <path d="M9 2c1 1.5 3 1.5 3 3" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round"/>
    </svg>
  );
}
export function IconeVoiture({ taille = 20, ...props }) {
  return (
    <svg width={taille} height={taille} viewBox="0 0 24 24" fill="none" aria-hidden="true" {...props}>
      <path d="M5 17H3v-5l2.5-5H18.5L21 12v5h-2" stroke="currentColor" strokeWidth="1.8" strokeLinejoin="round"/>
      <circle cx="7" cy="17" r="2" stroke="currentColor" strokeWidth="1.5"/>
      <circle cx="17" cy="17" r="2" stroke="currentColor" strokeWidth="1.5"/>
      <path d="M5 15h14M7 7l-1.5 5h13L17 7" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round"/>
    </svg>
  );
}
export function IconeAvion({ taille = 20, ...props }) {
  return (
    <svg width={taille} height={taille} viewBox="0 0 24 24" fill="none" aria-hidden="true" {...props}>
      <path d="M22 12L15 5l-1.5 1.5 3 3H10L3 8v2l7 2v4l-2.5 1V19l3-1.5L13 21h2l1-5.5 5 1.5V15l-5-1.5V9.5l3 3L22 12z" stroke="currentColor" strokeWidth="1.5" strokeLinejoin="round"/>
    </svg>
  );
}

export function IconeRail({ taille = 20, ...props }) {
  return (
    <svg width={taille} height={taille} viewBox="0 0 24 24" fill="none" aria-hidden="true" {...props}>
      <rect x="3" y="5" width="18" height="12" rx="2" stroke="currentColor" strokeWidth="2" />
      <path d="M3 10h18" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
      <path d="M7 17l-2 2M17 17l2 2" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
      <path d="M9 5V3M15 5V3" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
    </svg>
  );
}
