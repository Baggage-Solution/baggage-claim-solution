"""
Unit tests for ClaimState — T-020.

Comprehensive coverage of:
  - Default field values
  - State helper methods (set_error, add_debug, is_lane1_eligible)
  - All 5 lane-routing scenarios via is_lane1_eligible()
  - Edge cases: boundary values, combined flags

No providers, no DB, no API calls — pure Python state logic only.
"""

from __future__ import annotations

import pytest

from backend.graph.state import ClaimState


# ── Helpers ───────────────────────────────────────────────────────────────────


def make_state(**kwargs) -> ClaimState:
    """Create a ClaimState with sensible defaults, overridable via kwargs."""
    defaults = {
        "session_id": "test-session",
        "passenger_message": "my bag is damaged",
    }
    defaults.update(kwargs)
    return ClaimState(**defaults)


# ── Default-value tests ───────────────────────────────────────────────────────


def test_default_routing_lane_is_none():
    """routing_lane defaults to None — not yet decided by A4."""
    s = make_state()
    assert s.routing_lane is None


def test_default_execution_completed_is_false():
    """execution_completed defaults to False — pipeline not yet done."""
    s = make_state()
    assert s.execution_completed is False


def test_default_fraud_score_is_zero():
    """fraud_score defaults to 0.0 — innocent until proven guilty."""
    s = make_state()
    assert s.fraud_score == 0.0


def test_default_fraud_flags_is_empty_list():
    """fraud_flags defaults to an empty list."""
    s = make_state()
    assert s.fraud_flags == []


def test_default_image_paths_is_empty_list():
    """image_paths defaults to an empty list."""
    s = make_state()
    assert s.image_paths == []


def test_default_damage_types_is_empty_list():
    """damage_types defaults to an empty list."""
    s = make_state()
    assert s.damage_types == []


def test_default_conversation_step():
    """conversation_step defaults to 'greeting'."""
    s = make_state()
    assert s.conversation_step == "greeting"


def test_default_is_luxury_is_false():
    """is_luxury defaults to False."""
    s = make_state()
    assert s.is_luxury is False


def test_default_severity_score_is_zero():
    """severity_score defaults to 0.0."""
    s = make_state()
    assert s.severity_score == 0.0


def test_default_compensation_estimate_is_zero():
    """compensation_estimate_usd defaults to 0.0."""
    s = make_state()
    assert s.compensation_estimate_usd == 0.0


def test_default_notification_sent_is_false():
    """notification_sent defaults to False."""
    s = make_state()
    assert s.notification_sent is False


def test_default_hitl_queued_is_false():
    """hitl_queued defaults to False."""
    s = make_state()
    assert s.hitl_queued is False


def test_default_re_request_tag_is_false():
    """re_request_tag defaults to False."""
    s = make_state()
    assert s.re_request_tag is False


def test_default_re_request_damage_is_false():
    """re_request_damage defaults to False."""
    s = make_state()
    assert s.re_request_damage is False


def test_default_tag_data_complete_is_false():
    """tag_data_complete defaults to False."""
    s = make_state()
    assert s.tag_data_complete is False


def test_default_tag_manually_entered_is_false():
    """tag_manually_entered defaults to False."""
    s = make_state()
    assert s.tag_manually_entered is False


def test_default_not_a_bag_is_false():
    """not_a_bag defaults to False — images assumed to be bags until A2 says otherwise."""
    s = make_state()
    assert s.not_a_bag is False


def test_default_non_bag_attempts_is_zero():
    """non_bag_attempts defaults to 0."""
    s = make_state()
    assert s.non_bag_attempts == 0


def test_default_error_is_none():
    """error defaults to None — no error initially."""
    s = make_state()
    assert s.error is None


def test_default_debug_is_empty_dict():
    """debug defaults to an empty dict."""
    s = make_state()
    assert s.debug == {}


# ── set_error tests ───────────────────────────────────────────────────────────


def test_set_error_stores_message():
    """set_error() stores the error message in state.error."""
    s = make_state()
    s.set_error("A2 failed: image too dark")
    assert s.error == "A2 failed: image too dark"


def test_set_error_marks_execution_completed():
    """set_error() sets execution_completed=True to stop the graph."""
    s = make_state()
    s.set_error("something went wrong")
    assert s.execution_completed is True


def test_set_error_can_be_called_multiple_times():
    """set_error() overwrites previous error message."""
    s = make_state()
    s.set_error("first error")
    s.set_error("second error — more specific")
    assert s.error == "second error — more specific"
    assert s.execution_completed is True


def test_set_error_empty_string():
    """set_error() with empty string still marks execution_completed."""
    s = make_state()
    s.set_error("")
    assert s.error == ""
    assert s.execution_completed is True


# ── add_debug tests ───────────────────────────────────────────────────────────


def test_add_debug_stores_key_value():
    """add_debug() writes a key/value pair to the debug dict."""
    s = make_state()
    s.add_debug("a2_images_processed", 3)
    assert s.debug["a2_images_processed"] == 3


def test_add_debug_multiple_entries():
    """add_debug() can store multiple distinct keys."""
    s = make_state()
    s.add_debug("phase", "a4")
    s.add_debug("fraud_score", 0.2)
    s.add_debug("routing_lane", 1)
    assert s.debug["phase"] == "a4"
    assert s.debug["fraud_score"] == 0.2
    assert s.debug["routing_lane"] == 1


