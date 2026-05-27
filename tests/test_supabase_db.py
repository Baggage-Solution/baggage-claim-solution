"""
Unit tests for SupabaseDBProvider — T-014.

All Supabase API calls are mocked — no real Supabase project needed.
Tests verify:
  1. save_claim()          — insert + return id
  2. update_claim_status() — update status column
  3. get_claim()           — select by id (found + not found)
  4. get_claim_count()     — PNR frequency count (fraud check)
  5. get_recent_hashes()   — pHash lookup (fraud check)
  6. __init__ validation   — raises ValueError on missing credentials
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from backend.db.supabase_client import SupabaseDBProvider

# ── Helpers ───────────────────────────────────────────────────────────────────

FAKE_URL = "https://test-project.supabase.co"
FAKE_KEY = "fake-service-role-key-abc123"


def make_provider() -> tuple[SupabaseDBProvider, MagicMock]:
    """
    Returns (provider, mock_client) — provider is fully wired to mock_client.
    Bypasses __init__ so supabase-py does not need to be installed in CI.
    """
    mock_client = MagicMock()
    provider = SupabaseDBProvider.__new__(SupabaseDBProvider)
    provider._client = mock_client
    return provider, mock_client


def make_chain(mock_client: MagicMock, return_data=None, count: int = 0):
    """
    Wire mock_client so that any .table().x().y().execute() returns a
    response with .data = return_data and .count = count.
    """
    mock_response = MagicMock()
    mock_response.data = return_data if return_data is not None else []
    mock_response.count = count

    chain = MagicMock()
    chain.execute.return_value = mock_response
    chain.select.return_value = chain
    chain.insert.return_value = chain
    chain.update.return_value = chain
    chain.eq.return_value = chain
    chain.gte.return_value = chain
    mock_client.table.return_value = chain

    return chain, mock_response


# ── __init__ validation ───────────────────────────────────────────────────────


def test_init_raises_on_missing_url():
    """ValueError if SUPABASE_URL is None — fires before create_client is called."""
    with pytest.raises(ValueError, match="SUPABASE_URL"):
        # Patch create_client at the local import inside __init__ so supabase
        # package is not required to be installed in the test environment.
        with patch(
            "backend.db.supabase_client.SupabaseDBProvider.__init__",
            wraps=SupabaseDBProvider.__init__,
        ):
            # Call __init__ directly with None url — ValueError fires first
            provider = SupabaseDBProvider.__new__(SupabaseDBProvider)
            SupabaseDBProvider.__init__(provider, url=None, service_role_key=FAKE_KEY)


def test_init_raises_on_missing_key():
    """ValueError if SUPABASE_SERVICE_ROLE_KEY is None."""
    with pytest.raises(ValueError, match="SUPABASE_SERVICE_ROLE_KEY"):
        provider = SupabaseDBProvider.__new__(SupabaseDBProvider)
        SupabaseDBProvider.__init__(provider, url=FAKE_URL, service_role_key=None)


def test_init_raises_on_empty_url():
    """ValueError if SUPABASE_URL is an empty string."""
    with pytest.raises(ValueError):
        provider = SupabaseDBProvider.__new__(SupabaseDBProvider)
        SupabaseDBProvider.__init__(provider, url="", service_role_key=FAKE_KEY)


# ── save_claim ────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_save_claim_inserts_and_returns_id():
    """save_claim() calls table('claims').insert(data).execute() and returns claim id."""
    provider, mock_client = make_provider()
    claim_data = {"id": "CLM-20260522-AB12", "pnr": "ABC123", "status": "PENDING"}
    chain, _ = make_chain(mock_client, return_data=[{"id": "CLM-20260522-AB12"}])

    result = await provider.save_claim(claim_data)

    assert result == "CLM-20260522-AB12"
    mock_client.table.assert_called_with("claims")
    chain.insert.assert_called_once_with(claim_data)
    chain.execute.assert_called()


@pytest.mark.asyncio
async def test_save_claim_raises_on_empty_response():
    """save_claim() raises RuntimeError if Supabase returns no data."""
    provider, mock_client = make_provider()
    make_chain(mock_client, return_data=[])

    with pytest.raises(RuntimeError, match="no data"):
        await provider.save_claim({"id": "CLM-TEST", "pnr": "XYZ"})


# ── update_claim_status ───────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_update_claim_status_calls_update():
    """update_claim_status() calls .update({'status': ...}).eq('id', ...).execute()."""
    provider, mock_client = make_provider()
    chain, _ = make_chain(mock_client)

    await provider.update_claim_status("CLM-20260522-AB12", "AWAITING_REVIEW")

    mock_client.table.assert_called_with("claims")
    chain.update.assert_called_once_with({"status": "AWAITING_REVIEW"})
    chain.eq.assert_called_once_with("id", "CLM-20260522-AB12")
    chain.execute.assert_called()


@pytest.mark.asyncio
async def test_update_claim_status_resolved():
    """update_claim_status() works with RESOLVED status (agent approve flow)."""
    provider, mock_client = make_provider()
    chain, _ = make_chain(mock_client)

    await provider.update_claim_status("CLM-TEST", "RESOLVED")

    chain.update.assert_called_once_with({"status": "RESOLVED"})


# ── get_claim ─────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_get_claim_returns_dict_when_found():
    """get_claim() returns the claim dict when Supabase finds a row."""
    provider, mock_client = make_provider()
    expected = {"id": "CLM-20260522-AB12", "pnr": "ABC123", "routing_lane": 1}
    make_chain(mock_client, return_data=[expected])

    result = await provider.get_claim("CLM-20260522-AB12")

    assert result == expected
    assert result["pnr"] == "ABC123"


@pytest.mark.asyncio
async def test_get_claim_returns_none_when_not_found():
    """get_claim() returns None when no row matches the claim_id."""
    provider, mock_client = make_provider()
    make_chain(mock_client, return_data=[])

    result = await provider.get_claim("CLM-DOESNOTEXIST")

    assert result is None


# ── get_claim_count ───────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_get_claim_count_returns_integer():
    """get_claim_count() returns the count from Supabase response."""
    provider, mock_client = make_provider()
    make_chain(mock_client, return_data=[], count=2)

    result = await provider.get_claim_count("ABC123", days=30)

    assert result == 2
    mock_client.table.assert_called_with("claims")


@pytest.mark.asyncio
async def test_get_claim_count_zero_for_new_pnr():
    """get_claim_count() returns 0 for a PNR with no prior claims."""
    provider, mock_client = make_provider()
    make_chain(mock_client, return_data=[], count=0)

    result = await provider.get_claim_count("NEWPNR", days=30)

    assert result == 0


@pytest.mark.asyncio
async def test_get_claim_count_passes_pnr_filter():
    """get_claim_count() filters by pnr using .eq()."""
    provider, mock_client = make_provider()
    chain, _ = make_chain(mock_client, count=3)

    await provider.get_claim_count("FRAUD1", days=30)

    chain.eq.assert_any_call("pnr", "FRAUD1")


# ── get_recent_hashes ─────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_get_recent_hashes_returns_list():
    """get_recent_hashes() returns a list of hash strings."""
    provider, mock_client = make_provider()
    make_chain(
        mock_client,
        return_data=[
            {"hash_value": "aabbccdd"},
            {"hash_value": "11223344"},
        ],
    )

    result = await provider.get_recent_hashes("ABC123")

    assert result == ["aabbccdd", "11223344"]


@pytest.mark.asyncio
async def test_get_recent_hashes_empty_for_new_pnr():
    """get_recent_hashes() returns [] for a PNR with no prior images."""
    provider, mock_client = make_provider()
    make_chain(mock_client, return_data=[])

    result = await provider.get_recent_hashes("NEWPNR")

    assert result == []


@pytest.mark.asyncio
async def test_get_recent_hashes_filters_by_pnr():
    """get_recent_hashes() queries image_hashes table filtered by pnr."""
    provider, mock_client = make_provider()
    chain, _ = make_chain(mock_client, return_data=[])

    await provider.get_recent_hashes("XYZ789")

    mock_client.table.assert_called_with("image_hashes")
    chain.eq.assert_called_once_with("pnr", "XYZ789")
