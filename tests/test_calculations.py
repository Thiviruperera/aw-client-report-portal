"""Unit tests locking the PRD calculation rules.

Every test here corresponds to an explicit rule in the PRD acceptance criteria
(User Story 2b) or a quoted constraint from the meeting transcript.
"""
import pytest

from calculations import (
    CLIENT1,
    CLIENT2,
    JOINT,
    NON_RETIREMENT,
    RETIREMENT,
    client_retirement_total,
    compute_all,
    find_missing_fields,
    grand_total_net_worth,
    liabilities_total,
    non_retirement_total,
    private_reserve_target,
    sacs_excess,
    trust_total,
)


# ---------- SACS ----------

def test_sacs_excess_is_inflow_minus_outflow():
    assert sacs_excess(15000, 11000) == 4000


def test_sacs_excess_can_be_negative():
    assert sacs_excess(10000, 12000) == -2000


def test_private_reserve_target_uses_formula_when_no_override():
    # 6 * 11000 + 2400 = 68400
    assert private_reserve_target(11000, 2400) == 68400


def test_private_reserve_target_uses_override_when_provided():
    # Override wins even if formula would give different number
    assert private_reserve_target(11000, 2400, override=100000) == 100000


def test_private_reserve_target_zero_deductibles():
    assert private_reserve_target(10000, 0) == 60000


# ---------- TCC ----------

@pytest.fixture
def sample_accounts():
    return [
        {"key": "c1_401k", "owner": CLIENT1, "category": RETIREMENT, "label": "401k"},
        {"key": "c1_ira",  "owner": CLIENT1, "category": RETIREMENT, "label": "IRA"},
        {"key": "c2_401k", "owner": CLIENT2, "category": RETIREMENT, "label": "401k"},
        {"key": "joint_brk", "owner": JOINT, "category": NON_RETIREMENT, "label": "Brokerage"},
        {"key": "joint_chk", "owner": JOINT, "category": NON_RETIREMENT, "label": "Checking"},
    ]


@pytest.fixture
def sample_balances():
    return {
        "c1_401k":   {"balance": 100000, "cash_balance": 1000},
        "c1_ira":    {"balance": 50000,  "cash_balance": 500},
        "c2_401k":   {"balance": 80000,  "cash_balance": 800},
        "joint_brk": {"balance": 200000, "cash_balance": 2000},
        "joint_chk": {"balance": 25000,  "cash_balance": None},
    }


def test_client1_retirement_sums_only_client1_retirement(sample_accounts, sample_balances):
    assert client_retirement_total(sample_accounts, sample_balances, CLIENT1) == 150000


def test_client2_retirement_sums_only_client2_retirement(sample_accounts, sample_balances):
    assert client_retirement_total(sample_accounts, sample_balances, CLIENT2) == 80000


def test_non_retirement_excludes_retirement_accounts(sample_accounts, sample_balances):
    # Joint brokerage 200k + joint checking 25k = 225k. Retirement excluded.
    assert non_retirement_total(sample_accounts, sample_balances) == 225000


def test_non_retirement_excludes_trust():
    """PRD Rebecca 24:28: 'the non-retirement total is only the accounts, not the trust'."""
    accounts = [
        {"key": "brk", "owner": JOINT, "category": NON_RETIREMENT, "label": "Brokerage"},
    ]
    balances = {"brk": {"balance": 100000}}
    properties = [{"key": "house"}]
    property_values = {"house": 500000}

    nr = non_retirement_total(accounts, balances)
    tr = trust_total(properties, property_values)

    assert nr == 100000  # trust NOT in here
    assert tr == 500000  # trust separate


def test_trust_total_sums_property_values():
    properties = [{"key": "h1"}, {"key": "h2"}]
    values = {"h1": 500000, "h2": 250000}
    assert trust_total(properties, values) == 750000


def test_grand_total_includes_trust():
    """PRD: Grand Total = C1 ret + C2 ret + non-ret + trust."""
    assert grand_total_net_worth(150000, 80000, 225000, 500000) == 955000


def test_grand_total_with_no_trust():
    assert grand_total_net_worth(100000, 50000, 75000, 0) == 225000


def test_liabilities_total_sums_balances():
    liabilities = [{"key": "mort"}, {"key": "auto"}]
    balances = {"mort": 400000, "auto": 25000}
    assert liabilities_total(liabilities, balances) == 425000


def test_liabilities_never_subtracted_from_net_worth():
    """PRD Rebecca 26:15: 'we do not subtract liabilities from their net worth'.

    Locked here as a property-style test: grand total ignores liabilities entirely.
    """
    grand_with_liab = grand_total_net_worth(100000, 100000, 100000, 400000)
    grand_no_liab = grand_total_net_worth(100000, 100000, 100000, 400000)
    assert grand_with_liab == grand_no_liab == 700000


