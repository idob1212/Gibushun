"""Notes board, single-mode memory and saved acts (field feedback, round 2).

Covers:
- notes board: grade comments are "תחנה" with their grade (they used to be
  wrapped as ניטרלית notes), shown once (not again from the summary row),
  newest first, everything on GET; old POSTs and the admin board still work
- single mode: the ✓ map, auto-advance to the next ungraded candidate
- grading modes: one switcher on the four screens, the dock is tagged
- acts: new acts keep the finishing place and the time; acts saved before
  that are read back correctly; reorder recomputes grades in place; redo
  replaces the order and keeps name, number and time; a move can be undone
  back to the exact name
- photos: no forced camera

Run like the other scripts (pinned deps):
    python tests/test_notes_acts.py
"""
import json
import os
import re
from datetime import datetime

os.environ["DATABASE_URL"] = "sqlite:////tmp/test_notes_acts.db"

from main import app, db, User, Candidate, Review, Note, act_grades  # noqa: E402

app.config["WTF_CSRF_ENABLED"] = False

with app.app_context():
    db.drop_all()
    db.create_all()
    db.session.add_all([
        User(id=0, name="admin", password="x", mitam_num=0, sprint_num=0, crawl_num=0, alonka_num=0),
        User(id=1, name="group", password="pw", mitam_num=1, sprint_num=0, crawl_num=0, alonka_num=0),
    ])
    for n in range(1, 7):
        db.session.add(Candidate(id=f"1/{n}", group_id=1, name=f"מגובש {n}"))
    db.session.commit()

client = app.test_client()


def login_as(user_id):
    with client.session_transaction() as sess:
        sess["_user_id"] = str(user_id)
        sess["_fresh"] = True


def html_of(resp):
    return resp.get_data(as_text=True)


def board_kinds(html):
    """The kind of each card, in page order."""
    return re.findall(r'<li class="card[^"]*" data-kind="([^"]+)" data-number="(\d+)"', html)


login_as(1)

# 1) Notes board: a grade comment is "תחנה" with its grade, shown once
client.post("/new-note", data={"subject": "2", "type": "טובה", "text": "עזר לכולם"})
client.post("/new-review", data={"station": "שולחן חול", "subject": "3", "grade": "4", "note": "הציג מצוין"})
with app.app_context():
    # fixed times; an older note with a date only, and a grade saved before
    # times were kept (the column default fills new rows, so clear it after)
    Note.query.filter_by(subject_id="1/2").one().date = "02-11-2026 20:00"
    Review.query.filter_by(station="שולחן חול", subject_id="1/3").one().created_at = datetime(2026, 11, 2, 21, 0)
    db.session.add(Note(subject_id="1/1", type="רעה", text="איחר", author_id=1, date="01-11-2026"))
    old = Review(station="הרצאות", subject_id="1/4", grade=2, note="בינוני", author_id=1)
    db.session.add(old)
    db.session.flush()
    old.created_at = None
    db.session.commit()
html = html_of(client.get("/show-notes"))
cards = board_kinds(html)
assert ("תחנה", "3") in cards and ("ניטרלית", "3") not in cards, "a grade comment is not a neutral note"
assert cards.count(("תחנה", "3")) == 1, "shown once, not again from its summary row"
assert "ציון 4" in html and "badge-success font-bold\">ציון 4" in html, "coloured by the grade"
assert cards == [("תחנה", "3"), ("טובה", "2"), ("רעה", "1"), ("תחנה", "4")], \
    "newest first; a date-only note by its day; undated rows last"
assert "02/11 21:00" in html and ">01/11<" in html
for kind in ("טובה", "ניטרלית", "רעה", "תחנה"):
    assert f'data-kind="{kind}" data-tone=' in html, f"a filter chip for {kind}"
assert 'data-kind="רפואה"' not in html, "staff chips only when such a note exists"
# old pages posted the candidate to show — same board, that candidate picked
html = html_of(client.post("/show-notes", data={"id": "3"}))
assert '<option value="3" selected>' in html
print("OK: notes board — station comments with their grade, newest first, one page")

# 1b) The admin board shows a group's notes, read-only
login_as(0)
html = html_of(client.get("/notes-admin/?group=1"))
assert ("תחנה", "3") in board_kinds(html) and not re.search(r"<a [^>]*data-board-edit", html)
login_as(1)
print("OK: admin notes board per group")

# 2) Single mode: ✓ map and the next ungraded candidate
html = html_of(client.post("/new-review", data={"station": "שולחן חול", "subject": "4", "grade": "2"}))
assert 'id="subject-5" checked' in html, "after 4 comes 5 (3 was graded here already)"
graded = json.loads(re.search(r"var graded = ([^;]*);", html).group(1))
assert graded["שולחן חול"] == [3, 4], "the page knows who has a grade at the station"
restores = re.compile(r"<form [^>]*data-restore-station")
assert not restores.search(html) and restores.search(html_of(client.get("/new-review"))), \
    "a fresh visit restores the remembered station; a save keeps the one just used"
html = html_of(client.post("/new-review", data={"station": "שולחן חול", "subject": "6", "grade": "2"}))
assert 'id="subject-1" checked' in html, "wraps around to the first without a grade"
print("OK: single mode moves on to the next ungraded candidate and keeps the station")

# 3) One mode switcher on the grading screens; the dock is tagged
for path in ("/circles", "/counter-review", "/new-review", "/new-group-review"):
    html = html_of(client.get(path))
    assert 'data-grade-modes="1"' in html and len(re.findall(r'class="mode-tab( is-active)?"', html)) == 4, path
    assert 'aria-current="page"' in html.split('data-grade-modes')[1].split("</nav>")[0], path
    assert "עבור למצב" not in html, path
    assert 'data-grade-dock="1"' in html
