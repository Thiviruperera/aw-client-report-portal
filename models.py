from datetime import datetime
from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()


class Client(db.Model):
    __tablename__ = "clients"

    id = db.Column(db.Integer, primary_key=True)
    household_name = db.Column(db.String(200), nullable=False)

    primary_first = db.Column(db.String(80), nullable=False)
    primary_last = db.Column(db.String(80), nullable=False)
    primary_dob = db.Column(db.Date, nullable=False)
    primary_ssn_last4 = db.Column(db.String(4), nullable=False)

    spouse_first = db.Column(db.String(80))
    spouse_last = db.Column(db.String(80))
    spouse_dob = db.Column(db.Date)
    spouse_ssn_last4 = db.Column(db.String(4))

    monthly_inflow = db.Column(db.Integer, nullable=False)
    monthly_outflow = db.Column(db.Integer, nullable=False)
    total_insurance_deductibles = db.Column(db.Integer, nullable=False, default=0)
    private_reserve_target_override = db.Column(db.Integer)

    accounts_json = db.Column(db.JSON, nullable=False, default=list)
    liabilities_json = db.Column(db.JSON, nullable=False, default=list)
    properties_json = db.Column(db.JSON, nullable=False, default=list)

    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    reports = db.relationship(
        "Report", backref="client", lazy="dynamic", order_by="Report.created_at.desc()"
    )

    @property
    def has_spouse(self):
        return bool(self.spouse_first)

    @property
    def primary_age(self):
        return _age(self.primary_dob)

    @property
    def spouse_age(self):
        return _age(self.spouse_dob) if self.spouse_dob else None

    @property
    def latest_report(self):
        return self.reports.first()


class Report(db.Model):
    __tablename__ = "reports"

    id = db.Column(db.Integer, primary_key=True)
    client_id = db.Column(db.Integer, db.ForeignKey("clients.id"), nullable=False)
    period_label = db.Column(db.String(20), nullable=False)

    inputs_json = db.Column(db.JSON, nullable=False)
    calculated_json = db.Column(db.JSON, nullable=False)

    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)


def _age(dob):
    if not dob:
        return None
    today = datetime.utcnow().date()
    return today.year - dob.year - ((today.month, today.day) < (dob.month, dob.day))
