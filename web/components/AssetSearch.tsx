"use client";

import { useState } from "react";
import type { Asset } from "@/lib/data";

export default function AssetSearch({
  assets,
  activeCounts,
}: {
  assets: Asset[];
  activeCounts: Record<string, number>;
}) {
  const [query, setQuery] = useState("");

  const filtered = assets.filter((a) => {
    const q = query.trim().toLowerCase();
    if (!q) return true;
    return a.symbol.toLowerCase().includes(q) || a.name.toLowerCase().includes(q);
  });

  return (
    <>
      <input
        className="search-input"
        placeholder="Buscar activo (XAUUSD, BTC, ETH...)"
        value={query}
        onChange={(e) => setQuery(e.target.value)}
        autoFocus
      />
      <div className="asset-grid">
        {filtered.map((asset) => {
          const activeCount = activeCounts[asset.id] ?? 0;
          return (
            <a key={asset.id} className="asset-card" href={`/asset/${asset.symbol}`}>
              <div className="asset-symbol">{asset.symbol}</div>
              <div className="asset-name">{asset.name}</div>
              {activeCount > 0 ? (
                <span className="badge badge-active">{activeCount} señal(es) activa(s)</span>
              ) : (
                <span className="badge-none">Sin señales activas</span>
              )}
            </a>
          );
        })}
        {filtered.length === 0 && <p className="empty-state">Sin resultados para &quot;{query}&quot;.</p>}
      </div>
    </>
  );
}
