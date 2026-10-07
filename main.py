import os
import re
import csv
import json
import time
import hashlib
import unicodedata
from collections import defaultdict
from io import BytesIO, StringIO
import logging
import flask
import pytz
import requests
import sqlalchemy
from flask import Flask, render_template, redirect, url_for, flash, abort, request, jsonify, send_from_directory, \
    send_file, after_this_request, request, session
from flask_bootstrap import Bootstrap
from flask_ckeditor import CKEditor
from datetime import date, datetime, timedelta
from functools import wraps
from sqlalchemy import engine, distinct, func
from werkzeug.security import generate_password_hash, check_password_hash
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.orm import relationship
from flask_login import UserMixin, login_user, LoginManager, login_required, current_user, logout_user
from forms import CounterReviewForm, LoginForm, RegisterForm, CreateReviewForm, EditUserForm, Search_review, EditReviewForm, \
    UpdateDateForm, NewCandidateForm, SelectPhysicalReviewsForm, selectCandidate, AddFinalStatusForm, \
    SelectPhysicalReviewsFormAdmin, selectCandidateAdmin, selectGroup, AddNameForm, InterviewForm, \
    GroupReviewForm, CreateNoteForm, FinalWeightedGradeForm
from flask_gravatar import Gravatar
import sys
import logging
import pandas as pd
import xlwt
from xlwt.Workbook import *
from pandas import ExcelWriter
import xlsxwriter
import zipfile
import openpyxl
from openpyxl.utils.exceptions import InvalidFileException
import logging



app = Flask(__name__)
app.config['SECRET_KEY'] = "8BYkEfBA6O6donzWlSihBXox7C0sKR6b"
ckeditor = CKEditor(app)
Bootstrap(app)
gravatar = Gravatar(app, size=100, rating='g', default='retro', force_default=False, force_lower=False, use_ssl=False, base_url=None)
app.logger.addHandler(logging.StreamHandler(sys.stdout))
app.logger.setLevel(logging.ERROR)




##CONNECT TO DB
_database_url = os.environ.get("DATABASE_URL", "sqlite:///data.db")
if _database_url.startswith("postgres://"):
    _database_url = _database_url.replace("postgres://", "postgresql://", 1)
app.config['SQLALCHEMY_DATABASE_URI'] = _database_url
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
_engine_options = {
    'pool_pre_ping': True,
    'pool_recycle': 280,
}
if _database_url.startswith("postgresql"):
    # QueuePool sizing only applies to the pooled Postgres backend; SQLite uses NullPool.
    _engine_options['pool_size'] = 5
    _engine_options['max_overflow'] = 10
    _engine_options['connect_args'] = {
        'keepalives': 1,
        'keepalives_idle': 30,
        'keepalives_interval': 10,
        'keepalives_count': 5,
        'sslmode': 'require',
    }
app.config['SQLALCHEMY_ENGINE_OPTIONS'] = _engine_options
db = SQLAlchemy(app)
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

PUBLIC_ENDPOINTS = {'login', 'register', 'static', 'service_worker', 'offline'}

# Built-in staff stations. They log in by role (no group number) and enter
# notes on any group's candidates, so the doctor and the HR officer no longer
# switch between group accounts. Negative ids keep them out of the group list.
DOCTOR_ID = -1
HR_ID = -2
STAFF_ROLES = {
    DOCTOR_ID: {"key": "doctor", "title": "רופא", "short": "רופא", "note_type": "רפואה", "icon": "fa-user-md"},
    HR_ID: {"key": "hr", "title": "קצינת כוח אדם", "short": "קצינת כ\"א", "note_type": "כוח אדם", "icon": "fa-id-card"},
}
STAFF_BY_KEY = {role["key"]: user_id for user_id, role in STAFF_ROLES.items()}
NOTE_TYPES = ["טובה", "ניטרלית", "רעה"]
STAFF_NOTE_TYPES = [role["note_type"] for role in STAFF_ROLES.values()]
# Everything a staff station may reach; any other page sends it back home.
STAFF_ENDPOINTS = PUBLIC_ENDPOINTS | {
    'logout', 'home', 'staff_home', 'note_quick', 'delete_note',
    'delete_candidate', 'return_candidate',
}

PHYSICAL_BASE_STATIONS = ["ספרינטים", "זחילות", "אלונקה סוציומטרית", "מתלה שזיפים"]
# Interview / opinion scale (best → worst order is not implied here).
GRADE_OPTIONS = ["לא לגעת - קו אדום", "בלית ברירה", "כן, אבל", "להתאבד"]
# Final weighted grade: categories only, ordered best → worst. The final
# summary screen ranks candidates inside each category.
FINAL_CATEGORIES = ["להתאבד", "לקחת", "כן, אבל", "בלית ברירה", "לא לגעת - קו אדום"]
# New groups start with numbered placeholder candidates; the group renames
# them in "ניהול קבוצה" instead of typing every number by hand.
DEFAULT_GROUP_SIZE = 25
PLACEHOLDER_NAME_RE = re.compile(r"^מגובש \d+$")
MAX_PHOTO_BYTES = 2 * 1024 * 1024
PHOTO_TYPES = {"image/jpeg": b"\xff\xd8\xff", "image/png": b"\x89PNG", "image/webp": b"RIFF"}


def is_staff(user):
    return bool(user and user.is_authenticated and user.id in STAFF_ROLES)


def is_admin(user):
    return bool(user and user.is_authenticated and user.id == 0)


def staff_role(user):
    return STAFF_ROLES.get(user.id) if is_staff(user) else None


def placeholder_name(number):
    return f"מגובש {number}"


def is_placeholder_name(name):
    return bool(PLACEHOLDER_NAME_RE.match((name or "").strip()))


@app.before_request
def _require_login():
    if request.endpoint is None or request.endpoint in PUBLIC_ENDPOINTS:
        return None
    if not current_user.is_authenticated:
        return redirect(url_for('login'))
    if is_staff(current_user) and request.endpoint not in STAFF_ENDPOINTS:
        if request.method == "GET":
            return redirect(url_for('staff_home'))
        abort(403)


app.logger.addHandler(logging.StreamHandler(sys.stdout))
app.logger.setLevel(logging.ERROR)

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))




class User(UserMixin, db.Model):
    __tablename__ = "users"
    id = db.Column(db.Integer, primary_key=True)
    password = db.Column(db.String(1000), nullable=False)
    name = db.Column(db.String(1000), nullable=False)
    reviews = relationship("Review", back_populates="author")
    notes = relationship("Note", back_populates="author")
    candidates = relationship("Candidate", back_populates="group")
    sprint_num = db.Column(db.Integer, nullable=False)
    crawl_num = db.Column(db.Integer, nullable=False)
    alonka_num = db.Column(db.Integer, nullable=False)
    mitam_num = db.Column(db.Integer, nullable=False)


class Candidate(db.Model):
    __tablename__ = "candidates"
    id = db.Column(db.String(250), primary_key=True)
    group_id = db.Column(db.Integer, db.ForeignKey("users.id"))
    group = relationship("User", back_populates="candidates")
    name = db.Column(db.String(1000), nullable=False)
    final_status = db.Column(db.String(1000))
    final_note = db.Column(db.Text)
    status = db.Column(db.String(1000))
    withdraw_reason = db.Column(db.String(50))
    interviewer = db.Column(db.String(1000))
    interview_grade = db.Column(db.String(1000))
    interview_note = db.Column(db.Text)
    tash_prob = db.Column(db.String(1000))
    medical_prob = db.Column(db.String(1000))
    final_weighted_grade = db.Column(db.String(1000))
    final_weighted_note = db.Column(db.Text)
    # Priority inside the final-grade category (1 = first). NULL = unranked.
    final_rank = db.Column(db.Integer)
    reviews = relationship("Review", back_populates="subject")
    notes = relationship("Note", back_populates="subject")

    @property
    def number(self):
        return int(self.id.split("/")[1])

class Review(db.Model):
    __tablename__ = "reviews"
    id = db.Column(db.Integer, primary_key=True)
    author_id = db.Column(db.Integer, db.ForeignKey("users.id"))
    author = relationship("User", back_populates="reviews")
    station = db.Column(db.String(1000), nullable=False)
    subject_id = db.Column(db.String(250), db.ForeignKey("candidates.id"))
    subject = relationship("Candidate", back_populates="reviews")
    grade = db.Column(db.Float, nullable=False)
    note = db.Column(db.Text)
    counter_value = db.Column(db.Integer, nullable=True)

class Note(db.Model):
    __tablename__ = "notes"
    id = db.Column(db.Integer, primary_key=True)
    author_id = db.Column(db.Integer, db.ForeignKey("users.id"))
    author = relationship("User", back_populates="notes")
    subject_id = db.Column(db.String(250), db.ForeignKey("candidates.id"))
    subject = relationship("Candidate", back_populates="notes")
    type = db.Column(db.String(1000), nullable=False)
    text = db.Column(db.Text)
    location = db.Column(db.String(1000))
    date = db.Column(db.String(1000))


class ProcessedRequest(db.Model):
    __tablename__ = "processed_requests"
    request_id = db.Column(db.String(64), primary_key=True)


class CandidatePhoto(db.Model):
    # Stored in the DB: the Heroku filesystem is ephemeral. The client
    # downsizes to a small JPEG first, so a row is tens of KB.
    __tablename__ = "candidate_photos"
    candidate_id = db.Column(db.String(250), db.ForeignKey("candidates.id"), primary_key=True)
    mime = db.Column(db.String(50), nullable=False)
    data = db.Column(db.LargeBinary, nullable=False)
    version = db.Column(db.Integer, nullable=False, default=1)


class PriorInterview(db.Model):
    """One answer of the unit's interview form (the Google Forms "תגובות"
    sheet), synced by the admin to flag candidates who were already
    interviewed. Only what the alert shows is kept: no ID numbers and no
    medical or ת"ש answers."""
    __tablename__ = "prior_interviews"
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(300), nullable=False)
    name_key = db.Column(db.String(300), nullable=False, index=True)
    interviewed_at = db.Column(db.DateTime)
    interviewer = db.Column(db.String(300))
    gibush = db.Column(db.String(300))
    rating = db.Column(db.String(300))
    impression = db.Column(db.Text)


class InterviewSync(db.Model):
    """The last interview-file sync (a single row)."""
    __tablename__ = "interview_syncs"
    id = db.Column(db.Integer, primary_key=True)
    filename = db.Column(db.String(300))
    synced_at = db.Column(db.DateTime, nullable=False)


db.create_all()


def _migrate_text_columns():
    if not _database_url.startswith("postgresql"):
        return
    alterations = [
        ("candidates", "interview_note"),
        ("candidates", "final_note"),
        ("reviews", "note"),
        ("notes", "text"),
    ]
    with db.engine.connect() as conn:
        for table, column in alterations:
            conn.execute(
                sqlalchemy.text(
                    f'ALTER TABLE {table} ALTER COLUMN {column} TYPE TEXT'
                )
            )


_migrate_text_columns()


def _add_withdraw_reason_column():
    inspector = sqlalchemy.inspect(db.engine)
    columns = [col["name"] for col in inspector.get_columns("candidates")]
    if "withdraw_reason" in columns:
        return
    with db.engine.connect() as conn:
        conn.execute(
            sqlalchemy.text(
                "ALTER TABLE candidates ADD COLUMN withdraw_reason VARCHAR(50)"
            )
        )


_add_withdraw_reason_column()


def _add_final_weighted_columns():
    inspector = sqlalchemy.inspect(db.engine)
    columns = [col["name"] for col in inspector.get_columns("candidates")]
    to_add = [
        ("final_weighted_grade", "VARCHAR(1000)"),
        ("final_weighted_note", "TEXT"),
    ]
    with db.engine.connect() as conn:
        for name, col_type in to_add:
            if name not in columns:
                conn.execute(
                    sqlalchemy.text(
                        f"ALTER TABLE candidates ADD COLUMN {name} {col_type}"
                    )
                )


_add_final_weighted_columns()


def _add_final_rank_column():
    inspector = sqlalchemy.inspect(db.engine)
    columns = [col["name"] for col in inspector.get_columns("candidates")]
    if "final_rank" in columns:
        return
    with db.engine.connect() as conn:
        conn.execute(sqlalchemy.text("ALTER TABLE candidates ADD COLUMN final_rank INTEGER"))


_add_final_rank_column()

app.config['WTF_CSRF_TIME_LIMIT'] = None
# iOS can drop the session-only cookie between field days; the remember cookie
# logs the group back in so queued offline writes do not bounce to /login.
app.config['REMEMBER_COOKIE_DURATION'] = timedelta(days=60)
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'


class _SameSiteRememberCookie:
    """Lax remember cookie: Flask-Login 0.5 has no setting for it, and without
    it a cross-site POST would still arrive logged in (CSRF)."""

    def __init__(self, wsgi_app):
        self.wsgi_app = wsgi_app

    def __call__(self, environ, start_response):
        def _start_response(status, headers, exc_info=None):
            headers = [
                (k, v + "; SameSite=Lax")
                if k.lower() == "set-cookie" and v.startswith("remember_token=") and "samesite" not in v.lower()
                else (k, v)
                for k, v in headers
            ]
            return start_response(status, headers, exc_info)
        return self.wsgi_app(environ, _start_response)


app.wsgi_app = _SameSiteRememberCookie(app.wsgi_app)
# Let the service worker own asset caching; without this Flask's 12h HTTP cache
# would serve stale CSS/JS to both the browser and the SW after a deploy.
app.config['SEND_FILE_MAX_AGE_DEFAULT'] = 0


def is_duplicate_request():
    # Only writes count. fetch() keeps the X-Request-Id header when it
    # follows the post-save 302 as a GET — without this guard that GET is
    # seen as a duplicate and redirects to itself in an infinite loop.
    if request.method != "POST":
        return False
    request_id = request.headers.get("X-Request-Id")
    if not request_id and request.is_json:
        request_id = (request.get_json(silent=True) or {}).get("request_id")
    if not request_id:
        request_id = request.form.get("request_id")
    if not request_id:
        return False
    request_id = str(request_id)[:64]
    if db.session.query(ProcessedRequest.request_id).filter_by(request_id=request_id).first():
        return True
    db.session.add(ProcessedRequest(request_id=request_id))
    try:
        # Claim the id now: a concurrent retry with the same id blocks on the
        # primary key and is then reported as a duplicate instead of a 500.
        db.session.flush()
    except sqlalchemy.exc.IntegrityError:
        db.session.rollback()
        return True
    return False


