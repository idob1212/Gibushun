"""Smoke tests for the PWA field-feedback round (Givati gibush, 2026-08, v4).

Covers:
- new groups start with numbered placeholder candidates; naming them
- arrival order (circles): numeric order, single finisher, act summaries
- saved acts: rename to another station, delete
- editing / deleting a saved grade from the candidate page
- quick notes (group, admin, staff), request-id dedupe
- built-in doctor / HR stations: login, permissions, notes on the home page
- final grade categories (no note) and ranking inside a category
- candidate photos
- interview summary shows every interview by default
- removed pages redirect; page views no longer write when nothing changed
- SameSite cookies, POST-only deletes

Run inside the project Docker image (local python can't install the pinned deps):
    docker build -t gibushun-smoke .
    docker run --rm -v "$PWD:/app" -w /app -e PYTHONPATH=/app gibushun-smoke \
        python tests/test_pwa_feedback_v4.py
"""
import io
import os
import struct
import zlib

os.environ["DATABASE_URL"] = "sqlite:////tmp/test_pwa_feedback_v4.db"

from sqlalchemy import event  # noqa: E402

from main import (app, db, User, Candidate, Review, Note, CandidatePhoto,  # noqa: E402
                  DOCTOR_ID, HR_ID, update_avgs_nf)

app.config["WTF_CSRF_ENABLED"] = False

with app.app_context():
    db.drop_all()
    db.create_all()
    db.session.add_all([
        User(id=0, name="admin", password="x", mitam_num=0, sprint_num=0, crawl_num=0, alonka_num=0),
        User(id=2, name="other", password="y", mitam_num=1, sprint_num=1, crawl_num=1, alonka_num=1),
    ])
    db.session.add(Candidate(id="2/1", group_id=2, name="זר"))
    db.session.commit()

client = app.test_client()


def login_as(user_id):
    with client.session_transaction() as sess:
        sess["_user_id"] = str(user_id)
        sess["_fresh"] = True


def html_of(resp):
    return resp.get_data(as_text=True)


# 1) A new group starts with 25 numbered placeholders, in one save
login_as(0)
resp = client.post("/register", data={"id": "1", "name": "גבעתי", "mitam": "3",
                                      "password": "pw", "candidates_count": "25"})
assert resp.status_code == 302
with app.app_context():
    numbers = sorted(c.number for c in Candidate.query.filter_by(group_id=1))
    assert numbers == list(range(1, 26)), numbers
    assert Candidate.query.get("1/7").name == "מגובש 7"
resp = client.post("/register", data={"id": "5", "name": "ריקה", "mitam": "3",
                                      "password": "pw", "candidates_count": "0"})
with app.app_context():
    assert Candidate.query.filter_by(group_id=5).count() == 0
print("OK: new group gets placeholders 1-25 (and 0 when asked)")

# 1b) Only the admin creates groups (it used to be open to anyone)
login_as(2)
assert client.post("/register", data={"id": "9", "name": "x", "mitam": "1", "password": "p",
                                      "candidates_count": "25"}).status_code == 403
client.get("/logout")
assert client.get("/register").status_code == 302
with app.app_context():
    assert User.query.get(9) is None
print("OK: group registration is admin-only")

# 2) Naming the placeholders: bulk form, single add and batch add fill names
login_as(1)
resp = client.post("/group-manage/names", data={"name-1": "אבי", "name-2": "", "name-3": "  גדי "})
assert resp.status_code == 302
with app.app_context():
    assert Candidate.query.get("1/1").name == "אבי"
    assert Candidate.query.get("1/2").name == "מגובש 2", "empty field keeps the placeholder"
    assert Candidate.query.get("1/3").name == "גדי"
client.post("/add-candidate", data={"id": "4", "name": "דני"})
resp = client.post("/add-candidate-batch", json=[{"id": "5", "name": "הדר"}, {"id": "1", "name": "כפול"}])
data = resp.get_json()
with app.app_context():
    assert Candidate.query.get("1/4").name == "דני"
    assert Candidate.query.get("1/5").name == "הדר"
    assert Candidate.query.get("1/1").name == "אבי", "a real name is never overwritten"
