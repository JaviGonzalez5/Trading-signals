import { getServerSupabase } from "./supabase-server";

export type Asset = {
  id: string;
  symbol: string;
  name: string;
  asset_class: string;
  data_source: string;
  source_ticker: string | null;
  timeframe: string;
  active: boolean;
};

export type Signal = {
  id: string;
  asset_id: string;
  direction: "LONG" | "SHORT";
  entry_price: number;
  stop_loss: number;
  take_profit: number;
  risk_pct: number;
  capital_snapshot: number | null;
  position_size: number | null;
  status: "ACTIVE" | "HIT_TP" | "HIT_SL" | "TIMEOUT" | "CANCELLED";
  exit_price: number | null;
  r_multiple: number | null;
  signal_ts: string;
  closed_at: string | null;
  created_at: string;
  // Contexto de la estrategia en el momento de la señal (worker/main.py) y
  // excursión durante el trade (worker/check_results.py) — para el diario
  // de trades y el motor de sugerencias, no solo el resultado final.
  rsi_at_signal: number | null;
  atr_at_signal: number | null;
  ema_fast: number | null;
  ema_slow: number | null;
  mae_r: number | null;
  mfe_r: number | null;
};

export type SignalWithAsset = Signal & { asset_symbol: string };

export type DailyReview = {
  id: string;
  review_date: string;
  signal_ids: string[];
  narrative: string;
  created_at: string;
};

export type FundamentalAnalysis = {
  id: string;
  asset_id: string;
  analysis_date: string;
  sentiment: "ALCISTA" | "BAJISTA" | "NEUTRAL" | null;
  narrative: string;
  created_at: string;
};

export async function getAssets(): Promise<Asset[]> {
  const supabase = getServerSupabase();
  const { data, error } = await supabase.from("assets").select("*").order("symbol");
  if (error) throw error;
  return data ?? [];
}

export async function getAssetBySymbol(symbol: string): Promise<Asset | null> {
  const supabase = getServerSupabase();
  const { data, error } = await supabase
    .from("assets")
    .select("*")
    .ilike("symbol", symbol)
    .limit(1);
  if (error) throw error;
  return data?.[0] ?? null;
}

export async function getSignalsForAsset(assetId: string): Promise<Signal[]> {
  const supabase = getServerSupabase();
  const { data, error } = await supabase
    .from("signals")
    .select("*")
    .eq("asset_id", assetId)
    .order("signal_ts", { ascending: false });
  if (error) throw error;
  return data ?? [];
}

/** Todas las señales resueltas (cualquier activo), para el diario de
 * trades y el motor de sugerencias — ordenadas más reciente primero. */
export async function getAllResolvedSignals(): Promise<SignalWithAsset[]> {
  const supabase = getServerSupabase();
  const { data, error } = await supabase
    .from("signals")
    .select("*, assets(symbol)")
    .in("status", ["HIT_TP", "HIT_SL"])
    .order("closed_at", { ascending: false });
  if (error) throw error;
  return (data ?? []).map((row) => {
    const { assets, ...signal } = row as Signal & { assets: { symbol: string } | null };
    return { ...signal, asset_symbol: assets?.symbol ?? "?" };
  });
}

/** Revisiones narradas (última primero) — explican lo ya pasado, nunca
 * proponen operaciones nuevas (ver worker/daily_review.py). */
export async function getDailyReviews(limit = 14): Promise<DailyReview[]> {
  const supabase = getServerSupabase();
  const { data, error } = await supabase
    .from("daily_reviews")
    .select("*")
    .order("review_date", { ascending: false })
    .limit(limit);
  if (error) throw error;
  return data ?? [];
}

/** Últimos análisis fundamentales de un activo (más reciente primero) —
 * lectura de sentimiento vía búsqueda web, nunca propone una operación
 * (ver worker/fundamental_analysis.py). */
export async function getFundamentalAnalyses(assetId: string, limit = 7): Promise<FundamentalAnalysis[]> {
  const supabase = getServerSupabase();
  const { data, error } = await supabase
    .from("fundamental_analyses")
    .select("*")
    .eq("asset_id", assetId)
    .order("analysis_date", { ascending: false })
    .limit(limit);
  if (error) throw error;
  return data ?? [];
}

/** Nº de señales ACTIVE por asset_id, para pintar el badge en el listado. */
export async function getActiveSignalCounts(): Promise<Record<string, number>> {
  const supabase = getServerSupabase();
  const { data, error } = await supabase.from("signals").select("asset_id").eq("status", "ACTIVE");
  if (error) throw error;
  const counts: Record<string, number> = {};
  for (const row of data ?? []) {
    counts[row.asset_id] = (counts[row.asset_id] ?? 0) + 1;
  }
  return counts;
}