print("OK: one mode switcher, dock remembers the mode")

# 4) Acts keep places and time; reorder and redo work in place
resp = client.post("/circles/finished-act", json={"finished": [3, 1, 5, 2], "movement_type": "זחילות"})
assert resp.get_json()["station"] == "זחילות - אקט 1"
with app.app_context():
    rows = {r.subject_id: r for r in Review.query.filter_by(station="זחילות - אקט 1")}
    assert [rows[f"1/{n}"].place for n in (3, 1, 5, 2, 4, 6)] == [1, 2, 3, 4, 0, 0]
    assert all(isinstance(r.created_at, datetime) for r in rows.values())
    saved_at = rows["1/3"].created_at
html = html_of(client.get("/acts"))
assert "זחילות · אקט 1" in html and "4 סיימו · 2 לא סיימו" in html and "ראשונים:" in html
assert "סדר מחדש" in html and "בצע מחדש" in html

# reorder: 5 moves to first, 2 does not finish, 4 joins at the end
resp = client.post("/acts/order", json={"station": "זחילות - אקט 1", "finished": [5, 3, 1, 4], "unfinished": [2, 6]})
assert resp.get_json()["success"]
expect = dict(zip([5, 3, 1, 4], act_grades(4)))
with app.app_context():
    rows = {int(r.subject_id.split("/")[1]): r for r in Review.query.filter_by(station="זחילות - אקט 1")}
    assert all(abs(rows[n].grade - expect[n]) < 0.006 for n in expect)  # stored rounded to 2 places
    assert rows[2].grade == 1 and rows[2].place == 0
    assert [rows[n].place for n in (5, 3, 1, 4)] == [1, 2, 3, 4]
    assert all(r.created_at == saved_at for r in rows.values()), "the saved time stays"
    summary = Review.query.filter_by(station="סיכום זחילות - אקט 1", subject_id="1/5").one()
    assert summary.grade == 4
html = html_of(client.get("/acts/order?station=זחילות - אקט 1"))
assert "[5, 3, 1, 4]" in html and "[2, 6]" in html
assert client.post("/acts/order", json={"station": "זחילות - אקט 9", "finished": [1]}).status_code == 404

# redo: replaces the order, same name and number
html = html_of(client.get("/circles?redo=זחילות - אקט 1"))
assert "מבצע מחדש · זחילות · אקט 1" in html and "ביטול — השאר את הסדר הקודם" in html
resp = client.post("/circles/finished-act", json={"finished": [6, 2], "movement_type": "זחילות",
                                                  "replace": "זחילות - אקט 1"})
data = resp.get_json()
assert data["replaced"] and data["station"] == "זחילות - אקט 1"
with app.app_context():
    rows = {int(r.subject_id.split("/")[1]): r for r in Review.query.filter_by(station="זחילות - אקט 1")}
    assert len(rows) == 6 and rows[6].place == 1 and rows[6].grade == 4 and rows[2].place == 2
    assert rows[5].place == 0 and rows[5].grade == 1
    assert Review.query.filter(Review.station.like("זחילות - אקט 2%")).count() == 0, "no new act number"
assert "הסדר של &#34;זחילות - אקט 1&#34; הוחלף" in html_of(client.get(data["redirect"])) or \
    'הסדר של "זחילות - אקט 1" הוחלף' in html_of(client.get(data["redirect"]))
print("OK: acts keep their place and time; reorder and redo change the order in place")

# 5) Acts saved before places were kept are read back right
with app.app_context():
    finishers = [4, 2, 6, 1, 3]   # 5 finishers: the last two also got 1
    for n, grade in zip(finishers, act_grades(5)):
        db.session.add(Review(station="ספרינטים - אקט 1", subject_id=f"1/{n}", grade=round(grade, 2), author_id=1))
    db.session.add(Review(station="ספרינטים - אקט 1", subject_id="1/5", grade=1, author_id=1))
    db.session.flush()
    for r in Review.query.filter_by(station="ספרינטים - אקט 1"):
        r.created_at = None
    db.session.commit()
html = html_of(client.get("/acts/order?station=ספרינטים - אקט 1"))
assert "[4, 2, 6, 1, 3]" in html and "[5]" in html, "finishers vs non-finishers recovered from the grades"
print("OK: older acts (no places saved) split into finishers and non-finishers")

# 6) Moving an act shows up with an undo that restores the exact name
resp = client.post("/acts/rename", data={"station": "ספרינטים - אקט 1", "new_base": "זחילות"}, follow_redirects=True)
html = html_of(resp)
assert html.count("הועבר ל-") == 1, "one message: the undo bar (no flash repeating it)"
assert '"ספרינטים - אקט 1" הועבר ל-"זחילות - אקט 2"' in html
client.post("/acts/undo-move", data={"station": "זחילות - אקט 2", "back": "ספרינטים - אקט 1"})
with app.app_context():
    assert Review.query.filter_by(station="ספרינטים - אקט 1").count() == 6
    assert Review.query.filter_by(station="זחילות - אקט 2").count() == 0
print("OK: a moved act can be put back under its exact name")

# 7) Photos: the system picker (camera or library), not a forced camera
html = html_of(client.get("/group-manage"))
assert 'data-photo-input' in html and 'capture=' not in html
print("OK: photo picker offers the library too")

print("ALL NOTES / ACTS TESTS PASSED")
