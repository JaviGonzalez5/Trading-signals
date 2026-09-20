"""Acceso a Supabase (proyecto propio de señales-trading, service_role key)."""

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
