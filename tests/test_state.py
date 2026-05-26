"""Unit tests for ClaimState — T-020"""
from backend.graph.state import ClaimState


def test_default_state():
    s = ClaimState(session_id="s1", passenger_message="hi")
    assert s.routing_lane is None
    assert s.execution_completed is False
    assert s.fraud_score == 0.0


def test_set_error():
    s = ClaimState(session_id="s1", passenger_message="hi")
    s.set_error("something failed")
    assert s.error == "something failed"
    assert s.execution_completed is True


def test_add_debug():
    s = ClaimState(session_id="s1", passenger_message="hi")
    s.add_debug("phase", "a4")
    assert s.debug["phase"] == "a4"


def test_lane1_eligible_low_value():
    """Low value, non-luxury, low fraud → lane 1."""
    s = ClaimState(session_id="s1", passenger_message="hi")
    s.compensation_estimate_usd = 50.0
    s.is_luxury = False
    s.fraud_score = 0.1
    assert s.is_lane1_eligible() is True


def test_lane1_ineligible_high_value():
    """High value → lane 2."""
    s = ClaimState(session_id="s1", passenger_message="hi")
    s.compensation_estimate_usd = 200.0
    s.is_luxury = False
    s.fraud_score = 0.0
    assert s.is_lane1_eligible() is False


def test_lane1_ineligible_luxury():
    """Luxury bag → lane 2 regardless of value."""
    s = ClaimState(session_id="s1", passenger_message="hi")
    s.compensation_estimate_usd = 50.0
    s.is_luxury = True
    s.fraud_score = 0.0
    assert s.is_lane1_eligible() is False


def test_lane1_ineligible_high_fraud():
    """High fraud score → lane 2."""
    s = ClaimState(session_id="s1", passenger_message="hi")
    s.compensation_estimate_usd = 30.0
    s.is_luxury = False
    s.fraud_score = 0.8
    assert s.is_lane1_eligible() is False
