import { getAllResolvedSignals } from "@/lib/data";
import { buildSuggestions } from "@/lib/suggestions";

export const dynamic = "force-dynamic";

function fmtPrice(n: number) {
  return n.toLocaleString("es-ES", { maximumFractionDigits: 5 });
}

function fmtDate(iso: string | null) {
  if (!iso) return "—";
  return new Date(iso).toLocaleString("es-ES", {
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

export default async function TradesPage() {
  const signals = await getAllResolvedSignals();
  const suggestions = buildSuggestions(signals);

  return (
    <>
      <a className="back-link" href="/">
        ← Volver
      </a>
      <div className="asset-header">
        <h1>Diario de trades</h1>
        <p style={{ color: "var(--muted)" }}>
          Todas las señales resueltas, con el contexto que las generó — para que decidas tú qué ajustar, no un
          sistema automático.
        </p>
      </div>

      <section>
        <h2>Sugerencias</h2>
        {signals.length < 15 ? (
          <p className="empty-state">
            Hacen falta al menos 15 señales resueltas para que un patrón no sea ruido estadístico. Llevas{" "}
            {signals.length}. Sigue dejando correr el sistema.
          </p>
        ) : suggestions.length === 0 ? (
          <p className="empty-state">
            Con {signals.length} señales resueltas, no hay ningún patrón lo bastante marcado todavía para sugerir
            un cambio.
          </p>
        ) : (
          <div className="suggestions-list">
            {suggestions.map((s) => (
              <div key={s.id} className="suggestion-card">
                <div className="suggestion-title">{s.title}</div>
                <p className="suggestion-detail">{s.detail}</p>
                <div className="suggestion-meta">
                  Muestra: {s.sampleSize} señales · {s.bucketWinRatePct}% acierto (vs {s.baselineWinRatePct}%
                  general)
                </div>
              </div>
            ))}
          </div>
        )}
      </section>

      <section>
        <h2>Histórico completo ({signals.length})</h2>
        {signals.length === 0 ? (
          <p className="empty-state">Todavía no hay señales resueltas.</p>
        ) : (
          <table>
            <thead>
              <tr>
                <th>Fecha</th>
                <th>Activo</th>
                <th>Dirección</th>
                <th>Entrada</th>
                <th>Resultado</th>
                <th>R</th>
                <th>RSI señal</th>
                <th>MAE (R)</th>
                <th>MFE (R)</th>
              </tr>
            </thead>
            <tbody>
              {signals.map((s) => (
                <tr key={s.id}>
                  <td>{fmtDate(s.closed_at ?? s.signal_ts)}</td>
                  <td>
                    <a href={`/asset/${s.asset_symbol}`}>{s.asset_symbol}</a>
                  </td>
                  <td className={s.direction === "LONG" ? "dir-long" : "dir-short"}>
                    {s.direction === "LONG" ? "COMPRA" : "VENTA"}
                  </td>
                  <td>{fmtPrice(s.entry_price)}</td>
                  <td className={s.status === "HIT_TP" ? "status-tp" : "status-sl"}>
                    {s.status === "HIT_TP" ? "✅ TP" : "❌ SL"}
                  </td>
                  <td>{s.r_multiple != null ? s.r_multiple.toFixed(2) : "—"}</td>
                  <td>{s.rsi_at_signal != null ? s.rsi_at_signal.toFixed(1) : "—"}</td>
                  <td>{s.mae_r != null ? s.mae_r.toFixed(2) : "—"}</td>
                  <td>{s.mfe_r != null ? s.mfe_r.toFixed(2) : "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </section>
    </>
  );
}
