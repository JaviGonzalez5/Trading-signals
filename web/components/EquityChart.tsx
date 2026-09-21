import type { EquityPoint } from "@/lib/stats";

const WIDTH = 900;
const HEIGHT = 220;
const PAD = 32;

export default function EquityChart({ points }: { points: EquityPoint[] }) {
  if (points.length < 2) {
    return <p className="empty-state">Hacen falta al menos 2 señales resueltas para dibujar la curva.</p>;
  }

  const values = [0, ...points.map((p) => p.cum)];
  const min = Math.min(...values);
  const max = Math.max(...values);
  const range = max - min || 1;

  const innerW = WIDTH - PAD * 2;
  const innerH = HEIGHT - PAD * 2;

  const xFor = (i: number) => PAD + (i / (points.length - 1)) * innerW;
  const yFor = (v: number) => PAD + innerH - ((v - min) / range) * innerH;

  const linePath = points.map((p, i) => `${i === 0 ? "M" : "L"} ${xFor(i)} ${yFor(p.cum)}`).join(" ");
  const zeroY = yFor(0);
  const areaPath = `${linePath} L ${xFor(points.length - 1)} ${zeroY} L ${xFor(0)} ${zeroY} Z`;

  const last = points[points.length - 1].cum;
  const lineColor = last >= 0 ? "#3fb950" : "#f85149";

  return (
    <svg viewBox={`0 0 ${WIDTH} ${HEIGHT}`} width="100%" height={HEIGHT} role="img" aria-label="Curva de rentabilidad acumulada">
      <line x1={PAD} y1={zeroY} x2={WIDTH - PAD} y2={zeroY} stroke="#232e3a" strokeDasharray="4 4" />
      <path d={areaPath} fill={lineColor} fillOpacity={0.12} stroke="none" />
      <path d={linePath} fill="none" stroke={lineColor} strokeWidth={2} />
      {points.map((p, i) => (
        <circle key={i} cx={xFor(i)} cy={yFor(p.cum)} r={3} fill={lineColor} />
      ))}
      <text x={PAD} y={16} fill="#8b98a5" fontSize={11}>
        {max.toFixed(1)}%
      </text>
      <text x={PAD} y={HEIGHT - 8} fill="#8b98a5" fontSize={11}>
        {min.toFixed(1)}%
      </text>
    </svg>
  );
}
