from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from backend.db.base import DBProvider

logger = logging.getLogger(__name__)


class SupabaseDBProvider(DBProvider):
    """
    Supabase implementation (POC — free tier, 500MB, no credit card).
    https://supabase.com/pricing

    Table schema (create in Supabase dashboard — T-014):
        create table claims (
          id            text primary key,
          pnr           text,
          bag_id        text,
          flight_number text,
          damage_types  jsonb,
          severity_score float,
          is_luxury     boolean,
          brand         text,
          compensation  float,
          fraud_score   float,
          fraud_flags   jsonb,
          routing_lane  int,
          voucher_code  text,
          status        text default 'PENDING',
          created_at    timestamptz default now(),
          updated_at    timestamptz default now()
        );
    """

    def __init__(self, url: str, service_role_key: str) -> None:
        from supabase import create_client

        self._client = create_client(url, service_role_key)

    async def save_claim(self, claim_data: Dict[str, Any]) -> str:
        # TODO (T-014):
        # response = self._client.table("claims").insert(claim_data).execute()
        # return response.data[0]["id"]
        logger.info(
            "supabase_save_claim_stub", extra={"claim_id": claim_data.get("id")}
        )
        return claim_data.get("id", "")

    async def get_claim(self, claim_id: str) -> Optional[Dict[str, Any]]:
        # TODO (T-014):
        # response = self._client.table("claims").select("*").eq("id", claim_id).execute()
        # return response.data[0] if response.data else None
        return None

    async def update_claim_status(self, claim_id: str, status: str) -> None:
        # TODO (T-014 + T-017):
        # self._client.table("claims").update({"status": status}).eq("id", claim_id).execute()
        logger.info(
            "supabase_update_status_stub",
            extra={"claim_id": claim_id, "status": status},
        )

    async def get_claim_count(self, pnr: str, days: int = 30) -> int:
        # TODO (T-012 + T-014):
        # Query claims table: count where pnr=pnr AND created_at > now()-interval
        return 0

    async def get_recent_hashes(self, pnr: str) -> list:
        # TODO (T-012 + T-014):
        # Query image_hashes table for pnr
        return []