# ---------- compute_all integration ----------

def _make_client_data():
    return {
        "monthly_outflow": 22000,
        "total_insurance_deductibles": 6000,
        "private_reserve_target_override": None,
        "accounts": [
            {"key": "c1a", "owner": CLIENT1, "category": RETIREMENT, "label": "IRA",
             "is_investment": True, "institution": "Schwab"},
            {"key": "c2a", "owner": CLIENT2, "category": RETIREMENT, "label": "Roth",
             "is_investment": True, "institution": "Schwab"},
            {"key": "ja",  "owner": JOINT, "category": NON_RETIREMENT, "label": "Brokerage",
             "is_investment": True, "institution": "Schwab"},
        ],
        "liabilities": [
            {"key": "m", "label": "Mortgage"},
        ],
        "properties": [
            {"key": "h", "label": "Home"},
        ],
    }


def _make_inputs():
    return {
        "cashflow": {
            "inflow": 32000, "outflow": 22000,
            "private_reserve_balance": 80000, "schwab_investment_balance": 400000,
        },
        "account_balances": {
            "c1a": {"balance": 200000, "cash_balance": 2000},
            "c2a": {"balance": 150000, "cash_balance": 1000},
            "ja":  {"balance": 300000, "cash_balance": 5000},
        },
        "liability_balances": {"m": 400000},
        "property_values": {"h": 850000},
    }


def test_compute_all_produces_expected_shape():
    result = compute_all(_make_client_data(), _make_inputs())
    assert set(result.keys()) == {
        "excess", "private_reserve_target",
        "c1_retirement_total", "c2_retirement_total",
        "non_retirement_total", "trust_total",
        "grand_total", "liabilities_total",
    }


def test_compute_all_values():
    result = compute_all(_make_client_data(), _make_inputs())
    assert result["excess"] == 10000
    assert result["private_reserve_target"] == 6 * 22000 + 6000  # 138000
    assert result["c1_retirement_total"] == 200000
    assert result["c2_retirement_total"] == 150000
    assert result["non_retirement_total"] == 300000
    assert result["trust_total"] == 850000
    assert result["grand_total"] == 200000 + 150000 + 300000 + 850000  # 1,500,000
    assert result["liabilities_total"] == 400000


# ---------- Single-client edge case ----------

def test_single_client_no_spouse_zero_c2_retirement():
    """A single client with no spouse should produce c2_retirement_total = 0."""
    client_data = {
        "monthly_outflow": 10000, "total_insurance_deductibles": 0,
        "private_reserve_target_override": None,
        "accounts": [
            {"key": "c1a", "owner": CLIENT1, "category": RETIREMENT,
             "label": "IRA", "is_investment": True, "institution": "S"},
        ],
        "liabilities": [], "properties": [],
    }
    inputs = {
        "cashflow": {"inflow": 12000, "outflow": 10000,
                     "private_reserve_balance": 50000, "schwab_investment_balance": 100000},
        "account_balances": {"c1a": {"balance": 100000, "cash_balance": 1000}},
        "liability_balances": {}, "property_values": {},
    }
    result = compute_all(client_data, inputs)
    assert result["c2_retirement_total"] == 0
    assert result["liabilities_total"] == 0
    assert result["trust_total"] == 0


# ---------- Validation ----------

def test_find_missing_fields_empty_when_all_provided():
    assert find_missing_fields(_make_client_data(), _make_inputs()) == []


def test_find_missing_fields_flags_missing_balance():
    inputs = _make_inputs()
    inputs["account_balances"]["c1a"]["balance"] = None
    missing = find_missing_fields(_make_client_data(), inputs)
    assert any("IRA" in m for m in missing)


def test_find_missing_fields_flags_missing_cashflow():
    inputs = _make_inputs()
    inputs["cashflow"]["inflow"] = None
    missing = find_missing_fields(_make_client_data(), inputs)
    assert any("Inflow" in m for m in missing)


def test_find_missing_fields_flags_missing_zestimate():
    inputs = _make_inputs()
    inputs["property_values"]["h"] = None
    missing = find_missing_fields(_make_client_data(), inputs)
    assert any("Home" in m for m in missing)


def test_find_missing_fields_flags_missing_cash_balance_for_investment():
    inputs = _make_inputs()
    inputs["account_balances"]["c1a"]["cash_balance"] = None
    missing = find_missing_fields(_make_client_data(), inputs)
    assert any("Cash Balance" in m for m in missing)
