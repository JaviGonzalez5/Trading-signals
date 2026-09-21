import type { Signal } from "./data";

/**
 * Motor de sugerencias — NO ajusta nada solo. Busca patrones objetivos
 * (agrupando trades reales por RSI/dirección/excursión) y, si hay muestra
 * suficiente para que el patrón no sea ruido, propone un cambio de
 * parámetro concreto con los números que lo respaldan. El usuario decide
 * si aplicarlo — de ahí que no haya botón "aplicar": cambiar
 * strategy/core.py es una decisión humana, a propósito (ver conversación
 * de diseño: NO es un sistema de auto-ajuste autónomo).
 */

export type Suggestion = {
  id: string;
  title: string;
  detail: string;
  sampleSize: number;
  baselineWinRatePct: number;
  bucketWinRatePct: number;
};

// Por debajo de esto, cualquier diferencia de winrate es ruido estadístico,
// no un patrón real — no se sugiere nada.
const MIN_SAMPLE = 15;
// Diferencia mínima de winrate (puntos porcentuales) para que merezca la
// pena mencionarlo — evita sugerencias por ruido de 2-3 puntos.
const MIN_GAP_PCT = 15;

const round = (n: number, decimals: number) => Math.round(n * 10 ** decimals) / 10 ** decimals;

function winRatePct(signals: Signal[]): number | null {
  if (signals.length === 0) return null;
  const wins = signals.filter((s) => s.status === "HIT_TP").length;
  return (wins / signals.length) * 100;
}

export function buildSuggestions(allSignals: Signal[]): Suggestion[] {
  const resolved = allSignals.filter((s) => s.status === "HIT_TP" || s.status === "HIT_SL");
  const overallWR = winRatePct(resolved);
  const suggestions: Suggestion[] = [];

  if (resolved.length < MIN_SAMPLE || overallWR == null) {
    return suggestions;
  }

  // 1) RSI extremo en el momento de la señal (lejos de zona neutral).
  const extremeRsi = resolved.filter(
    (s) => s.rsi_at_signal != null && (s.direction === "LONG" ? s.rsi_at_signal > 65 : s.rsi_at_signal < 35)
  );
  if (extremeRsi.length >= MIN_SAMPLE) {
    const bucketWR = winRatePct(extremeRsi)!;
    if (overallWR - bucketWR >= MIN_GAP_PCT) {
      suggestions.push({
        id: "rsi-extreme",
        title: "Las entradas con RSI extremo fallan más",
        detail: `De ${extremeRsi.length} señales con RSI muy alejado de 50 al entrar, solo ${bucketWR.toFixed(
          1
        )}% ganaron, frente al ${overallWR.toFixed(
          1
        )}% general. Podría interesar exigir un RSI más moderado antes de generar la señal (RSI_LONG_MIN/RSI_SHORT_MAX en strategy/core.py).`,
        sampleSize: extremeRsi.length,
        baselineWinRatePct: round(overallWR, 1),
        bucketWinRatePct: round(bucketWR, 1),
      });
    }
  }

  // 2) Sesgo direccional (COMPRA vs VENTA rinden distinto).
  for (const dir of ["LONG", "SHORT"] as const) {
    const dirSignals = resolved.filter((s) => s.direction === dir);
    if (dirSignals.length < MIN_SAMPLE) continue;
    const dirWR = winRatePct(dirSignals)!;
    if (overallWR - dirWR >= MIN_GAP_PCT) {
      suggestions.push({
        id: `direction-${dir}`,
        title: `Las señales de ${dir === "LONG" ? "COMPRA" : "VENTA"} rinden peor`,
        detail: `${dirSignals.length} señales ${dir === "LONG" ? "COMPRA" : "VENTA"}, ${dirWR.toFixed(
          1
        )}% de acierto frente al ${overallWR.toFixed(
          1
        )}% general. Puede haber un sesgo direccional real en este activo/timeframe — vale la pena mirarlo antes de arriesgar más capital en ese lado.`,
        sampleSize: dirSignals.length,
        baselineWinRatePct: round(overallWR, 1),
        bucketWinRatePct: round(dirWR, 1),
      });
    }
  }

  // 3) Ganadoras que estuvieron muy cerca de saltar el stop — indicio de
  // que el SL está demasiado ajustado para el ruido normal del precio.
  const nearMissWins = resolved.filter((s) => s.status === "HIT_TP" && s.mae_r != null && s.mae_r <= -0.8);
  if (nearMissWins.length >= MIN_SAMPLE) {
    suggestions.push({
      id: "near-miss-wins",
      title: "Muchas ganadoras estuvieron a un paso de perder",
      detail: `${nearMissWins.length} señales ganadoras llegaron a superar -0.8R en contra antes de girar hacia el TP. El stop puede estar demasiado ajustado para el ruido normal del precio — considera subir SL_ATR_MULT en strategy/core.py.`,
      sampleSize: nearMissWins.length,
      baselineWinRatePct: round(overallWR, 1),
      bucketWinRatePct: round(winRatePct(nearMissWins) ?? 0, 1),
    });
  }

  return suggestions;
}
