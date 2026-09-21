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
