"""Pure functions for SACS and TCC calculations.

All money values are integer dollars. No float math.
Locked by tests in tests/test_calculations.py.
Rules sourced from PRD acceptance criteria (User Story 2b).
"""

CLIENT1 = "CLIENT1"
CLIENT2 = "CLIENT2"
JOINT = "JOINT"

RETIREMENT = "RETIREMENT"
NON_RETIREMENT = "NON_RETIREMENT"


def sacs_excess(monthly_inflow, monthly_outflow):
    return monthly_inflow - monthly_outflow


def private_reserve_target(monthly_outflow, total_insurance_deductibles, override=None):
    if override is not None:
        return override
    return 6 * monthly_outflow + total_insurance_deductibles


def _sum_balances(accounts, account_balances, predicate):
    total = 0
    for acct in accounts:
        if not predicate(acct):
            continue
        bal = account_balances.get(acct["key"], {}).get("balance")
        if bal:
            total += bal
    return total


def client_retirement_total(accounts, account_balances, owner):
    return _sum_balances(
        accounts,
        account_balances,
        lambda a: a["category"] == RETIREMENT and a["owner"] == owner,
    )


def non_retirement_total(accounts, account_balances):
    """Sum of all non-retirement account balances. Excludes trust per PRD."""
    return _sum_balances(
        accounts,
        account_balances,
        lambda a: a["category"] == NON_RETIREMENT,
    )


def trust_total(properties, property_values):
    total = 0
    for prop in properties:
        z = property_values.get(prop["key"])
        if z:
            total += z
    return total


def grand_total_net_worth(c1_retirement, c2_retirement, non_retirement, trust):
    """Per PRD: trust included; liabilities NOT subtracted."""
    return c1_retirement + c2_retirement + non_retirement + trust


def liabilities_total(liabilities, liability_balances):
    """Displayed separately. NOT subtracted from net worth."""
    total = 0
    for liab in liabilities:
        bal = liability_balances.get(liab["key"])
        if bal:
            total += bal
    return total


def compute_all(client_data, inputs):
    """Run every calculation given a client dict and inputs dict.

    client_data: {monthly_outflow_default, total_insurance_deductibles,
                  private_reserve_target_override, accounts, liabilities, properties}
    inputs: {cashflow:{inflow,outflow,private_reserve_balance,schwab_investment_balance},
             account_balances, liability_balances, property_values}
    Returns dict matching Report.calculated_json shape.
    """
    cashflow = inputs["cashflow"]
    inflow = cashflow["inflow"]
    outflow = cashflow["outflow"]

    excess = sacs_excess(inflow, outflow)
    pr_target = private_reserve_target(
        outflow,
        client_data["total_insurance_deductibles"],
        client_data.get("private_reserve_target_override"),
    )

    c1 = client_retirement_total(
        client_data["accounts"], inputs["account_balances"], CLIENT1
    )
    c2 = client_retirement_total(
        client_data["accounts"], inputs["account_balances"], CLIENT2
    )
    nr = non_retirement_total(client_data["accounts"], inputs["account_balances"])
    tr = trust_total(client_data["properties"], inputs["property_values"])
    grand = grand_total_net_worth(c1, c2, nr, tr)
    liab = liabilities_total(client_data["liabilities"], inputs["liability_balances"])

    return {
        "excess": excess,
        "private_reserve_target": pr_target,
        "c1_retirement_total": c1,
        "c2_retirement_total": c2,
        "non_retirement_total": nr,
        "trust_total": tr,
        "grand_total": grand,
        "liabilities_total": liab,
    }


REQUIRED_CASHFLOW = ("inflow", "outflow", "private_reserve_balance", "schwab_investment_balance")


def find_missing_fields(client_data, inputs):
    """Return list of human-readable missing field labels. Empty = valid."""
    missing = []
    cashflow = inputs.get("cashflow", {})
    for k in REQUIRED_CASHFLOW:
        if cashflow.get(k) in (None, ""):
            missing.append(f"Cashflow: {k.replace('_', ' ').title()}")

    balances = inputs.get("account_balances", {})
    for acct in client_data["accounts"]:
        b = balances.get(acct["key"], {})
        if b.get("balance") in (None, ""):
            missing.append(f"Balance: {acct['label']} ({acct['institution']})")
        if acct.get("is_investment") and b.get("cash_balance") in (None, ""):
            missing.append(f"Cash Balance: {acct['label']}")

    liab_b = inputs.get("liability_balances", {})
    for liab in client_data["liabilities"]:
        if liab_b.get(liab["key"]) in (None, ""):
            missing.append(f"Liability: {liab['label']}")

    prop_v = inputs.get("property_values", {})
    for prop in client_data["properties"]:
        if prop_v.get(prop["key"]) in (None, ""):
            missing.append(f"Property Zestimate: {prop['label']}")

    return missing
