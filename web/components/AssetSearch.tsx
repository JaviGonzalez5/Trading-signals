"use client";

import { useState } from "react";
import type { Asset } from "@/lib/data";
import { IconActivity, IconSearch } from "@/components/icons";

function avatarLetters(symbol: string) {
  return symbol.replace(/USD[T]?$/i, "").slice(0, 3).toUpperCase() || symbol.slice(0, 3).toUpperCase();
}

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
      <div className="search-wrap">
        <IconSearch className="icon-search" size={16} />
        <input
          className="search-input"
          placeholder="Buscar activo (XAUUSD, BTC, ETH...)"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          autoFocus
        />
      </div>
      <div className="asset-grid">
        {filtered.map((asset) => {
          const activeCount = activeCounts[asset.id] ?? 0;
          return (
            <a key={asset.id} className="asset-card" href={`/asset/${asset.symbol}`}>
              <div className="asset-card-top">
                <span className="asset-avatar">{avatarLetters(asset.symbol)}</span>
                <div>
                  <div className="asset-symbol">{asset.symbol}</div>
                  <div className="asset-name">{asset.name}</div>
                </div>
              </div>
              {activeCount > 0 ? (
                <span className="badge badge-active">
                  <IconActivity size={11} />
                  {activeCount} señal{activeCount === 1 ? "" : "es"} activa{activeCount === 1 ? "" : "s"}
                </span>
              ) : (
                <span className="badge-none">Sin señales activas</span>
              )}
            </a>
          );
        })}
        {filtered.length === 0 && (
          <p className="empty-state">
            <IconSearch className="icon-empty" size={22} />
            Sin resultados para &quot;{query}&quot;.
          </p>
        )}
      </div>
    </>
  );
}