assert data["summary"]["total_successful"] == 1 and len(data["results"]["existing_candidates"]) == 1
html = html_of(client.get("/group-manage"))
assert 'name="name-2"' in html and "שם זמני" in html
print("OK: placeholders are named in bulk / single / batch; real names kept")

# 3) Removing an unused number; a number with data cannot be removed
resp = client.post("/group-manage/remove/25")
with app.app_context():
    assert Candidate.query.get("1/25") is None
    db.session.add(Review(author_id=1, station="דיון מילוט", subject_id="1/24", grade=3.0))
    db.session.commit()
client.post("/group-manage/remove/24")
with app.app_context():
    assert Candidate.query.get("1/24") is not None
print("OK: empty numbers can be removed, used ones cannot")

# 4) Arrival order renders in numeric order even when added out of order
with app.app_context():
    db.session.add(Candidate(id="1/30", group_id=1, name="מאוחר"))
    db.session.commit()
html = html_of(client.get("/circles"))
start = html.index("var NUMBERS = ")
numbers = eval(html[start + len("var NUMBERS = "):html.index(";", start)])
assert numbers == sorted(numbers) and numbers[-1] == 30, numbers
print("OK: arrival screen lists numbers in order")

# 5) A heat with one finisher saves (was a division by zero)
resp = client.post("/circles/finished-act", json={"finished": [3], "movement_type": "ספרינטים"})
assert resp.status_code == 200 and resp.get_json()["success"], resp.get_data()
resp = client.post("/circles/finished-act", json={"finished": [], "movement_type": "ספרינטים"})
assert resp.status_code == 400
with app.app_context():
    assert Review.query.filter_by(subject_id="1/3", station="ספרינטים - אקט 1").first().grade == 4
    assert Review.query.filter_by(subject_id="1/1", station="ספרינטים - אקט 1").first().grade == 1
print("OK: one-finisher heat saves; empty heat is refused")

# 6) Acts: summaries, numbering, legacy payload, dedupe
resp = client.post("/circles/finished-act", json={"circle_numbers": [1, 2, 0, 3], "movement_type": "ספרינטים"},
                   headers={"X-Request-Id": "act-2"})
assert resp.get_json()["station"] == "ספרינטים - אקט 2"
client.post("/circles/finished-act", json={"circle_numbers": [1, 2, 0, 3], "movement_type": "ספרינטים"},
            headers={"X-Request-Id": "act-2"})
with app.app_context():
    assert Review.query.filter_by(station="ספרינטים - אקט 3").count() == 0, "replay must be ignored"
    a1 = Review.query.filter_by(subject_id="1/1", station="סיכום ספרינטים - אקט 2").first()
    assert a1 and a1.grade == 4
    summary = Review.query.filter_by(subject_id="1/1", station="ספרינטים סיכום").all()
    assert len(summary) == 1 and summary[0].grade == 2.5, [s.grade for s in summary]
print("OK: act summaries, numbering, old payload and replay dedupe")

# 7) Moving an act to the right station, then deleting it
resp = client.post("/acts/rename", data={"station": "ספרינטים - אקט 2", "new_base": "זחילות"})
assert resp.status_code == 302
with app.app_context():
    assert Review.query.filter_by(station="ספרינטים - אקט 2").count() == 0
    assert Review.query.filter_by(station="זחילות - אקט 1").count() > 0
    assert Review.query.filter_by(subject_id="1/1", station="זחילות סיכום").first().grade == 4
    assert Review.query.filter_by(subject_id="1/1", station="ספרינטים סיכום").first().grade == 1
assert "זחילות" in html_of(client.get("/acts"))
client.post("/acts/delete", data={"station": "ספרינטים - אקט 1"})
with app.app_context():
    assert Review.query.filter(Review.station.like("%ספרינטים%")).count() == 0, \
        "deleting the last act removes its summaries too"
