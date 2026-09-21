// Descarga de velas directo de Kraken (API pública, sin key) para dibujar
// el gráfico de precio. Réplica en TS de worker/data_sources.py::fetch_kraken_klines
// — solo lectura para la web, no toca la lógica de generación de señales.

export type Candle = { time: number; open: number; high: number; low: number; close: number };

const KRAKEN_OHLC_URL = "https://api.kraken.com/0/public/OHLC";
const INTERVAL_MINUTES: Record<string, number> = {
  "1m": 1,
  "5m": 5,
  "15m": 15,
  "30m": 30,
  "1h": 60,
  "4h": 240,
  "1d": 1440,
};

export async function fetchKrakenCandles(pair: string, timeframe = "1h", sinceUnix?: number): Promise<Candle[]> {
  const minutes = INTERVAL_MINUTES[timeframe] ?? 60;
  const params = new URLSearchParams({ pair, interval: String(minutes) });
  if (sinceUnix != null) params.set("since", String(sinceUnix));

  const res = await fetch(`${KRAKEN_OHLC_URL}?${params.toString()}`, {
    next: { revalidate: 60 }, // cachea 60s: evita golpear Kraken en cada request de un visitante
  });
  if (!res.ok) throw new Error(`Kraken OHLC ${pair} respondió ${res.status}`);
  const body = await res.json();
  if (body.error?.length) throw new Error(`Kraken error para ${pair}: ${body.error.join(", ")}`);

  const result = body.result ?? {};
  const rows: unknown[] = Object.entries(result).find(([k]) => k !== "last")?.[1] as unknown[] | undefined ?? [];

  return rows.map((row) => {
    const r = row as [number, string, string, string, string, string, string, number];
    return {
      time: r[0],
      open: parseFloat(r[1]),
      high: parseFloat(r[2]),
      low: parseFloat(r[3]),
      close: parseFloat(r[4]),
    };
  });
}