def test_add_debug_overwrites_existing_key():
    """add_debug() overwrites an existing key silently."""
    s = make_state()
    s.add_debug("counter", 1)
    s.add_debug("counter", 2)
    assert s.debug["counter"] == 2


def test_add_debug_accepts_any_json_serialisable_value():
    """add_debug() can store lists, dicts, booleans, None."""
    s = make_state()
    s.add_debug("flags", ["phash_duplicate"])
    s.add_debug("nested", {"key": "val"})
    s.add_debug("ok", True)
    s.add_debug("nothing", None)
    assert s.debug["flags"] == ["phash_duplicate"]
    assert s.debug["nested"] == {"key": "val"}
    assert s.debug["ok"] is True
    assert s.debug["nothing"] is None


# ── is_lane1_eligible — Scenario 1: Standard bag, low value → Lane 1 ─────────


def test_scenario1_standard_bag_low_value_is_lane1():
    """
    Scenario 1 (from architecture doc):
    Standard bag, low compensation ($50), no luxury, no fraud → Lane 1.
    """
    s = make_state()
    s.compensation_estimate_usd = 50.0
    s.is_luxury = False
    s.fraud_score = 0.0
    assert s.is_lane1_eligible() is True


def test_scenario1_at_exact_threshold_is_lane1():
    """Compensation exactly at $100 threshold is still eligible for Lane 1."""
    s = make_state()
    s.compensation_estimate_usd = 100.0
    s.is_luxury = False
    s.fraud_score = 0.0
    assert s.is_lane1_eligible() is True


# ── is_lane1_eligible — Scenario 2: High value → Lane 2 ─────────────────────


def test_scenario2_high_value_is_not_lane1():
    """
    Scenario 2: Compensation above $100 → must route to Lane 2.
    """
    s = make_state()
    s.compensation_estimate_usd = 101.0
    s.is_luxury = False
    s.fraud_score = 0.0
    assert s.is_lane1_eligible() is False


def test_scenario2_very_high_value_is_not_lane1():
    """$500 claim is well above Lane 1 threshold."""
    s = make_state()
    s.compensation_estimate_usd = 500.0
    s.is_luxury = False
    s.fraud_score = 0.0
    assert s.is_lane1_eligible() is False


# ── is_lane1_eligible — Scenario 3: Luxury bag → Lane 2 ──────────────────────


def test_scenario3_luxury_bag_is_not_lane1():
    """
    Scenario 3: Luxury bag always routes to Lane 2,
    even when compensation is well below $100 and fraud_score is zero.
    """
    s = make_state()
    s.compensation_estimate_usd = 40.0
    s.is_luxury = True
    s.fraud_score = 0.0
    assert s.is_lane1_eligible() is False


def test_scenario3_luxury_at_zero_compensation_is_not_lane1():
    """Luxury flag alone is sufficient to disqualify Lane 1, even at $0."""
    s = make_state()
    s.compensation_estimate_usd = 0.0
    s.is_luxury = True
    s.fraud_score = 0.0
    assert s.is_lane1_eligible() is False


# ── is_lane1_eligible — Scenario 4: pHash duplicate → Lane 2 ─────────────────


def test_scenario4_phash_fraud_score_high_is_not_lane1():
    """
    Scenario 4: pHash duplicate detected → fraud_score >= 0.5 → Lane 2.
    The actual flag injection is A4's job; here we just verify the threshold.
    """
    s = make_state()
    s.compensation_estimate_usd = 60.0
    s.is_luxury = False
    s.fraud_score = 0.5  # at or above threshold
    assert s.is_lane1_eligible() is False


def test_scenario4_fraud_score_just_below_threshold_is_lane1():
    """fraud_score = 0.49 is still below the 0.5 threshold → Lane 1."""
    s = make_state()
    s.compensation_estimate_usd = 60.0
    s.is_luxury = False
    s.fraud_score = 0.49
    assert s.is_lane1_eligible() is True


# ── is_lane1_eligible — Scenario 5: High frequency → Lane 2 ──────────────────


def test_scenario5_high_frequency_fraud_score_is_not_lane1():
    """
    Scenario 5: High claim frequency pushes fraud_score above 0.5 → Lane 2.
    Tests the outcome of A4's frequency check (not the check itself).
    """
    s = make_state()
    s.compensation_estimate_usd = 60.0
    s.is_luxury = False
    s.fraud_score = 0.6  # frequency check added 0.3 → total 0.6
    assert s.is_lane1_eligible() is False


# ── is_lane1_eligible — Combined flag tests ───────────────────────────────────


def test_combined_luxury_and_high_value_is_not_lane1():
    """Both luxury and high value together → Lane 2 (either alone would suffice)."""
    s = make_state()
    s.compensation_estimate_usd = 200.0
    s.is_luxury = True
    s.fraud_score = 0.0
    assert s.is_lane1_eligible() is False


def test_combined_all_flags_set_is_not_lane1():
    """All disqualifying flags set simultaneously → still Lane 2."""
    s = make_state()
    s.compensation_estimate_usd = 300.0
    s.is_luxury = True
    s.fraud_score = 0.9
    assert s.is_lane1_eligible() is False


def test_zero_compensation_non_luxury_zero_fraud_is_lane1():
    """$0 estimate, non-luxury, no fraud — minimal valid Lane 1 claim."""
    s = make_state()
    s.compensation_estimate_usd = 0.0
    s.is_luxury = False
    s.fraud_score = 0.0
    assert s.is_lane1_eligible() is True