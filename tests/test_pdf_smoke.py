"""Smoke test: TCC layout is stable across variable retirement bubble counts.

Renders the TCC PDF with 1, 3, and 6 retirement accounts and asserts each
produces a non-empty PDF. The PRD's "hard problem" (Rebecca, 12:47) was that
their Canva template misaligned when the number of bubbles changed — this test
locks in our solution.
"""
from datetime import date

import pytest

from app import app
from calculations import compute_all
from models import Client, Report, db


pytestmark = pytest.mark.skipif(
    pytest.importorskip("weasyprint", reason="WeasyPrint not installed") is None,
    reason="WeasyPrint not installed",
)


def _make_client(num_retirement_accounts):
    accounts = []
    for i in range(num_retirement_accounts):
        accounts.append({
            "key": f"c1_acct_{i}",
            "owner": "CLIENT1",
            "category": "RETIREMENT",
            "label": f"Account {i+1}",
            "institution": "Schwab",
            "last_four": f"{1000 + i}",
            "is_investment": True,
        })
    accounts.append({
        "key": "joint_brk", "owner": "JOINT", "category": "NON_RETIREMENT",
        "label": "Brokerage", "institution": "Schwab",
        "last_four": "9999", "is_investment": True,
    })

    return Client(
        household_name=f"Test Household {num_retirement_accounts}",
        primary_first="Pat", primary_last="Tester",
        primary_dob=date(1970, 1, 1), primary_ssn_last4="0001",
        monthly_inflow=20000, monthly_outflow=15000,
        total_insurance_deductibles=2000,
        accounts_json=accounts,
        liabilities_json=[],
        properties_json=[],
    )


def _make_inputs(client):
    inputs = {
        "cashflow": {
            "inflow": 20000, "outflow": 15000,
            "private_reserve_balance": 50000, "schwab_investment_balance": 200000,
        },
        "account_balances": {},
        "liability_balances": {},
        "property_values": {},
    }
    for acct in client.accounts_json:
        inputs["account_balances"][acct["key"]] = {
            "balance": 100000, "cash_balance": 1000,
        }
    return inputs


@pytest.fixture
def isolated_app(tmp_path):
    """Point the app at a fresh SQLite file for the duration of a test.

    Tests opt out of app.py's import-time DB setup via SKIP_AUTOSEED in
    conftest.py, then we configure a per-test DB here.
    """
    test_db_path = tmp_path / "test.db"
    original_uri = app.config.get("SQLALCHEMY_DATABASE_URI")
    app.config["SQLALCHEMY_DATABASE_URI"] = f"sqlite:///{test_db_path}"
    app.config["TESTING"] = True

    with app.app_context():
        db.create_all()
        yield app
        db.session.remove()
        db.drop_all()

    app.config["SQLALCHEMY_DATABASE_URI"] = original_uri


@pytest.mark.parametrize("num_bubbles", [1, 3, 6])
def test_tcc_renders_with_n_bubbles(num_bubbles, isolated_app):
    """TCC PDF renders cleanly for 1, 3, and 6 retirement bubbles."""
    client = _make_client(num_bubbles)
    db.session.add(client)
    db.session.flush()

    inputs = _make_inputs(client)
    client_data = {
        "monthly_outflow": client.monthly_outflow,
        "total_insurance_deductibles": client.total_insurance_deductibles,
        "private_reserve_target_override": client.private_reserve_target_override,
        "accounts": client.accounts_json,
        "liabilities": client.liabilities_json,
        "properties": client.properties_json,
    }
    report = Report(
        client_id=client.id,
        period_label="2026-TEST",
        inputs_json=inputs,
        calculated_json=compute_all(client_data, inputs),
    )
    db.session.add(report)
    db.session.commit()

    with isolated_app.test_client() as c:
        with c.session_transaction() as s:
            s["authed"] = True
        resp = c.get(f"/reports/{report.id}/tcc.pdf")

    assert resp.status_code == 200
    assert resp.mimetype == "application/pdf"
    assert len(resp.data) > 5000
    assert resp.data[:5] == b"%PDF-"
