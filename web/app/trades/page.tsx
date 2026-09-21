import { getAllResolvedSignals, getDailyReviews } from "@/lib/data";
import { buildSuggestions } from "@/lib/suggestions";
import {
  IconChevronLeft,
  IconCheckCircle,
  IconFileText,
  IconInbox,
  IconLightbulb,
  IconTrendingDown,
  IconTrendingUp,
  IconXCircle,
} from "@/components/icons";

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

function fmtDay(isoDate: string) {
  return new Date(`${isoDate}T00:00:00Z`).toLocaleDateString("es-ES", {
    weekday: "long",
    day: "2-digit",
    month: "long",
  });
}

export default async function TradesPage() {
  const [signals, reviews] = await Promise.all([getAllResolvedSignals(), getDailyReviews()]);
  const suggestions = buildSuggestions(signals);

  return (
    <>
      <a className="back-link" href="/">
        <IconChevronLeft size={15} />
        Volver
      </a>
      <div className="asset-header">
        <h1>Diario de trades</h1>
        <p className="page-subtitle">
          Todas las señales resueltas, con el contexto que las generó — para que decidas tú qué ajustar, no un
          sistema automático.
        </p>
      </div>

      <section>
        <h2>Revisión narrada</h2>
        {reviews.length === 0 ? (
          <p className="empty-state">
            <IconFileText className="icon-empty" size={22} />
            Todavía no hay ninguna revisión narrada — se genera automáticamente el día que se resuelva al menos
            una señal (requiere <code>ANTHROPIC_API_KEY</code> configurada en Railway).
          </p>
        ) : (
          <div className="reviews-list">
            {reviews.map((r) => (
              <div key={r.id} className="card">
                <div className="card-header">
                  <span className="icon-chip accent">
                    <IconFileText size={15} />
                  </span>
                  <div className="card-title-group">
                    <span className="card-title">Revisión del día</span>
                    <span className="card-meta">{fmtDay(r.review_date)}</span>
                  </div>
                </div>
                <p className="card-body">{r.narrative}</p>
              </div>
            ))}
          </div>
        )}
      </section>

      <section>
        <h2>Sugerencias</h2>
        {signals.length < 15 ? (
          <p className="empty-state">
            <IconLightbulb className="icon-empty" size={22} />
            Hacen falta al menos 15 señales resueltas para que un patrón no sea ruido estadístico. Llevas{" "}
            {signals.length}. Sigue dejando correr el sistema.
          </p>
        ) : suggestions.length === 0 ? (
          <p className="empty-state">
            <IconLightbulb className="icon-empty" size={22} />
            Con {signals.length} señales resueltas, no hay ningún patrón lo bastante marcado todavía para sugerir
            un cambio.
          </p>
        ) : (
          <div className="suggestions-list">
            {suggestions.map((s) => (
              <div key={s.id} className="card">
                <div className="card-header">
                  <span className="icon-chip warn">
                    <IconLightbulb size={15} />
                  </span>
                  <div className="card-title-group">
                    <span className="card-title">{s.title}</span>
                  </div>
                </div>
                <p className="card-body">{s.detail}</p>
                <div className="card-footer">
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
          <p className="empty-state">
            <IconInbox className="icon-empty" size={22} />
            Todavía no hay señales resueltas.
          </p>
        ) : (
          <div className="table-wrap">
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
                {signals.map((s) => {
                  const isTp = s.status === "HIT_TP";
                  const DirIcon = s.direction === "LONG" ? IconTrendingUp : IconTrendingDown;
                  const ResultIcon = isTp ? IconCheckCircle : IconXCircle;
                  return (
                    <tr key={s.id}>
                      <td>{fmtDate(s.closed_at ?? s.signal_ts)}</td>
                      <td>
                        <a href={`/asset/${s.asset_symbol}`}>{s.asset_symbol}</a>
                      </td>
                      <td className={`dir ${s.direction === "LONG" ? "dir-long" : "dir-short"}`}>
                        <DirIcon size={13} />
                        {s.direction === "LONG" ? "COMPRA" : "VENTA"}
                      </td>
                      <td>{fmtPrice(s.entry_price)}</td>
                      <td className={`status ${isTp ? "status-tp" : "status-sl"}`}>
                        <ResultIcon size={13} />
                        {isTp ? "TP" : "SL"}
                      </td>
                      <td className={s.r_multiple != null ? (s.r_multiple >= 0 ? "positive" : "negative") : undefined}>
                        {s.r_multiple != null ? s.r_multiple.toFixed(2) : "—"}
                      </td>
                      <td>{s.rsi_at_signal != null ? s.rsi_at_signal.toFixed(1) : "—"}</td>
                      <td>{s.mae_r != null ? s.mae_r.toFixed(2) : "—"}</td>
                      <td>{s.mfe_r != null ? s.mfe_r.toFixed(2) : "—"}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </>
  );
}
