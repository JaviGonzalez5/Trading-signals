import { notFound } from "next/navigation";
import { getAssetBySymbol, getSignalsForAsset, getFundamentalAnalyses, type Signal } from "@/lib/data";
import { summarize, equityCurve } from "@/lib/stats";
import { fetchKrakenCandles } from "@/lib/kraken";
import PriceChart from "@/components/PriceChart";
import EquityChart from "@/components/EquityChart";
import {
  IconBan,
  IconChevronLeft,
  IconCheckCircle,
  IconClock,
  IconFileText,
  IconInbox,
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
    day: "2-digit",
    month: "long",
    year: "numeric",
  });
}

function sentimentLabel(sentiment: "ALCISTA" | "BAJISTA" | "NEUTRAL" | null) {
  switch (sentiment) {
    case "ALCISTA":
      return { text: "Alcista", cls: "sentiment-up", chip: "up", Icon: IconTrendingUp };
    case "BAJISTA":
      return { text: "Bajista", cls: "sentiment-down", chip: "down", Icon: IconTrendingDown };
    default:
      return { text: "Neutral", cls: "sentiment-neutral", chip: "", Icon: IconInbox };
  }
}

function statusLabel(status: Signal["status"]) {
  switch (status) {
    case "ACTIVE":
      return { text: "Activa", cls: "status-active", Icon: IconClock };
    case "HIT_TP":
      return { text: "TP", cls: "status-tp", Icon: IconCheckCircle };
    case "HIT_SL":
      return { text: "SL", cls: "status-sl", Icon: IconXCircle };
    case "TIMEOUT":
      return { text: "Timeout", cls: "status-other", Icon: IconClock };
    case "CANCELLED":
      return { text: "Cancelada", cls: "status-other", Icon: IconBan };
    default:
      return { text: status, cls: "status-other", Icon: IconClock };
  }
}

function SignalsTable({ signals, showResult }: { signals: Signal[]; showResult: boolean }) {
  if (signals.length === 0) {
    return (
      <p className="empty-state">
        <IconInbox className="icon-empty" size={22} />
        Nada por aquí todavía.
      </p>
    );
  }
  return (
    <div className="table-wrap">
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
            const StatusIcon = st.Icon;
            const DirIcon = s.direction === "LONG" ? IconTrendingUp : IconTrendingDown;
            return (
              <tr key={s.id}>
                <td>{fmtDate(s.signal_ts)}</td>
                <td className={`dir ${s.direction === "LONG" ? "dir-long" : "dir-short"}`}>
                  <DirIcon size={13} />
                  {s.direction === "LONG" ? "COMPRA" : "VENTA"}
                </td>
                <td>{fmtPrice(s.entry_price)}</td>
                <td>{fmtPrice(s.stop_loss)}</td>
                <td>{fmtPrice(s.take_profit)}</td>
                {showResult && <td>{s.exit_price != null ? fmtPrice(s.exit_price) : "—"}</td>}
                {showResult && (
                  <td className={s.r_multiple != null ? (s.r_multiple >= 0 ? "positive" : "negative") : undefined}>
                    {s.r_multiple != null ? s.r_multiple.toFixed(2) : "—"}
                  </td>
                )}
                <td className={`status ${st.cls}`}>
                  <StatusIcon size={13} />
                  {st.text}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

export default async function AssetPage({ params }: { params: Promise<{ symbol: string }> }) {
  const { symbol } = await params;
  const asset = await getAssetBySymbol(symbol);
  if (!asset) notFound();

  const [signals, fundamentalAnalyses] = await Promise.all([
    getSignalsForAsset(asset.id),
    getFundamentalAnalyses(asset.id),
  ]);
  const active = signals.filter((s) => s.status === "ACTIVE");
  const historic = signals.filter((s) => s.status !== "ACTIVE");
  const stats = summarize(signals);
  const curve = equityCurve(signals);
  const latestFundamental = fundamentalAnalyses[0] ?? null;

  let candles: Awaited<ReturnType<typeof fetchKrakenCandles>> = [];
  if (asset.data_source === "kraken") {
    const fiveDaysAgo = Math.floor(Date.now() / 1000) - 5 * 24 * 3600;
    try {
      candles = await fetchKrakenCandles(asset.source_ticker ?? asset.symbol, asset.timeframe, fiveDaysAgo);
    } catch {
      candles = []; // el resto de la página sigue funcionando sin el gráfico de precio
    }
  }

  const sentiment = latestFundamental ? sentimentLabel(latestFundamental.sentiment) : null;

  return (
    <>
      <a className="back-link" href="/">
        <IconChevronLeft size={15} />
        Volver
      </a>
      <div className="asset-header">
        <h1>{asset.symbol}</h1>
        <p className="page-subtitle">{asset.name}</p>
      </div>

      {latestFundamental && sentiment && (
        <section>
          <h2>Análisis fundamental</h2>
          <div className="card">
            <div className="card-header">
              <span className={`icon-chip ${sentiment.chip}`}>
                <sentiment.Icon size={15} />
              </span>
              <div className="card-title-group">
                <span className={`card-title ${sentiment.cls}`}>{sentiment.text}</span>
                <span className="card-meta">Sentimiento de mercado</span>
              </div>
              <span className="card-meta-right">{fmtDay(latestFundamental.analysis_date)}</span>
            </div>
            <p className="card-body">{latestFundamental.narrative}</p>
          </div>
        </section>
      )}

      <section>
        <h2>Estadísticas (señales resueltas)</h2>
        {stats.numTrades === 0 ? (
          <p className="empty-state">
            <IconInbox className="icon-empty" size={22} />
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
                <span className="positive">{stats.wins}</span>
                <span style={{ color: "var(--muted-dim)" }}>/</span>
                <span className="negative">{stats.losses}</span>
              </div>
            </div>
            <div className="stat-card">
              <div className="stat-label">Retorno estimado</div>
              <div
                className={`stat-value ${
                  (stats.estimatedReturnPct ?? 0) >= 0 ? "positive" : "negative"
                }`}
              >
                {(stats.estimatedReturnPct ?? 0) >= 0 ? (
                  <IconTrendingUp className="icon-trend" size={15} />
                ) : (
                  <IconTrendingDown className="icon-trend" size={15} />
                )}
                {stats.estimatedReturnPct}%
              </div>
            </div>
            <div className="stat-card">
              <div className="stat-label">Drawdown máximo</div>
              <div className="stat-value negative">
                <IconTrendingDown className="icon-trend" size={15} />
                {stats.maxDrawdownPct}%
              </div>
            </div>
          </div>
        )}
      </section>

      <section>
        <h2>Precio (últimos días)</h2>
        <PriceChart
          candles={candles}
          signals={active.map((s) => ({
            id: s.id,
            direction: s.direction,
            entry_price: s.entry_price,
            stop_loss: s.stop_loss,
            take_profit: s.take_profit,
          }))}
        />
      </section>

      {curve.length >= 2 && (
        <section>
          <h2>Rentabilidad acumulada</h2>
          <EquityChart points={curve} />
        </section>
      )}

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
