"""Smoke tests for the feedback-round fixes (2026-08).

Covers:
- counter mode includes the sandbag stations
- scores board "כולם" returns rows
- admin group summary keeps the selected group
- interview requires a summary note; duplicate request is ignored
- group score entry gives last place to unscored candidates
- final weighted grade page saves and exports
- station rankings list only scored stations

Run inside the project Docker image (local python can't install the pinned deps):
    docker build -t gibushun-smoke .
    docker run --rm -v "$PWD:/app" -w /app -e PYTHONPATH=/app gibushun-smoke \
        python tests/test_feedback_fixes.py
"""
import os

os.environ["DATABASE_URL"] = "sqlite:////tmp/test_feedback_fixes.db"

from main import app, db, User, Candidate, Review, MODE_STATIONS  # noqa: E402

with app.app_context():
    db.drop_all()
    db.create_all()
    admin = User(id=0, name="admin", password="x", mitam_num=0,
                 sprint_num=0, crawl_num=0, alonka_num=0)
    g1 = User(id=1, name="group1", password="x", mitam_num=7,
              sprint_num=2, crawl_num=2, alonka_num=2)
    g4 = User(id=4, name="group4", password="x", mitam_num=8,
              sprint_num=2, crawl_num=2, alonka_num=2)
    db.session.add_all([admin, g1, g4])
    for num in (1, 2, 3):
        db.session.add(Candidate(id=f"1/{num}", group_id=1, name=f"c{num}", status="פעיל"))
    db.session.add(Candidate(id="4/1", group_id=4, name="d1", status="פעיל"))
    db.session.add(Review(author_id=1, station="דיון מילוט", subject_id="1/1", grade=3.0))
    db.session.commit()

# 1) counter mode includes the sandbag stations
assert "שקי חול" in MODE_STATIONS["counter"] and "שקי חול 2" in MODE_STATIONS["counter"]
print("OK: counter mode includes sandbag stations")

client = app.test_client()
app.config["WTF_CSRF_ENABLED"] = False
with client.session_transaction() as sess:
    sess["_user_id"] = "1"

# 2) scores board "כולם" returns rows
resp = client.post("/candidates/", data={"id": "כולם"})
assert resp.status_code == 200
html = resp.get_data(as_text=True)
assert "דיון מילוט" in html, "כולם view must show the existing review"
print("OK: scores board כולם shows rows")

# 3) interview without a note is rejected (form error re-render, no save)
resp = client.post("/interview/", data={
    "id": "1", "interviewer": "x", "grade": "כן, אבל", "note": "",
    "tash": "אין", "medical": "אין"})
with app.app_context():
    assert Candidate.query.get("1/1").interview_grade is None
print("OK: interview without note is not saved")

# 4) interview with a note saves; replay with same request id is ignored
resp = client.post("/interview/", data={
    "id": "1", "interviewer": "x", "grade": "כן, אבל", "note": "טוב",
    "tash": "אין", "medical": "אין"}, headers={"X-Request-Id": "req-1"})
with app.app_context():
    assert Candidate.query.get("1/1").interview_grade == "כן, אבל"
resp = client.post("/interview/", data={
    "id": "1", "interviewer": "y", "grade": "להתאבד", "note": "אחר",
    "tash": "אין", "medical": "אין"}, headers={"X-Request-Id": "req-1"})
with app.app_context():
    assert Candidate.query.get("1/1").interview_grade == "כן, אבל", "duplicate must be ignored"
print("OK: interview saves once per request id")

# 5) group score entry: unscored candidates get last place (grade 1)
resp = client.post("/add-all", data={
    "station": ["בניית מאהל"] * 3,
    "grade": ["4", "0", "3"],
    "note": ["", "", ""]})
with app.app_context():
    r2 = Review.query.filter_by(station="בניית מאהל", subject_id="1/2").first()
    assert r2 is not None and r2.grade == 1.0, "unscored candidate must get last place"
    r1 = Review.query.filter_by(station="בניית מאהל", subject_id="1/1").first()
    assert r1.grade == 4.0
print("OK: unscored candidates get the last-place grade")

# 6) final weighted grade page saves
resp = client.post("/final-grade/", data={"id": "1", "grade": "91", "note": "חזק"})
with app.app_context():
    c = Candidate.query.get("1/1")
    assert c.final_weighted_grade == "91" and c.final_weighted_note == "חזק"
print("OK: final weighted grade saves")

# 7) station rankings list only scored stations
resp = client.get("/station-reviews/")
html = resp.get_data(as_text=True)
assert "דיון מילוט" in html
assert "נאסא" not in html, "unscored stations must not appear"
print("OK: station list shows only scored stations")

# 8) admin group summary keeps the selected group
with client.session_transaction() as sess:
    sess["_user_id"] = "0"
resp = client.get("/4/")
html = resp.get_data(as_text=True)
assert ('<option selected value="4">' in html) or ('<option value="4" selected>' in html), \
    "group 4 must stay selected"
print("OK: admin group summary keeps the selection")

print("ALL FEEDBACK SMOKE TESTS PASSED")
