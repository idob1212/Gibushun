"""Required fields on every form (field feedback, Nov 2026 test round).

Covers:
- refused POSTs re-render with the Hebrew message under the field AND carry
  X-Form-Errors, so the offline outbox never counts them as synced
- notes: type and text required, location optional, same rules as /notes/quick
- single grade: no pre-selected grade, custom station name required, the
  station is kept after a save; grade edits load the saved grade
- group grading: "–" rows, a note without a grade is refused (never dropped),
  an all-"–" sheet is refused, ungraded rows get 1 and saved grades survive
- march counters: a note autosave before any count gives nobody a 1
- interview / final status start on an empty "choose" entry
- batch add: empty name and number 0 refused; staff password spaces

Run like the other scripts (pinned deps):
    python tests/test_form_rules.py
"""
import os
import re
from urllib.parse import unquote

os.environ["DATABASE_URL"] = "sqlite:////tmp/test_form_rules.db"

from main import app, db, User, Candidate, Review, Note, DOCTOR_ID  # noqa: E402

app.config["WTF_CSRF_ENABLED"] = False

with app.app_context():
    db.drop_all()
    db.create_all()
    db.session.add_all([
        User(id=0, name="admin", password="x", mitam_num=0, sprint_num=0, crawl_num=0, alonka_num=0),
        User(id=1, name="group", password="pw", mitam_num=1, sprint_num=0, crawl_num=0, alonka_num=0),
    ])
    for n in range(1, 6):
        db.session.add(Candidate(id=f"1/{n}", group_id=1, name=f"מגובש {n}"))
    db.session.commit()

client = app.test_client()


def login_as(user_id):
    with client.session_transaction() as sess:
        sess["_user_id"] = str(user_id)
        sess["_fresh"] = True


def html_of(resp):
    return resp.get_data(as_text=True)


def refused(resp):
    header = resp.headers.get("X-Form-Errors")
    return unquote(header) if header is not None else None


login_as(1)

# 1) Notes: type is required — online the message shows, offline replay is refused
resp = client.post("/new-note", data={"subject": "1", "text": "עזר לכולם", "location": ""})
assert resp.status_code == 200
assert "בחר סוג הערה" in html_of(resp), "the error is shown under the field"
assert "סוג הערה: בחר סוג הערה" in refused(resp)
resp = client.post("/new-note", data={"subject": "1", "type": "טובה", "text": "   "})
assert "כתוב את ההערה" in refused(resp), "a note of spaces is no note"
resp = client.post("/new-note", data={"subject": "1", "type": "טובה", "text": "עזר לכולם"})
assert resp.status_code == 302 and resp.headers.get("X-Form-Errors") is None
with app.app_context():
    note = Note.query.filter_by(subject_id="1/1").one()
    assert (note.type, note.text, note.location) == ("טובה", "עזר לכולם", "")
html = html_of(client.get("/new-note"))
assert html.count('name="type"') == 3 and 'required' in html.split('name="type"')[1][:200]
assert html.index("סוג הערה") < html.index('name="text"') < html.index('name="location"'), \
    "same order as the quick note: candidate, type, note, location"
assert "(לא חובה)" in html
print("OK: notes need a type and text (shown on screen + X-Form-Errors), location is optional")

# 1b) Editing a note without a location no longer forces one
with app.app_context():
    note_id = Note.query.filter_by(subject_id="1/1").one().id
resp = client.post(f"/edit-note/{note_id}", data={"subject": "1", "type": "רעה", "text": "תוקן"})
assert resp.status_code == 302
with app.app_context():
    assert Note.query.get(note_id).type == "רעה"
print("OK: editing a note keeps the same rules")

# 2) Single grade: no grade is pre-selected; custom name required; station kept
html = html_of(client.get("/new-review"))
assert 'name="grade" value="1" required' in html and "checked" not in html.split('name="grade"')[1][:80]
resp = client.post("/new-review", data={"station": "הרצאות", "subject": "2", "note": ""})
assert "ציון: בחר ציון" in refused(resp)
resp = client.post("/new-review", data={"station": "אחר", "odt": " ", "subject": "2", "grade": "3"})
assert "שם תחנה: כתוב את שם התחנה" in refused(resp)
resp = client.post("/new-review", data={"station": "אחר", "odt": "חבלים", "subject": "2", "grade": "3"})
assert resp.status_code == 200 and resp.headers.get("X-Form-Errors") is None
html = html_of(resp)
assert 'value="חבלים"' in html and '<option selected value="אחר">' in html, "station kept for the next one"
# the next candidate without a grade at this station is picked (and named
# on the save button by the page script); nobody else is
assert 'id="subject-3" checked' in html and len(re.findall(r'id="subject-\d+"', html)) == 5
assert html.count(" checked required") == 1, "exactly one candidate picked"
with app.app_context():
    review = Review.query.filter_by(station="חבלים", subject_id="1/2").one()
    assert review.grade == 3
print("OK: single grade has no default, needs a name for 'אחר', keeps the station, moves to the next")

# 2b) Editing a saved grade shows it (it used to show 1 and overwrite it)
with app.app_context():
    review_id = review.id
html = html_of(client.get(f"/edit-review/{review_id}"))
assert 'value="3" required data-msg="בחר ציון" checked' in html
resp = client.post(f"/edit-review/{review_id}", data={"station": "חבלים", "subject": "2", "grade": "4", "note": ""})
assert resp.status_code == 302
with app.app_context():
    assert Review.query.get(review_id).grade == 4
print("OK: grade edits load the saved grade")

