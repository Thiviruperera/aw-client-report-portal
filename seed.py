"""Seed one demo client with a complete profile and a prior-quarter report.

Run with: python seed.py
The CLI entry drops and recreates the database; the seed_demo_data() function
is idempotent and is also called automatically by app.py on first boot.
"""
import os
from datetime import date, datetime

# Suppress app.py's import-time auto-seed; the CLI entry handles it explicitly.
os.environ.setdefault("SKIP_AUTOSEED", "1")

from calculations import compute_all  # noqa: E402
from models import Client, Report, db  # noqa: E402


DEMO_CLIENT = dict(
    household_name="Henderson Family",
    primary_first="James",
    primary_last="Henderson",
    primary_dob=date(1973, 6, 14),
    primary_ssn_last4="4821",
    spouse_first="Sarah",
    spouse_last="Henderson",
    spouse_dob=date(1976, 11, 2),
    spouse_ssn_last4="9314",
    monthly_inflow=32000,
    monthly_outflow=22000,
    total_insurance_deductibles=6000,
    private_reserve_target_override=None,
    accounts_json=[
        {"key": "c1_401k", "owner": "CLIENT1", "category": "RETIREMENT",
         "label": "401(k)", "institution": "Schwab", "last_four": "1042", "is_investment": True},
        {"key": "c1_roth", "owner": "CLIENT1", "category": "RETIREMENT",
         "label": "Roth IRA", "institution": "Schwab", "last_four": "7831", "is_investment": True},
        {"key": "c1_ira", "owner": "CLIENT1", "category": "RETIREMENT",
         "label": "Traditional IRA", "institution": "Schwab", "last_four": "5510", "is_investment": True},
        {"key": "c2_401k", "owner": "CLIENT2", "category": "RETIREMENT",
         "label": "401(k)", "institution": "Vanguard", "last_four": "2298", "is_investment": True},
        {"key": "c2_roth", "owner": "CLIENT2", "category": "RETIREMENT",
         "label": "Roth IRA", "institution": "Schwab", "last_four": "6604", "is_investment": True},
        {"key": "joint_brokerage", "owner": "JOINT", "category": "NON_RETIREMENT",
         "label": "Brokerage", "institution": "Schwab", "last_four": "0917", "is_investment": True},
        {"key": "joint_checking", "owner": "JOINT", "category": "NON_RETIREMENT",
         "label": "Checking", "institution": "Pinnacle Bank", "last_four": "3344", "is_investment": False},
        {"key": "joint_savings", "owner": "JOINT", "category": "NON_RETIREMENT",
         "label": "Private Reserve (HYSA)", "institution": "Pinnacle Bank", "last_four": "8821", "is_investment": False},
    ],
    liabilities_json=[
        {"key": "mortgage", "label": "Mortgage", "institution": "Pinnacle Bank",
         "interest_rate": 4.25, "last_four": "5577"},
        {"key": "auto", "label": "Auto Loan", "institution": "Pinnacle Bank",
         "interest_rate": 6.50, "last_four": "1209"},
    ],
    properties_json=[
        {"key": "primary_residence", "label": "Primary Residence",
         "address": "1428 Peachtree Lane NE, Atlanta, GA 30309"},
    ],
)

PRIOR_INPUTS = {
    "cashflow": {
        "inflow": 32000,
        "outflow": 22000,
        "private_reserve_balance": 84500,
        "schwab_investment_balance": 412300,
    },
    "account_balances": {
        "c1_401k":          {"balance": 418200, "cash_balance": 4200},
        "c1_roth":          {"balance": 92400,  "cash_balance": 1100},
        "c1_ira":           {"balance": 156800, "cash_balance": 2300},
        "c2_401k":          {"balance": 287100, "cash_balance": 3500},
        "c2_roth":          {"balance": 71500,  "cash_balance": 800},
        "joint_brokerage":  {"balance": 412300, "cash_balance": 8900},
        "joint_checking":   {"balance": 18400,  "cash_balance": None},
        "joint_savings":    {"balance": 84500,  "cash_balance": None},
    },
    "liability_balances": {
        "mortgage": 412000,
        "auto": 28400,
    },
    "property_values": {
        "primary_residence": 875000,
    },
}


def seed_demo_data():
    """Insert the demo client + prior-quarter report. Skips if any client exists."""
    if Client.query.first() is not None:
        print("Database already has clients — skipping seed.")
        return None

    client = Client(**DEMO_CLIENT)
    db.session.add(client)
    db.session.flush()

    client_data = {
        "monthly_outflow": client.monthly_outflow,
        "total_insurance_deductibles": client.total_insurance_deductibles,
        "private_reserve_target_override": client.private_reserve_target_override,
        "accounts": client.accounts_json,
        "liabilities": client.liabilities_json,
        "properties": client.properties_json,
    }
    calculated = compute_all(client_data, PRIOR_INPUTS)

    prior = Report(
        client_id=client.id,
        period_label="2026-Q1",
        inputs_json=PRIOR_INPUTS,
        calculated_json=calculated,
        created_at=datetime(2026, 3, 30, 14, 0),
    )
    db.session.add(prior)
    db.session.commit()

    print(f"Seeded client {client.id}: {client.household_name}")
    print(f"Seeded prior report {prior.id}: {prior.period_label}")
    print(f"  Grand Total Net Worth: ${calculated['grand_total']:,}")
    return client


def seed():
    """CLI entry point — drops and recreates everything."""
    from app import app
    with app.app_context():
        db.drop_all()
        db.create_all()
        seed_demo_data()


if __name__ == "__main__":
    seed()
