"""Acceso a Supabase (proyecto propio de señales-trading, service_role key)."""

from datetime import datetime, timedelta

from supabase import Client, create_client

from worker import config


def get_client() -> Client:
    if not config.SUPABASE_URL or not config.SUPABASE_KEY:
        raise RuntimeError(
            "Faltan SUPABASE_URL/SUPABASE_KEY — configúralas como variables de "
            "entorno en Railway antes de arrancar el worker."
        )
    return create_client(config.SUPABASE_URL, config.SUPABASE_KEY)


def get_active_assets(client: Client) -> list[dict]:
    resp = client.table("assets").select("*").eq("active", True).execute()
    return resp.data or []


def has_signal_for_ts(client: Client, asset_id: str, signal_ts_iso: str) -> bool:
    resp = (
        client.table("signals")
        .select("id")
        .eq("asset_id", asset_id)
        .eq("signal_ts", signal_ts_iso)
        .limit(1)
        .execute()
    )
    return bool(resp.data)


def insert_signal(client: Client, row: dict) -> dict:
    resp = client.table("signals").insert(row).execute()
    return resp.data[0]


def mark_notified(client: Client, signal_id: str, when_iso: str) -> None:
    client.table("signals").update({"telegram_notified_at": when_iso}).eq("id", signal_id).execute()


def get_active_signals(client: Client) -> list[dict]:
    resp = client.table("signals").select("*").eq("status", "ACTIVE").execute()
    return resp.data or []


def get_asset(client: Client, asset_id: str) -> dict | None:
    resp = client.table("assets").select("*").eq("id", asset_id).limit(1).execute()
    data = resp.data or []
    return data[0] if data else None


def close_signal(
    client: Client,
    signal_id: str,
    status: str,
    exit_price: float,
    r_multiple: float,
    closed_at_iso: str,
    mae_r: float | None = None,
    mfe_r: float | None = None,
) -> None:
    client.table("signals").update({
        "status": status,
        "exit_price": exit_price,
        "r_multiple": r_multiple,
        "closed_at": closed_at_iso,
        "mae_r": mae_r,
        "mfe_r": mfe_r,
    }).eq("id", signal_id).execute()


def daily_review_exists(client: Client, review_date_iso: str) -> bool:
    resp = client.table("daily_reviews").select("id").eq("review_date", review_date_iso).limit(1).execute()
    return bool(resp.data)


def get_recent_closed_signals(client: Client, asset_id: str, limit: int = 10) -> list[dict]:
    """Últimos N cierres (HIT_TP/HIT_SL) de un activo, más recientes primero
    — para que worker/risk_guard.py detecte una racha de pérdidas seguidas."""
    resp = (
        client.table("signals")
        .select("status,closed_at")
        .eq("asset_id", asset_id)
        .in_("status", ["HIT_TP", "HIT_SL"])
        .order("closed_at", desc=True)
        .limit(limit)
        .execute()
    )
    return resp.data or []


def get_signals_closed_on(client: Client, date_iso: str) -> list[dict]:
    """Señales resueltas (HIT_TP/HIT_SL) cuyo closed_at cae dentro del día
    `date_iso` (UTC), para la revisión narrada diaria."""
    start = f"{date_iso}T00:00:00+00:00"
    end_dt = datetime.fromisoformat(date_iso) + timedelta(days=1)
    end = f"{end_dt.date().isoformat()}T00:00:00+00:00"
    resp = (
        client.table("signals")
        .select("*")
        .in_("status", ["HIT_TP", "HIT_SL"])
        .gte("closed_at", start)
        .lt("closed_at", end)
        .execute()
    )
    return resp.data or []


def fundamental_analysis_exists(client: Client, asset_id: str, analysis_date_iso: str) -> bool:
    resp = (
        client.table("fundamental_analyses")
        .select("id")
        .eq("asset_id", asset_id)
        .eq("analysis_date", analysis_date_iso)
        .limit(1)
        .execute()
    )
    return bool(resp.data)


def save_daily_review(client: Client, review_date_iso: str, signal_ids: list[str], narrative: str) -> None:
    """Upsert por review_date: si el cron se reintenta el mismo día, se
    sobrescribe en vez de duplicar (unique constraint en review_date)."""
    client.table("daily_reviews").upsert(
        {"review_date": review_date_iso, "signal_ids": signal_ids, "narrative": narrative},
        on_conflict="review_date",
    ).execute()


def save_fundamental_analysis(
    client: Client, asset_id: str, analysis_date_iso: str, sentiment: str | None, narrative: str
) -> None:
    """Upsert por (asset_id, analysis_date): si el cron se reintenta el
    mismo día para el mismo activo, se sobrescribe en vez de duplicar."""
    client.table("fundamental_analyses").upsert(
        {
            "asset_id": asset_id,
            "analysis_date": analysis_date_iso,
            "sentiment": sentiment,
            "narrative": narrative,
        },
        on_conflict="asset_id,analysis_date",
    ).execute()
