"""Tests for report management routes."""
from datetime import date

import pytest

from app import app
from calculations import compute_all
from models import Client, Report, db


@pytest.fixture
def isolated_app(tmp_path):
    test_db_path = tmp_path / "test_routes.db"
    original_uri = app.config.get("SQLALCHEMY_DATABASE_URI")
    app.config["SQLALCHEMY_DATABASE_URI"] = f"sqlite:///{test_db_path}"
    app.config["TESTING"] = True
    with app.app_context():
        db.create_all()
        yield app
        db.session.remove()
        db.drop_all()
    app.config["SQLALCHEMY_DATABASE_URI"] = original_uri


def _seed(app_context):
    """Insert a minimal client + report; return (client_id, report_id)."""
    client = Client(
        household_name="Delete Test Family",
        primary_first="Alex", primary_last="Tester",
        primary_dob=date(1980, 1, 1), primary_ssn_last4="0000",
        monthly_inflow=20000, monthly_outflow=15000,
        total_insurance_deductibles=0,
        accounts_json=[{
            "key": "c1_ira", "owner": "CLIENT1", "category": "RETIREMENT",
            "label": "IRA", "institution": "Schwab", "last_four": "0001",
            "is_investment": True,
        }],
        liabilities_json=[],
        properties_json=[],
    )
    db.session.add(client)
    db.session.flush()

    inputs = {
        "cashflow": {
            "inflow": 20000, "outflow": 15000,
            "private_reserve_balance": 60000, "schwab_investment_balance": 100000,
        },
        "account_balances": {"c1_ira": {"balance": 200000, "cash_balance": 2000}},
        "liability_balances": {},
        "property_values": {},
    }
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
        period_label="2026-Q1",
        inputs_json=inputs,
        calculated_json=compute_all(client_data, inputs),
    )
    db.session.add(report)
    db.session.commit()
    return client.id, report.id


def test_delete_report_removes_it_and_redirects(isolated_app):
    """POST /reports/<id>/delete deletes the report and redirects to client detail."""
    with isolated_app.app_context():
        client_id, report_id = _seed(isolated_app)

    with isolated_app.test_client() as c:
        with c.session_transaction() as s:
            s["authed"] = True
        resp = c.post(f"/reports/{report_id}/delete")

    assert resp.status_code == 302
    assert f"/clients/{client_id}" in resp.headers["Location"]

    with isolated_app.app_context():
        assert Report.query.get(report_id) is None


def test_delete_report_requires_login(isolated_app):
    """Delete route redirects unauthenticated users to login."""
    with isolated_app.app_context():
        _, report_id = _seed(isolated_app)

    with isolated_app.test_client() as c:
        resp = c.post(f"/reports/{report_id}/delete")

    assert resp.status_code == 302
    assert "/login" in resp.headers["Location"]


def test_delete_nonexistent_report_returns_404(isolated_app):
    """POST to a non-existent report ID returns 404."""
    with isolated_app.test_client() as c:
        with c.session_transaction() as s:
            s["authed"] = True
        resp = c.post("/reports/99999/delete")

    assert resp.status_code == 404


def test_delete_does_not_affect_other_reports(isolated_app):
    """Deleting one report leaves other reports for the same client intact."""
    with isolated_app.app_context():
        client_id, report_id_1 = _seed(isolated_app)
        # Add a second report for the same client.
        with isolated_app.app_context():
            client = Client.query.get(client_id)
            inputs = {
                "cashflow": {
                    "inflow": 21000, "outflow": 15000,
                    "private_reserve_balance": 65000, "schwab_investment_balance": 105000,
                },
                "account_balances": {"c1_ira": {"balance": 210000, "cash_balance": 2100}},
                "liability_balances": {},
                "property_values": {},
            }
            client_data = {
                "monthly_outflow": client.monthly_outflow,
                "total_insurance_deductibles": client.total_insurance_deductibles,
                "private_reserve_target_override": client.private_reserve_target_override,
                "accounts": client.accounts_json,
                "liabilities": client.liabilities_json,
                "properties": client.properties_json,
            }
            report2 = Report(
                client_id=client_id, period_label="2026-Q2",
                inputs_json=inputs, calculated_json=compute_all(client_data, inputs),
            )
            db.session.add(report2)
            db.session.commit()
            report_id_2 = report2.id

    with isolated_app.test_client() as c:
        with c.session_transaction() as s:
            s["authed"] = True
        c.post(f"/reports/{report_id_1}/delete")

    with isolated_app.app_context():
        assert Report.query.get(report_id_1) is None
        assert Report.query.get(report_id_2) is not None