print("OK: acts move between stations and delete cleanly")

# 8) Editing / deleting a saved grade from the candidate page
with app.app_context():
    act_row = Review.query.filter_by(subject_id="1/2", station="זחילות - אקט 1").first()
    station_row = Review(author_id=1, station="דיון מילוט", subject_id="1/2", grade=2.0, note="")
    counter_row = Review(author_id=1, station="מסע 1", subject_id="1/2", grade=3.0, counter_value=4)
    db.session.add_all([station_row, counter_row])
    db.session.commit()
    act_id, station_id, counter_id = act_row.id, station_row.id, counter_row.id
html = html_of(client.get("/candidate/1/2"))
assert f"/review/{act_id}/update" in html and f"/review/{counter_id}/update" not in html
client.post(f"/review/{act_id}/update", data={"grade": "1.5"})
client.post(f"/review/{station_id}/update", data={"grade": "4", "note": "מצוין"})
resp = client.post(f"/review/{station_id}/update", data={"grade": "7"})
with app.app_context():
    assert Review.query.get(act_id).grade == 1.5
    assert Review.query.filter_by(subject_id="1/2", station="סיכום זחילות - אקט 1").first().grade == 1.5
    assert Review.query.filter_by(subject_id="1/2", station="זחילות סיכום").first().grade == 1.5
    r = Review.query.get(station_id)
    assert r.grade == 4 and r.note == "מצוין", "an out-of-range grade must not be saved"
client.post(f"/review/{counter_id}/delete")
client.post(f"/review/{act_id}/delete")
with app.app_context():
    assert Review.query.get(counter_id) is not None, "march rows are edited on the march page"
    assert Review.query.get(act_id) is None
    assert Review.query.filter_by(subject_id="1/2", station="זחילות סיכום").first() is None
login_as(2)
assert client.post(f"/review/{station_id}/delete").status_code == 403
assert client.get("/candidate/1/2").status_code == 403
login_as(1)
assert client.get(f"/delete-review/{station_id}").status_code == 405, "deletes are POST-only"
print("OK: grades are edited and deleted from the candidate page, with permissions")

# 9) Quick notes
# A group user cannot aim at another group: the group field is ignored.
resp = client.post("/notes/quick", json={"group": 2, "subject": 1, "type": "טובה", "text": "עוזר לאחרים",
                                         "location": "זחילות"}, headers={"X-Request-Id": "qn-1"})
assert resp.get_json()["success"]
resp = client.post("/notes/quick", json={"subject": 1, "type": "טובה", "text": "עוזר לאחרים"},
                   headers={"X-Request-Id": "qn-1"})
assert resp.get_json().get("duplicate"), "same request id = the same note"
assert client.post("/notes/quick", json={"subject": 1, "type": "רפואה", "text": "x"}).status_code == 400
assert client.post("/notes/quick", json={"subject": 1, "type": "טובה", "text": "  "}).status_code == 400
with app.app_context():
    notes = Note.query.filter_by(subject_id="1/1").all()
    assert len(notes) == 1 and notes[0].location == "זחילות" and notes[0].author_id == 1
    assert Note.query.filter_by(subject_id="2/1").count() == 0
login_as(0)
resp = client.post("/notes/quick", json={"group": 2, "subject": 1, "type": "רעה", "text": "מנהל"})
assert resp.get_json()["success"]
with app.app_context():
    assert Note.query.filter_by(subject_id="2/1", author_id=0).count() == 1
assert 'id="qn-sheet"' in html_of(client.get("/2/")), "admin home has the quick-note sheet"
print("OK: quick notes save once, scoped per role")

# 10) Doctor / HR stations
resp = client.post("/login", data={"role": "doctor", "password": "d"})
assert "/login" in resp.location, "not configured yet"
# Throwaway station passwords for this test database only (not real credentials).
client.post("/admin/staff/doctor", data={"password": "doc1"})  # ggignore
client.post("/admin/staff/hr", data={"password": "hr12"})  # ggignore
with app.app_context():
    assert User.query.get(DOCTOR_ID) and User.query.get(HR_ID)
