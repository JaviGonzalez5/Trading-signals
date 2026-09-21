import type { EquityPoint } from "@/lib/stats";
import { CHART_COLORS } from "@/lib/chart-theme";
import { IconInbox } from "@/components/icons";

const WIDTH = 900;
const HEIGHT = 220;
const PAD = 32;

export default function EquityChart({ points }: { points: EquityPoint[] }) {
  if (points.length < 2) {
    return (
      <p className="empty-state">
        <IconInbox className="icon-empty" size={22} />
        Hacen falta al menos 2 señales resueltas para dibujar la curva.
      </p>
    );
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
  const positive = last >= 0;
  const lineColor = positive ? CHART_COLORS.green : CHART_COLORS.red;
  const gradientId = positive ? "equity-gradient-up" : "equity-gradient-down";

  return (
    <div className="chart-card">
      <svg
        viewBox={`0 0 ${WIDTH} ${HEIGHT}`}
        width="100%"
        height={HEIGHT}
        role="img"
        aria-label="Curva de rentabilidad acumulada"
      >
        <defs>
          <linearGradient id={gradientId} x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor={lineColor} stopOpacity={0.28} />
            <stop offset="100%" stopColor={lineColor} stopOpacity={0} />
          </linearGradient>
        </defs>
        <line x1={PAD} y1={zeroY} x2={WIDTH - PAD} y2={zeroY} stroke={CHART_COLORS.grid} strokeDasharray="4 4" />
        <path d={areaPath} fill={`url(#${gradientId})`} stroke="none" />
        <path d={linePath} fill="none" stroke={lineColor} strokeWidth={2} strokeLinejoin="round" strokeLinecap="round" />
        {points.map((p, i) =>
          i === points.length - 1 ? (
            <g key={i}>
              <circle cx={xFor(i)} cy={yFor(p.cum)} r={7} fill={lineColor} fillOpacity={0.16} />
              <circle cx={xFor(i)} cy={yFor(p.cum)} r={3.5} fill={lineColor} stroke={CHART_COLORS.bg} strokeWidth={1.5} />
            </g>
          ) : (
            <circle key={i} cx={xFor(i)} cy={yFor(p.cum)} r={2.5} fill={lineColor} fillOpacity={0.7} />
          )
        )}
        <text x={PAD} y={16} fill={CHART_COLORS.text} fontSize={11} fontFamily="var(--font-mono)">
          {max.toFixed(1)}%
        </text>
        <text x={PAD} y={HEIGHT - 8} fill={CHART_COLORS.text} fontSize={11} fontFamily="var(--font-mono)">
          {min.toFixed(1)}%
        </text>
      </svg>
    </div>
  );
}
