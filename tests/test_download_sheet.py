"""Smoke test: /download-sheet/ must return 200 + a real xlsx.

Regression: adding a column to Candidate (withdraw_reason) shifted the
positional column rename in downloadb() and 500'd the admin data export.

Run inside the project Docker image (local python can't install the pinned deps):
    docker build -t gibushun-smoke .
    docker run --rm -v "$PWD:/app" -w /app -e PYTHONPATH=/app gibushun-smoke \
        python tests/test_download_sheet.py
"""
import io
import os
import zipfile

# Force a throwaway DB before importing main — this test drops all tables.
os.environ["DATABASE_URL"] = "sqlite:////tmp/test_download_sheet.db"

from main import app, db, User, Candidate, Review  # noqa: E402

with app.app_context():
    db.drop_all()
    db.create_all()
    admin = User(id=0, name="admin", password="x", mitam_num=0,
                 sprint_num=0, crawl_num=0, alonka_num=0)
    group = User(id=1, name="group1", password="x", mitam_num=7,
                 sprint_num=0, crawl_num=0, alonka_num=0)
    db.session.add_all([admin, group])
    active = Candidate(id="1/1", group_id=1, name="a", status="פעיל")
    withdrawn = Candidate(id="1/2", group_id=1, name="b", status="פרש",
                          withdraw_reason="רפואי")
    active.final_weighted_grade = "88"
    active.final_weighted_note = "מצוין"
    db.session.add_all([active, withdrawn])
    db.session.add(Review(author_id=1, station="בוחן", subject_id="1/1", grade=3.0))
    db.session.commit()

client = app.test_client()
with client.session_transaction() as sess:
    sess["_user_id"] = "0"

resp = client.get("/download-sheet/")
assert resp.status_code == 200, f"expected 200, got {resp.status_code}"
data = resp.get_data()
assert data[:2] == b"PK", "response is not an xlsx (zip) file"
zf = zipfile.ZipFile(io.BytesIO(data))
assert any(n.startswith("xl/") for n in zf.namelist())

# The weighted final grade must be the LAST column of the results sheet.
# (No xlsx reader in the image — parse the sheet XML directly.)
from xml.etree import ElementTree as ET  # noqa: E402

shared = ET.fromstring(zf.read("xl/sharedStrings.xml"))
strings = ["".join(t.text or "" for t in si.iter() if t.tag.endswith("}t"))
           for si in shared]
sheet = ET.fromstring(zf.read("xl/worksheets/sheet1.xml"))
ns = {"m": sheet.tag.split("}")[0][1:]}
header = sheet.find(".//m:sheetData/m:row", ns)
last_cell = header.findall("m:c", ns)[-1]
val = last_cell.findtext("m:v", namespaces=ns)
if last_cell.get("t") == "s":
    val = strings[int(val)]
assert val == "ציון סופי משוקלל ראיון וגיבוש", f"last column is {val!r}"
assert "88" in strings, "weighted grade value missing from the sheet"
print("OK: /download-sheet/ returned 200 with a valid xlsx,", len(data), "bytes")
print("OK: weighted final grade is the last column")
