"""One-off cleanup: remove demo reports with unrealistically small net worth.

Deletes any Report where grand_total < 1_000_000.
The Henderson demo client has a realistic ~$2.4M grand total; anything below
$1M is test data accidentally left in the database.

Usage (Railway one-off):
    railway run python clean_db.py

Alternative full reset (drops all tables, re-seeds from scratch):
    railway run python seed.py
"""
from app import app
from models import Report, db

FLOOR = 1_000_000  # $1M — below this is clearly test/broken data

with app.app_context():
    all_reports = Report.query.order_by(Report.id).all()
    bad = [r for r in all_reports if r.calculated_json.get("grand_total", 0) < FLOOR]

    if not bad:
        print(f"Database is clean — {len(all_reports)} report(s) found, all above ${FLOOR:,}.")
    else:
        for r in bad:
            gt = r.calculated_json.get("grand_total", 0)
            print(f"  Deleting Report id={r.id}  period={r.period_label}  "
                  f"grand_total=${gt:,}  client_id={r.client_id}")
        for r in bad:
            db.session.delete(r)
        db.session.commit()
        print(f"\nDone. Removed {len(bad)} bad report(s). "
              f"{len(all_reports) - len(bad)} report(s) remain.")