assert "עמדות מובנות" in html_of(client.get("/admin-panel"))
client.get("/logout")
resp = client.post("/login", data={"role": "group", "id": "abc", "password": "x"})
assert resp.status_code == 302, "non-numeric group id must not 500"
resp = client.post("/login", data={"role": "doctor", "password": "wrong"})
assert "/login" in resp.location
resp = client.post("/login", data={"role": "doctor", "password": "doc1"})
assert resp.status_code == 302
assert client.get("/").location.endswith("/staff")
assert client.get("/circles").location.endswith("/staff"), "staff only reach their own pages"
assert client.post("/add-all", data={}).status_code == 403
html = html_of(client.get("/staff?group=1"))
assert "שלום, רופא" in html and "קבוצה 1" in html
resp = client.post("/notes/quick", json={"group": 1, "subject": 4, "type": "טובה", "text": "כאב ברך"})
assert resp.get_json()["success"]
client.post("/delete-candidate/6?group=1")
with app.app_context():
    note = Note.query.filter_by(subject_id="1/4", author_id=DOCTOR_ID).first()
    assert note.type == "רפואה", "staff notes always get the station's type"
    c6 = Candidate.query.get("1/6")
    assert c6.status == "פרש" and c6.withdraw_reason == "רפואי"
client.get("/logout")
client.post("/login", data={"role": "hr", "password": "hr12"})
client.post("/notes/quick", json={"group": 1, "subject": 4, "type": "טובה", "text": "בעיית ת\"ש"})
assert client.post("/delete-candidate/7?group=1").status_code == 403, "HR cannot retire"
client.get("/logout")
login_as(1)
html = html_of(client.get("/"))
assert "כאב ברך" in html and "בעיית ת" in html, "doctor/HR notes show on the group home page"
print("OK: doctor/HR stations log in by role, write notes, show on home")

# 11) Home page sorting by physical score
html = html_of(client.get("/?sort=physical"))
assert 'aria-pressed="true"' in html and 'data-sort="physical"' in html
print("OK: home page sorts by physical score")

# 12) Final grade: categories only, ranking inside a category
html = html_of(client.get("/final-grade/"))
assert 'name="note"' not in html, "the final grade has no free-text note"
client.post("/final-grade/", data={"id": "1", "grade": "91"})
with app.app_context():
    assert Candidate.query.get("1/1").final_weighted_grade is None
for number in (1, 2, 3):
    client.post("/final-grade/", data={"id": str(number), "grade": "לקחת"})
resp = client.post("/final-summary/save", json={"order": {"לקחת": [3, 1, 2]}})
assert resp.get_json()["success"]
with app.app_context():
    assert [Candidate.query.get(f"1/{n}").final_rank for n in (3, 1, 2)] == [1, 2, 3]
html = html_of(client.get("/final-summary/"))
assert html.index('data-number="3"') < html.index('data-number="1"') < html.index('data-number="2"')
assert client.post("/final-summary/save", json={"order": {"מצוין": [1]}}).status_code == 400
client.post("/final-grade/", data={"id": "3", "grade": "בלית ברירה"})
with app.app_context():
    c3 = Candidate.query.get("1/3")
    assert c3.final_weighted_grade == "בלית ברירה" and c3.final_rank is None
print("OK: final grade by category and ranking inside it")


# 13) Candidate photos
def tiny_png():
    raw = b"\x00\xff\x00\x00"
    def chunk(kind, data):
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data) & 0xffffffff)
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(raw)) + chunk(b"IEND", b""))


resp = client.post("/candidate-photo/1/1", data={"photo": (io.BytesIO(tiny_png()), "p.png")},
                   content_type="multipart/form-data")
body = resp.get_json()
assert body["success"] and "v=" in body["url"], body
resp = client.get(body["url"])
assert resp.status_code == 200 and resp.mimetype == "image/png"
assert "immutable" in resp.headers["Cache-Control"]
resp = client.post("/candidate-photo/1/1", data={"photo": (io.BytesIO(b"<svg/>"), "x.svg")},
                   content_type="multipart/form-data")
