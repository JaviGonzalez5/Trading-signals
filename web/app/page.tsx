import { getActiveSignalCounts, getAssets } from "@/lib/data";
import AssetSearch from "@/components/AssetSearch";

export const dynamic = "force-dynamic"; // siempre datos frescos, nunca cacheado estático

export default async function HomePage() {
  const [assets, activeCounts] = await Promise.all([getAssets(), getActiveSignalCounts()]);

  return (
    <>
      <div className="asset-header">
        <h1>Activos</h1>
        <p className="page-subtitle">Busca un activo para ver sus señales, gráfico y estadísticas.</p>
      </div>
      <AssetSearch assets={assets} activeCounts={activeCounts} />
    </>
  );
}
