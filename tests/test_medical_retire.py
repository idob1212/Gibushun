"""Smoke test: the admin (doctor) medical-withdrawal page.

The doctor works from the admin account, so /medical-retire must let admin
withdraw and reinstate a candidate in ANY group — the group panel's
/delete-candidate builds the id from current_user.id and 404s for admin.

Run inside the project Docker image (local python can't install the pinned deps):
    docker build -t gibushun-smoke .
    docker run --rm -v "$PWD:/app" -w /app -e PYTHONPATH=/app gibushun-smoke \
        python tests/test_medical_retire.py
"""
import os

# Force a throwaway DB before importing main — this test drops all tables.
os.environ["DATABASE_URL"] = "sqlite:////tmp/test_medical_retire.db"

from main import app, db, User, Candidate  # noqa: E402

app.config["WTF_CSRF_ENABLED"] = False

with app.app_context():
    db.drop_all()
    db.create_all()
    admin = User(id=0, name="admin", password="x", mitam_num=0,
                 sprint_num=0, crawl_num=0, alonka_num=0)
    group1 = User(id=1, name="group1", password="x", mitam_num=7,
                  sprint_num=0, crawl_num=0, alonka_num=0)
    group2 = User(id=2, name="group2", password="x", mitam_num=7,
                  sprint_num=0, crawl_num=0, alonka_num=0)
    db.session.add_all([admin, group1, group2])
    db.session.add_all([
        Candidate(id="1/1", group_id=1, name="ראשון", status=""),
        Candidate(id="1/2", group_id=1, name="שני", status=""),
        Candidate(id="2/1", group_id=2, name="שלישי", status=""),
    ])
    db.session.commit()

client = app.test_client()
with client.session_transaction() as sess:
    sess["_user_id"] = "0"

# The page loads and defaults to the first group.
resp = client.get("/medical-retire")
assert resp.status_code == 200, f"expected 200, got {resp.status_code}"
body = resp.get_data(as_text=True)
assert "הפרשת רופא" in body
assert "שני" in body, "group 1 candidates should be listed"
assert "שלישי" not in body, "another group's candidates must not leak in"

# ?group= picks a different group.
body = client.get("/medical-retire?group=2").get_data(as_text=True)
assert "שלישי" in body and "שני" not in body

# Retiring marks the candidate as withdrawn by the doctor.
resp = client.post("/medical-retire/retire/1/2")
assert resp.status_code == 302, f"expected redirect, got {resp.status_code}"
assert "/medical-retire?group=1" in resp.headers["Location"]
with app.app_context():
    candidate = Candidate.query.get("1/2")
    assert candidate.status == "פרש", candidate.status
    assert candidate.withdraw_reason == "רפואי", candidate.withdraw_reason
    assert Candidate.query.get("1/1").status == "", "only the picked candidate changes"

# The retired candidate moves to the withdrawn list with the doctor badge.
body = client.get("/medical-retire?group=1").get_data(as_text=True)
assert 'הופרש ע"י הרופא' in body

# Reinstating clears both fields.
resp = client.post("/medical-retire/return/1/2")
assert resp.status_code == 302, f"expected redirect, got {resp.status_code}"
with app.app_context():
    candidate = Candidate.query.get("1/2")
    assert candidate.status == "", candidate.status
    assert candidate.withdraw_reason is None, candidate.withdraw_reason

# Unknown candidate -> 404, not a 500.
assert client.post("/medical-retire/retire/1/99").status_code == 404

# Group users must not reach the doctor page or its actions.
with client.session_transaction() as sess:
    sess["_user_id"] = "1"
assert client.get("/medical-retire").status_code == 403
assert client.post("/medical-retire/retire/1/1").status_code == 403
assert client.post("/medical-retire/return/1/1").status_code == 403

print("test_medical_retire: OK")