# 2c) A grade replayed for a candidate who retired meanwhile says so (and is refused)
with app.app_context():
    Candidate.query.get("1/5").status = "פרש"
    db.session.commit()
resp = client.post("/new-review", data={"station": "הרצאות", "subject": "5", "grade": "3"})
assert "מספר מגובש: המגובש כבר לא פעיל" in refused(resp)
assert "המגובש כבר לא פעיל" in html_of(resp)
with app.app_context():
    Candidate.query.get("1/5").status = None
    db.session.commit()
print("OK: a retired candidate's replayed grade is refused with a clear reason")

# 3) Group grading: a note on a "–" row is refused, not dropped
form = {"station": "שולחן חול", "subject": ["1", "2", "3", "4", "5"],
        "grade-1": "3", "grade-2": "0", "note-2": "שקט מאוד", "grade-3": "0", "grade-4": "0", "grade-5": "0"}
resp = client.post("/add-all", data=form)
assert resp.status_code == 200
assert "יש הערה בלי ציון" in html_of(resp) and "שקט מאוד" in html_of(resp), "the note is still on screen"
assert "מגובש 2" in refused(resp)
with app.app_context():
    assert Review.query.filter_by(station="שולחן חול").count() == 0, "nothing half-saved"
# ... and a sheet with no grade at all is refused instead of "saved"
resp = client.post("/add-all", data={"station": "שולחן חול", "subject": ["1", "2"], "grade-1": "0", "grade-2": "0"})
assert "לא סומן אף ציון" in refused(resp)
# graded: the note is saved, "–" rows get 1, the flash counts what happened
form["grade-2"] = "2"
resp = client.post("/add-all", data=form, follow_redirects=True)
assert "נשמרו 2 ציונים" in html_of(resp) and "3 שלא דורגו קיבלו 1" in html_of(resp)
with app.app_context():
    grades = {r.subject_id: (r.grade, r.note) for r in Review.query.filter_by(station="שולחן חול")}
    assert grades["1/2"] == (2, "שקט מאוד") and grades["1/5"] == (1.0, "")
# a later "–" never overwrites a saved grade
client.post("/add-all", data={"station": "שולחן חול", "subject": ["1", "2"], "grade-1": "4", "grade-2": "0"})
with app.app_context():
    assert Review.query.filter_by(station="שולחן חול", subject_id="1/2").one().grade == 2
# the page shows saved grades per station and comes back on the same station
html = html_of(client.get("/new-group-review?station=שולחן חול"))
assert '<option selected value="שולחן חול">' in html and '"שולחן חול"' in html
# old pages (and their queued posts) still work: parallel lists
client.post("/add-all", data={"station": "הסתתרות", "subject": ["1", "2"], "grade": ["4", "0"], "note": ["", ""]})
with app.app_context():
    assert Review.query.filter_by(station="הסתתרות", subject_id="1/1").one().grade == 4
print("OK: group grading refuses notes without a grade and empty sheets, never drops a note")

# 4) March counters: a note autosave before any count gives nobody a 1
resp = client.post("/update-counter-reviews", json={"station": "מסע 1", "reviews": [
    {"subject": "1", "counter": 0, "note": "צולע"}, {"subject": "2", "counter": 0, "note": ""}]})
assert resp.get_json()["success"]
with app.app_context():
    rows = Review.query.filter_by(station="מסע 1").all()
    assert [r.subject_id for r in rows] == ["1/1"] and rows[0].note == "צולע"
print("OK: march notes save without handing everyone a 1")

# 5) Interview and final status start on an empty "choose" entry
html = html_of(client.get("/interview/"))
assert 'required><option value="">— בחרו ציון —</option>' in html and "selected" not in html.split('id="grade"')[1][:400]
resp = client.post("/interview/", data={"id": "1", "interviewer": "דן", "note": "טוב"})
assert "ציון ראיון: בחר ציון ראיון" in refused(resp)
html = html_of(client.get("/final-status/"))
assert 'required><option selected value="">— בחרו סטטוס —</option>' in html
resp = client.post("/final-status/", data={"id": "1", "final_note": "x"})
assert "בחר סטטוס סיכום" in refused(resp)
print("OK: interview grade and final status must be chosen")

# 6) Adding candidates: number 0 and empty names are refused in both ways
resp = client.post("/add-candidate", data={"id": "0", "name": "אפס"})
assert "מספר מגובש מתחיל מ-1" in html_of(resp)
data = client.post("/add-candidate-batch", json=[{"id": "0", "name": "אפס"}, {"id": "9", "name": " "}]).get_json()
assert [e["error"] for e in data["results"]["invalid_data"]] == ["מספר מגובש מתחיל מ-1", "חסר שם"]
with app.app_context():
    assert Candidate.query.get("1/0") is None and Candidate.query.get("1/9") is None
print("OK: candidate numbers start at 1 and need a name, single and batch")

# 7) Login shows its error; staff passwords ignore stray spaces like when set
client.get("/logout")
resp = client.post("/login", data={"role": "group", "id": "1", "password": ""})
assert "הזן סיסמה" in html_of(resp)
login_as(0)
client.post("/admin/staff/doctor", data={"password": " 1234 "})
client.get("/logout")
resp = client.post("/login", data={"role": "doctor", "password": " 1234 "})
assert resp.status_code == 302 and resp.headers["Location"].endswith("/")
with app.app_context():
    assert User.query.get(DOCTOR_ID).password == "1234"
print("OK: login errors show; staff password spaces handled alike")

print("ALL FORM RULE TESTS PASSED")
