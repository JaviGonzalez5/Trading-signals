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
) -> None:
    client.table("signals").update({
        "status": status,
        "exit_price": exit_price,
        "r_multiple": r_multiple,
        "closed_at": closed_at_iso,
    }).eq("id", signal_id).execute()
