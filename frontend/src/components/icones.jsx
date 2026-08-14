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
