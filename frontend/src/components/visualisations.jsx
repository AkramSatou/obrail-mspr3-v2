import { useId } from "react";

export function GraphiqueAires({ points, couleur = "#6366f1", hauteur = 64, label = "" }) {
  const uid = useId();
  const gId = `ag-${uid.replace(/:/g, "")}`;

  if (!points || points.length < 2) return null;
  const max = Math.max(...points.map((p) => p.valeur), 1);
  const W = 300;
  const H = hauteur;
  const pad = 4;
  const pts = points.map((p, i) => ({
    x: pad + (i / (points.length - 1)) * (W - pad * 2),
    y: pad + (1 - p.valeur / max) * (H - pad * 2 - 4),
  }));

  /* Courbe Bézier cubique lisse entre chaque paire de points */
  function smooth(pts) {
    let d = `M ${pts[0].x},${pts[0].y}`;
    for (let i = 1; i < pts.length; i++) {
      const p0 = pts[i - 1];
      const p1 = pts[i];
      const cpx = (p0.x + p1.x) / 2;
      d += ` C ${cpx},${p0.y} ${cpx},${p1.y} ${p1.x},${p1.y}`;
    }
    return d;
  }

  const curve = smooth(pts);
  const last = pts[pts.length - 1];
  const area = `${curve} L${last.x},${H - pad} L${pts[0].x},${H - pad} Z`;

  return (
    <svg
      width="100%"
      height={H}
      viewBox={`0 0 ${W} ${H}`}
      preserveAspectRatio="none"
      role="img"
      aria-label={label}
      style={{ display: "block" }}
    >
      <defs>
        <linearGradient id={gId} x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor={couleur} stopOpacity="0.35" />
          <stop offset="100%" stopColor={couleur} stopOpacity="0" />
        </linearGradient>
      </defs>
      <path d={area} fill={`url(#${gId})`} />
      <path
        d={curve}
        fill="none"
        stroke={couleur}
        strokeWidth="2.5"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}

export function AnneauProgression({ valeur, max = 100, label, couleur = "#6366f1", taille = 100 }) {
  const rayon = (taille - 16) / 2;
  const C = 2 * Math.PI * rayon;
  const progres = Math.min(Math.max(valeur / max, 0), 1);
  const offset = C * (1 - progres);
  const pct = Math.round(progres * 100);

  return (
    <div className="anneau-wrapper" aria-label={`${label} : ${pct}%`}>
      <svg
        width={taille}
        height={taille}
        viewBox={`0 0 ${taille} ${taille}`}
        role="img"
        aria-label={`${label} : ${pct}%`}
      >
        <circle
          cx={taille / 2}
          cy={taille / 2}
          r={rayon}
          fill="none"
          stroke="currentColor"
          strokeOpacity="0.12"
          strokeWidth="10"
        />
        <circle
          cx={taille / 2}
          cy={taille / 2}
          r={rayon}
          fill="none"
          stroke={couleur}
          strokeWidth="10"
          strokeLinecap="round"
          strokeDasharray={C}
          strokeDashoffset={offset}
          transform={`rotate(-90 ${taille / 2} ${taille / 2})`}
          style={{ transition: "stroke-dashoffset 0.7s ease" }}
        />
        <text
          x="50%"
          y="50%"
          textAnchor="middle"
          dominantBaseline="central"
          fontSize={taille * 0.19}
          fontWeight="800"
          fill="currentColor"
        >
          {pct}%
        </text>
      </svg>
      <p className="anneau-label">{label}</p>
    </div>
  );
}

export function GrilleActivite({ lignes, colonnes, donnees, couleur = "#6366f1", label = "" }) {
  const max = Math.max(...Object.values(donnees), 1);
  const cell = 20;
  const gap = 4;
  const offsetX = 52;
  const offsetY = 18;
  const W = offsetX + colonnes.length * (cell + gap) - gap;
  const H = offsetY + lignes.length * (cell + gap) - gap;

  return (
    <div className="grille-activite">
      <svg
        width="100%"
        height={H}
        viewBox={`0 0 ${W} ${H}`}
        role="img"
        aria-label={label}
      >
        {colonnes.map((col, ci) => (
          <text
            key={col}
            x={offsetX + ci * (cell + gap) + cell / 2}
            y={offsetY - 6}
            textAnchor="middle"
            fontSize="7"
            fill="currentColor"
            opacity="0.5"
          >
            {col}
          </text>
        ))}
        {lignes.map((ligne, li) => (
          <g key={ligne}>
            <text
              x={offsetX - 6}
              y={offsetY + li * (cell + gap) + cell / 2}
              textAnchor="end"
              fontSize="7.5"
              dominantBaseline="central"
              fill="currentColor"
              opacity="0.5"
            >
              {ligne}
            </text>
            {colonnes.map((col, ci) => {
              const val = donnees[`${ligne}-${col}`] || 0;
              const op = val > 0 ? 0.12 + (val / max) * 0.75 : 0.06;
              return (
                <rect
                  key={col}
                  x={offsetX + ci * (cell + gap)}
                  y={offsetY + li * (cell + gap)}
                  width={cell}
                  height={cell}
                  rx={4}
                  fill={couleur}
                  opacity={op}
                >
                  <title>{`${ligne} / ${col} : ${val}`}</title>
                </rect>
              );
            })}
          </g>
        ))}
      </svg>
    </div>
  );
}
