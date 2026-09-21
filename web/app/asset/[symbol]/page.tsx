import { notFound } from "next/navigation";
import { getAssetBySymbol, getSignalsForAsset, type Signal } from "@/lib/data";
import { summarize } from "@/lib/stats";

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

function statusLabel(status: Signal["status"]) {
  switch (status) {
    case "ACTIVE":
      return { text: "Activa", cls: "status-active" };
    case "HIT_TP":
      return { text: "✅ TP", cls: "status-tp" };
    case "HIT_SL":
      return { text: "❌ SL", cls: "status-sl" };
    case "TIMEOUT":
      return { text: "Timeout", cls: "status-other" };
    case "CANCELLED":
      return { text: "Cancelada", cls: "status-other" };
    default:
      return { text: status, cls: "status-other" };
  }
}

function SignalsTable({ signals, showResult }: { signals: Signal[]; showResult: boolean }) {
  if (signals.length === 0) {
    return <p className="empty-state">Nada por aquí todavía.</p>;
  }
  return (
    <table>
      <thead>
        <tr>
          <th>Fecha</th>
          <th>Dirección</th>
          <th>Entrada</th>
          <th>SL</th>
          <th>TP</th>
          {showResult && <th>Resultado</th>}
          {showResult && <th>R</th>}
          <th>Estado</th>
        </tr>
      </thead>
      <tbody>
        {signals.map((s) => {
          const st = statusLabel(s.status);
          return (
            <tr key={s.id}>
              <td>{fmtDate(s.signal_ts)}</td>
              <td className={s.direction === "LONG" ? "dir-long" : "dir-short"}>
                {s.direction === "LONG" ? "COMPRA" : "VENTA"}
              </td>
              <td>{fmtPrice(s.entry_price)}</td>
              <td>{fmtPrice(s.stop_loss)}</td>
              <td>{fmtPrice(s.take_profit)}</td>
              {showResult && <td>{s.exit_price != null ? fmtPrice(s.exit_price) : "—"}</td>}
              {showResult && <td>{s.r_multiple != null ? s.r_multiple.toFixed(2) : "—"}</td>}
              <td className={st.cls}>{st.text}</td>
            </tr>
          );
        })}
      </tbody>
    </table>
  );
}

export default async function AssetPage({ params }: { params: Promise<{ symbol: string }> }) {
  const { symbol } = await params;
  const asset = await getAssetBySymbol(symbol);
  if (!asset) notFound();

  const signals = await getSignalsForAsset(asset.id);
  const active = signals.filter((s) => s.status === "ACTIVE");
  const historic = signals.filter((s) => s.status !== "ACTIVE");
  const stats = summarize(signals);

  return (
    <>
      <a className="back-link" href="/">
        ← Volver
      </a>
      <div className="asset-header">
        <h1>{asset.symbol}</h1>
        <p style={{ color: "var(--muted)" }}>{asset.name}</p>
      </div>

      <section>
        <h2>Estadísticas (señales resueltas)</h2>
        {stats.numTrades === 0 ? (
          <p className="empty-state">
            Todavía no hay señales resueltas (TP/SL tocado) para calcular estadísticas.
          </p>
        ) : (
          <div className="stats-grid">
            <div className="stat-card">
              <div className="stat-label">Señales</div>
              <div className="stat-value">{stats.numTrades}</div>
            </div>
            <div className="stat-card">
              <div className="stat-label">% Acierto</div>
              <div className="stat-value">{stats.winRatePct}%</div>
            </div>
            <div className="stat-card">
              <div className="stat-label">Ganadas / Perdidas</div>
              <div className="stat-value">
                {stats.wins} / {stats.losses}
              </div>
            </div>
            <div className="stat-card">
              <div className="stat-label">Retorno estimado</div>
              <div
                className={`stat-value ${
                  (stats.estimatedReturnPct ?? 0) >= 0 ? "positive" : "negative"
                }`}
              >
                {stats.estimatedReturnPct}%
              </div>
            </div>
            <div className="stat-card">
              <div className="stat-label">Drawdown máximo</div>
              <div className="stat-value negative">{stats.maxDrawdownPct}%</div>
            </div>
          </div>
        )}
      </section>

      <section>
        <h2>Señales activas</h2>
        <SignalsTable signals={active} showResult={false} />
      </section>

      <section>
        <h2>Histórico</h2>
        <SignalsTable signals={historic} showResult={true} />
      </section>
    </>
  );
}
