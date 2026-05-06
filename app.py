"""AW Client Report Portal — single-file Flask app.

Demo build for the Sagan AI Engineer assessment. Scope intentionally tight:
one shared password, one seeded client, structured form -> deterministic
calculations -> WeasyPrint-rendered SACS and TCC PDFs.

See README.md for assumptions and V2 roadmap.
"""
import hmac
import io
import os
from datetime import datetime
from functools import wraps

from flask import (
    Flask,
    abort,
    flash,
    redirect,
    render_template,
    request,
    send_file,
    session,
    url_for,
)

from calculations import compute_all, find_missing_fields
from models import Client, Report, db


def create_app():
    app = Flask(__name__)
    app.config["SQLALCHEMY_DATABASE_URI"] = os.environ.get(
        "DATABASE_URL", "sqlite:///app.db"
    )
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "dev-secret-change-me")
    app.config["APP_PASSWORD"] = os.environ.get("APP_PASSWORD", "demo")
    db.init_app(app)
    return app


app = create_app()


# ---------- Auth ----------

def require_login(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not session.get("authed"):
            return redirect(url_for("login", next=request.path))
        return view(*args, **kwargs)
    return wrapped


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        provided = request.form.get("password", "")
        if hmac.compare_digest(provided, app.config["APP_PASSWORD"]):
            session["authed"] = True
            return redirect(request.args.get("next") or url_for("clients_list"))
        flash("Incorrect password.", "error")
    return render_template("login.html")


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


# ---------- Routes ----------

@app.route("/")
@require_login
def clients_list():
    clients = Client.query.order_by(Client.household_name).all()
    return render_template("clients_list.html", clients=clients)


@app.route("/clients/<int:client_id>")
@require_login
def client_detail(client_id):
    client = Client.query.get_or_404(client_id)
    reports = client.reports.all()
    return render_template("client_detail.html", client=client, reports=reports)


@app.route("/clients/<int:client_id>/reports/new")
@require_login
def report_new(client_id):
    client = Client.query.get_or_404(client_id)
    last = client.latest_report
    last_inputs = last.inputs_json if last else None
    suggested_period = _suggest_period_label(last)
    return render_template(
        "report_form.html",
        client=client,
        last_inputs=last_inputs,
        suggested_period=suggested_period,
        errors=[],
        submitted={},
    )


@app.route("/clients/<int:client_id>/reports", methods=["POST"])
@require_login
def report_create(client_id):
    client = Client.query.get_or_404(client_id)
    inputs = _parse_form_inputs(request.form, client)

    client_data = _client_to_data(client)
    missing = find_missing_fields(client_data, inputs)
    if missing:
        last = client.latest_report
        return render_template(
            "report_form.html",
            client=client,
            last_inputs=last.inputs_json if last else None,
            suggested_period=request.form.get("period_label", _suggest_period_label(last)),
            errors=missing,
            submitted=inputs,
        ), 400

    calculated = compute_all(client_data, inputs)
    report = Report(
        client_id=client.id,
        period_label=request.form.get("period_label", "").strip() or _suggest_period_label(client.latest_report),
        inputs_json=inputs,
        calculated_json=calculated,
    )
    db.session.add(report)
    db.session.commit()
    return redirect(url_for("report_preview", report_id=report.id))


@app.route("/reports/<int:report_id>")
@require_login
def report_preview(report_id):
    report = Report.query.get_or_404(report_id)
    return render_template("report_preview.html", report=report, client=report.client)


@app.route("/reports/<int:report_id>/sacs.pdf")
@require_login
def report_sacs_pdf(report_id):
    report = Report.query.get_or_404(report_id)
    return _render_pdf("pdf/sacs.html", report, suffix="SACS")


@app.route("/reports/<int:report_id>/tcc.pdf")
@require_login
def report_tcc_pdf(report_id):
    report = Report.query.get_or_404(report_id)
    return _render_pdf("pdf/tcc.html", report, suffix="TCC")


@app.route("/reports/<int:report_id>/delete", methods=["POST"])
@require_login
def report_delete(report_id):
    report = Report.query.get_or_404(report_id)
    client_id = report.client_id
    db.session.delete(report)
    db.session.commit()
    return redirect(url_for("client_detail", client_id=client_id))


# ---------- Helpers ----------

def _client_to_data(client):
    return {
        "monthly_outflow": client.monthly_outflow,
        "total_insurance_deductibles": client.total_insurance_deductibles,
        "private_reserve_target_override": client.private_reserve_target_override,
        "accounts": client.accounts_json,
        "liabilities": client.liabilities_json,
        "properties": client.properties_json,
    }


def _parse_int(value):
    if value is None:
        return None
    s = str(value).strip().replace(",", "").replace("$", "")
    if not s:
        return None
    try:
        return int(round(float(s)))
    except ValueError:
        return None


def _parse_form_inputs(form, client):
    inputs = {
        "cashflow": {
            "inflow": _parse_int(form.get("cashflow.inflow")),
            "outflow": _parse_int(form.get("cashflow.outflow")),
            "private_reserve_balance": _parse_int(form.get("cashflow.private_reserve_balance")),
            "schwab_investment_balance": _parse_int(form.get("cashflow.schwab_investment_balance")),
        },
        "account_balances": {},
        "liability_balances": {},
        "property_values": {},
    }
    for acct in client.accounts_json:
        key = acct["key"]
        inputs["account_balances"][key] = {
            "balance": _parse_int(form.get(f"account.{key}.balance")),
            "cash_balance": _parse_int(form.get(f"account.{key}.cash_balance")),
        }
    for liab in client.liabilities_json:
        inputs["liability_balances"][liab["key"]] = _parse_int(
            form.get(f"liability.{liab['key']}")
        )
    for prop in client.properties_json:
        inputs["property_values"][prop["key"]] = _parse_int(
            form.get(f"property.{prop['key']}")
        )
    return inputs


def _suggest_period_label(last_report):
    today = datetime.utcnow().date()
    quarter = (today.month - 1) // 3 + 1
    suggested = f"{today.year}-Q{quarter}"
    if last_report and last_report.period_label == suggested:
        # Already exists; bump to next quarter.
        next_q = quarter % 4 + 1
        next_year = today.year + (1 if quarter == 4 else 0)
        suggested = f"{next_year}-Q{next_q}"
    return suggested


def _render_pdf(template_name, report, suffix):
    # Import lazily so test imports don't require GTK to be installed.
    from weasyprint import HTML

    html = render_template(template_name, report=report, client=report.client)
    pdf_bytes = HTML(string=html, base_url=request.host_url).write_pdf()
    filename = f"{report.client.household_name.replace(' ', '_')}_{report.period_label}_{suffix}.pdf"
    return send_file(
        io.BytesIO(pdf_bytes),
        mimetype="application/pdf",
        as_attachment=False,
        download_name=filename,
    )


# ---------- Jinja filters ----------

@app.template_filter("money")
def money_filter(value):
    if value is None or value == "":
        return "—"
    try:
        return f"${int(value):,}"
    except (TypeError, ValueError):
        return str(value)


@app.template_filter("money_signed")
def money_signed_filter(value):
    if value is None or value == "":
        return "—"
    v = int(value)
    sign = "-" if v < 0 else ""
    return f"{sign}${abs(v):,}"


# ---------- CLI entry ----------

@app.cli.command("init-db")
def init_db():
    """Create tables (idempotent — does not drop existing)."""
    db.create_all()
    print("Tables created.")


def _auto_seed_if_empty():
    """On first boot with an empty DB, seed the demo client.

    Runs at import time so a fresh Railway deploy is immediately usable.
    No-op if any client already exists.
    """
    from seed import seed_demo_data
    seed_demo_data()


if not os.environ.get("SKIP_AUTOSEED"):
    with app.app_context():
        db.create_all()
        _auto_seed_if_empty()


if __name__ == "__main__":
    app.run(debug=True, port=5000)
