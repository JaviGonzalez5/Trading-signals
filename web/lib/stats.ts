import type { Signal } from "./data";

export type Stats = {
  numTrades: number;
  wins: number;
  losses: number;
  winRatePct: number | null;
  avgRMultiple: number | null;
  totalRMultiple: number | null;
  /** Suma de (r_multiple * risk_pct) de cada señal, en el orden en que se
   * cerraron — mismo concepto que "estimated_return_pct" del backtest
   * (backtest/engine.py::summarize), pero usando el risk_pct real de cada
   * señal en vez de uno único fijo para todo el lote. */
  estimatedReturnPct: number | null;
  maxDrawdownPct: number | null;
};

const round = (n: number, decimals: number) => Math.round(n * 10 ** decimals) / 10 ** decimals;

export type EquityPoint = { date: string; cum: number };

/** Señales resueltas (HIT_TP/HIT_SL) ordenadas por fecha de cierre — la
 * misma base que usan summarize() y equityCurve(), factorizada para no
 * ordenar dos veces. */
function resolvedSignals(signals: Signal[]): Signal[] {
  return signals
    .filter((s) => s.status === "HIT_TP" || s.status === "HIT_SL")
    .slice()
    .sort((a, b) => new Date(a.closed_at ?? a.signal_ts).getTime() - new Date(b.closed_at ?? b.signal_ts).getTime());
}

/** Curva de equity: cada punto es la rentabilidad acumulada (%) justo
 * después de cerrarse esa señal. Usada tanto por summarize() (para el
 * drawdown máximo) como por el gráfico de la web. */
export function equityCurve(signals: Signal[]): EquityPoint[] {
  const resolved = resolvedSignals(signals);
  let cum = 0;
  return resolved.map((s) => {
    cum += (s.r_multiple ?? 0) * (s.risk_pct ?? 1);
    return { date: s.closed_at ?? s.signal_ts, cum: round(cum, 3) };
  });
}

/** Solo cuentan las señales ya resueltas (HIT_TP/HIT_SL) — mismo criterio
 * que backtest/engine.py::summarize. TIMEOUT/CANCELLED no puntúan a favor
 * ni en contra (no hay bastantes en producción todavía para decidir cómo
 * tratarlas; se dejan fuera a propósito). */
export function summarize(signals: Signal[]): Stats {
  const resolved = resolvedSignals(signals);

  if (resolved.length === 0) {
    return {
      numTrades: 0,
      wins: 0,
      losses: 0,
      winRatePct: null,
      avgRMultiple: null,
      totalRMultiple: null,
      estimatedReturnPct: null,
      maxDrawdownPct: null,
    };
  }

  const wins = resolved.filter((s) => s.status === "HIT_TP");
  const losses = resolved.filter((s) => s.status === "HIT_SL");
  const rValues = resolved.map((s) => s.r_multiple ?? 0);
  const totalR = rValues.reduce((a, b) => a + b, 0);
  const avgR = totalR / resolved.length;

  const curve = equityCurve(signals);
  let peak = 0;
  let maxDD = 0;
  for (const p of curve) {
    peak = Math.max(peak, p.cum);
    maxDD = Math.min(maxDD, p.cum - peak);
  }

  return {
    numTrades: resolved.length,
    wins: wins.length,
    losses: losses.length,
    winRatePct: round((wins.length / resolved.length) * 100, 2),
    avgRMultiple: round(avgR, 3),
    totalRMultiple: round(totalR, 2),
    estimatedReturnPct: round(curve[curve.length - 1]?.cum ?? 0, 2),
    maxDrawdownPct: round(maxDD, 2),
  };
}