assert resp.status_code == 400
assert 'avatar-hero' in html_of(client.get("/candidate/1/1"))
login_as(2)
assert client.get(body["url"]).status_code == 404, "another group cannot see the photo"
login_as(1)
client.post("/candidate-photo/1/1/delete")
with app.app_context():
    gone = CandidatePhoto.query.get("1/1")
    assert gone is None or not gone.data
assert client.get(body["url"]).status_code == 404
assert "avatar-hero" not in html_of(client.get("/candidate/1/1"))
again = client.post("/candidate-photo/1/1", data={"photo": (io.BytesIO(tiny_png()), "p.png")},
                    content_type="multipart/form-data").get_json()
assert again["url"] != body["url"], "a new photo must never reuse a cached (immutable) URL"
print("OK: candidate photos upload, show, stay private, delete, never reuse a URL")

# 14) Interview summary shows every interview without filtering first
client.post("/interview/", data={"id": "4", "interviewer": "x", "grade": "כן, אבל", "note": "טוב",
                                 "tash": "אין", "medical": "אין"})
html = html_of(client.get("/show-interview/"))
assert "כל הראיונות שבוצעו" in html and "דני" in html
login_as(0)
assert "דני" in html_of(client.get("/show-interview-admin/"))
login_as(1)
print("OK: interview summaries list everything by default")

# 15) Removed pages redirect home and are gone from the menus
assert client.get("/station-reviews/").status_code == 302
assert client.get("/candidates/").status_code == 302
html = html_of(client.get("/"))
assert "דירוג לפי תחנה" not in html and "הקבוצה שלי" not in html
print("OK: station ranking and 'my group' pages are removed")

# 16) Page views write nothing once summaries are up to date, and stay cheap
statements = []


def count(conn, cursor, statement, *args):
    statements.append(statement.split()[0].upper())


with app.app_context():
    update_avgs_nf(1)  # settle
    event.listen(db.engine, "before_cursor_execute", count)
    update_avgs_nf(1)
    event.remove(db.engine, "before_cursor_execute", count)
assert not [s for s in statements if s in ("INSERT", "UPDATE", "DELETE")], statements
statements.clear()
with app.app_context():
    event.listen(db.engine, "before_cursor_execute", count)
client.get("/")
with app.app_context():
    event.remove(db.engine, "before_cursor_execute", count)
assert len(statements) < 20, f"home page ran {len(statements)} queries"
print(f"OK: no writes on a settled page view; home page = {len(statements)} queries")

# 16b) Stale or replayed writes never roll newer data back
with app.app_context():
    Candidate.query.get("1/9").name = "מגובש 9"
    db.session.commit()
client.post("/group-manage/names", data={"name-9": "ראשון", "orig-9": "מגובש 9"})
client.post("/group-manage/names", data={"name-9": "ישן", "orig-9": "מגובש 9"})  # stale page
with app.app_context():
    assert Candidate.query.get("1/9").name == "ראשון"
for number in (10, 11):
    client.post("/final-grade/", data={"id": str(number), "grade": "כן, אבל"})
client.post("/final-grade/", data={"id": "11", "grade": "בלית ברירה"})  # changed elsewhere
resp = client.post("/final-summary/save", json={"order": {"כן, אבל": [11, 10]}, "from": {"10": "כן, אבל", "11": "כן, אבל"}})
assert resp.get_json().get("stale") == 1
with app.app_context():
    assert Candidate.query.get("1/11").final_weighted_grade == "בלית ברירה"
march = {"station": "מסע 3", "reviews": [{"subject": 1, "counter": 5, "note": ""}]}
client.post("/update-counter-reviews", json=march, headers={"X-Request-Id": "m-1"})
client.post("/update-counter-reviews", json={"station": "מסע 3", "reviews": [{"subject": 1, "counter": 8, "note": ""}]},
            headers={"X-Request-Id": "m-2"})
