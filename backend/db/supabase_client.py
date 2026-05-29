from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from backend.db.base import DBProvider

logger = logging.getLogger(__name__)


class SupabaseDBProvider(DBProvider):
    """
    Supabase implementation of DBProvider (POC — free tier, 500MB, no credit card).
    https://supabase.com/pricing

    Run this SQL migration in your Supabase project (SQL Editor → New Query):

        -- ── claims table ─────────────────────────────────────────────────────────
        create table if not exists claims (
            id              text primary key,
            pnr             text,
            bag_id          text,
            flight_number   text,
            damage_types    jsonb,
            severity_score  float,
            is_luxury       boolean default false,
            brand           text,
            compensation    float,
            fraud_score     float default 0,
            fraud_flags     jsonb  default '[]',
            routing_lane    int,
            voucher_code    text,
            status          text   default 'PENDING',
            created_at      timestamptz default now(),
            updated_at      timestamptz default now()
        );

        -- ── image_hashes table (pHash duplicate fraud check) ──────────────────────
        create table if not exists image_hashes (
            id          bigserial primary key,
            pnr         text    not null,
            hash_value  text    not null,
            claim_id    text    references claims(id) on delete cascade,
            created_at  timestamptz default now()
        );

        -- ── indexes ───────────────────────────────────────────────────────────────
        create index if not exists idx_claims_pnr         on claims (pnr);
        create index if not exists idx_claims_status      on claims (status);
        create index if not exists idx_image_hashes_pnr   on image_hashes (pnr);

        -- ── Row Level Security (disable for POC service-role key usage) ───────────
        alter table claims       disable row level security;
        alter table image_hashes disable row level security;

    How to wire into the app
    ------------------------
    Dependencies already wired: provide_db() in backend/dependencies.py returns
    SupabaseDBProvider(url, service_role_key) when DB_PROVIDER=supabase (default).
    Set the following in your .env:

        SUPABASE_URL=https://<your-project-ref>.supabase.co
        SUPABASE_SERVICE_ROLE_KEY=<your-service-role-key>

    The service role key bypasses Row Level Security — correct for backend use.
    Never expose it on the frontend.

    IMPORTANT — async client
    ------------------------
    supabase-py 2.x ships both a sync Client (create_client) and an async
    AsyncClient (acreate_client / create_async_client).  FastAPI runs on an
    asyncio event loop; calling the *synchronous* Supabase client from inside
    an async def blocks the event loop and on Windows causes:

        [Errno 11001] getaddrinfo failed

    because Windows' asyncio event loop (ProactorEventLoop) does not allow
    blocking socket calls on the loop thread.  The fix is to use
    acreate_client() and await every .execute() call.  That is what this
    class does — _client is an AsyncClient, not the sync Client.
    """

    def __init__(self, url: str, service_role_key: str) -> None:
        """
        Store credentials for deferred async initialisation.

        The AsyncClient must be created with ``await acreate_client()``, which
        cannot be done in __init__ (synchronous).  _client is therefore set to
        None here and initialised lazily on the first DB call via
        ``_get_client()``.

        Args:
            url: Supabase project URL (SUPABASE_URL env var).
            service_role_key: Service-role key (SUPABASE_SERVICE_ROLE_KEY env var).

        Raises:
            ValueError: If url or service_role_key is None/empty.
        """
        if not url or not service_role_key:
            raise ValueError(
                "SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY must be set in .env"
            )
        self._url = url
        self._service_role_key = service_role_key
        self._client = None  # lazily initialised in _get_client()
        logger.info("supabase_provider_created", extra={"url": url[:40]})

    async def _get_client(self):
        """
        Return the cached AsyncClient, creating it on first call.

        Uses acreate_client() so the underlying httpx.AsyncClient session is
        properly initialised inside the running event loop.  Subsequent calls
        return the cached instance (no reconnect overhead).

        Returns:
            supabase.AsyncClient: Ready-to-use async Supabase client.
        """
        if self._client is None:
            from supabase import acreate_client

            self._client = await acreate_client(self._url, self._service_role_key)
            logger.info(
                "supabase_async_client_initialised", extra={"url": self._url[:40]}
            )
        return self._client

    # ── write operations ──────────────────────────────────────────────────────

    async def save_claim(self, claim_data: Dict[str, Any]) -> str:
        """
        Insert a new claim row into the claims table.

        Called by A4DecisionAgent after routing decision is made.

        Args:
            claim_data: Flat dict matching the claims table schema.
                        Must include 'id' (CLM-YYYYMMDD-XXXX format).

        Returns:
            The claim_id that was inserted.

        Raises:
            Exception: Re-raised from supabase-py on network/auth error.
        """
        claim_id = claim_data.get("id", "")
        logger.info("supabase_save_claim", extra={"claim_id": claim_id})

        client = await self._get_client()
        response = await client.table("claims").insert(claim_data).execute()

        if not response.data:
            raise RuntimeError(f"Supabase insert returned no data for claim {claim_id}")

        saved_id: str = response.data[0]["id"]
        logger.info("supabase_save_claim_ok", extra={"claim_id": saved_id})
        return saved_id

    async def update_claim_status(self, claim_id: str, status: str) -> None:
        """
        Update the status of an existing claim.

        Called by:
        - A5NotificationAgent (Lane 2 → AWAITING_REVIEW)
        - /decision endpoint (agent approve/reject → RESOLVED / REJECTED)

        Args:
            claim_id: Claim to update.
            status: New status string, e.g. 'AWAITING_REVIEW', 'RESOLVED', 'REJECTED'.

        Raises:
            Exception: Re-raised from supabase-py on network/auth error.
        """
        logger.info(
            "supabase_update_status",
            extra={"claim_id": claim_id, "status": status},
        )

        client = await self._get_client()
        await client.table("claims").update({"status": status}).eq(
            "id", claim_id
        ).execute()

        logger.info(
            "supabase_update_status_ok",
            extra={"claim_id": claim_id, "status": status},
        )

    async def update_claim(
        self, claim_id: str, fields: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        """
        Update arbitrary columns of a claim in a single write and return the row.

        Called by the /decision endpoint so an agent approve/reject can persist
        the new status, an edited compensation amount, and a voucher code all at
        once. Always bumps updated_at so the dashboard/simulator see fresh data.

        Args:
            claim_id: Claim to update.
            fields:   Column → value mapping to write.

        Returns:
            The updated claim dict, or None if no row matched.

        Raises:
            Exception: Re-raised from supabase-py on network/auth error.
        """
        if not fields:
            return await self.get_claim(claim_id)

        payload = dict(fields)
        payload["updated_at"] = "now()"

        logger.info(
            "supabase_update_claim",
            extra={"claim_id": claim_id, "fields": list(payload.keys())},
        )

        client = await self._get_client()
        response = (
            await client.table("claims").update(payload).eq("id", claim_id).execute()
        )

        if not response.data:
            logger.warning(
                "supabase_update_claim_no_row",
                extra={"claim_id": claim_id},
            )
            return None

        logger.info("supabase_update_claim_ok", extra={"claim_id": claim_id})
        return response.data[0]

    # ── read operations ───────────────────────────────────────────────────────

    async def get_claim(self, claim_id: str) -> Optional[Dict[str, Any]]:
        """
        Retrieve a single claim by its ID.

        Args:
            claim_id: The CLM-YYYYMMDD-XXXX claim identifier.

        Returns:
            Claim dict if found, None if not found.

        Raises:
            Exception: Re-raised from supabase-py on network/auth error.
        """
        logger.debug("supabase_get_claim", extra={"claim_id": claim_id})

        client = await self._get_client()
        response = (
            await client.table("claims").select("*").eq("id", claim_id).execute()
        )

        if not response.data:
            logger.debug("supabase_get_claim_not_found", extra={"claim_id": claim_id})
            return None

        return response.data[0]

    async def get_claims_by_status(self, status: str) -> List[Dict[str, Any]]:
        """
        Return all claims with the given status, ordered newest first.

        Called by GET /claims/pending to populate the agent dashboard.

        Args:
            status: Status to filter by e.g. 'AWAITING_REVIEW'.

        Returns:
            List of claim dicts, empty list if none found.

        Raises:
            Exception: Re-raised from supabase-py on network/auth error.
        """
        logger.info("supabase_get_claims_by_status", extra={"status": status})

        client = await self._get_client()
        response = (
            await client.table("claims")
            .select("*")
            .eq("status", status)
            .order("created_at", desc=True)
            .execute()
        )

        claims: List[Dict[str, Any]] = response.data or []
        logger.info(
            "supabase_get_claims_by_status_ok",
            extra={"status": status, "count": len(claims)},
        )
        return claims

    async def get_claim_count(self, pnr: str, days: int = 30) -> int:
        """
        Count how many claims a passenger (PNR) has filed in the last N days.

        Used by A4DecisionAgent for the claim-frequency fraud check.
        A count >= MAX_CLAIMS_PER_PASSENGER adds 0.3 to fraud_score.

        Args:
            pnr: Passenger Name Record / booking reference (6-char alphanumeric).
            days: Lookback window in days (default 30, configurable via env).

        Returns:
            Integer count of claims for this PNR in the window.

        Raises:
            Exception: Re-raised from supabase-py on network/auth error.
        """
        logger.debug("supabase_get_claim_count", extra={"pnr": pnr, "days": days})

        client = await self._get_client()
        # Supabase supports Postgres interval syntax directly
        response = (
            await client.table("claims")
            .select("id", count="exact")
            .eq("pnr", pnr)
            .gte("created_at", f"now() - interval '{days} days'")
            .execute()
        )

        count: int = response.count or 0
        logger.debug(
            "supabase_claim_count_result",
            extra={"pnr": pnr, "count": count},
        )
        return count

    async def get_recent_hashes(self, pnr: str) -> List[str]:
        """
        Return all stored pHash values for a given PNR.

        Used by A4DecisionAgent for the duplicate-image fraud check.
        A near-match (hamming distance < FRAUD_PHASH_THRESHOLD) adds 0.4
        to fraud_score and flags 'phash_duplicate'.

        Args:
            pnr: Passenger Name Record to look up image hashes for.

        Returns:
            List of hex hash strings (may be empty if no prior claims).

        Raises:
            Exception: Re-raised from supabase-py on network/auth error.
        """
        logger.debug("supabase_get_hashes", extra={"pnr": pnr})

        client = await self._get_client()
        response = (
            await client.table("image_hashes")
            .select("hash_value")
            .eq("pnr", pnr)
            .execute()
        )

        hashes: List[str] = [row["hash_value"] for row in (response.data or [])]
        logger.debug(
            "supabase_hashes_result",
            extra={"pnr": pnr, "count": len(hashes)},
        )
        return hashes
