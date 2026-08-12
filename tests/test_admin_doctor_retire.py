"""Smoke tests for doctor retirement from the admin dashboard.

Covers:
- admin retires a candidate in any group with a medical reason
- admin dashboard shows the retired candidate with the doctor badge
- admin returns a retired candidate to active
- a regular group user cannot use the "group" argument on another group
- the regular group flow (no "group" argument) stays unchanged

Run inside the project Docker image (local python can't install the pinned deps):
    docker build -t gibushun-smoke .
    docker run --rm -v "$PWD:/app" -w /app -e PYTHONPATH=/app gibushun-smoke \
        python tests/test_admin_doctor_retire.py
"""
import os

os.environ["DATABASE_URL"] = "sqlite:////tmp/test_admin_doctor_retire.db"

from main import app, db, User, Candidate  # noqa: E402

with app.app_context():
    db.drop_all()
    db.create_all()
    admin = User(id=0, name="admin", password="x", mitam_num=0,
                 sprint_num=0, crawl_num=0, alonka_num=0)
    g1 = User(id=1, name="group1", password="x", mitam_num=7,
              sprint_num=2, crawl_num=2, alonka_num=2)
    g2 = User(id=2, name="group2", password="x", mitam_num=7,
              sprint_num=2, crawl_num=2, alonka_num=2)
    db.session.add_all([admin, g1, g2])
    for num in (1, 2):
        db.session.add(Candidate(id=f"1/{num}", group_id=1, name=f"c{num}", status="פעיל"))
    db.session.add(Candidate(id="2/1", group_id=2, name="d1", status="פעיל"))
    db.session.commit()

client = app.test_client()
app.config["WTF_CSRF_ENABLED"] = False
with client.session_transaction() as sess:
    sess["_user_id"] = "0"

# 1) admin retires candidate 1/1 with a medical reason
resp = client.post("/delete-candidate/1?reason=medical&group=1")
assert resp.status_code == 302 and resp.location.rstrip("/").endswith("/1"), resp.location
with app.app_context():
    c = Candidate.query.get("1/1")
    assert c.status == "פרש" and c.withdraw_reason == "רפואי"
print("OK: admin retires a candidate with a medical reason")

# 2) admin dashboard shows the retired section and the doctor badge
resp = client.get("/1/")
html = resp.get_data(as_text=True)
assert "מגובשים שפרשו" in html and "הופרש ע\"י הרופא" in html
assert "הופרש על ידי הרופא" in html, "active cards must show the doctor button"
print("OK: admin dashboard shows the retired candidate and the badge")

# 3) admin returns the candidate to active
resp = client.post("/return/1?group=1")
assert resp.status_code == 302
with app.app_context():
    c = Candidate.query.get("1/1")
    assert c.status == "" and c.withdraw_reason is None
resp = client.get("/1/")
assert "מגובשים שפרשו" not in resp.get_data(as_text=True)
print("OK: admin returns a retired candidate to active")

# 4) admin can also retire in a different group
resp = client.post("/delete-candidate/1?group=2")
with app.app_context():
    c = Candidate.query.get("2/1")
    assert c.status == "פרש" and c.withdraw_reason is None
    Candidate.query.get("2/1").status = ""
    db.session.commit()
print("OK: admin retires in a different group, no medical reason")

# 5) a regular user cannot use the group argument on another group
with client.session_transaction() as sess:
    sess["_user_id"] = "1"
resp = client.post("/delete-candidate/1?group=2")
assert resp.status_code == 403
with app.app_context():
    assert Candidate.query.get("2/1").status == ""
print("OK: a regular user gets 403 for another group")

# 6) the regular group flow stays unchanged
resp = client.post("/delete-candidate/2")
assert resp.status_code == 302 and resp.location.endswith("/group-manage")
with app.app_context():
    assert Candidate.query.get("1/2").status == "פרש"
resp = client.post("/return/2")
with app.app_context():
    assert Candidate.query.get("1/2").status == ""
print("OK: the regular group flow works as before")

print("ALL TESTS PASSED")