def admin_only(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated or current_user.id != 0:
            return abort(403)
        return f(*args, **kwargs)
    return decorated_function

def get_groups():
    groups = User.query.all()
    groups = [group.id for group in groups if group.id > 0]
    groups.sort()
    return groups


def safe_next(default):
    """Local redirect target from ?next=, never an absolute/foreign URL."""
    target = request.args.get("next") or request.form.get("next") or ""
    if target.startswith("/") and not target.startswith("//") and "\\" not in target:
        return target
    return default


def can_edit_candidate(candidate):
    return bool(candidate) and (is_admin(current_user) or candidate.group_id == current_user.id)


def active_candidates(group_id):
    candidates = Candidate.query.filter_by(group_id=group_id).all()
    candidates = [c for c in candidates if c.status != "פרש"]
    candidates.sort(key=lambda c: c.number)
    return candidates


def active_candidate_numbers(group_id):
    return [c.number for c in active_candidates(group_id)]


# "X - אקט N" is one circle-mode heat; "סיכום X - אקט N" is its per-candidate
# summary, and "X סיכום" averages a candidate's act summaries for station X.
ACT_STATION_RE = re.compile(r"^(סיכום )?(.+) - אקט (\d+)$")


def parse_act_station(station):
    """Return (base, act_number, is_summary) for an act station, else None."""
    match = ACT_STATION_RE.match(station or "")
    if not match:
        return None
    return match.group(2), int(match.group(3)), bool(match.group(1))


def reviews_by_candidate(candidate_ids):
    # One query for a whole group instead of one (or ~16) per candidate.
    grouped = defaultdict(list)
    candidate_ids = list(candidate_ids)
    if not candidate_ids:
        return grouped
    for review in Review.query.filter(Review.subject_id.in_(candidate_ids)).order_by(Review.id).all():
        grouped[review.subject_id].append(review)
    return grouped


def _custom_physical(bases):
    """Custom circle stations that get their own "X סיכום". A name that
    contains a built-in one ("ספרינטים 2") has always been averaged into the
    built-in station instead (see act_belongs_to), so it is left out."""
    custom = []
    for base in bases:
        if any(name in base for name in PHYSICAL_BASE_STATIONS) or base in custom:
            continue
        custom.append(base)
    return custom


def physical_stations_for(group_id, reviews=None):
    """Circle-mode station names of a group: the built-ins plus custom ones."""
    if reviews is None:
        rows = db.session.query(distinct(Review.station)).filter(
            Review.author_id == group_id, Review.station.like('%אקט%')).all()
        stations = [station for (station,) in rows]
    else:
        stations = [r.station for r in reviews if r.author_id == group_id]
    bases = [parsed[0] for parsed in map(parse_act_station, stations) if parsed and not parsed[2]]
    return PHYSICAL_BASE_STATIONS + _custom_physical(bases)


def act_belongs_to(station, act_summary_station):
    """The original whole-word match: "סיכום ספרינטים 2 - אקט 1" counts
    toward "ספרינטים" as well. Kept as is so averages do not shift."""
    return f" {station} " in f" {act_summary_station} "


def candidate_scores(reviews, physical_stations):
    """(physical average, general average) — the numbers the home page shows."""
    tiz_names = {f"{station} סיכום" for station in physical_stations}
    tiz_names |= set(MODE_STATIONS["counter"])
    seen, tiz_sum, tiz_count = set(), 0, 0
    total_sum, total_count = 0, 0
    for review in reviews:
        if review.grade is None or not review.station:
            continue
        if review.station in tiz_names and review.station not in seen:
            seen.add(review.station)  # one review per station, the oldest
            tiz_sum += review.grade
            tiz_count += 1
        if (review.station not in physical_stations and "אקט" not in review.station
                and ("ODT" not in review.station or review.station == "ODT סיכום")):
            total_sum += review.grade
            total_count += 1
    tiz = round(tiz_sum / tiz_count, 2) if tiz_count else 0
    total = round(total_sum / total_count, 2) if total_count else 0
    return tiz, total


def staff_notes_by_candidate(candidate_ids):
    """{candidate_id: {note_type: [notes newest first]}} for doctor/HR notes."""
    grouped = defaultdict(lambda: defaultdict(list))
    candidate_ids = list(candidate_ids)
    if not candidate_ids:
        return grouped
    notes = Note.query.filter(Note.subject_id.in_(candidate_ids), Note.type.in_(STAFF_NOTE_TYPES)) \
        .order_by(Note.id.desc()).all()
    for note in notes:
        grouped[note.subject_id][note.type].append(note)
    return grouped


def candidate_rows(candidates, group_id):
    """Score rows for a list of candidates, with one query for all reviews."""
    by_candidate = reviews_by_candidate(c.id for c in candidates)
    group_reviews = [r for reviews in by_candidate.values() for r in reviews]
    physical = physical_stations_for(group_id, group_reviews)
    staff_notes = staff_notes_by_candidate(c.id for c in candidates)
    rows = []
    for candidate in candidates:
        tiz, total = candidate_scores(by_candidate.get(candidate.id, []), physical)
        rows.append({
            "candidate": candidate,
            "number": candidate.number,
            "tiz": tiz,
            "total": total,
            "staff_notes": staff_notes.get(candidate.id, {}),
        })
    return rows

@app.route('/admin-home', methods=["GET", "POST"])
@admin_only
def admin_home():
    if len(get_groups()) == 0:
        return redirect(url_for('register'))
    first_group = get_groups()[0]
    return redirect(url_for('homeAdmin', group_id= first_group))


HOME_SORTS = ("total", "physical", "number")


def sort_rows(rows, sort):
    if sort == "number":
        rows.sort(key=lambda r: r["number"])
    elif sort == "physical":
        rows.sort(key=lambda r: (-r["tiz"], r["number"]))
    else:
        rows.sort(key=lambda r: (-r["total"], r["number"]))
    return rows


@app.route('/<int:group_id>/', methods=["GET", "POST"])
@admin_only
def homeAdmin(group_id):
    form = selectGroup()
    form.group.choices = get_groups()
    if form.validate_on_submit():
        return redirect(url_for('homeAdmin', group_id=form.group.data))
    # Keep the current group selected — .default is a no-op after process().
    form.group.data = str(group_id)
    update_avgs_nf(group_id)
    candidates = Candidate.query.filter_by(group_id=group_id).all()
    active = sorted((c for c in candidates if c.status != "פרש"), key=lambda c: c.number)
    retired = sorted((c for c in candidates if c.status == "פרש"), key=lambda c: c.number)
    rows = sort_rows(candidate_rows(active, group_id), "total")
    # The interview check spans every group: the admin sees all matches.
    prior_sync = InterviewSync.query.first()
    prior = {}
    if prior_sync:
        everyone = Candidate.query.filter(Candidate.group_id > 0).all()
        prior = prior_interview_matches(c for c in everyone if c.status != "פרש")
    return render_template("admin-home.html", group_id=group_id, rows=rows, retired=retired, form=form,
                           prior_sync=prior_sync, prior_by_id=prior,
                           prior_matches=prior_interview_list(prior),
                           prior_total=PriorInterview.query.count() if prior_sync else 0,
                           prior_open=session.pop("prior_interviews_open", False))


@app.route('/')
def home():
    if not current_user.is_authenticated:
        return redirect(url_for("login"))
    if is_staff(current_user):
        return redirect(url_for("staff_home"))
    if current_user.id == 0:
        return redirect(url_for("admin_home"))
    group_id = current_user.id
    update_avgs_nf(group_id)
    candidates = active_candidates(group_id)
    rows = candidate_rows(candidates, group_id)
    sort = request.args.get('sort')
    if sort not in HOME_SORTS:
        sort = "total"
    sort_rows(rows, sort)
    prior = prior_interview_matches(candidates)
    return render_template("home.html", rows=rows, sort=sort, active_candidates_count=len(rows),
                           prior_by_id=prior, prior_matches=prior_interview_list(prior))


def review_kind(review):
    """How a review row may be edited from the candidate page."""
    station = review.station or ""
    if station.startswith("סיכום ") or station.endswith(" סיכום"):
        return "summary"  # derived — recomputed, never edited by hand
    parsed = parse_act_station(station)
    if parsed:
        return "act"
    if station in MODE_STATIONS["counter"] or review.counter_value is not None:
        return "counter"
    return "station"


@app.route("/candidate/<path:candidate_id>")
def candidate_profile(candidate_id):
    candidate = Candidate.query.get(candidate_id)
    if not candidate:
        abort(404)
    if not can_edit_candidate(candidate):
        abort(403)
    update_avgs_nf(candidate.group_id, candidates=[candidate])

    physical_stations = physical_stations_for(candidate.group_id)
    counter_stations = MODE_STATIONS["counter"]
    all_reviews = Review.query.filter_by(subject_id=candidate.id).order_by(Review.id).all()
    first_by_station = {}
    for review in all_reviews:
        first_by_station.setdefault(review.station, review)

    summary_names = [f"{station} סיכום" for station in physical_stations] + counter_stations
    physical_reviews = [first_by_station[name] for name in summary_names if name in first_by_station]
    physical_reviews.sort(key=lambda x: x.grade, reverse=True)
    tiz_avg, total_avg = candidate_scores(all_reviews, physical_stations)

    general_reviews = [r for r in all_reviews if r.station not in physical_stations and ("ODT" not in r.station or r.station == "ODT סיכום")]
    general_reviews = [r for r in general_reviews if ("אקט" not in r.station) or ("אקט" in r.station and "סיכום" in r.station)]
    general_reviews = [r for r in general_reviews if r.station not in counter_stations]
    general_reviews.sort(key=lambda x: x.grade, reverse=True)

    # Raw entries the group can fix or remove after saving (newest first).
    history = []
    for review in reversed(all_reviews):
        kind = review_kind(review)
        if kind == "summary":
            continue
        history.append({"review": review, "kind": kind})

    notes = sorted(candidate.notes, key=lambda n: n.id, reverse=True)
    staff_notes = [n for n in notes if n.type in STAFF_NOTE_TYPES]
    notes = [n for n in notes if n.type not in STAFF_NOTE_TYPES]
    photo = CandidatePhoto.query.get(candidate.id)
    if photo and not photo.data:
        photo = None
    prior = prior_interview_matches([candidate]).get(candidate.id)

    return render_template(
        "candidate-profile.html",
        candidate=candidate,
        number=candidate.number,
        prior=prior,
        general_reviews=general_reviews,
        physical_reviews=physical_reviews,
        history=history,
        notes=notes,
        staff_notes=staff_notes,
        staff_roles=STAFF_ROLES,
        photo_version=photo.version if photo else None,
        tiz_avg=tiz_avg,
        total_avg=total_avg,
    )


@app.route('/register', methods=["GET", "POST"])
def register():
    # Admin only. The one exception is an empty system: the first account
    # (the admin, group 0) has to be created from here.
    bootstrap = User.query.get(0) is None
    if not bootstrap and not is_admin(current_user):
        if not current_user.is_authenticated:
            return redirect(url_for('login'))
        abort(403)
    form = RegisterForm()
    if form.validate_on_submit():
        if User.query.filter_by(id=form.id.data).first():
            print(User.query.filter_by(id=form.id.data).first())
            #User already exists
            flash("משתמש כבר קיים!")
            return redirect(url_for('register'))

        # hash_and_salted_password = generate_password_hash(
        #     form.password.data,
        #     method='pbkdf2:sha256',
        #     salt_length=8
        # )
        if form.id.data < 0 or (form.id.data == 0 and not bootstrap):
            flash("מספר קבוצה חייב להיות חיובי", "error")
            return render_template("register.html", form=form, current_user=current_user)
        new_user = User(
            id=form.id.data,
            name=form.name.data,
            password=form.password.data,
            sprint_num = 1,
            crawl_num = 1,
            alonka_num = 1,
            mitam_num=form.mitam.data
        )
        db.session.add(new_user)
        # The group starts with numbered placeholders, all in the same
        # transaction, so it can score from minute one; names are filled in
        # later from "ניהול קבוצה".
        size = (form.candidates_count.data or 0) if new_user.id > 0 else 0
        taken = {cid for (cid,) in db.session.query(Candidate.id).filter(
            Candidate.id.like(f"{new_user.id}/%")).all()}
        db.session.add_all([
            Candidate(id=f"{new_user.id}/{n}", group_id=new_user.id, name=placeholder_name(n))
            for n in range(1, size + 1) if f"{new_user.id}/{n}" not in taken
        ])
        db.session.commit()
        if size:
            flash(f'קבוצה {form.name.data} (מס\' {form.id.data}) נוספה עם {size} מגובשים (1–{size}). '
                  f'את השמות מעדכנים ב"ניהול קבוצה".', 'success')
        else:
            flash(f'קבוצה {form.name.data} (מס\' {form.id.data}) נוספה בהצלחה!', 'success')
        return redirect(url_for('register'))
    return render_template("register.html", form=form, current_user=current_user)


def candidate_has_data(candidate):
    """True once anything was recorded for the candidate (safe-delete guard)."""
    return bool(
        Review.query.filter_by(subject_id=candidate.id).first()
        or Note.query.filter_by(subject_id=candidate.id).first()
        or CandidatePhoto.query.filter(CandidatePhoto.candidate_id == candidate.id, CandidatePhoto.mime != "").first()
        or candidate.interview_grade or candidate.final_status or candidate.final_weighted_grade
    )


@app.route('/add-candidate', methods=["GET", "POST"])
def addCandidate():
    form = NewCandidateForm()
    
    # Get existing candidate numbers for the current user's group
    existing_candidates = Candidate.query.filter_by(group_id=current_user.id).all()
    existing_numbers = [candidate.id.split("/")[1] for candidate in existing_candidates]
    existing_numbers.sort(key=lambda x: int(x) if x.isdigit() else float('inf'))
    
    if form.validate_on_submit():
        new_id = str(form.id.data).strip()
        existing = Candidate.query.filter_by(id=str(current_user.id) + "/" + new_id, group_id=current_user.id).first()
        if existing and is_placeholder_name(existing.name):
            # The number was pre-created with the group — just name it.
            existing.name = form.name.data.strip()
            db.session.commit()
            flash(f'מגובש {existing.name} עודכן במספר {new_id}', 'success')
            return redirect(url_for('addCandidate'))
        if existing:
            flash("מגובש כבר קיים!")
            return render_template("add-candidate.html", current_user=current_user, form=form, existing_numbers=existing_numbers)

        # hash_and_salted_password = generate_password_hash(
        #     form.password.data,
        #     method='pbkdf2:sha256',
        #     salt_length=8
        # )
        new_candidate = Candidate(
            id=str(current_user.id) + "/" + new_id,
            name=form.name.data,
            group_id=current_user.id,
            group=current_user
        )
        db.session.add(new_candidate)
        db.session.commit()
        flash(f'מגובש {form.name.data} נוסף בהצלחה!', 'success')
        return redirect(url_for('addCandidate'))
    return render_template("add-candidate.html", form=form, current_user=current_user, existing_numbers=existing_numbers)

# ... existing imports ...

@app.route('/add-candidate-batch', methods=["GET", "POST"])
def addCandidateBatch():
    if not current_user.is_authenticated:
        return redirect(url_for("login"))

    form = NewCandidateForm()

    if request.method == "POST":
        try:
            data = request.get_json()
            if data is None:
                return jsonify({
                    "success": False,
                    "error": "Invalid JSON data received"
                }), 400

        except Exception as e:
            return jsonify({
                "success": False,
                "error": f"Error parsing JSON: {str(e)}"
            }), 400

        if not isinstance(data, list):
            return jsonify({
                "success": False,
                "error": "Expected JSON array of candidates"
            }), 400

        # Track all results for detailed feedback
        results = {
            "successful_adds": [],
            "existing_candidates": [],
            "invalid_data": [],
            "duplicate_in_batch": [],
            "errors": []
        }
        
        # Track candidate IDs in this batch to detect duplicates
        batch_ids = []
        
        for i, candidate in enumerate(data):
            # Validate required fields
            if not all(k in candidate for k in ['id', 'name']):
                results["invalid_data"].append({
                    "row": i + 1,
                    "id": candidate.get('id', ''),
                    "name": candidate.get('name', ''),
                    "error": "חסרים שדות חובה (מספר או שם)"
                })
                continue
                
            # Clean and validate candidate ID
            new_id = str(candidate['id']).strip()
            if not new_id:
                results["invalid_data"].append({
                    "row": i + 1,
                    "id": new_id,
                    "name": candidate['name'],
                    "error": "מספר מגובש לא יכול להיות ריק"
                })
                continue
                
            # Validate that candidate ID is an integer (including 0)
            try:
                candidate_number = int(new_id)
                if candidate_number < 0:
                    results["invalid_data"].append({
                        "row": i + 1,
                        "id": new_id,
                        "name": candidate['name'],
                        "error": "מספר מגובש חייב להיות מספר שלם חיובי או אפס"
                    })
                    continue
                # Convert back to string for consistency with existing logic
                new_id = str(candidate_number)
            except ValueError:
                results["invalid_data"].append({
                    "row": i + 1,
                    "id": new_id,
                    "name": candidate['name'],
                    "error": "מספר מגובש חייב להיות מספר שלם (כולל 0)"
                })
                continue
                
            # Check for duplicate within the batch
            if new_id in batch_ids:
                results["duplicate_in_batch"].append({
                    "row": i + 1,
                    "id": new_id,
                    "name": candidate['name'],
                    "error": "מספר מגובש כפול בטופס"
                })
                continue
                
            batch_ids.append(new_id)

            # Check if candidate already exists in database
            full_id = f"{current_user.id}/{new_id}"
            existing = Candidate.query.filter_by(id=full_id, group_id=current_user.id).first()
            if existing and is_placeholder_name(existing.name) and candidate['name'].strip():
                # Pre-created placeholder for this number: fill in the name.
                existing.name = candidate['name'].strip()
                db.session.commit()
                results["successful_adds"].append({"row": i + 1, "id": new_id, "name": candidate['name']})
                continue
            if existing:
                results["existing_candidates"].append({
                    "row": i + 1,
                    "id": new_id,
                    "name": candidate['name'],
                    "error": "מספר מגובש כבר קיים במערכת"
                })
                continue

            try:
                new_candidate = Candidate(
                    id=full_id,
                    name=candidate['name'].strip(),
                    group_id=current_user.id,
                    group=current_user
                )
                db.session.add(new_candidate)
                db.session.commit()
                results["successful_adds"].append({
                    "row": i + 1,
                    "id": new_id,
                    "name": candidate['name']
                })

            except Exception as e:
                db.session.rollback()
                results["errors"].append({
                    "row": i + 1,
                    "id": new_id,
                    "name": candidate['name'],
                    "error": f"שגיאה בשמירה: {str(e)}"
                })

        # Calculate summary
        total_processed = len(data)
        total_successful = len(results["successful_adds"])
        total_failed = total_processed - total_successful
        
        return jsonify({
            "success": True,
            "summary": {
                "total_processed": total_processed,
                "total_successful": total_successful,
                "total_failed": total_failed
            },
            "results": results
        })

    # Get existing candidate numbers for the current user's group
    existing_candidates = Candidate.query.filter_by(group_id=current_user.id).all()
    existing_numbers = [candidate.id.split("/")[1] for candidate in existing_candidates]
    existing_numbers.sort(key=lambda x: int(x) if x.isdigit() else float('inf'))
    
    return render_template(
        "add-candidate-batch.html",
        form=form,
        current_user=current_user,
        existing_numbers=existing_numbers
    )

@app.route('/login', methods=["GET", "POST"])
def login():
    form = LoginForm()
    if form.validate_on_submit():
        role = form.role.data or "group"
        password = form.password.data
        if role in STAFF_BY_KEY:
            user = User.query.get(STAFF_BY_KEY[role])
            if not user:
                flash("העמדה עדיין לא הוגדרה — יש לבקש מהמנהל להגדיר לה סיסמה", "error")
                return redirect(url_for('login', role=role))
        else:
            raw_id = (form.id.data or "").strip()
            # A non-numeric id would raise in Postgres (integer column).
            user = User.query.get(int(raw_id)) if raw_id.isdigit() else None
            if not user:
                flash("מספר קבוצה שגוי", "error")
                return redirect(url_for('login'))
        if user.password != password:
            flash('סיסמה לא נכונה', "error")
            return redirect(url_for('login', role=role if role in STAFF_BY_KEY else None))
        login_user(user, remember=True)
        return redirect(url_for('home'))
    if request.method == "GET" and request.args.get("role") in STAFF_BY_KEY:
        form.role.data = request.args["role"]
    return render_template("login.html", form=form, current_user=current_user, staff_roles=STAFF_ROLES)

@app.route('/add-name', methods=["GET", "POST"])
def addName():
    form = AddNameForm()
    if form.validate_on_submit():
        name = form.name.data
        current_user.name = name
        db.session.commit()
        return redirect(url_for('home'))
    return render_template("register.html", form=form, current_user=current_user)


@app.route('/logout')
def logout():
    logout_user()
    return redirect(url_for('home'))

stations = ["ספרינטים", "זחילות", "משימת מחשבה", "דיון מילוט", "פירוק והרכבת נשק", "מסע", "שקים", "ODT", "מעגל זנבות", "אלונקה סוציומטרית", "הרצאות", "בניית שוח", "חפירת בור","חפירת בור מכשול קבוצתי","בניית ערימת חול", "נאסא","מתלה שזיפים", "אחר"]

# --- Station guide (the "?" help feature) ---------------------------------
# Per-station explanation shown behind the "?" on the scoring screens.
# Text comes from the unit's "תחנות גיבוש" doc; keys are the app's own station
# names (some doc names differ — e.g. doc "ריצות קצרות" is our "ספרינטים",
# doc "מתח" is "מתלה שזיפים"). "values" are the ערכי צה"ל examined at the station.
_MARCH_INFO = {
    "purpose": "מסע אלונקות — תרגיל קבוצתי ואישי הכולל מאמץ פיזי עצים, שמטרתו להכין 'את הקרקע' לקראת מילוי חוות דעת עמיתים.",
    "values": ["דבקות במשימה וחתירה לניצחון", "חיי אדם", "אחריות", "רעות", "דוגמא אישית"],
}
_SANDBAG_INFO = {
    "purpose": "סחיבת שקי חול — תרגיל אישי הכולל מאמץ פיזי עצים, לבחינת התמדה ותפקוד המועמדים תחת עומס.",
    "values": ["דבקות במשימה וחתירה לניצחון", "מקצועיות", "משמעת"],
}
STATION_INFO = {
    "ספרינטים": {
        "purpose": "תרגיל ריצות קצרות (ספרינטים) — תרגיל אישי הכולל מאמץ פיזי קצר ועצים, לבחינת המועמדים תחת מאמץ.",
        "values": ["דבקות במשימה וחתירה לניצחון", "מקצועיות", "משמעת"],
    },
    "זחילות": {
        "purpose": "תרגיל זחילות הינו תרגיל אישי הכולל מאמץ פיזי עצים ומהווה סימולציה לתפקוד המועמדים.",
        "values": ["דבקות במשימה וחתירה לניצחון", "מקצועיות", "משמעת"],
    },
    "הרכבה ופירוק נשק": {
        "purpose": "פירוק והרכבת נשק — תרגיל אישי וביצועי הבודק יכולת למידת משימה טכנית, בחלקה תחת לחץ זמן ועומס מנטאלי או פיזי, לחץ חברתי ותחת אש נוכח כישלון.",
        "values": ["דבקות במשימה וחתירה לניצחון", "מקצועיות", "אחריות", "טוהר הנשק"],
    },
    "הרצאות": {
        "purpose": "תרגיל אישי לא פיזי המהווה סימולציה לתפקוד המועמדים.",
        "values": ["דוגמא אישית", "מקצועיות", "אחריות"],
    },
    "פינוי לאלונקה": {
        "purpose": "תרגיל קבוצתי הכולל מאמץ פיזי עצים ומהווה סימולציה לתפקוד המועמדים.",
        "values": ["דבקות במשימה וחתירה לניצחון", "מקצועיות", "משמעת"],
    },
    "הסתתרות": {
        "purpose": "תרגיל אישי הכולל מאמץ פיזי לא עצים, לבחינת ההתמדה וההשקעה של היכולות האישיות של המועמדים.",
        "values": ["דבקות במשימה וחתירה לניצחון", "מקצועיות", "אחריות", "דוגמא אישית"],
    },
    "קורי עכביש": {
        "purpose": "משימה קבוצתית שבה על החיילים להעביר את כלל הצוות — לרבות האפודים והפק\"לים — וכן אלונקה פתוחה דרך רשת חבלים. המטרה: השתלבות בצוות.",
        "values": ["רעות", "אחריות", "אמינות", "שליחות"],
    },
    "תחנות פשיטה": {
        "purpose": "תחנת תכנון פשיטה — תרגיל ביצועי קבוצתי הכולל מאמץ פיזי מתון ומהווה סימולציה לתפקוד המועמדים.",
        "values": ["אחריות", "רעות", "שליחות"],
    },
    "דיון מילוט": {
        "purpose": "דיון מילוט הינו תרגיל קבוצתי ללא מאמץ פיזי ומהווה סימולציה לתפקוד המועמדים.",
        "values": ["אחריות", "רעות", "דוגמא אישית", "דבקות במשימה וחתירה לניצחון"],
    },
    "בניית פסל סביבתי": {
        "purpose": "תרגיל ביצועי קבוצתי הכולל מאמץ פיזי ומהווה סימולציה לתפקוד המועמדים.",
        "values": ["חיי אדם", "דבקות במשימה וחתירה לניצחון", "אחריות", "רעות", "מקצועיות"],
    },
    "בניית מאהל": {
        "purpose": "תרגיל קבוצתי הכולל מאמץ פיזי לא עצים ומהווה סימולציה לתפקוד המועמדים.",
        "values": ["אחריות", "רעות", "חיי אדם", "מקצועיות"],
    },
    "בניית צילייה": {
        "purpose": "תרגיל קבוצתי הכולל מאמץ פיזי לא עצים ומהווה סימולציה לתפקוד.",
        "values": ["אחריות", "רעות", "חיי אדם", "מקצועיות"],
    },
    "שולחן חול": {
        "purpose": "תרגיל ביצועי אישי לא פיזי, המהווה סימולציה לתפקוד המועמדים ביכולת קוגניטיבית ועמידה בתנאי לחץ.",
        "values": ["דבקות במשימה וחתירה לניצחון", "מקצועיות", "אחריות"],
    },
    "חפירת בור": {
        "purpose": "תרגיל אישי בו על המתמיין לחפור, במשך זמן מוקצב ולא ידוע, בור עמוק ככל הניתן.",
        "values": ["דבקות במשימה וחתירה לניצחון", "מקצועיות"],
    },
    "כיול תדרים": {
        "purpose": "תרגיל אישי ללא מאמץ פיזי, הכולל למידה עצמאית של כיול תדרים במכשיר קשר ובחינה אישית. נבחנים הבנה וזיכרון של סדר פעולות, סקרנות, חוש לוגי ואחריות ללמידה עצמאית.",
        "values": ["אחריות", "אמינות", "משמעת"],
    },
    "מתלה שזיפים": {
        "purpose": "תרגיל מתח (מתלה שזיפים) — ביצועי אישי וקבוצתי הכולל מאמץ פיזי מתון ומהווה סימולציה לתפקוד המועמדים.",
        "values": ["אחריות", "רעות", "דבקות במשימה וחתירה לניצחון", "מקצועיות"],
    },
    "אלונקה סוציומטרית": {
        "purpose": "תחנת משימה אישית הבודקת תפקוד תחת מאמץ עצים ולחץ, בשילוב קואורדינציה וביצוע משימה מוגדרת — תוך הקפדה על הנחיות מדויקות והעלאה הדרגתית של רמת הקושי.",
        "values": ["אחריות", "רעות", "דבקות במשימה וחתירה לניצחון", "מקצועיות"],
    },
    "מסע 1": _MARCH_INFO,
    "מסע 2": _MARCH_INFO,
    "מסע 3": _MARCH_INFO,
    "שקי חול": _SANDBAG_INFO,
    "שקי חול 2": _SANDBAG_INFO,
}

# Which stations the guide lists per scoring mode. This mirrors the app's
# existing mode split — it does NOT change what's gradable, only what the "?"
# guide shows, opened to the mode the user is in.
MODE_STATIONS = {
    "circles": ["ספרינטים", "זחילות", "אלונקה סוציומטרית", "מתלה שזיפים"],
    "group": ["פינוי לאלונקה", "קורי עכביש", "תחנות פשיטה", "דיון מילוט", "בניית פסל סביבתי",
              "בניית מאהל", "בניית צילייה", "הסתתרות", "שולחן חול", "חפירת בור", "כיול תדרים"],
    "individual": ["בניית פסל סביבתי", "הרכבה ופירוק נשק", "הרצאות", "הסתתרות",
                   "שולחן חול", "חפירת בור", "כיול תדרים"],
    "counter": ["מסע 1", "מסע 2", "מסע 3", "שקי חול", "שקי חול 2"],
}


@app.context_processor
def inject_station_guide():
    # Available to every template so the scoring screens can render the guide.
    return {"STATION_INFO": STATION_INFO, "MODE_STATIONS": MODE_STATIONS}


def _upsert_summary(rows, grade, make_row):
    """Keep exactly one summary row with `grade` (None = no row at all).
    Returns True when anything changed. Extra rows are left-over duplicates
    from concurrent saves and are removed."""
    changed = False
    if grade is None:
        for row in rows:
            db.session.delete(row)
            changed = True
        return changed
    if rows:
        if rows[0].grade != grade:
            rows[0].grade = grade
            changed = True
        for extra in rows[1:]:
            db.session.delete(extra)
            changed = True
    else:
        db.session.add(make_row(grade))
        changed = True
    return changed


def update_avgs_nf(group_id=None, candidates=None, extra_stations=()):
    """Bring a group's derived summary rows ("X סיכום", "ODT סיכום") up to date.

    Runs on page views as a safety net, so it must be cheap: one query for the
    whole group, everything computed in memory, and a commit only when a value
    actually changed (the old version did ~4 queries and a commit per
    candidate on every view, which stalled the server under field load).
    extra_stations forces a station to be re-checked even after its last act
    was deleted or renamed away.
    """
    if group_id is None:
        group_id = current_user.id
    if group_id is None or int(group_id) <= 0:
        return  # admin and staff own no candidates
    group_id = int(group_id)
    if candidates is None:
        candidates = Candidate.query.filter_by(group_id=group_id).all()
    if not candidates:
        return
    by_candidate = reviews_by_candidate(c.id for c in candidates)
    group_reviews = [r for reviews in by_candidate.values() for r in reviews]
    physical = set(physical_stations_for(group_id, group_reviews)) | set(_custom_physical(extra_stations))
    changed = False
    for candidate in candidates:
        reviews = by_candidate.get(candidate.id, [])
        by_station = defaultdict(list)
        act_summaries = []
        for review in reviews:
            by_station[review.station].append(review)
            if review.grade is not None and round(review.grade, 2) != review.grade:
                review.grade = round(review.grade, 2)
                changed = True
            parsed = parse_act_station(review.station)
            if parsed and parsed[2] and review.grade is not None:
                act_summaries.append(review)

        for station in physical:
            grades = [r.grade for r in act_summaries if act_belongs_to(station, r.station)]
            avg = round(sum(grades) / len(grades), 2) if grades else None
            changed |= _upsert_summary(
                by_station.get(f"{station} סיכום", []), avg,
                lambda g, s=station, c=candidate: Review(
                    station=f"{s} סיכום", subject_id=c.id, grade=g, note="", author_id=group_id))

        odt = [r.grade for r in reviews if r.station and "ODT" in r.station
               and r.station != "ODT סיכום" and r.grade is not None]
        avg = round(sum(odt) / len(odt), 2) if odt else None
        changed |= _upsert_summary(
            by_station.get("ODT סיכום", []), avg,
            lambda g, c=candidate: Review(
                station="ODT סיכום", subject_id=c.id, grade=g, note="", author_id=group_id))
    if changed:
        db.session.commit()


def recompute_act_summary(candidate_id, act_station, author_id):
    """Rebuild "סיכום <act>" for one candidate from its raw act rows."""
    raw = Review.query.filter_by(subject_id=candidate_id, station=act_station).all()
    rows = Review.query.filter_by(subject_id=candidate_id, station=f"סיכום {act_station}") \
        .order_by(Review.id).all()
    grades = [r.grade for r in raw if r.grade is not None]
    avg = round(sum(grades) / len(grades), 2) if grades else None
    _upsert_summary(rows, avg, lambda g: Review(
        station=f"סיכום {act_station}", subject_id=candidate_id, grade=g, note="אקט", author_id=author_id))

def update_avgs(form):
    physical_stations = getPhysicalStations()
    physical_stations = physical_stations + ["ספרינטים", "זחילות", "אלונקה סוציומטרית", "מתלה שזיפים"]
    if form.station.data in physical_stations:
        if not Review.query.filter_by(station=f"{form.station.data} סיכום", subject_id=str(current_user.id) + "/" + form.subject.data).first():
            new_review = Review(station=f"{form.station.data} סיכום",
                                subject_id=str(current_user.id) + "/" + str(form.subject.data),
                                grade=form.grade.data, note=form.note.data, author=current_user,
                                subject=Candidate.query.filter_by(
                                id=str(current_user.id) + "/" + str(form.subject.data)).first())
            db.session.add(new_review)
            db.session.commit()
        else:
            count = len(Review.query.filter_by(station=f"{form.station.data} סיכום", subject_id=str(current_user.id) + "/" + form.subject.data).all())
            review = Review.query.filter_by(station=f"{form.station.data} סיכום", subject_id=str(current_user.id) + "/" + form.subject.data).first()
            review.grade = (review.grade * (count - 1) + int(form.grade.data)) / count
            db.session.commit()

    if "ODT" in form.station.data:
        if not Review.query.filter_by(station="ODT סיכום", subject_id = str(current_user.id) + "/" + form.subject.data).first():
            new_review = Review(station="ODT סיכום", subject_id=str(current_user.id) + "/" + str(form.subject.data),
                                grade=form.grade.data, note=form.note.data, author=current_user,
                                subject=Candidate.query.filter_by(
                                    id=str(current_user.id) + "/" + str(form.subject.data)).first())
            db.session.add(new_review)
            db.session.commit()
        else:
            reviews = Review.query.filter_by(subject_id=str(current_user.id) + "/" + form.subject.data)
            reviews = [review for review in reviews if "ODT" in review.station and review.station != "ODT סיכום"]
            grades = [float(review.grade) for review in reviews]
            grades_sum = sum(grades)
            count = len(reviews)
            review = Review.query.filter_by(station="ODT סיכום", subject_id=str(current_user.id) + "/" + form.subject.data).first()
            review.grade = (grades_sum) / count
            db.session.commit()


@app.route('/subjects/<group>')
def subject(group):
    subjects = Candidate.query.filter_by(group_id=group).all()
    subjects = [int(subject.id.split("/")[1]) for subject in subjects if subject.status != "פרש"]
    subjects.sort()
    subjectsArray = []

    for subject in subjects:
        subjectObj = {}
        subjectObj['id'] = subject

        subjectsArray.append(subjectObj)

    return jsonify({'subjects' : subjectsArray})

@app.route('/physicals/<group>')
def physicals(group):
    stations = ["ספרינטים", "זחילות", "אלונקה סוציומטרית", "מתלה שזיפים"] + getPhysicalStationsGroup(int(group))
    stationsArray = []

    for station in stations:
        stationObj = {}
        stationObj['id'] = station

        stationsArray.append(stationObj)

    return jsonify({'stations': stationsArray})

def getAllStations():
    """
    Helper function to get all stations including custom ones created via 'אחר' mode.
    Returns a list combining predefined stations with custom stations from the database.
    Excludes circle mode stations (containing "אקט") which are handled separately.
    """
    # Get all unique station names from the database
    unique_stations = db.session.query(distinct(Review.station)).all()
    unique_station_values = [station[0] for station in unique_stations]
    
    # Predefined stations list
    predefined_stations = ["משימת מחשבה", "דיון מילוט", "פירוק והרכבת נשק", "מסע", "שקים", "מעגל זנבות", "ODT", "הרצאות", "בניית שוח", "חפירת בור","חפירת בור מכשול קבוצתי","בניית ערימת חול", "נאסא"]
    
    # Filter out circle mode stations (containing "אקט") and summary stations (containing "סיכום")
    # Circle mode stations are stored with " - אקט X" suffix and handled separately
    unique_station_values = [station for station in unique_station_values if "אקט" not in station and "סיכום" not in station]
    
    # Get custom stations that are not in predefined list
    custom_stations = [station for station in unique_station_values if station not in predefined_stations]
    
    # Combine predefined stations with custom stations and add "אחר" at the end
    all_stations = predefined_stations + custom_stations + ["אחר"]
    
    return all_stations

@app.route("/new-review", methods=["GET", "POST"])
def add_new_review():
    # Only the stations for this mode (plus "אחר" for a one-off custom name).
    stations = MODE_STATIONS["individual"] + ["אחר"]
    form = CreateReviewForm()
    form.station.choices = stations
    candidates = Candidate.query.filter_by(group_id=current_user.id).all()
    candidate_nums = []
    for candidate in candidates:
        if candidate.status != "פרש":
            candidate_nums.append(int(candidate.id.split("/")[1]))
    candidate_nums.sort()
    form.subject.choices = candidate_nums
    if form.validate_on_submit():
        if is_duplicate_request():
            flash('חוות הדעת כבר נשמרה', 'success')
            return redirect(url_for('add_new_review'))
        if form.station.data == "ODT":
            form.station.data = form.station.data + " " + form.odt.data
        if form.station.data == "אחר":
            form.station.data = form.odt.data
        new_review = Review(
            station=form.station.data,
            subject_id=str(current_user.id) + "/" + str(form.subject.data),
            grade=form.grade.data,
            note=form.note.data,
            author=current_user,
            subject=Candidate.query.filter_by(id=str(current_user.id) + "/" + str(form.subject.data)).first()
        )
        db.session.add(new_review)
        db.session.commit()
        update_avgs(form)
        candidate_name = Candidate.query.filter_by(id=str(current_user.id) + "/" + str(form.subject.data)).first().name
        flash(f'הערכת תחנה {form.station.data} עבור {candidate_name} נשמרה בהצלחה!', 'success')
        form.note.data = ""
        form.odt.data = ""
        return render_template("make-post.html", form=form, current_user=current_user, selected_subject=form.station.data)
    return render_template("make-post.html", form=form, current_user=current_user, selected_subject=0)

@app.route("/new-group-review", methods=["GET", "POST"])
def add_new_group_review():
    form = GroupReviewForm()
    # Only the stations for this mode (plus "אחר" for a one-off custom name).
    stations = MODE_STATIONS["group"] + ["אחר"]
    form.station.choices = stations
    candidates = Candidate.query.filter_by(group_id=current_user.id).all()
    candidates = [int(candidate.id.split("/")[1]) for candidate in candidates if candidate.status != "פרש"]
    candidates.sort()
    return render_template('make-post-group.html', candidates=candidates, user_form=form, current_user=current_user)

def normalize_counter_reviews(station, candidates, current_user):
    """
    Normalizes review grades for a station based on counter values.

    Args:
        station (str): The station name to normalize reviews for
        candidates (list): List of candidate IDs
        current_user: The current user object
    """
    # Get all reviews for the selected station
    station_reviews = []
    for candidate_id in candidates:
        review = Review.query.filter_by(
            station=station,
            subject_id=f"{current_user.id}/{candidate_id}"
        ).first()

        if not review:
            # Create new review with counter=0 if it doesn't exist
            review = Review(
                station=station,
                subject_id=f"{current_user.id}/{candidate_id}",
                grade=1.0,  # Default minimum grade
                counter_value=0,
                author=current_user,
                subject=Candidate.query.filter_by(id=f"{current_user.id}/{candidate_id}").first()
            )
            db.session.add(review)
            db.session.commit()

        station_reviews.append(review)

    # Find max counter value for normalization
    max_counter = max(review.counter_value for review in station_reviews)
    if max_counter > 0:
        # Normalize grades based on counter values
        for review in station_reviews:
            normalized_grade = 1.0 + (3.0 * review.counter_value / max_counter)
            review.grade = round(normalized_grade, 2)
            db.session.commit()

def station_reviews_by_number(station, group_id):
    """{candidate number: oldest review of this group at the station}."""
    found = {}
    for review in Review.query.filter_by(station=station, author_id=group_id).order_by(Review.id).all():
        found.setdefault(int(review.subject_id.split("/")[1]), review)
    return found


@app.route('/counter-review', methods=["GET", "POST"])
def counter_review():
    counter_stations = MODE_STATIONS["counter"]
    form = CounterReviewForm()
    form.station.choices = counter_stations
    form.subject.choices = active_candidate_numbers(current_user.id)
    selected = request.args.get("station")
    if selected not in counter_stations:
        selected = counter_stations[0]
    return render_template('counter-review.html', form=form, selected_station=selected,
                           existing=station_reviews_by_number(selected, current_user.id))

@app.route('/update-counter-reviews', methods=["POST"])
def update_counter_reviews():
    if is_duplicate_request():
        return jsonify({'success': True, 'message': 'הנתונים כבר נשמרו'})
    data = request.get_json(silent=True) or {}
    station = data.get('station')
    reviews = data.get('reviews') or []

    if not station or not reviews:
        # Nothing to save (e.g. a group with no active candidates, or an empty
        # replay from the offline outbox). Treat as a no-op instead of 500ing.
        return jsonify({'success': True, 'message': 'לא נמצאו נתונים לשמירה'})

    # Find max counter value for normalization
    max_counter = max(review['counter'] for review in reviews)

    # Update or create reviews with normalized grades
    for review_data in reviews:
        candidate_id = f"{current_user.id}/{review_data['subject']}"

        # Calculate normalized grade (1-4 scale)
        normalized_grade = 1.0
        if max_counter > 0:
            normalized_grade = 1.0 + (3.0 * review_data['counter'] / max_counter)

        # Find existing review or create new one
        review = Review.query.filter_by(
            station=station,
            subject_id=candidate_id,
            author_id=current_user.id
        ).first()

        if review:
            review.grade = round(normalized_grade, 2)
            review.counter_value = review_data['counter']
            review.note = review_data['note']
        else:
            review = Review(
                station=station,
                subject_id=candidate_id,
                author_id=current_user.id,
                grade=round(normalized_grade, 2),
                counter_value=review_data['counter'],
                note=review_data['note'],
                subject=Candidate.query.get(candidate_id)
            )
            db.session.add(review)

    db.session.commit()
    return jsonify({'success': True, 'message': f'ציוני התחנה {station} נשמרו בהצלחה!'})

@app.route('/add-review-candidate', methods=['POST'])
def addOneReview():
  form = GroupReviewForm()
  if form.validate_on_submit():
    if int(form.grade.data) != 0:
        if form.station.data == "ODT":
            form.station.data = form.station.data + " " + form.odt.data
        if form.station.data == "אחר":
            form.station.data = form.odt.data
        new_review = Review(
            station=form.station.data,
            subject_id=str(current_user.id) + "/" + str(form.subject.data),
            grade=form.grade.data,
            note=form.note.data,
            author=current_user,
            subject=Candidate.query.filter_by(id=str(current_user.id) + "/" + str(form.subject.data)).first()
        )
        db.session.add(new_review)
        db.session.commit()
        update_avgs(form)
        form.note.data = ""
  return 'User updated'

@app.route('/add-all', methods=['GET','POST'])
def update_all():
    if is_duplicate_request():
        flash('הציונים כבר נשמרו', 'success')
        return redirect(url_for('add_new_group_review'))
    candidates = Candidate.query.filter_by(group_id=current_user.id).all()
    candidates = [int(candidate.id.split("/")[1]) for candidate in candidates if candidate.status != "פרש"]
    candidates.sort()
    result2 = request.form.to_dict(flat=False)
    if 'station' not in result2:
        return redirect(url_for('add_new_group_review'))
    station = result2['station'][0]
    if station == "ODT":
        station = station + " " + result2.get('odt', [''])[0]
    if station == "אחר":
        station = result2.get('odt', [''])[0]
    # Only look at grade/note - the form may carry extra keys (csrf_token,
    # request_id from the offline replay) with a different number of values.
    grades = result2.get('grade', [])
    notes = result2.get('note', [])
    any_scored = any(g not in ('', '0') for g in grades)
    # Each row names its candidate. Matching by position (older pages and
    # queued offline posts) breaks once the group's list changed meanwhile.
    subjects = result2.get('subject', [])
    if subjects and len(subjects) == len(grades):
        active = set(candidates)
        rows = [int(n) if str(n).isdigit() and int(n) in active else None for n in subjects]
    else:
        rows = candidates
    for i, (candidate_num, grade) in enumerate(zip(rows, grades)):
        if candidate_num is None:
            continue
        try:
            grade = int(grade)
        except ValueError:
            continue
        if grade == 0 and any_scored:
            # Unscored candidate gets the last-place grade, but an existing
            # review is never overwritten by the sentinel.
            subject_id = str(current_user.id) + "/" + str(candidate_num)
            existing = Review.query.filter_by(
                station=station, subject_id=subject_id, author_id=current_user.id
            ).first()
            if not existing:
                db.session.add(Review(
                    station=station,
                    subject_id=subject_id,
                    grade=1.0,
                    note="",
                    author=current_user,
                    subject=Candidate.query.filter_by(id=subject_id).first()
                ))
                db.session.commit()
            continue
        if grade != 0:
            note = notes[i] if i < len(notes) else ''
            subject_id = str(current_user.id) + "/" + str(candidate_num)
            # Upsert: re-submitting the group station form is a correction,
            # not a second review — duplicates here double candidates in the
            # station ranking and skew averages.
            review = Review.query.filter_by(
                station=station, subject_id=subject_id, author_id=current_user.id
            ).first()
            if review:
                review.grade = grade
                review.note = note
            else:
                db.session.add(Review(
                    station=station,
                    subject_id=subject_id,
                    grade=grade,
                    note=note,
                    author=current_user,
                    subject=Candidate.query.filter_by(id=subject_id).first()
                ))
            db.session.commit()
    update_avgs_nf()
    flash(f'ציוני התחנה {station} נשמרו בהצלחה!', 'success')
    return redirect(url_for('add_new_group_review'))

@app.route('/group-manage', methods=["GET", "POST"])
def manageCandidates():
    everyone = Candidate.query.filter_by(group_id=current_user.id).all()
    everyone.sort(key=lambda c: c.number)
    candidates = [c for c in everyone if c.status != "פרש"]
    retired = [c for c in everyone if c.status == "פרש"]
    ids = [c.id for c in everyone]
    with_data = set()
    if ids:
        with_data |= {sid for (sid,) in db.session.query(distinct(Review.subject_id)).filter(Review.subject_id.in_(ids))}
        with_data |= {sid for (sid,) in db.session.query(distinct(Note.subject_id)).filter(Note.subject_id.in_(ids))}
    photos = photo_versions(ids)
    with_data |= set(photos)
    with_data |= {c.id for c in everyone if c.interview_grade or c.final_status or c.final_weighted_grade}
    placeholders = sum(1 for c in candidates if is_placeholder_name(c.name))
    return render_template('panel.html', candidates=candidates, retired=retired, photos=photos,
                           with_data=with_data, placeholders=placeholders,
                           is_placeholder=is_placeholder_name, current_user=current_user)


@app.route('/admin-panel', methods=["GET", "POST"])
@admin_only
def manageGroups():
    groups = User.query.filter(User.id > 0).order_by(User.id).all()
    staff = [{"key": role["key"], "title": role["title"], "icon": role["icon"],
              "ready": User.query.get(user_id) is not None}
             for user_id, role in STAFF_ROLES.items()]
    return render_template('admin-panel.html', groups=groups, staff=staff)


def _retire_group_id():
    # The admin (id 0) and the doctor station can act on any group through
    # the "group" query argument; a regular user only on the own group.
    if is_staff(current_user) and current_user.id != DOCTOR_ID:
        abort(403)
    group_id = request.args.get("group", type=int)
    if group_id is None:
        if current_user.id <= 0:
            abort(400)
        return current_user.id
    if current_user.id not in (0, DOCTOR_ID):
        abort(403)
    return group_id


def _after_retire(group_id):
    if current_user.id == DOCTOR_ID:
        return redirect(url_for('staff_home', group=group_id))
    if current_user.id == 0:
        return redirect(url_for('homeAdmin', group_id=group_id))
    return redirect(url_for('manageCandidates'))


@app.route("/delete-candidate/<candidate_id>", methods=["POST"])
def delete_candidate(candidate_id):
    group_id = _retire_group_id()
    candidate_to_delete = Candidate.query.get(f"{group_id}/{candidate_id}")
    if not candidate_to_delete:
        abort(404)
    candidate_to_delete.status = "פרש"
    medical = request.args.get("reason") == "medical" or current_user.id == DOCTOR_ID
    candidate_to_delete.withdraw_reason = "רפואי" if medical else None
    db.session.commit()
    return _after_retire(group_id)

@app.route("/return/<candidate_id>", methods=["POST"])
def return_candidate(candidate_id):
    group_id = _retire_group_id()
    user_to_return = Candidate.query.get(f"{group_id}/{candidate_id}")
    if not user_to_return:
        abort(404)
    if current_user.id == DOCTOR_ID and user_to_return.withdraw_reason != "רפואי":
        abort(403)  # the doctor undoes only medical retirements
    user_to_return.status = ""
    user_to_return.withdraw_reason = None
    db.session.commit()
    return _after_retire(group_id)


@app.route("/edit-user/<int:user_id>", methods=["GET", "POST"])
@admin_only
def edit_user(user_id):
    user = User.query.get(user_id)
    edit_form = EditUserForm(
        name=user.name,
    )
    if edit_form.validate_on_submit():
        user.name = edit_form.name.data
        db.session.commit()
        return redirect(url_for("manageGroups"))
    return render_template("register.html", form=edit_form, is_edit=True, current_user=current_user)


@app.route("/delete/<int:user_id>", methods=["POST"])
@admin_only
def delete_user(user_id):
    user_to_delete = User.query.get(user_id)
    db.session.delete(user_to_delete)
    db.session.commit()
    update_avgs_nf()
    return redirect(url_for('manageGroups'))


@app.route("/edit-candidate/<string:candidate_id>", methods=["GET", "POST"])
def edit_candidate(candidate_id):
    candidate = Candidate.query.get(candidate_id.replace("-", "/"))
    if not can_edit_candidate(candidate):
        abort(404)
    edit_form = EditUserForm(
        name=candidate.name,
    )
    if edit_form.validate_on_submit():
        candidate.name = edit_form.name.data
        db.session.commit()
        return redirect(url_for("manageCandidates"))
    return render_template("add-candidate.html", form=edit_form, is_edit=True)


@app.route('/reviews-finder', methods=["GET", "POST"])
@admin_only
def search_reviews():
    form = Search_review()
    if form.validate_on_submit():
        name = form.name.data
        if name == "":
            return redirect(url_for('show_reviews', user_id=0))
        else:
            user = User.query.filter_by(name=form.name.data).first()
            if user:
                return redirect(url_for('show_reviews', user_id=user.id))
            else:
                flash("לא נמצא משתמש")
                return render_template("search.html", form=form)
    return render_template("search.html", form=form)

@app.context_processor
def inject_debug():
    return dict(debug=app.debug)

@app.route("/reviews/<int:user_id>", methods=["GET", "POST"])
@admin_only
def show_reviews(user_id):
    if user_id == 0:
        reviews = Review.query.all()
        return render_template('reviews.html', reviews=reviews, user_id=user_id)
    user = User.query.filter_by(id=user_id).first()
    reviews = Review.query.filter_by(subject=user.name).all()
    return render_template('reviews.html', reviews=reviews, user_id=user_id)

@app.route("/physical-reviews/", methods=["GET", "POST"])
def showPhysicalReviews():
    update_avgs_nf()
    form = SelectPhysicalReviewsForm()
    choices = ["ספרינטים", "זחילות", "אלונקה סוציומטרית", "מתלה שזיפים"] + getPhysicalStations()
    form.station.choices = choices
    candidates = Candidate.query.filter_by(group_id=current_user.id).all()
    candidate_nums = []
    for candidate in candidates:
        if candidate.status != "פרש":
            candidate_nums.append(int(candidate.id.split("/")[1]))
    candidate_nums.sort()
    form.subject.choices = candidate_nums
    if form.validate_on_submit():
        candidate = Candidate.query.filter_by(id=str(current_user.id) + "/" + str(form.subject.data)).first()
        reviews = Review.query.filter_by(subject_id=candidate.id).all()
        reviews = [review for review in reviews if "סיכום" in review.station and f" {form.station.data} " in f" {review.station} "]
        return render_template('physical-reviews.html', reviews=reviews, candidate_id=candidate.id.split("/")[1], form=form, choices = choices)
    return render_template('physical-reviews.html', form=form, choices=choices)


@app.route("/physical-reviews-admin/", methods=["GET", "POST"])
@admin_only
def showPhysicalReviewsAdmin():
    update_avgs_nf()
    form = SelectPhysicalReviewsFormAdmin()
    form.group.choices = get_groups()
    if form.group.data:
        candidates = [candidate.id.split("/")[1] for candidate in Candidate.query.filter_by(group_id=int(form.group.data)).all() if candidate.status != "פרש"]
        choices = ["ספרינטים", "זחילות", "אלונקה סוציומטרית", "מתלה שזיפים"] + getPhysicalStationsGroup(form.group.data)
    else:
        candidates = [int(candidate.id.split("/")[1]) for candidate in Candidate.query.filter_by(group_id=1).all() if candidate.status != "פרש"]
        choices = ["ספרינטים", "זחילות", "אלונקה סוציומטרית", "מתלה שזיפים"] + getPhysicalStationsGroup(1)
    form.station.choices = choices
    candidates.sort()
    form.subject.choices = candidates
    if request.method == "POST":
        candidate = Candidate.query.filter_by(id=str(form.group.data) + "/" + str(form.subject.data)).first()
        reviews = Review.query.filter_by(subject_id=candidate.id).all()
        reviews = [review for review in reviews if "סיכום" in review.station and f" {form.station.data} " in f" {review.station} "]
        return render_template('show-physical-admin.html', reviews=reviews, candidate_id=candidate.id.split("/")[1], form=form)
    return render_template('show-physical-admin.html', form=form)


@app.route("/odt-reviews/", methods=["GET", "POST"])
def showODTReviews():
    form = selectCandidate()
    update_avgs_nf()
    candidates = Candidate.query.filter_by(group_id=current_user.id).all()
    candidate_nums = []
    for candidate in candidates:
        if candidate.status != "פרש":
            candidate_nums.append(int(candidate.id.split("/")[1]))
    candidate_nums.sort()
    form.id.choices = candidate_nums
    if form.validate_on_submit():
        form = selectCandidate()
        candidates = Candidate.query.filter_by(group_id=current_user.id).all()
        candidate_nums = []
        for candidate in candidates:
            if candidate.status != "פרש":
                candidate_nums.append(int(candidate.id.split("/")[1]))
        candidate_nums.sort()
        form.id.choices = candidate_nums
        candidate = Candidate.query.filter_by(id=str(current_user.id) + "/" + str(form.id.data)).first()
        reviews = Review.query.filter_by(subject_id=candidate.id).all()
        reviews = [review for review in reviews if ("ODT" in review.station or "נאסא" in review.station or "הרצאות" in review.station) and review.station != "ODT סיכום"]
        return render_template('ODT-sum.html', reviews=reviews, candidate_id=candidate.id.split("/")[1], form=form)
    return render_template('ODT-sum.html', form=form)
@app.route("/odt-reviews-admin/", methods=["GET", "POST"])
@admin_only
def showODTReviewsAdmin():
    form = selectCandidateAdmin()
    update_avgs_nf()
    form.group.choices = get_groups()
    if form.group.data:
        candidates = [candidate.id.split("/")[1] for candidate in Candidate.query.filter_by(group_id=int(form.group.data)).all() if candidate.status != "פרש"]
        candidates.sort()
        form.id.choices = candidates
    elif len(get_groups()) > 0:
        candidates = [int(candidate.id.split("/")[1]) for candidate in Candidate.query.filter_by(group_id=get_groups()[0]).all() if candidate.status != "פרש"]
        candidates.sort()
        form.id.choices = candidates
    if request.method == "POST":
        candidate = Candidate.query.filter_by(id=str(form.group.data) + "/" + str(form.id.data)).first()
        reviews = Review.query.filter_by(subject_id=candidate.id).all()
        reviews = [review for review in reviews if ("ODT" in review.station or "נאסא" in review.station or "הרצאות" in review.station) and review.station != "ODT סיכום"]
        return render_template('ODT-sum-admin.html', reviews=reviews, candidate_id=candidate.id.split("/")[1], form=form)
    return render_template('ODT-sum-admin.html', form=form)

def _board_reviews(subject_id, physical_stations):
    # One filter for the scores board — the "כולם" and single-candidate views
    # must show the same rows. Keeps act summaries, drops raw act rows.
    reviews = Review.query.filter_by(subject_id=subject_id).all()
    clean = [review for review in reviews
             if review.station not in physical_stations
             and ("ODT" not in review.station or review.station == "ODT סיכום")
             and ("אקט" not in review.station or "סיכום" in review.station)]
    clean.sort(key=lambda x: x.grade, reverse=True)
    return clean


@app.route("/candidates/", methods=["GET", "POST"])
def showCandidate():
    # "הקבוצה שלי" was removed (field feedback); each candidate's page holds
    # the scores and their edit/delete actions now.
    return redirect(url_for("home"))

@app.route("/candidates-admin/", methods=["GET", "POST"])
@admin_only
def showCandidateAdmin():
    form = selectCandidateAdmin()
    update_avgs_nf()
    form.group.choices = get_groups()
    clean_reviews = []
    candidates = []
    if form.group.data:
        candidates = [candidate.id.split("/")[1] for candidate in Candidate.query.filter_by(group_id=int(form.group.data)).all() if candidate.status != "פרש"]
        candidates.sort()
        candidates = ["כולם"] + candidates
        form.id.choices = candidates
    elif len(get_groups()) > 0:
        candidates = [int(candidate.id.split("/")[1]) for candidate in Candidate.query.filter_by(group_id=get_groups()[0]).all() if candidate.status != "פרש"]
        candidates.sort()
        candidates = ["כולם"] + candidates
        form.id.choices = candidates
    physical_stations = getPhysicalStationsGroup(form.group.data) + ["ספרינטים", "זחילות", "אלונקה סוציומטרית", "מתלה שזיפים"]
    if request.method == "POST":
        if form.id.data == "כולם":
            all_reviews = []
            for candidate_num in candidates[1:]:
                subject_id = str(form.group.data) + "/" + str(candidate_num)
                all_reviews.append(_board_reviews(subject_id, physical_stations))
            return render_template('candidate-admin.html', form=form, all_reviews=all_reviews, group=form.group.data)
        candidate = Candidate.query.filter_by(id=str(form.group.data) + "/" + str(form.id.data)).first()
        if not candidate:
            return render_template('candidate-admin.html', form=form)
        clean_reviews = _board_reviews(candidate.id, physical_stations)
        return render_template('candidate-admin.html', reviews=clean_reviews, candidate_id=candidate.id.split("/")[1], form=form)
    return render_template('candidate-admin.html', form=form)

@app.route("/final-status/", methods=["GET", "POST"])
def AddStatus():
    form = AddFinalStatusForm()
    candidates = Candidate.query.filter_by(group_id=current_user.id).all()
    candidate_nums = []
    for candidate in candidates:
        if candidate.status != "פרש":
            candidate_nums.append(int(candidate.id.split("/")[1]))
    candidate_nums.sort()
    form.id.choices = candidate_nums
    form.final_status.choices = GRADE_OPTIONS

    # Get selected_id from URL or form data
    selected_id = request.args.get('candidate_id')
    if form.is_submitted():
        selected_id = form.id.data
    elif selected_id is None and candidate_nums:
        selected_id = candidate_nums[0]

    # Set form defaults based on selected candidate
    if selected_id:
        candidate = Candidate.query.filter_by(id=f"{current_user.id}/{selected_id}").first()
        if candidate:
            # Set form defaults before form validation
            if not form.is_submitted():
                form.id.default = int(selected_id)
                form.final_status.default = candidate.final_status
                form.final_note.default = candidate.final_note
                form.process()  # This is crucial - it processes the defaults

    if form.validate_on_submit():
        candidate = Candidate.query.filter_by(id=f"{current_user.id}/{form.id.data}").first()
        candidate.final_status = form.final_status.data
        candidate.final_note = form.final_note.data
        db.session.commit()
        flash(f'נתוני סיכום עבור {candidate.name} נשמרו בהצלחה!', 'success')
        return redirect(url_for('AddStatus', candidate_id=form.id.data))

    return render_template('add-status.html', form=form)

@app.route("/interview/", methods=["GET", "POST"])
def Interview():
    if is_duplicate_request():
        flash('הראיון כבר נשמר', 'success')
        return redirect(url_for('Interview'))
    form = InterviewForm()
    candidates = Candidate.query.filter_by(group_id=current_user.id).all()
    candidate_nums = []
    interviewed = []
    for candidate in candidates:
        if candidate.status != "פרש":
            num = int(candidate.id.split("/")[1])
            candidate_nums.append(num)
            if candidate.interview_grade:
                interviewed.append(num)
    candidate_nums.sort()
    form.id.choices = candidate_nums
    form.grade.choices = GRADE_OPTIONS

    if form.validate_on_submit():
        candidate = Candidate.query.filter_by(id=str(current_user.id) + "/" + str(form.id.data)).first()
        candidate.interviewer = form.interviewer.data
        candidate.interview_grade = form.grade.data
        candidate.interview_note = form.note.data
        candidate.tash_prob = form.tash.data
        candidate.medical_prob = form.medical.data
        db.session.commit()
        flash(f'הראיון עבור {candidate.name} נשמר בהצלחה!', 'success')
        return redirect(url_for('Interview'))
    return render_template('interview.html', form=form, interviewed=interviewed)

@app.route("/final-grade/", methods=["GET", "POST"])
def final_weighted_grade():
    if is_duplicate_request():
        flash('הציון כבר נשמר', 'success')
        return redirect(url_for('final_weighted_grade'))
    form = FinalWeightedGradeForm()
    candidates = active_candidates(current_user.id)
    form.id.choices = [c.number for c in candidates]
    # An explicit "choose" entry: a candidate without a grade must not show
    # (and accidentally save) the first category.
    form.grade.choices = [("", "— בחרו קטגוריה —")] + [(c, c) for c in FINAL_CATEGORIES]
    # Current category per candidate, so switching candidates pre-selects the
    # saved value instantly (the old page reloaded on every change).
    current = {c.number: c.final_weighted_grade for c in candidates
               if c.final_weighted_grade in FINAL_CATEGORIES}

    if not form.is_submitted():
        selected_id = request.args.get('candidate_id', type=int)
        if selected_id not in current and selected_id not in form.id.choices:
            selected_id = form.id.choices[0] if form.id.choices else None
        if selected_id is not None:
            form.id.data = str(selected_id)
            form.grade.data = current.get(selected_id)

    if form.validate_on_submit():
        candidate = Candidate.query.filter_by(id=f"{current_user.id}/{form.id.data}").first()
        if candidate.final_weighted_grade != form.grade.data:
            candidate.final_rank = None  # joins the end of its new category
        candidate.final_weighted_grade = form.grade.data
        db.session.commit()
        flash(f'הציון הסופי של {candidate.name}: {form.grade.data}', 'success')
        return redirect(url_for('final_weighted_grade', candidate_id=form.id.data))
    return render_template('final-grade.html', form=form, current=current)


@app.route("/edit-interview/<string:candidate_id>", methods=["GET", "POST"])
def edit_interview(candidate_id):
    candidate_id = candidate_id.replace("-", "/")
    candidate = Candidate.query.get(candidate_id)
    if not can_edit_candidate(candidate):
        abort(404)

    form = InterviewForm(id=int(candidate_id.split("/")[1]), interviewer=candidate.interviewer, grade=candidate.interview_grade, note=candidate.interview_note, tash=candidate.tash_prob, medical=candidate.medical_prob)
    form.grade.choices = GRADE_OPTIONS
    form.id.choices = [int(candidate_id.split("/")[1])]

    if form.validate_on_submit():
        candidate.interviewer = form.interviewer.data
        candidate.interview_grade = form.grade.data
        candidate.interview_note = form.note.data
        candidate.tash_prob = form.tash.data
        candidate.medical_prob = form.medical.data

        try:
            db.session.commit()
            flash('הראיון עודכן בהצלחה', 'success')  # Success message in Hebrew
            return redirect(url_for('showInterview'))
        except Exception as e:
            db.session.rollback()
            flash('שגיאה בשמירת הנתונים', 'error')  # Error message in Hebrew
            print(f"Error saving interview: {e}")

    return render_template("interview.html", form=form, is_edit=True)

@app.route("/show-interview/", methods=["GET", "POST"])
def showInterview():
    form = selectCandidate()
    candidates = active_candidates(current_user.id)
    form.id.choices = ["כולם"] + [c.number for c in candidates]
    if form.validate_on_submit() and form.id.data != "כולם":
        candidate = next((c for c in candidates if str(c.number) == str(form.id.data)), None)
        return render_template('show-interview.html', form=form, candidate=candidate,
                               candidate_id=candidate.number if candidate else None, all_candidates=[])
    # Default view: every interview done so far, no filter step first.
    if not form.is_submitted():
        form.id.data = "כולם"
    interviewed = [c for c in candidates if c.interview_grade]
    return render_template('show-interview.html', form=form, all_candidates=interviewed,
                           show_all=True, total=len(candidates))


@app.route("/show-interview-admin/", methods=["GET", "POST"])
@admin_only
def showInterviewAdmin():
    form = selectCandidateAdmin()
    groups = get_groups()
    form.group.choices = groups
    group_for_choices = int(form.group.data) if form.group.data else (groups[0] if groups else None)
    numbers = active_candidate_numbers(group_for_choices) if group_for_choices is not None else []
    form.id.choices = ["כולם"] + numbers
    if form.validate_on_submit():
        group_id = int(form.group.data)
        if form.id.data == "כולם":
            interviewed = [c for c in active_candidates(group_id) if c.interview_grade]
            return render_template('show-interview-admin.html', form=form, all_candidates=interviewed,
                                   show_all=True, group=group_id)
        candidate = Candidate.query.filter_by(id=f"{group_id}/{form.id.data}").first()
        return render_template('show-interview-admin.html', form=form, candidate=candidate,
                               candidate_id=form.id.data, all_candidates=[])
    # Default view: every interview of every group, no filter step first.
    form.id.data = "כולם"
    interviewed = [c for c in Candidate.query.filter(Candidate.group_id > 0).all()
                   if c.status != "פרש" and c.interview_grade]
    interviewed.sort(key=lambda c: (c.group_id, c.number))
    return render_template('show-interview-admin.html', form=form, all_candidates=interviewed,
                           show_all=True, every_group=True)

@app.route("/station-reviews-admin/", methods=["GET", "POST"])
@admin_only
def showStationReviewsAdmin():
    return redirect(url_for("admin_home"))

@app.route("/station-reviews/", methods=["GET", "POST"])
def showStationReviews():
    # "דירוג לפי תחנה" was removed (field feedback). Old links and pages the
    # service worker cached before the update land on the home page.
    return redirect(url_for("home"))

@app.route("/edit-review/<int:review_id>", methods=["GET", "POST"])
def edit_review(review_id):
    unique_stations = db.session.query(distinct(Review.station)).filter(Review.author_id == current_user.id).all()
    unique_station_values = [station[0] for station in unique_stations]
    stations = ["ספרינטים", "זחילות", "משימת מחשבה", "דיון מילוט", "פירוק והרכבת נשק", "מסע", "שקים", "ODT", "מעגל זנבות",
                "אלונקה סוציומטרית","מתלה שזיפים", "הרצאות", "בניית שוח", "חפירת בור","חפירת בור מכשול קבוצתי","בניית ערימת חול","נאסא"]
    unique_station_values = [station for station in unique_station_values if "אקט" not in station and "סיכום" not in station]
    final_stations = [station for station in unique_station_values if station not in stations]
    unique_station_values = stations + final_stations
    review = Review.query.get_or_404(review_id)
    if not can_edit_candidate(Candidate.query.get(review.subject_id)):
        abort(403)
    candidates = Candidate.query.filter_by(group_id=current_user.id).all()
    candidate_nums = []
    for candidate in candidates:
        if candidate.status != "פרש":
            candidate_nums.append(int(candidate.id.split("/")[1]))
    candidate_nums.sort()
    if "ODT" in review.station:
        form = CreateReviewForm(station=review.station, grade=review.grade, note=review.note,
                                subject=review.subject_id.split("/")[1])
    else:
        form = CreateReviewForm(station=review.station, grade=int(review.grade), note=review.note, subject=review.subject_id.split("/")[1])
    form.subject.choices = candidate_nums
    form.station.choices = unique_station_values
    # form.station.data = review.station
    # form.subject.data = review.subject_id.split("/")[1]
    # form.grade.data = review.grade
    if form.validate_on_submit():
        if form.station.data == "ODT":
            review.station = form.station.data
        else:
            review.station = form.station.data
        review.subject_id = str(current_user.id) + "/" + str(form.subject.data)
        review.grade = form.grade.data
        review.note = form.note.data
        db.session.commit()
        update_avgs(form)
        return redirect(url_for("candidate_profile", candidate_id=review.subject_id))
    return render_template("make-post.html", form=form, current_user=current_user)



@app.route("/edit-physical-review/<int:review_id>", methods=["GET", "POST"])
def edit_physical_review(review_id):
    # Get all stations including custom ones plus physical stations for editing
    base_stations = getAllStations()
    physical_stations = ["ספרינטים", "זחילות", "אלונקה סוציומטרית", "מתלה שזיפים"]
    # Combine physical stations with all stations, avoiding duplicates
    stations = physical_stations + [s for s in base_stations if s not in physical_stations]
    review = Review.query.get(review_id)
    candidates = Candidate.query.filter_by(group_id=current_user.id).all()
    candidate_nums = []
    for candidate in candidates:
        if candidate.status != "פרש":
            candidate_nums.append(int(candidate.id.split("/")[1]))
    candidate_nums.sort()
    form = CreateReviewForm(station=review.station, grade=review.grade, note=review.note, subject=review.subject_id.split("/")[1] )
    form.subject.choices = candidate_nums
    form.station.choices = stations
    if form.validate_on_submit():
        review.station = form.station.data
        review.subject_id = str(current_user.id) + "/" + str(form.subject.data)
        review.grade = form.grade.data
        review.note = form.note.data
        db.session.commit()
        update_avgs(form)
        return redirect(url_for("showPhysicalReviews"))
    return render_template("make-post.html", form=form, current_user=current_user)

@app.route("/edit-odt-review/<int:review_id>", methods=["GET", "POST"])
def edit_odt_review(review_id):
    # Get all stations including custom ones plus physical stations for editing
    base_stations = getAllStations()
    physical_stations = ["ספרינטים", "זחילות", "אלונקה סוציומטרית", "מתלה שזיפים"]
    # Combine physical stations with all stations, avoiding duplicates
    stations = physical_stations + [s for s in base_stations if s not in physical_stations]
    review = Review.query.get(review_id)
    candidates = Candidate.query.filter_by(group_id=current_user.id).all()
    candidate_nums = []
    for candidate in candidates:
        if candidate.status != "פרש":
            candidate_nums.append(int(candidate.id.split("/")[1]))
    candidate_nums.sort()
    form = CreateReviewForm(station="ODT", grade=review.grade, note=review.note, subject=review.subject_id.split("/")[1], odt=review.station.split("T ")[1])
    form.subject.choices = candidate_nums
    form.station.choices = stations
    form.odt.data = review.station.split("T ")[1]
    form.note.data = review.note
    if form.validate_on_submit():
        review.station = form.station.data + " " + form.odt.data
        review.subject_id = str(current_user.id) + "/" + str(form.subject.data)
        review.grade = form.grade.data
        review.note = form.note.data
        db.session.commit()
        update_avgs(form)
        return redirect(url_for("showODTReviews"))
    return render_template("make-post.html", form=form, current_user=current_user, odt_val = review.station.split("T ")[1], grade = int(review.grade), note = review.note)


@app.route("/delete-review/<int:review_id>", methods=["POST"])
def delete_review(review_id):
    review_to_delete = Review.query.get_or_404(review_id)
    candidate = Candidate.query.get(review_to_delete.subject_id)
    if not can_edit_candidate(candidate):
        abort(403)
    db.session.delete(review_to_delete)
    db.session.commit()
    update_avgs_nf(candidate.group_id)
    return redirect(safe_next(url_for("home")))

@app.route("/delete-physical-review/<int:review_id>", methods=["POST"])
def delete_physical_review(review_id):
    review_to_delete = Review.query.get_or_404(review_id)
    candidate = Candidate.query.get(review_to_delete.subject_id)
    if not can_edit_candidate(candidate):
        abort(403)
    db.session.delete(review_to_delete)
    db.session.commit()
    update_avgs_nf(candidate.group_id)
    return redirect(safe_next(url_for("showPhysicalReviews")))

@app.route("/delete-odt-review/<int:review_id>", methods=["POST"])
def delete_odt_review(review_id):
    review_to_delete = Review.query.get_or_404(review_id)
    candidate = Candidate.query.get(review_to_delete.subject_id)
    if not can_edit_candidate(candidate):
        abort(403)
    db.session.delete(review_to_delete)
    db.session.commit()
    update_avgs_nf(candidate.group_id)
    return redirect(safe_next(url_for("showODTReviews")))



@app.route("/update-date", methods=["GET", "POST"])
def update_date():
    form = UpdateDateForm(last_15_date=current_user.last_15_date)
    if form.validate_on_submit():
        last_15 = form.last_15_date.data
        current_user.last_15_date = last_15
        db.session.commit()
        return render_template("index.html", current_user=current_user)
    return render_template("update-date.html", form=form, current_user=current_user)

def getStationName(review):
    station = review.station.split(" - ")[0]
    station = station.split("סיכום")[1]
    if station[0] == " ":
        station = station[1:]
    return station

def getPhysicalStations():
    reviews = Review.query.filter_by(author_id=current_user.id).filter(Review.station.like(f'%אקט%')).all()
    physical_stations = [review.station for review in reviews]
    physical_stations = [station.split(" - ")[0] for station in physical_stations if "אקט" in station]
    physical_stations = [station for station in physical_stations if "ספרינטים" not in station and "זחילות" not in station and "אלונקה סוציומטרית" not in station and "מתלה שזיפים" not in station]
    physical_stations = [station.split(" סיכום")[0] for station in physical_stations]
    physical_stations = [station for station in physical_stations if station != '"' and station != " " and "סיכום" not in station.split()]
    physical_stations = list(set(physical_stations))
    physical_stations = physical_stations
    return physical_stations

def getPhysicalStationsGroup(group):
    reviews = Review.query.filter_by(author_id=group).filter(Review.station.like(f'%אקט%')).all()
    physical_stations = [review.station for review in reviews]
    physical_stations = [station.split(" - ")[0] for station in physical_stations if "אקט" in station]
    physical_stations = [station for station in physical_stations if "ספרינטים" not in station and "זחילות" not in station and "אלונקה סוציומטרית" not in station and "מתלה שזיפים" not in station]
    physical_stations = [station.split(" סיכום")[0] for station in physical_stations]
    physical_stations = [station for station in physical_stations if station != '"' and station != " " and "סיכום" not in station.split()]
    physical_stations = list(set(physical_stations))
    physical_stations = physical_stations
    return physical_stations

@app.route('/sw.js')
def service_worker():
    response = send_from_directory('static', 'sw.js')
    response.headers['Service-Worker-Allowed'] = '/'
    response.headers['Cache-Control'] = 'no-cache'
    response.headers['Content-Type'] = 'application/javascript'
    return response


@app.route('/offline')
def offline():
    return render_template('offline.html')


@app.route('/circles', methods=['GET', 'POST'])
def circles():
    physical_stations = []
    if request.method == 'POST':
        circle_numbers = request.json['circle_numbers']
        # Process the circle numbers as desired
        print(circle_numbers)
        return redirect(url_for("circles"))
    # Prepare data for the circles
    circles = [{'id': n, 'clicked': False, 'finished': False} for n in active_candidate_numbers(current_user.id)]
    # Custom ("אחר") stations this group already ran stay selectable.
    custom = sorted(s for s in getPhysicalStations() if s not in MODE_STATIONS["circles"])
    return render_template('test.html', circles=circles, physical_stations=custom)


@app.route('/circles/finished', methods=['POST'])
def circles_finished():
    if is_duplicate_request():
        return jsonify({'success': True, 'message': 'הציונים כבר נשמרו'})
    circle_numbers = request.json['circle_numbers']
    circle_numbers = circle_numbers[:circle_numbers.index(0)]
    reverse_mode = request.json.get('reverse_mode', False)

    if reverse_mode:
        circle_numbers = circle_numbers[::-1]  # Reverse the order

    candidates = Candidate.query.filter_by(group_id=current_user.id).all()
    full_candidates = [int(candidate.id.split("/")[1]) for candidate in candidates if candidate.status != "פרש"]
    candidates = [candidate for candidate in full_candidates if candidate not in circle_numbers]
    station = request.json['movement_type']
    other_flag = False
    if station == "אחר":
        station = request.json['other']
        other_flag = True
    if not circle_numbers:
        return jsonify({'success': False, 'message': 'לא סומנו מגובשים שסיימו'}), 400
    num_of_circles = len(circle_numbers) - 1
    counter = -1
    penalty = 4 / num_of_circles if num_of_circles > 0 else 0
    reviews = Review.query.filter_by(author_id=current_user.id).filter(Review.station.like(f'%{station}%')).all()
    reviews = [review for review in reviews if "סיכום" in review.station.split() and "אקט" in review.station.split()]
    reviews = [review for review in reviews if getStationName(review) == station]
    if len(reviews) > 0:
        if len(reviews) > 0:
            acts = [int(review.station.split("אקט")[1]) for review in reviews]
            act_num = max(acts, default=0) + 1
            station = f"{station} - אקט {act_num}"
        else:
            act_num = 1
            station = f"{station} - אקט {act_num}"
    else:
        act_num = 1
        station = f"{station} - אקט {act_num}"
    all_ids = [str(current_user.id) + "/" + str(n) for n in circle_numbers + candidates]
    candidate_map = {c.id: c for c in Candidate.query.filter(Candidate.id.in_(all_ids)).all()}
    for circle_number in circle_numbers:
        counter += 1
        subject_id = str(current_user.id) + "/" + str(circle_number)
        review = Review(station=station, author=current_user, subject_id=subject_id, grade=max(1, 4 - counter * penalty), subject=candidate_map.get(subject_id))
        db.session.add(review)
    for circle_number in candidates:
        subject_id = str(current_user.id) + "/" + str(circle_number)
        review = Review(station=station, author=current_user, subject_id=subject_id, grade=1, subject=candidate_map.get(subject_id))
        db.session.add(review)
    db.session.commit()
    # Process the finished circle numbers as desired
    physical_stations = getPhysicalStations()
    circles = [{'id': i, 'clicked': False, 'finished': False} for i in full_candidates]
    update_avgs_nf()
    return jsonify({'success': True, 'message': f'ציוני התחנה {station} נשמרו בהצלחה!'})


def next_act_number(group_id, base):
    """Next free heat number for a circle station of this group."""
    stations = db.session.query(distinct(Review.station)).filter(
        Review.author_id == group_id, Review.station.like('%אקט%')).all()
    numbers = [parsed[1] for (station,) in stations
               for parsed in [parse_act_station(station)] if parsed and parsed[0] == base]
    return max(numbers, default=0) + 1


@app.route('/circles/finished-act', methods=['POST'])
def circles_finished_act():
    if is_duplicate_request():
        return jsonify({'success': True, 'message': 'הציונים כבר נשמרו'})
    data = request.get_json(silent=True) or {}
    if 'finished' in data:
        circle_numbers = data.get('finished') or []
    else:
        # Older clients (and queued offline items) send finished + 0 + rest.
        circle_numbers = data.get('circle_numbers') or []
        if 0 in circle_numbers:
            circle_numbers = circle_numbers[:circle_numbers.index(0)]
    group_id = current_user.id
    full_candidates = active_candidate_numbers(group_id)
    # A stale screen may still show a number that was retired or removed —
    # drop it instead of failing the whole heat on the foreign key.
    circle_numbers = [int(n) for n in circle_numbers if int(n) in full_candidates]
    if not circle_numbers:
        return jsonify({'success': False, 'message': 'לא סומנו מגובשים שסיימו'}), 400
    if data.get('reverse_mode'):
        circle_numbers = circle_numbers[::-1]

    unfinished = [n for n in full_candidates if n not in circle_numbers]
    base = data.get('movement_type') or ''
    if base == "אחר":
        base = (data.get('other') or '').strip()
    if not base:
        return jsonify({'success': False, 'message': 'יש לבחור תחנה'}), 400
    station = f"{base} - אקט {next_act_number(group_id, base)}"

    # Linear 4 → 1 by finishing position; everyone who did not finish gets 1.
    penalty = 4 / (len(circle_numbers) - 1) if len(circle_numbers) > 1 else 0
    grades = [(n, max(1, 4 - i * penalty)) for i, n in enumerate(circle_numbers)]
    grades += [(n, 1) for n in unfinished]
    for number, grade in grades:
        db.session.add(Review(station=station, author_id=group_id,
                              subject_id=f"{group_id}/{number}", grade=grade))
    db.session.flush()
    # Only this heat's summaries change — the old updateActAvgs() re-queried
    # every act of every candidate on each save and slowed down as the day
    # went on.
    for number, _ in grades:
        recompute_act_summary(f"{group_id}/{number}", station, group_id)
    db.session.commit()
    update_avgs_nf(group_id)
    return jsonify({'success': True, 'station': station,
                    'message': f'ציוני התחנה {station} נשמרו בהצלחה!'})



@app.route('/circles/reset', methods=['GET'])
def reset_circles():
    circles = [{'id': n, 'clicked': False, 'finished': False} for n in active_candidate_numbers(current_user.id)]
    return render_template('test.html', circles=circles, physical_stations=[])

@app.route("/new-note", methods=["GET", "POST"])
def add_new_note():
    form = CreateNoteForm()
    candidates = Candidate.query.filter_by(group_id=current_user.id).all()
    candidate_nums = []
    for candidate in candidates:
        if candidate.status != "פרש":
            candidate_nums.append(int(candidate.id.split("/")[1]))
    candidate_nums.sort()
    form.subject.choices = candidate_nums
    israel_tz = pytz.timezone('Israel')
    if form.validate_on_submit():
        if is_duplicate_request():
            flash('ההערה כבר נשמרה', 'success')
            return redirect(url_for('add_new_note'))
        current_time_israel = datetime.now(israel_tz)
        formatted_time = current_time_israel.strftime('%d-%m-%Y %H:%M')
        new_note = Note(
            subject_id=str(current_user.id) + "/" + str(form.subject.data),
            type=form.type.data,
            text=form.text.data,
            author=current_user,
            subject=Candidate.query.filter_by(id=str(current_user.id) + "/" + str(form.subject.data)).first(),
            date=formatted_time,
            location=form.location.data
        )
        db.session.add(new_note)
        db.session.commit()
        candidate_name = Candidate.query.filter_by(id=str(current_user.id) + "/" + str(form.subject.data)).first().name
        flash(f'הערה {form.type.data} עבור {candidate_name} נשמרה בהצלחה!', 'success')
        return redirect(url_for('add_new_note'))
    return render_template("make-note.html", form=form, current_user=current_user)

@app.route("/edit-note/<int:note_id>", methods=["GET", "POST"])
def edit_note(note_id):
    note = Note.query.get_or_404(note_id)
    if not can_delete_note(note) or is_staff(current_user):
        abort(403)
    form = CreateNoteForm(
        subject=int(note.subject_id.split("/")[1]),
        type=note.type,
        text=note.text,
        location=note.location
    )

    candidates = Candidate.query.filter_by(group_id=current_user.id).all()
    candidate_nums = []
    for candidate in candidates:
        if candidate.status != "פרש":
            candidate_nums.append(int(candidate.id.split("/")[1]))
    candidate_nums.sort()
    form.subject.choices = candidate_nums

    israel_tz = pytz.timezone('Israel')
    if form.validate_on_submit():
        note.subject_id = str(current_user.id) + "/" + str(form.subject.data)
        note.type = form.type.data
        note.text = form.text.data
        note.location = form.location.data
        note.subject = Candidate.query.filter_by(id=str(current_user.id) + "/" + str(form.subject.data)).first()
        current_time_israel = datetime.now(israel_tz)
        formatted_time = current_time_israel.strftime('%d-%m-%Y %H:%M')
        note.date = formatted_time


        db.session.commit()
        flash("ההערה עודכנה", "success")
        return redirect(safe_next(url_for('show_notes')))

    return render_template("make-note.html", form=form, current_user=current_user, is_edit=True)

@app.route("/show-notes", methods=["GET", "POST"])
def show_notes():
    form = selectCandidate()
    candidates = Candidate.query.filter_by(group_id=current_user.id).all()
    all_notes = []
    candidate_nums = []
    for candidate in candidates:
        if candidate.status != "פרש":
            candidate_nums.append(int(candidate.id.split("/")[1]))
    candidate_nums.sort()
    candidate_nums = ["כולם"] + candidate_nums
    candidate = ""
    form.id.choices = candidate_nums
    if form.validate_on_submit():
        if form.id.data == "כולם":
            for candidate_num in candidate_nums[1:]:
                candidate = Candidate.query.filter_by(id=str(current_user.id) + "/" + str(candidate_num)).first()
                notes = Note.query.filter_by(subject_id=candidate.id).all()
                reviews = Review.query.filter_by(subject_id=candidate.id).all()
                reviews = [review for review in reviews if review.note != None and review.note not in["", "אקט"]]
                for review in reviews:
                    template_note = Note(type="ניטרלית", text=review.note, location=review.station, date="", subject_id=candidate.id, subject=candidate, author=current_user, author_id=current_user.id)
                    notes.append(template_note)
                all_notes.append(notes)
            if len(candidate_nums) == 1:
                return render_template('show-notes.html', form=form)
            return render_template('show-notes.html', notes=all_notes, candidate_id=candidate.id.split("/")[1], form=form, all_notes=all_notes, everyone=True)
        candidate = Candidate.query.filter_by(id=str(current_user.id) + "/" + str(form.id.data)).first()
        notes = Note.query.filter_by(subject_id=candidate.id).all()
        reviews = Review.query.filter_by(subject_id=candidate.id).all()
        reviews = [review for review in reviews if review.note != None and review.note not in["", "אקט"]]
        for review in reviews:
            template_note = Note(type="ניטרלית", text=review.note, location=review.station, date="", subject_id=candidate.id, subject=candidate, author=current_user, author_id=current_user.id)
            notes.append(template_note)
        return render_template('show-notes.html', notes=notes, candidate_id=candidate.id.split("/")[1], form=form, all_notes=all_notes, everyone=False)
    return render_template('show-notes.html', form=form, everyone=False)

@app.route("/notes-admin/", methods=["GET", "POST"])
@admin_only
def showNotesAdmin():
    form = selectCandidateAdmin()
    form.group.choices = get_groups()
    clean_reviews = []
    candidates = []
    candidate = ""
    if form.group.data:
        candidates = [int(candidate.id.split("/")[1]) for candidate in Candidate.query.filter_by(group_id=int(form.group.data)).all() if candidate.status != "פרש"]
        candidates.sort()
        candidates = ["כולם"] + candidates
        form.id.choices = candidates
    elif len(get_groups()) > 0:
        candidates = [int(candidate.id.split("/")[1]) for candidate in Candidate.query.filter_by(group_id=get_groups()[0]).all() if candidate.status != "פרש"]
        candidates.sort()
        candidates = ["כולם"] + candidates
        form.id.choices = candidates
    if request.method == "POST":
        if form.id.data == "כולם":
            all_notes = []
            notes = []
            for candidate_num in candidates[1:]:
                candidate = Candidate.query.filter_by(id=str(form.group.data) + "/" + str(candidate_num)).first()
                notes = Note.query.filter_by(subject_id=candidate.id).all()
                reviews = Review.query.filter_by(subject_id=candidate.id).all()
                reviews = [review for review in reviews if review.note != None and review.note not in["", "אקט"]]
                for review in reviews:
                    template_note = Note(type="ניטרלית", text=review.note, location=review.station, date="", subject_id=candidate.id, subject=candidate, author=current_user, author_id=current_user.id)
                    notes.append(template_note)
                all_notes.append(notes)
            if len(candidates) == 1:
                return render_template('notes-admin.html', form=form)
            return render_template('notes-admin.html', notes=notes, candidate_id=candidate.id.split("/")[1], form=form, all_notes=all_notes, group=form.group.data)
        candidate = Candidate.query.filter_by(id=str(form.group.data) + "/" + str(form.id.data)).first()
        if not candidate:
            return render_template('notes-admin.html', form=form)
        notes = Note.query.filter_by(subject_id=candidate.id).all()
        reviews = Review.query.filter_by(subject_id=candidate.id).all()
        reviews = [review for review in reviews if review.note != None and review.note not in["", "אקט"]]
        for review in reviews:
            template_note = Note(type="ניטרלית", text=review.note, location=review.station, date="", subject_id=candidate.id, subject=candidate, author=current_user, author_id=current_user.id)
            notes.append(template_note)
        return render_template('notes-admin.html', notes=notes, candidate_id=candidate.id.split("/")[1], form=form, group = form.group.data)
    return render_template('notes-admin.html', form=form)

# --- Editing saved scores from the candidate page ---------------------------

def _profile_url(candidate, anchor=""):
    return url_for("candidate_profile", candidate_id=candidate.id) + anchor


@app.route("/review/<int:review_id>/update", methods=["POST"])
def review_update(review_id):
    review = Review.query.get_or_404(review_id)
    candidate = Candidate.query.get(review.subject_id)
    if not can_edit_candidate(candidate):
        abort(403)
    back = _profile_url(candidate, "#history")
    kind = review_kind(review)
    if kind not in ("act", "station"):
        flash("לא ניתן לערוך שורה זו כאן", "error")
        return redirect(back)
    try:
        grade = round(float(request.form.get("grade", "")), 2)
    except ValueError:
        grade = None
    if grade is None or not 1 <= grade <= 4:
        flash("הציון חייב להיות בין 1 ל-4", "error")
        return redirect(back)
    review.grade = grade
    if kind == "station":
        review.note = (request.form.get("note") or "").strip()
    db.session.flush()
    if kind == "act":
        recompute_act_summary(candidate.id, review.station, candidate.group_id)
    db.session.commit()
    update_avgs_nf(candidate.group_id, candidates=[candidate])
    flash(f'הציון ב"{review.station}" עודכן', 'success')
    return redirect(back)


@app.route("/review/<int:review_id>/delete", methods=["POST"])
def review_delete(review_id):
    review = Review.query.get_or_404(review_id)
    candidate = Candidate.query.get(review.subject_id)
    if not can_edit_candidate(candidate):
        abort(403)
    back = _profile_url(candidate, "#history")
    kind = review_kind(review)
    if kind not in ("act", "station"):
        flash("לא ניתן למחוק שורה זו כאן", "error")
        return redirect(back)
    station = review.station
    db.session.delete(review)
    db.session.flush()
    extra = set()
    if kind == "act":
        recompute_act_summary(candidate.id, station, candidate.group_id)
        extra.add(parse_act_station(station)[0])
    db.session.commit()
    update_avgs_nf(candidate.group_id, candidates=[candidate], extra_stations=extra)
    flash(f'הציון ב"{station}" נמחק', 'success')
    return redirect(back)


def can_delete_note(note):
    if is_admin(current_user):
        return True
    if is_staff(current_user):
        return note.author_id == current_user.id
    candidate = Candidate.query.get(note.subject_id)
    return bool(candidate) and candidate.group_id == current_user.id and note.type not in STAFF_NOTE_TYPES


@app.route("/note/<int:note_id>/delete", methods=["POST"])
def delete_note(note_id):
    note = Note.query.get_or_404(note_id)
    if not can_delete_note(note):
        abort(403)
    db.session.delete(note)
    db.session.commit()
    flash("ההערה נמחקה", "success")
    default = url_for("staff_home") if is_staff(current_user) else url_for("show_notes")
    return redirect(safe_next(default))


# --- Saved circle-mode heats ("אקטים") --------------------------------------

def group_acts(group_id):
    """The group's heats, newest first, each with its finishing order."""
    reviews = Review.query.filter(Review.author_id == group_id, Review.station.like('%אקט%')) \
        .order_by(Review.id).all()
    acts = {}
    for review in reviews:
        parsed = parse_act_station(review.station)
        if not parsed or parsed[2]:
            continue
        act = acts.setdefault(review.station, {
            "station": review.station, "base": parsed[0], "number": parsed[1], "rows": [], "last_id": 0})
        act["rows"].append(review)
        act["last_id"] = max(act["last_id"], review.id)
    for act in acts.values():
        # Rows are inserted in finishing order, non-finishers last.
        act["order"] = [(int(r.subject_id.split("/")[1]), r.grade) for r in act["rows"]]
    return sorted(acts.values(), key=lambda a: -a["last_id"])


@app.route("/acts")
def acts_page():
    if current_user.id <= 0:
        return redirect(url_for("home"))
    acts = group_acts(current_user.id)
    bases = list(MODE_STATIONS["circles"])
    bases += [a["base"] for a in acts if a["base"] not in bases]
    return render_template("acts.html", acts=acts, bases=list(dict.fromkeys(bases)))


def _act_from_form():
    station = request.form.get("station") or ""
    parsed = parse_act_station(station)
    if not parsed or parsed[2]:
        abort(400)
    rows = Review.query.filter_by(author_id=current_user.id, station=station).all()
    return station, parsed, rows


@app.route("/acts/delete", methods=["POST"])
def act_delete():
    station, parsed, rows = _act_from_form()
    if not rows:
        flash("האקט כבר לא קיים", "warning")
        return redirect(url_for("acts_page"))
    subject_ids = {r.subject_id for r in rows}
    for row in rows:
        db.session.delete(row)
    for summary in Review.query.filter(Review.station == f"סיכום {station}",
                                       Review.subject_id.in_(subject_ids)).all():
        db.session.delete(summary)
    db.session.commit()
    update_avgs_nf(current_user.id, extra_stations={parsed[0]})
    flash(f'"{station}" נמחק', 'success')
    return redirect(url_for("acts_page"))


@app.route("/acts/rename", methods=["POST"])
def act_rename():
    station, parsed, rows = _act_from_form()
    new_base = (request.form.get("new_base") or "").strip()
    if new_base == "אחר":
        new_base = (request.form.get("other") or "").strip()
    if not rows:
        flash("האקט כבר לא קיים", "warning")
        return redirect(url_for("acts_page"))
    if not new_base or " - אקט " in new_base:
        flash("יש לבחור שם תחנה תקין", "error")
        return redirect(url_for("acts_page"))
    if new_base == parsed[0]:
        flash("לא בוצע שינוי — זו כבר התחנה של האקט", "info")
        return redirect(url_for("acts_page"))
    group_id = current_user.id
    new_station = f"{new_base} - אקט {next_act_number(group_id, new_base)}"
    subject_ids = {r.subject_id for r in rows}
    for row in rows:
        row.station = new_station
    for summary in Review.query.filter(Review.station == f"סיכום {station}",
                                       Review.subject_id.in_(subject_ids)).all():
        db.session.delete(summary)
    db.session.flush()
    for subject_id in subject_ids:
        recompute_act_summary(subject_id, new_station, group_id)
    db.session.commit()
    update_avgs_nf(group_id, extra_stations={parsed[0], new_base})
    flash(f'"{station}" הועבר ל-"{new_station}"', 'success')
    return redirect(url_for("acts_page"))


# --- Quick notes (floating bubble) ------------------------------------------

def israel_now_str():
    return datetime.now(pytz.timezone('Israel')).strftime('%d-%m-%Y %H:%M')


@app.route("/notes/quick", methods=["POST"])
def note_quick():
    data = request.get_json(silent=True) or {}
    role = staff_role(current_user)
    text = (data.get("text") or "").strip()
    if not text:
        return jsonify({"success": False, "message": "יש לכתוב את ההערה"}), 400
    if len(text) > 4000:
        return jsonify({"success": False, "message": "ההערה ארוכה מדי"}), 400
    try:
        number = int(data.get("subject"))
        group_id = int(data.get("group")) if (role or is_admin(current_user)) else current_user.id
    except (TypeError, ValueError):
        return jsonify({"success": False, "message": "יש לבחור מגובש"}), 400
    candidate = Candidate.query.get(f"{group_id}/{number}")
    if not candidate or group_id <= 0:
        return jsonify({"success": False, "message": "המגובש לא נמצא"}), 404
    note_type = role["note_type"] if role else data.get("type")
    if not role and note_type not in NOTE_TYPES:
        return jsonify({"success": False, "message": "יש לבחור סוג הערה"}), 400
    if is_duplicate_request():
        return jsonify({"success": True, "duplicate": True, "message": "ההערה כבר נשמרה ✓"})
    location = (data.get("location") or "").strip()[:200] or (role["title"] if role else "")
    note = Note(subject_id=candidate.id, type=note_type, text=text, location=location,
                author_id=current_user.id, date=israel_now_str())
    db.session.add(note)
    db.session.commit()
    return jsonify({"success": True, "note_id": note.id,
                    "message": f"ההערה למגובש {number} נשמרה ✓"})


@app.context_processor
def inject_quick_note():
    def quick_note_data():
        """Candidates the quick-note sheet can target, per group."""
        if not current_user.is_authenticated:
            return None
        role = staff_role(current_user)
        if role or is_admin(current_user):
            group_ids = get_groups()
        else:
            group_ids = [current_user.id]
        names = {u.id: u.name for u in User.query.filter(User.id.in_(group_ids)).all()} if group_ids else {}
        groups = {gid: [] for gid in group_ids}
        if group_ids:
            for c in Candidate.query.filter(Candidate.group_id.in_(group_ids)).all():
                if c.status != "פרש":
                    groups[c.group_id].append([c.number, c.name])
        for members in groups.values():
            members.sort()
        return {
            "groups": [{"id": gid, "name": names.get(gid, ""), "candidates": groups[gid]} for gid in group_ids],
            "chooseGroup": bool(role or is_admin(current_user)),
            "types": [] if role else NOTE_TYPES,
            "fixedType": role["note_type"] if role else None,
        }
    return {"quick_note_data": quick_note_data}


# --- Built-in staff stations (doctor / HR officer) -------------------------

@app.route("/staff")
def staff_home():
    role = staff_role(current_user)
    if not role:
        return redirect(url_for("home"))
    groups = User.query.filter(User.id > 0).order_by(User.id).all()
    group_ids = [g.id for g in groups]
    group_id = request.args.get("group", type=int)
    if group_id not in group_ids:
        group_id = group_ids[0] if group_ids else None
    candidates = Candidate.query.filter_by(group_id=group_id).all() if group_id else []
    candidates.sort(key=lambda c: (c.status == "פרש", c.number))
    notes = defaultdict(list)
    if candidates:
        for note in Note.query.filter(Note.subject_id.in_([c.id for c in candidates]),
                                      Note.type == role["note_type"]).order_by(Note.id.desc()).all():
            notes[note.subject_id].append(note)
    return render_template("staff-home.html", role=role, groups=groups, group_id=group_id,
                           candidates=candidates, notes=notes, is_doctor=current_user.id == DOCTOR_ID)


@app.route("/admin/staff/<key>", methods=["POST"])
@admin_only
def set_staff_password(key):
    user_id = STAFF_BY_KEY.get(key)
    if user_id is None:
        abort(404)
    password = (request.form.get("password") or "").strip()
    if len(password) < 4:
        flash("הסיסמה חייבת להכיל לפחות 4 תווים", "error")
        return redirect(url_for("manageGroups"))
    role = STAFF_ROLES[user_id]
    user = User.query.get(user_id)
    if user:
        user.password = password
    else:
        db.session.add(User(id=user_id, name=role["title"], password=password,
                            sprint_num=0, crawl_num=0, alonka_num=0, mitam_num=0))
    db.session.commit()
    flash(f'הסיסמה של עמדת {role["title"]} נשמרה', 'success')
    return redirect(url_for("manageGroups"))


# --- Candidate photos -------------------------------------------------------

def _sniff_image(data):
    if data.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    return None


def _photo_candidate(group_id, number):
    candidate = Candidate.query.get(f"{group_id}/{number}")
    if not candidate or not can_edit_candidate(candidate):
        abort(404)
    return candidate


@app.route("/candidate-photo/<int:group_id>/<int:number>")
def candidate_photo(group_id, number):
    candidate = _photo_candidate(group_id, number)
    photo = CandidatePhoto.query.get(candidate.id)
    if not photo or not photo.data:
        abort(404)
    response = send_file(BytesIO(photo.data), mimetype=photo.mime)
    if request.args.get("v") == str(photo.version):
        # Versioned URL: the bytes behind it never change.
        response.headers["Cache-Control"] = "private, max-age=31536000, immutable"
    else:
        response.headers["Cache-Control"] = "private, no-cache"
    return response


@app.route("/candidate-photo/<int:group_id>/<int:number>", methods=["POST"])
def upload_candidate_photo(group_id, number):
    candidate = _photo_candidate(group_id, number)
    upload = request.files.get("photo")
    if not upload:
        return jsonify({"success": False, "message": "לא התקבלה תמונה"}), 400
    data = upload.read(MAX_PHOTO_BYTES + 1)
    if len(data) > MAX_PHOTO_BYTES:
        return jsonify({"success": False, "message": "התמונה גדולה מדי"}), 413
    mime = _sniff_image(data)
    if not mime:
        return jsonify({"success": False, "message": "קובץ התמונה אינו נתמך"}), 400
    photo = CandidatePhoto.query.get(candidate.id)
    # The version is part of an immutable, cached URL, so it must never repeat
    # — deleting keeps the row (empty) for exactly this reason.
    version = photo.version + 1 if photo else int(time.time())
    if photo:
        photo.data, photo.mime, photo.version = data, mime, version
    else:
        photo = CandidatePhoto(candidate_id=candidate.id, data=data, mime=mime, version=version)
        db.session.add(photo)
    db.session.commit()
    return jsonify({"success": True, "message": f"התמונה של מגובש {number} נשמרה ✓",
                    "url": url_for("candidate_photo", group_id=group_id, number=number, v=photo.version)})


@app.route("/candidate-photo/<int:group_id>/<int:number>/delete", methods=["POST"])
def delete_candidate_photo(group_id, number):
    candidate = _photo_candidate(group_id, number)
    photo = CandidatePhoto.query.get(candidate.id)
    if photo and photo.data:
        # Tombstone, not a delete: the next photo must get a new version.
        photo.data, photo.mime, photo.version = b"", "", photo.version + 1
        db.session.commit()
    flash(f"התמונה של מגובש {number} הוסרה", "success")
    return redirect(safe_next(url_for("manageCandidates")))


def photo_versions(candidate_ids):
    candidate_ids = list(candidate_ids)
    if not candidate_ids:
        return {}
    rows = db.session.query(CandidatePhoto.candidate_id, CandidatePhoto.version) \
        .filter(CandidatePhoto.candidate_id.in_(candidate_ids), CandidatePhoto.mime != "").all()
    return dict(rows)


# --- Group management: names for the pre-created candidates ----------------

@app.route('/group-manage/names', methods=["POST"])
def save_candidate_names():
    if current_user.id <= 0:
        abort(403)
    if is_duplicate_request():
        flash("השמות כבר נשמרו", "success")
        return redirect(url_for('manageCandidates'))
    changed = conflicts = 0
    for candidate in Candidate.query.filter_by(group_id=current_user.id).all():
        new_name = (request.form.get(f"name-{candidate.number}") or "").strip()[:200]
        if not new_name or new_name == candidate.name:
            continue
        # The page sends the name it showed. If someone renamed the candidate
        # since (another phone, or this save replayed late from the offline
        # queue), keep the newer name instead of rolling it back.
        shown = request.form.get(f"orig-{candidate.number}")
        if shown is not None and shown != candidate.name:
            conflicts += 1
            continue
        candidate.name = new_name
        changed += 1
    db.session.commit()
    flash(f"עודכנו {changed} שמות" if changed else "לא היו שינויים בשמות", "success")
    if conflicts:
        flash(f"{conflicts} שמות שונו בינתיים במכשיר אחר ולא נדרסו — בדקו ועדכנו שוב", "warning")
    return redirect(url_for('manageCandidates'))


@app.route('/group-manage/remove/<int:number>', methods=["POST"])
def remove_empty_candidate(number):
    candidate = Candidate.query.get(f"{current_user.id}/{number}")
    if not candidate or current_user.id <= 0:
        abort(404)
    if candidate_has_data(candidate):
        flash(f"למגובש {number} כבר הוזנו נתונים — אפשר לסמן אותו כפורש במקום להסיר", "error")
        return redirect(url_for('manageCandidates'))
    CandidatePhoto.query.filter_by(candidate_id=candidate.id).delete()  # an empty tombstone, if any
    db.session.delete(candidate)
    db.session.commit()
    flash(f"מגובש {number} הוסר מהקבוצה", "success")
    return redirect(url_for('manageCandidates'))


# --- Final grade summary: ranking inside each category ----------------------

def _final_group_id():
    if is_admin(current_user):
        groups = get_groups()
        group_id = request.args.get("group", type=int)
        if group_id is None:
            group_id = (request.get_json(silent=True) or {}).get("group")
        if group_id not in groups:
            group_id = groups[0] if groups else None
        return group_id
    return current_user.id


@app.route("/final-summary/")
def final_summary():
    group_id = _final_group_id()
    rows = candidate_rows(active_candidates(group_id), group_id) if group_id else []
    sections = []
    for category in FINAL_CATEGORIES:
        members = [r for r in rows if r["candidate"].final_weighted_grade == category]
        members.sort(key=lambda r: (r["candidate"].final_rank is None, r["candidate"].final_rank or 0, r["number"]))
        sections.append({"category": category, "rows": members})
    unassigned = [r for r in rows if r["candidate"].final_weighted_grade not in FINAL_CATEGORIES]
    return render_template("final-summary.html", sections=sections, unassigned=unassigned,
                           group_id=group_id, groups=get_groups() if is_admin(current_user) else [],
                           categories=FINAL_CATEGORIES)


@app.route("/final-summary/save", methods=["POST"])
def final_summary_save():
    group_id = _final_group_id()
    if not group_id:
        return jsonify({"success": False, "message": "לא נבחרה קבוצה"}), 400
    data = request.get_json(silent=True) or {}
    order = data.get("order")
    if not isinstance(order, dict):
        return jsonify({"success": False, "message": "נתונים חסרים"}), 400
    if any(category not in FINAL_CATEGORIES and category != "" for category in order):
        return jsonify({"success": False, "message": "קטגוריה לא מוכרת"}), 400
    if is_duplicate_request():
        return jsonify({"success": True, "message": "הדירוג כבר נשמר ✓"})
    by_number = {c.number: c for c in Candidate.query.filter_by(group_id=group_id).all()}
    seen_in = data.get("from") if isinstance(data.get("from"), dict) else {}
    stale = 0
    # The client sends the full order of every category it touched, plus the
    # category each candidate had when the page saved last. A row whose
    # category was changed elsewhere since (the final-grade page, another
    # phone, a late offline replay) is left alone instead of rolled back.
    for category, numbers in order.items():
        for rank, number in enumerate(numbers or [], start=1):
            try:
                candidate = by_number.get(int(number))
            except (TypeError, ValueError):
                candidate = None
            if not candidate:
                continue
            current = candidate.final_weighted_grade if candidate.final_weighted_grade in FINAL_CATEGORIES else ""
            if current != category and str(number) in seen_in and seen_in[str(number)] != current:
                stale += 1
                continue
            candidate.final_weighted_grade = category or None
            candidate.final_rank = rank if category else None
    db.session.commit()
    if stale:
        return jsonify({"success": True, "stale": stale,
                        "message": "חלק מהמגובשים עודכנו בינתיים ממקום אחר — רעננו את הדף"})
    return jsonify({"success": True, "message": "הדירוג נשמר ✓"})


# --- Prior interviews (the unit's interview form, synced from Excel) --------
# The admin uploads the form's export on the admin home. Every active
# candidate whose name appears in it is flagged — for the admin across all
# groups, and for a group on its own home page.

INTERVIEW_SYNC_MAX_BYTES = 5 * 1024 * 1024
INTERVIEW_SYNC_MAX_ROWS = 5000
# Field → the form's column title. Titles are compared with name_key(), so
# spacing, punctuation and final letters do not matter, and a longer title
# ("התרשמות כללית (נא להרחיב)") still matches.
INTERVIEW_COLUMNS = {
    "name": "שם מלא מרואיין",
    "interviewed_at": "חותמת זמן",
    "interviewer": "שם מראיין",
    "gibush": "איזה גיבוש ביצע",
    "rating": "דירוג המרואיין",
    "impression": "התרשמות כללית",
}
# A one-word name ("דניאל") would match half the gibush.
MIN_NAME_WORDS = 2
_NAME_DASHES = re.compile(r"[-־‐-―_/\\]")
_NAME_MARKS = re.compile(r"[֑-ׇ'\"`׳״‘’“”.,()\[\]]")
_FINAL_LETTERS = str.maketrans("ךםןףץ", "כמנפצ")
_HAS_LETTER = re.compile(r"[A-Za-zא-ת]")


def name_key(name):
    """A name in comparable form: no niqqud, quotes or dashes, final letters
    folded, single spaces. "ג׳ורג׳ בן-דוד " → "גורג בנ דוד"."""
    text = unicodedata.normalize("NFKC", str(name or ""))
    text = _NAME_DASHES.sub(" ", text)
    text = _NAME_MARKS.sub("", text)
    return " ".join(text.translate(_FINAL_LETTERS).lower().split())


def _cell_text(value, keep_lines=False):
    if value is None:
        return ""
    if isinstance(value, float) and value.is_integer():
        value = int(value)
    if isinstance(value, datetime):
        return value.strftime("%d/%m/%Y %H:%M")
    text = str(value).strip()
    if keep_lines:
        return "\n".join(" ".join(line.split()) for line in text.splitlines()).strip()
    return " ".join(text.split())


def _parse_when(value):
    if isinstance(value, datetime):
        return value.replace(microsecond=0)
    if isinstance(value, date):
        return datetime(value.year, value.month, value.day)
    text = _cell_text(value)
    for fmt in ("%d/%m/%Y %H:%M:%S", "%d/%m/%Y %H:%M", "%d/%m/%Y", "%d.%m.%Y %H:%M:%S",
                "%d.%m.%Y %H:%M", "%d.%m.%Y", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d"):
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            continue
    return None


def _upload_sheets(data):
    """Every sheet of an .xlsx or .csv upload, as lists of row values."""
    limit = INTERVIEW_SYNC_MAX_ROWS + 10
    if data[:4] == b"PK\x03\x04":  # .xlsx (a zip)
        try:
            workbook = openpyxl.load_workbook(BytesIO(data), read_only=True, data_only=True)
        except (zipfile.BadZipFile, KeyError, InvalidFileException):
            raise ValueError("הקובץ פגום או שאינו קובץ Excel. הורידו אותו שוב ונסו שנית")
        try:
            return [[list(row) for row, _ in zip(sheet.iter_rows(values_only=True), range(limit))]
                    for sheet in workbook.worksheets]
        finally:
            workbook.close()
    if data[:4] == b"\xd0\xcf\x11\xe0":  # legacy .xls
        raise ValueError("זהו קובץ Excel ישן (‎.xls). שמרו אותו כ-‎.xlsx ונסו שוב")
    for encoding in ("utf-8-sig", "cp1255"):
        try:
            text = data.decode(encoding)
            break
        except UnicodeDecodeError:
            continue
    else:
        raise ValueError("לא הצלחנו לקרוא את הקובץ. העלו את קובץ ה-Excel של טופס הראיונות")
    try:
        dialect = csv.Sniffer().sniff(text[:4096], delimiters=",;\t")
    except csv.Error:
        dialect = csv.excel
    reader = csv.reader(StringIO(text), dialect)
    return [[row for row, _ in zip(reader, range(limit))]]


def _interview_columns(header):
    """{field: column index} for a header row; must include "name"."""
    keys = [name_key(_cell_text(cell)) for cell in header]
    columns = {}
    for field, title in INTERVIEW_COLUMNS.items():
        wanted = name_key(title)
        for index, key in enumerate(keys):
            if key == wanted or key.startswith(wanted + " "):
                columns[field] = index
                break
    if "name" not in columns:
        # Another wording of the interviewee's name ("שם המרואיין"), never the
        # interviewer ("שם מראיין") or the ID column.
        for index, key in enumerate(keys):
            words = key.split()
            if "שמ" in words and any(w.endswith("מרואיינ") for w in words) and "זהות" not in words:
                columns["name"] = index
                break
    return columns


def parse_interview_file(data):
    """(rows, skipped) from an uploaded interview-form export. Picks the sheet
    whose header has "שם מלא מרואיין" and the most known columns. Raises
    ValueError with a message for the admin."""
    best = None
    for rows in _upload_sheets(data):
        for at, header in enumerate(rows[:10]):
            columns = _interview_columns(header)
            if "name" in columns:
                if best is None or len(columns) > len(best[0]):
                    best = (columns, rows[at + 1:])
                break
    if not best:
        raise ValueError('לא נמצאה בקובץ עמודה "שם מלא מרואיין". העלו את קובץ התגובות של טופס הראיונות')
    columns, rows = best

    def cell(row, field):
        index = columns.get(field)
        return row[index] if index is not None and index < len(row) else None

    parsed, skipped = [], 0
    for row in rows[:INTERVIEW_SYNC_MAX_ROWS]:
        if not any(_cell_text(value) for value in row):
            continue  # blank line
        name = _cell_text(cell(row, "name"))
        key = name_key(name)
        if not _HAS_LETTER.search(key):
            skipped += 1  # no name, or a number typed into the name column
            continue
        parsed.append({
            "name": name[:300],
            "name_key": key[:300],
            "interviewed_at": _parse_when(cell(row, "interviewed_at")),
            "interviewer": _cell_text(cell(row, "interviewer"))[:300] or None,
            "gibush": _cell_text(cell(row, "gibush"))[:300] or None,
            "rating": _cell_text(cell(row, "rating"))[:300] or None,
            "impression": _cell_text(cell(row, "impression"), keep_lines=True)[:4000] or None,
        })
    return parsed, skipped


def _interview_identity(name_key_value, interviewed_at, interviewer):
    """One form answer: the same person at the same time by the same
    interviewer. Re-uploading a newer export updates rows instead of
    duplicating them."""
    return name_key_value, interviewed_at, interviewer or ""


def prior_interview_matches(candidates):
    """{candidate id: match} for candidates whose name is in the synced
    interview form. The same words in any order is a match; one name's words
    all inside the other's (a middle name added or left out) is a possible
    match, shown as such. Placeholder names never match."""
    wanted = {}
    for candidate in candidates:
        if is_placeholder_name(candidate.name):
            continue
        words = name_key(candidate.name).split()
        if len(words) >= MIN_NAME_WORDS:
            wanted[candidate.id] = (candidate, frozenset(words), sorted(words))
    if not wanted:
        return {}
    index = db.session.query(PriorInterview.id, PriorInterview.name_key).all()
    if not index:
        return {}
    by_word, words_of = defaultdict(set), {}
    for interview_id, key in index:
        words = key.split()
        if len(words) < MIN_NAME_WORDS:
            continue
        words_of[interview_id] = (frozenset(words), sorted(words))
        for word in words:
            by_word[word].add(interview_id)

    hits = {}
    for candidate_id, (candidate, word_set, word_list) in wanted.items():
        exact, possible = [], []
        for interview_id in set().union(*(by_word.get(w, set()) for w in word_set)):
            other_set, other_list = words_of[interview_id]
            if other_list == word_list:
                exact.append(interview_id)
            elif word_set <= other_set or other_set <= word_set:
                possible.append(interview_id)
        if exact or possible:
            hits[candidate_id] = (bool(exact), exact or possible)
    if not hits:
        return {}

    ids = {i for _, interview_ids in hits.values() for i in interview_ids}
    interviews = {i.id: i for i in PriorInterview.query.filter(PriorInterview.id.in_(ids)).all()}
    matches = {}
    for candidate_id, (is_exact, interview_ids) in hits.items():
        found = sorted((interviews[i] for i in interview_ids if i in interviews),
                       key=lambda i: (i.interviewed_at or datetime.min, i.id), reverse=True)
        if not found:
            continue
        candidate = wanted[candidate_id][0]
        # Stable across re-syncs (ids change, the answers do not) so a phone
        # pops the alert again only for a match it has not seen.
        fingerprint = "|".join(sorted(f"{i.name_key}@{i.interviewed_at}" for i in found))
        matches[candidate_id] = {
            "candidate": candidate,
            "group_id": candidate.group_id,
            "number": candidate.number,
            "exact": is_exact,
            "interviews": found,
            "latest": found[0],
            "key": hashlib.sha1(f"{candidate_id}|{fingerprint}".encode("utf-8")).hexdigest()[:12],
        }
    return matches


def prior_interview_list(matches):
    return sorted(matches.values(), key=lambda m: (m["group_id"], m["number"]))


def prior_interview_text(match):
    """One line for the Excel export."""
    latest = match["latest"]
    parts = [latest.interviewed_at.strftime("%d/%m/%Y") if latest.interviewed_at else "רואיין"]
    if latest.interviewer:
        parts.append(f"מראיין: {latest.interviewer}")
    if latest.rating:
        parts.append(f"דירוג: {latest.rating}")
    if not match["exact"]:
        parts.append(f"שם דומה: {latest.name}")
    return " · ".join(parts)


def israel_now():
    return datetime.now(pytz.timezone('Israel')).replace(tzinfo=None, microsecond=0)


@app.route("/interviews/sync", methods=["POST"])
@admin_only
def interviews_sync():
    back = safe_next(url_for("admin_home"))
    upload = request.files.get("file")
    if not upload or not upload.filename:
        flash("בחרו את קובץ ה-Excel של טופס הראיונות", "error")
        return redirect(back)
    data = upload.read(INTERVIEW_SYNC_MAX_BYTES + 1)
    if len(data) > INTERVIEW_SYNC_MAX_BYTES:
        flash("הקובץ גדול מדי (עד 5MB)", "error")
        return redirect(back)
    try:
        rows, skipped = parse_interview_file(data)
    except ValueError as error:
        flash(str(error), "error")
        return redirect(back)
    except Exception:
        app.logger.exception("interview sync: unreadable file")
        flash("לא הצלחנו לקרוא את הקובץ. העלו את קובץ ה-Excel (‎.xlsx) של טופס הראיונות", "error")
        return redirect(back)
    if not rows:
        flash("לא נמצאו ראיונות בקובץ", "error")
        return redirect(back)

    existing = {_interview_identity(i.name_key, i.interviewed_at, i.interviewer): i
                for i in PriorInterview.query.all()}
    added = 0
    for row in rows:
        identity = _interview_identity(row["name_key"], row["interviewed_at"], row["interviewer"])
        interview = existing.get(identity)
        if interview is None:
            interview = existing[identity] = PriorInterview()
            db.session.add(interview)
            added += 1
        for field, value in row.items():
            setattr(interview, field, value)
    sync = InterviewSync.query.first() or InterviewSync()
    sync.filename = (upload.filename or "")[:300]
    sync.synced_at = israel_now()
    db.session.add(sync)
    db.session.commit()

    everyone = Candidate.query.filter(Candidate.group_id > 0).all()
    found = len(prior_interview_matches(c for c in everyone if c.status != "פרש"))
    summary = "סונכרן ראיון אחד" if len(rows) == 1 else f"סונכרנו {len(rows)} ראיונות"
    if added != len(rows):
        summary += " (אחד חדש)" if added == 1 else f" ({added} חדשים)"
    if skipped:
        summary += ". שורה אחת בלי שם דולגה" if skipped == 1 else f". {skipped} שורות בלי שם דולגו"
    if found:
        session["prior_interviews_open"] = True
        found_text = "מגובש אחד כבר רואיין" if found == 1 else f"{found} מגובשים כבר רואיינו"
        flash(f"{summary}. {found_text}", "warning")
    else:
        flash(f"{summary}. אף מגובש בגיבוש לא מופיע בקובץ", "success")
    return redirect(back)


@app.route("/interviews/clear", methods=["POST"])
@admin_only
def interviews_clear():
    PriorInterview.query.delete()
    InterviewSync.query.delete()
    db.session.commit()
    flash("רשימת הראיונות נמחקה", "success")
    return redirect(safe_next(url_for("admin_home")))


@app.route('/download-sheet/')
@admin_only
def downloadb():
    wb = Workbook()
    # candidates_query = db.query(Candidate)
    candidates = Candidate.query.all()
    df1 = pd.read_sql(db.session.query(Candidate).statement, db.session.bind)
    df1 = df1[(df1["status"] != "פרש") & (df1["group_id"] > 0)]
    # Rename by name and select explicitly, so adding columns to Candidate
    # (e.g. withdraw_reason) can't shift the mapping and 500 the export.
    export_columns = {"id": "מספר מגובש", "group_id": "מספר קבוצה", "name": "שם",
                      "final_status": "סטטוס סיכום", "final_note": "הערת סיכום",
                      "interviewer": "שם מראיין", "interview_grade": "ציון ראיון",
                      "interview_note": "סיכום ראיון", "tash_prob": "בעיות תש",
                      "medical_prob": "בעיות רפואיות",
                      "final_weighted_note": "הערות ציון סופי",
                      "final_rank": "דירוג בתוך הציון הסופי",
                      "final_weighted_grade": "ציון סופי משוקלל ראיון וגיבוש"}
    df1 = df1.rename(columns=export_columns)[list(export_columns.values())]
    df1["מתאם(קבוצת ליבה)"] = pd.Series()
    df1["מגבש"] = pd.Series()
    df1.index = df1['מספר מגובש']
    df1 = df1.drop(['מספר מגובש'], axis=1)
    df1.sort_index(inplace=True)
    candidates = df1.index.tolist()
    total_avgs = []
    tiz_avgs = []
    mitams = []
    for candidate in candidates:
        reviews = Review.query.filter_by(subject_id=candidate).all()
        sprint_avg = Review.query.filter_by(subject_id=candidate, station="ספרינטים סיכום").first()
        crawl_avg = Review.query.filter_by(subject_id=candidate, station="זחילות סיכום").first()
        if crawl_avg:
            crawl_avg = crawl_avg.grade
        if sprint_avg:
            sprint_avg = sprint_avg.grade
        if not sprint_avg and not crawl_avg:
            tiz_avgs.append(0)
        elif crawl_avg == 0 or not crawl_avg:
            tiz_avgs.append(round(sprint_avg, 2))
        elif sprint_avg == 0 or not sprint_avg:
            tiz_avgs.append(round(crawl_avg, 2))
        else:
            tiz_avgs.append(round((crawl_avg + sprint_avg) / 2, 2))
        reviews = Review.query.filter_by(subject_id=candidate).all()
        total_count = 0
        total_sum = 0
        for review in reviews:
            if review.station != "זחילות" and review.station != "ספרינטים" and (
                    "ODT" not in review.station or review.station == "ODT סיכום"):
                total_sum += review.grade
                total_count += 1
        if total_count == 0:
            total_avgs.append(0)
        else:
            total_avg = round(total_sum / total_count, 2)
            total_avgs.append(total_avg)
        mitams.append(User.query.get(candidate.split("/")[0]).mitam_num)
    tot = pd.Series(total_avgs, name="ממוצע כללי")
    tiz = pd.Series(tiz_avgs, name="ממוצע תיז")
    mitams = pd.Series(mitams, name="מתאם(קבוצת ליבה)")
    mitams.index = df1.index
    tot.index = df1.index
    tiz.index = df1.index
    final_review = pd.Series("", name="חוות דעת סופית")
    df1["ממוצע כללי"] = tot
    df1["ממוצע פיזי"] = tiz
    df1["מתאם(קבוצת ליבה)"] = mitams
    names = []
    df1["מגבש"] = pd.Series()
    df1["חוות דעת סופית"] = final_review
    exported = set(candidates)
    prior = prior_interview_matches(c for c in Candidate.query.filter(Candidate.group_id > 0).all() if c.id in exported)
    df1["ראיון קודם ביחידה"] = pd.Series({cid: prior_interview_text(m) for cid, m in prior.items()},
                                          index=df1.index, dtype=object).fillna("")
    # The weighted final grade must stay the LAST column in the sheet.
    for col in ["הערות ציון סופי", "דירוג בתוך הציון הסופי", "ציון סופי משוקלל ראיון וגיבוש"]:
        df1[col] = df1.pop(col)
    for value in df1.index:
        df1.loc[value,"מגבש"] = User.query.filter_by(id=int(df1.loc[value,"מספר קבוצה"])).first().name
    df2 = pd.DataFrame(columns=["שם","מספר בגיבוש", "מספר אישי", "שם מראיין", "מגבש", "ציון ממוצע בתחנות הגיבוש", 'חו"ד מראיין', 'חו"ד מגבש', "מצב עדכני במסלול(שליש)", "מתאם(קבוצת ליבה)"])
    df2.index = df2['מספר אישי']
    df2.drop(['מספר אישי'], axis=1, inplace=True)
    ws1 = wb.add_sheet('תוצאות גיבוש')
    ws2 = wb.add_sheet('מצב נוכחי')
    # Built in memory: a shared file on disk raced between concurrent exports.
    output = BytesIO()
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        df1.to_excel(writer, 'תוצאות גיבוש')
        df2.to_excel(writer, 'מצב נוכחי')
    output.seek(0)
    # file_stream = BytesIO()
    # file_stream.seek(0)
    return send_file(output, as_attachment=True, attachment_filename="data.xlsx", cache_timeout=5,
                     mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

@app.route('/get-station-reviews/<station>')
def get_station_reviews(station):
    existing = station_reviews_by_number(station, current_user.id)
    reviews = []
    for number in active_candidate_numbers(current_user.id):
        review = existing.get(number)
        reviews.append({
            'subject': number,
            'counter_value': (review.counter_value or 0) if review else 0,
            'note': (review.note or '') if review else '',
        })
    return jsonify({'reviews': reviews})

if __name__ == "__main__":
    app.run(host='0.0.0.0', port=3000)