client.post("/update-counter-reviews", json=march, headers={"X-Request-Id": "m-1"})  # late replay
with app.app_context():
    assert Review.query.filter_by(station="מסע 3", subject_id="1/1").first().counter_value == 8
# group scores follow the row's candidate number, not its position
client.post("/add-all", data={"station": ["הרצאות"] * 2, "subject": ["3", "1"], "grade": ["4", "2"], "note": ["", ""]})
with app.app_context():
    assert Review.query.filter_by(station="הרצאות", subject_id="1/3").first().grade == 4
    assert Review.query.filter_by(station="הרצאות", subject_id="1/1").first().grade == 2
print("OK: stale names / ranking / march snapshots / shifted rows cannot overwrite newer data")

# 16c) A heat that names a removed number still saves the rest
resp = client.post("/circles/finished-act", json={"finished": [999, 1], "movement_type": "זחילות"})
assert resp.status_code == 200 and resp.get_json()["success"]
print("OK: unknown numbers are dropped from a heat instead of failing it")

# 16d) Custom stations whose name contains a built-in one keep the old
#      averaging (merged into the built-in), on every screen alike
client.post("/circles/finished-act", json={"finished": [1, 2], "movement_type": "אחר", "other": "ספרינטים 2"})
with app.app_context():
    assert Review.query.filter_by(station="ספרינטים 2 סיכום").count() == 0
    s1 = Review.query.filter_by(subject_id="1/1", station="ספרינטים סיכום").first()
    assert s1 is not None and s1.grade == 4
html_home = html_of(client.get("/?sort=number"))
html_profile = html_of(client.get("/candidate/1/1"))
import re as _re
tiz_home = _re.search(r'data-number="1" data-total="[^"]*" data-tiz="([^"]*)"', html_home).group(1)
assert f">{tiz_home}<" in html_profile.replace(" ", ""), (tiz_home,)
print("OK: physical averages agree between home and candidate page")

# 16e) State changes are POST-only; the doctor undoes only medical retirements
assert client.get("/delete-candidate/12").status_code == 405
assert client.get("/return/12").status_code == 405
client.post("/delete-candidate/12")  # plain retirement by the group
client.get("/logout")
client.post("/login", data={"role": "doctor", "password": "doc1"})
assert client.post("/return/12?group=1").status_code == 403
client.get("/logout")
login_as(1)
print("OK: retire/return are POST-only; doctor scope enforced")

# 17) Cookies are SameSite=Lax (no cross-site POST arrives logged in)
client.get("/logout")
resp = client.post("/login", data={"role": "group", "id": "1", "password": "pw"})
cookies = resp.headers.getlist("Set-Cookie")
assert any(c.startswith("remember_token=") and "SameSite=Lax" in c for c in cookies), cookies
assert any(c.startswith("session=") and "SameSite=Lax" in c for c in cookies), cookies
print("OK: session and remember cookies are SameSite=Lax")

# 17b) Re-registering a number whose old candidates are still stored
login_as(0)
with app.app_context():
    db.session.add(Candidate(id="7/3", group_id=None, name="יתום"))
    db.session.commit()
resp = client.post("/register", data={"id": "7", "name": "חוזרת", "mitam": "1", "password": "p",
                                      "candidates_count": "5"})
assert resp.status_code == 302
with app.app_context():
    assert User.query.get(7) is not None
    assert Candidate.query.filter_by(group_id=7).count() == 4
print("OK: re-registering a group number skips numbers that still exist")

# 18) A brand-new system can still create its first (admin) account
with app.app_context():
    db.session.delete(User.query.get(0))
    db.session.commit()
client.get("/logout")
resp = client.post("/register", data={"id": "0", "name": "מנהל", "mitam": "0", "password": "a",
                                      "candidates_count": "25"})
with app.app_context():
    assert User.query.get(0) is not None and Candidate.query.filter_by(group_id=0).count() == 0
print("OK: first-run admin bootstrap still works")

print("ALL PWA FEEDBACK V4 TESTS PASSED")
