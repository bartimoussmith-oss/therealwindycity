import { shapeFor } from '../music/chordShapes';

interface Props {
  root: number;
  type: string;
  drop?: boolean;
  size?: number;
  label?: string;
}

/** SVG guitar chord box: six strings, five frets, dots, barre, x/o markers. */
export function ChordDiagram({ root, type, drop = false, size = 96, label }: Props) {
  const shape = shapeFor(root, type, drop);
  if (!shape) return null;
  const w = 100, h = 120;
  const left = 18, right = 92, top = 26, bottom = 110;
  const strings = 6, frets = 5;
  const sx = (i: number) => left + ((right - left) * i) / (strings - 1);
  const fy = (f: number) => top + ((bottom - top) * f) / frets;
  const rel = (f: number) => f - shape.baseFret + 1; // 1-based row
  return (
    <svg className="chord-diagram" viewBox={`0 0 ${w} ${h}`} width={size} height={(size * h) / w} role="img" aria-label={label ? `${label} chord diagram` : 'chord diagram'}>
      {shape.baseFret === 1 ? (
        <rect x={left - 1} y={top - 3} width={right - left + 2} height={4} className="nut" />
      ) : (
        <text x={left - 6} y={fy(0.62)} className="basefret" textAnchor="end">{shape.baseFret}</text>
      )}
      {Array.from({ length: frets + 1 }, (_, f) => (
        <line key={`f${f}`} x1={left} x2={right} y1={fy(f)} y2={fy(f)} className="fret" />
      ))}
      {Array.from({ length: strings }, (_, i) => (
        <line key={`s${i}`} x1={sx(i)} x2={sx(i)} y1={top} y2={bottom} className="string" />
      ))}
      {shape.barre && (
        <rect
          x={sx(shape.barre.from) - 5}
          y={fy(rel(shape.barre.fret) - 0.5) - 5}
          width={sx(shape.barre.to) - sx(shape.barre.from) + 10}
          height={10}
          rx={5}
          className="dot"
        />
      )}
      {shape.frets.map((f, i) => {
        if (f < 0) return <text key={i} x={sx(i)} y={top - 8} className="mark" textAnchor="middle">×</text>;
        if (f === 0) return <circle key={i} cx={sx(i)} cy={top - 11} r={3.6} className="open" />;
        if (shape.barre && f === shape.barre.fret && i >= shape.barre.from && i <= shape.barre.to) return null;
        return <circle key={i} cx={sx(i)} cy={fy(rel(f) - 0.5)} r={5.4} className="dot" />;
      })}
    </svg>
  );
}
