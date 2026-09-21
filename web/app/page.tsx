import { getActiveSignalCounts, getAssets } from "@/lib/data";
import AssetSearch from "@/components/AssetSearch";

export const dynamic = "force-dynamic"; // siempre datos frescos, nunca cacheado estático

export default async function HomePage() {
  const [assets, activeCounts] = await Promise.all([getAssets(), getActiveSignalCounts()]);

  return (
    <>
      <AssetSearch assets={assets} activeCounts={activeCounts} />
    </>
  );
}
