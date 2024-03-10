import os
from io import BytesIO
import logging
import flask
import pytz
import requests
import sqlalchemy
from flask import Flask, render_template, redirect, url_for, flash, abort, request, jsonify, send_from_directory, \
    send_file, after_this_request, request, session
from flask_bootstrap import Bootstrap
from flask_ckeditor import CKEditor
from datetime import date, datetime
from functools import wraps
from sqlalchemy import engine, distinct, func
from werkzeug.security import generate_password_hash, check_password_hash
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.orm import relationship
from flask_login import UserMixin, login_user, LoginManager, login_required, current_user, logout_user
from forms import LoginForm, RegisterForm, CreateReviewForm, EditUserForm, Search_review, EditReviewForm, \
    UpdateDateForm, NewCandidateForm, SelectPhysicalReviewsForm, ShowStaionForm, selectCandidate, AddFinalStatusForm, \
    SelectPhysicalReviewsFormAdmin, ShowStaionFormAdmin, selectCandidateAdmin, selectGroup, AddNameForm, InterviewForm, \
    GroupReviewForm, CreateNoteForm
from flask_gravatar import Gravatar
import sys
import logging
import pandas as pd
import xlwt
from xlwt.Workbook import *
from pandas import ExcelWriter
import xlsxwriter
import logging



app = Flask(__name__)
app.config['SECRET_KEY'] = "8BYkEfBA6O6donzWlSihBXox7C0sKR6b"
ckeditor = CKEditor(app)
Bootstrap(app)
gravatar = Gravatar(app, size=100, rating='g', default='retro', force_default=False, force_lower=False, use_ssl=False, base_url=None)
app.logger.addHandler(logging.StreamHandler(sys.stdout))
app.logger.setLevel(logging.ERROR)




##CONNECT TO DB
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get("DATABASE_URL", "sqlite:///data.db")
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)
login_manager = LoginManager()
login_manager.init_app(app)


app.logger.addHandler(logging.StreamHandler(sys.stdout))
app.logger.setLevel(logging.ERROR)

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))


##CONFIGURE TABLE


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
    final_note = db.Column(db.String(1000))
    status = db.Column(db.String(1000))
    interviewer = db.Column(db.String(1000))
    interview_grade = db.Column(db.String(1000))
    interview_note = db.Column(db.String(1000))
    tash_prob = db.Column(db.String(1000))
    medical_prob = db.Column(db.String(1000))
    reviews = relationship("Review", back_populates="subject")
    notes = relationship("Note", back_populates="subject")

class Review(db.Model):
    __tablename__ = "reviews"
    id = db.Column(db.Integer, primary_key=True)
    author_id = db.Column(db.Integer, db.ForeignKey("users.id"))
    author = relationship("User", back_populates="reviews")
    station = db.Column(db.String(1000), nullable=False)
    subject_id = db.Column(db.String(250), db.ForeignKey("candidates.id"))
    subject = relationship("Candidate", back_populates="reviews")
    grade = db.Column(db.Float, nullable=False)
    note = db.Column(db.String(1000))

class Note(db.Model):
    __tablename__ = "notes"
    id = db.Column(db.Integer, primary_key=True)
    author_id = db.Column(db.Integer, db.ForeignKey("users.id"))
    author = relationship("User", back_populates="notes")
    subject_id = db.Column(db.String(250), db.ForeignKey("candidates.id"))
    subject = relationship("Candidate", back_populates="notes")
    type = db.Column(db.String(1000), nullable=False)
    text = db.Column(db.String(1000))
    location = db.Column(db.String(1000))
    date = db.Column(db.String(1000))


db.create_all()


def admin_only(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if current_user.id != 0:
            return abort(403)
        return f(*args, **kwargs)
    return decorated_function

def get_groups():
    groups = User.query.all()
    groups = [group.id for group in groups if group.id != 0]
    groups.sort()
    return groups

@app.route('/admin-home', methods=["GET", "POST"])
@admin_only
def admin_home():
    if len(get_groups()) == 0:
        return redirect(url_for('register'))
    first_group = get_groups()[0]
    return redirect(url_for('homeAdmin', group_id= first_group))



@app.route('/<group_id>/', methods=["GET", "POST"])
@admin_only
def homeAdmin(group_id):
    form = selectGroup()
    form.group.choices = get_groups()
    form.group.default = group_id
    if form.validate_on_submit():
        return redirect(url_for('homeAdmin', group_id=form.group.data))
    candidates = Candidate.query.filter_by(group_id=group_id).all()
    tiz_avgs = []
    total_avgs = []
    if candidates:
        update_avgs_nf()
        for candidate in candidates:
            alonka = Review.query.filter_by(subject_id=candidate.id, station="אלונקה סוציומטרית סיכום").first()
            sprint_avg = Review.query.filter_by(subject_id=candidate.id, station="ספרינטים סיכום").first()
            crawl_avg = Review.query.filter_by(subject_id=candidate.id, station="זחילות סיכום").first()
            curr_avg = 0
            elements_num = 0
            if crawl_avg:
                curr_avg += crawl_avg.grade
                elements_num += 1
            if sprint_avg:
                curr_avg += sprint_avg.grade
                elements_num += 1
            if alonka:
                curr_avg += alonka.grade
                elements_num += 1
            if elements_num == 0:
                tiz_avgs.append(0)
            else:
                tiz_avg = round(curr_avg / elements_num, 2)
                tiz_avgs.append(tiz_avg)

            reviews = Review.query.filter_by(subject_id=candidate.id).all()
            total_count = 0
            total_sum = 0
            for review in reviews:
                if ("זחילות" not in review.station or review.station == "זחילות סיכום") and ("ספרינטים" not in review.station or review.station == "ספרינטים סיכום") and ("אלונקה סוציומטרית" not in review.station or review.station == "אלונקה סוציומטרית סיכום") and ("ODT" not in review.station or review.station == "ODT סיכום"):
                    total_sum += review.grade
                    total_count += 1
            if total_count == 0:
                total_avgs.append(0)
            else:
                total_avg = round(total_sum / total_count, 2)
                total_avgs.append(total_avg)
        zipped = zip(candidates, total_avgs, tiz_avgs)
        candidates = [x for _, x in sorted(zip(total_avgs, candidates), key=lambda pair: pair[0], reverse=True)]
        tiz_avgs = [x for _, x in sorted(zip(total_avgs, tiz_avgs), key=lambda pair: pair[0], reverse=True)]
        total_avgs.sort(reverse=True)
        return render_template("admin-home.html", group_id=group_id, candidates = enumerate(candidates), tiz_avg = tiz_avgs, total_avg = total_avgs, form = form)
    return render_template("admin-home.html", group_id=group_id, candidates = candidates, form=form)


@app.route('/')
def home():
    if not current_user.is_authenticated:
        return redirect(url_for("login"))
    if current_user.id == 0:
        return redirect(url_for("admin_home"))
    candidates = Candidate.query.filter_by(group_id=current_user.id).all()
    tiz_avgs = []
    total_avgs = []
    if candidates:
        update_avgs_nf()
        for candidate in candidates:
            alonka = Review.query.filter_by(subject_id=candidate.id, station="אלונקה סוציומטרית סיכום").first()
            sprint_avg = Review.query.filter_by(subject_id=candidate.id, station="ספרינטים סיכום").first()
            crawl_avg = Review.query.filter_by(subject_id=candidate.id, station="זחילות סיכום").first()
            curr_avg = 0
            elements_num = 0
            if crawl_avg:
                curr_avg += crawl_avg.grade
                elements_num += 1
            if sprint_avg:
                curr_avg += sprint_avg.grade
                elements_num += 1
            if alonka:
                curr_avg += alonka.grade
                elements_num += 1
            if elements_num == 0:
                tiz_avgs.append(0)
            else:
                tiz_avg = round(curr_avg / elements_num, 2)
                tiz_avgs.append(tiz_avg)
            reviews = Review.query.filter_by(subject_id=candidate.id).all()
            total_count = 0
            total_sum = 0
            for review in reviews:
                if ("זחילות" not in review.station or review.station == "זחילות סיכום") and ("ספרינטים" not in review.station or review.station == "ספרינטים סיכום") and ("אלונקה סוציומטרית" not in review.station or review.station == "אלונקה סוציומטרית סיכום") and ("ODT" not in review.station or review.station == "ODT סיכום"):
                    total_sum += review.grade
                    total_count += 1
            if total_count == 0:
                total_avgs.append(0)
            else:
                total_avg = round(total_sum / total_count, 2)
                total_avgs.append(total_avg)
        zipped = zip(candidates, total_avgs, tiz_avgs)
        candidates = [x for _, x in sorted(zip(total_avgs, candidates), key=lambda pair: pair[0], reverse=True)]
        tiz_avgs = [x for _, x in sorted(zip(total_avgs, tiz_avgs), key=lambda pair: pair[0], reverse=True)]
        total_avgs.sort(reverse=True)
        return render_template("home.html", current_user=current_user, candidates=enumerate(candidates), tiz_avg =tiz_avgs, total_avg =total_avgs)
    return render_template("home.html", current_user=current_user, candidates = candidates)


@app.route('/register', methods=["GET", "POST"])
def register():
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
        db.session.commit()
        # if current_user.id == 1:
        #     return redirect(url_for('manage'))
        # else:
        return redirect(url_for('register'))
    return render_template("register.html", form=form, current_user=current_user)


@app.route('/add-candidate', methods=["GET", "POST"])
def addCandidate():
    form = NewCandidateForm()
    if form.validate_on_submit():
        if Candidate.query.filter_by(id=str(current_user.id) + "/" + str(form.id.data), group_id=current_user.id).first():
            # print(User.query.filter_by(id=form.id.data).first())
            #User already exists
            flash("מגובש כבר קיים!")
            return render_template("add-candidate.html", current_user=current_user, form=form)

        # hash_and_salted_password = generate_password_hash(
        #     form.password.data,
        #     method='pbkdf2:sha256',
        #     salt_length=8
        # )
        new_candidate = Candidate(
            id=str(current_user.id) + "/" + str(form.id.data),
            name=form.name.data,
            group_id=current_user.id,
            group=current_user
        )
        db.session.add(new_candidate)
        db.session.commit()
        # if current_user.id == 1:
        #     return redirect(url_for('manage'))
        # else:
        return redirect(url_for('addCandidate'))
    return render_template("add-candidate.html", form=form, current_user=current_user)

@app.route('/login', methods=["GET", "POST"])
def login():
    form = LoginForm()
    if form.validate_on_submit():
        id = form.id.data
        password = form.password.data
        user = User.query.filter_by(id=id).first()
        # Email doesn't exist or password incorrect.
        if not user:
            flash("מספר קבוצה שגוי")
            return redirect(url_for('login'))
        elif not user.password == password:
            flash('סיסמה לא נכונה')
            return redirect(url_for('login'))
        else:
            login_user(user)
            return redirect(url_for('home'))
    return render_template("login.html", form=form, current_user=current_user)

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

stations = ["ספרינטים", "זחילות", "משימת מחשבה", "פירוק והרכבת נשק", "מסע", "שקים", "ODT", "מעגל זנבות", "אלונקה סוציומטרית", "הרצאות", "בניית שוח", "חפירת בור","חפירת בור מכשול קבוצתי","בניית ערימת חול", "נאסא", "אחר"]
def update_avgs_nf():
    physical_stations = getPhysicalStations()
    physical_stations = physical_stations + ["ספרינטים", "זחילות", "אלונקה סוציומטרית"]
    candidates = Candidate.query.filter_by(group_id=current_user.id).all()
    for candidate in candidates:
        for station in physical_stations:
            count = 0
            avg = 0
            reviews = Review.query.filter_by(subject_id=candidate.id).all()
            reviews = [review for review in reviews if
                       "סיכום" in review.station and f" {station} " in f" {review.station} " and "אקט" in review.station.split()]
            count = len(reviews)
            avg = sum([review.grade for review in reviews]) / count if count != 0 else 0
            review = Review.query.filter_by(station=station + " סיכום", subject_id=candidate.id).first()
            if review and count == 0:
                db.session.delete(review)
                db.session.commit()
            if count != 0 and not review:
                new_review = Review(station=station + " סיכום",
                                    subject_id=candidate.id,
                                    grade=avg, note="", author=current_user,
                                    subject=candidate)
                db.session.add(new_review)
                db.session.commit()
            if count != 0 and review:
                review.grade = avg
                db.session.commit()

        #
        # reviews = Review.query.filter_by(subject_id=candidate.id).all()
        # count = 0
        # avg = 0
        # reviews = Review.query.filter_by( subject_id=candidate.id).all()
        # reviews = [review for review in reviews if "סיכום" in review.station and "ספרינטים" in review.station and review.station != "ספרינטים סיכום"]
        # count = len(reviews)
        # avg = sum([review.grade for review in reviews]) / count if count != 0 else 0
        # review = Review.query.filter_by(station="ספרינטים סיכום", subject_id=candidate.id).first()
        # if review and count == 0:
        #     db.session.delete(review)
        #     db.session.commit()
        # if count != 0 and not review:
        #     new_review = Review(station="ספרינטים סיכום",
        #                         subject_id=candidate.id,
        #                         grade=avg, note="", author=current_user,
        #                         subject=candidate)
        #     db.session.add(new_review)
        #     db.session.commit()
        # if count != 0 and review:
        #     review.grade = avg
        #     db.session.commit()
        #
        # count = 0
        # avg = 0
        # reviews = Review.query.filter_by( subject_id=candidate.id).all()
        # reviews = [review for review in reviews if "סיכום" in review.station and "זחילות" in review.station and review.station != "זחילות סיכום"]
        # count = len(reviews)
        # avg = sum([review.grade for review in reviews]) / count if count != 0 else 0
        # review = Review.query.filter_by(station="זחילות סיכום", subject_id=candidate.id).first()
        # if review and count == 0:
        #     db.session.delete(review)
        #     db.session.commit()
        # if count != 0 and not review:
        #     new_review = Review(station="זחילות סיכום",
        #                         subject_id=candidate.id,
        #                         grade=avg, note="", author=current_user,
        #                         subject=candidate)
        #     db.session.add(new_review)
        #     db.session.commit()
        # if count != 0 and review:
        #     review.grade = avg
        #     db.session.commit()
        #
        # count = 0
        # avg = 0
        # reviews = Review.query.filter_by(subject_id=candidate.id).all()
        # reviews = [review for review in reviews if "סיכום" in review.station and "אלונקה סוציומטרית" in review.station and review.station != "אלונקה סוציומטרית סיכום"]
        # count = len(reviews)
        # avg = sum([review.grade for review in reviews]) / count if count != 0 else 0
        # review = Review.query.filter_by(station="אלונקה סוציומטרית סיכום", subject_id=candidate.id).first()
        # if review and count == 0:
        #     db.session.delete(review)
        #     db.session.commit()
        # if count != 0 and not review:
        #     new_review = Review(station="אלונקה סוציומטרית סיכום",
        #                         subject_id=candidate.id,
        #                         grade=avg, note="", author=current_user,
        #                         subject=candidate)
        #     db.session.add(new_review)
        #     db.session.commit()
        # if count != 0 and review:
        #     review.grade = avg
        #     db.session.commit()

        count = 0
        avg = 0
        reviews = Review.query.filter_by(subject_id=candidate.id).all()
        for review in reviews:
            review.grade = review.grade.__round__(2)
        reviews = [review for review in reviews if "ODT" in review.station and review.station != "ODT סיכום"]
        count = len(reviews)
        avg = sum([review.grade for review in reviews if "ODT" in review.station and review.station != "ODT סיכום"])
        review = Review.query.filter_by(station="ODT סיכום", subject_id=candidate.id).first()
        if review and count == 0:
            db.session.delete(review)
            db.session.commit()
        if count != 0 and not review:
            new_review = Review(station="ODT סיכום",
                                subject_id=candidate.id,
                                grade=0, note="", author=current_user,
                                subject=candidate)
            db.session.add(new_review)
            db.session.commit()
        if count != 0 and review:
            review.grade = avg/count
            db.session.commit()

def update_avgs(form):
    if form.station.data == "ספרינטים":
        if not Review.query.filter_by(station="ספרינטים סיכום", subject_id=str(current_user.id) + "/" + form.subject.data).first():
            new_review = Review(station="ספרינטים סיכום",
                                subject_id=str(current_user.id) + "/" + str(form.subject.data),
                                grade=form.grade.data, note=form.note.data, author=current_user,
                                subject=Candidate.query.filter_by(
                                id=str(current_user.id) + "/" + str(form.subject.data)).first())
            db.session.add(new_review)
            db.session.commit()
        else:
            count = len(Review.query.filter_by(station="ספרינטים", subject_id=str(current_user.id) + "/" + form.subject.data ).all())
            review = Review.query.filter_by(station="ספרינטים סיכום").first()
            review.grade = (review.grade * (count - 1) + int(form.grade.data)) / count
            db.session.commit()
    if form.station.data == "זחילות":
        if not Review.query.filter_by(station="זחילות סיכום", subject_id = str(current_user.id) + "/" + form.subject.data).first():
            new_review = Review(station="זחילות סיכום",
                                subject_id=str(current_user.id) + "/" + str(form.subject.data),
                                grade=form.grade.data, note=form.note.data, author=current_user,
                                subject=Candidate.query.filter_by(
                                    id=str(current_user.id) + "/" + str(form.subject.data)).first())
            db.session.add(new_review)
            db.session.commit()
        else:
            count = len(Review.query.filter_by(station="זחילות", subject_id=str(current_user.id) + "/" + form.subject.data).all())
            review = Review.query.filter_by(station="זחילות סיכום", subject_id = str(current_user.id) + "/" + form.subject.data).first()
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
    stations = ["ספרינטים", "זחילות", "אלונקה סוציומטרית"] + getPhysicalStationsGroup(int(group))
    stationsArray = []

    for station in stations:
        stationObj = {}
        stationObj['id'] = station

        stationsArray.append(stationObj)

    return jsonify({'stations': stationsArray})

@app.route('/stations/<group>')
def getStations(group):
    unique_stations = db.session.query(distinct(Review.station)).all()
    unique_station_values = [station[0] for station in unique_stations]
    stations = ["ספרינטים", "זחילות", "משימת מחשבה", "פירוק והרכבת נשק", "מסע", "שקים", "ODT", "מעגל זנבות",
                "אלונקה סוציומטרית", "הרצאות", "בניית שוח","חפירת בור","חפירת בור מכשול קבוצתי","בניית ערימת חול","נאסא"]
    unique_station_values = [station for station in unique_station_values if "אקט" not in station and "סיכום" not in station]
    final_stations = [station for station in unique_station_values if station not in stations]
    unique_station_values = stations + final_stations
    stations = unique_station_values + getPhysicalStationsGroup(int(group))
    stationsArray = []

    for station in stations:
        stationObj = {}
        stationObj['id'] = station

        stationsArray.append(stationObj)

    return jsonify({'stations': stationsArray})

@app.route("/new-review", methods=["GET", "POST"])
def add_new_review():
    stations = ["משימת מחשבה", "פירוק והרכבת נשק", "מסע", "שקים", "מעגל זנבות", "ODT", "הרצאות", "בניית שוח", "חפירת בור","חפירת בור מכשול קבוצתי","בניית ערימת חול" , "נאסא", "אחר"]
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
        form.odt.data = ""
        return render_template("make-post.html", form=form, current_user=current_user, selected_subject=form.station.data)
    return render_template("make-post.html", form=form, current_user=current_user, selected_subject=0)

@app.route("/new-group-review", methods=["GET", "POST"])
def add_new_group_review():
    form = GroupReviewForm()
    stations = ["משימת מחשבה", "פירוק והרכבת נשק", "מסע", "שקים", "מעגל זנבות","ODT", "הרצאות", "בניית שוח", "חפירת בור","חפירת בור מכשול קבוצתי","בניית ערימת חול" , "נאסא", "אחר"]
    form.station.choices = stations
    candidates = Candidate.query.filter_by(group_id=current_user.id).all()
    candidates = [int(candidate.id.split("/")[1]) for candidate in candidates if candidate.status != "פרש"]
    candidates.sort()
    return render_template('make-post-group.html', candidates=candidates, user_form=form, current_user=current_user)

@app.route('/add-review-candidate', methods=['POST'])
def addOneReview():
  form = GroupReviewForm()
  if form.validate_on_submit():
    if form.grade != 0:
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
    candidates = Candidate.query.filter_by(group_id=current_user.id).all()
    candidates = [int(candidate.id.split("/")[1]) for candidate in candidates if candidate.status != "פרש"]
    candidates.sort()
    counter = 0
    output = []
    result2 = request.form.to_dict(flat=False)
    station = result2['station'][0]
    if station == "ODT":
        station = station + " " + result2['odt'][0]
    if station == "אחר":
        station = result2['odt'][0]
    result2.pop('station')
    result2.pop("odt")
    datamap = [{key: value[i] for key, value in result2.items()} for i in range(len(result2['grade']))]
    for point in datamap:
        if int(point['grade']) != 0:
            new_review = Review(
                station=station,
                subject_id=str(current_user.id) + "/" + str(candidates[counter]),
                grade=int(point['grade']),
                note=point['note'],
                author=current_user,
                subject=Candidate.query.filter_by(id=str(current_user.id) + "/" + str(candidates[counter])).first()
            )
            db.session.add(new_review)
            db.session.commit()
        counter += 1
    update_avgs_nf()
    return redirect(url_for('add_new_group_review'))

@app.route('/group-manage', methods=["GET", "POST"])
def manageCandidates():
    candidates = Candidate.query.filter_by(group_id=current_user.id).all()
    candidates = [candidate for candidate in candidates if candidate.status != "פרש"]
    candidates.sort(key=lambda x: int(x.id.split("/")[1]))
    retired = Candidate.query.filter_by(group_id=current_user.id).all()
    retired = [candidate for candidate in retired if candidate.status == "פרש"]
    candidates.sort(key=lambda x: int(x.id.split("/")[1]))
    return render_template('panel.html', candidates=candidates, retired=retired, current_user=current_user)


@app.route('/admin-panel', methods=["GET", "POST"])
@admin_only
def manageGroups():
    groups = User.query.all()
    return render_template('admin-panel.html', groups=groups)


@app.route("/delete-candidate/<candidate_id>")
def delete_candidate(candidate_id):
    user_to_delete = Candidate.query.get(str(current_user.id) + "/" + candidate_id)
    db.session.delete(user_to_delete)
    db.session.commit()
    update_avgs_nf()
    return redirect(url_for('manageCandidates'))

@app.route("/return/<candidate_id>")
def return_candidate(candidate_id):
    user_to_return = Candidate.query.get(str(current_user.id) +"/" + candidate_id)
    user_to_return.status = ""
    db.session.commit()
    update_avgs_nf()
    return redirect(url_for('manageCandidates'))


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


@app.route("/delete/<int:user_id>")
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
    choices = ["ספרינטים", "זחילות", "אלונקה סוציומטרית"] + getPhysicalStations()
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
    choices = ["ספרינטים", "זחילות", "אלונקה סוציומטרית"] + getPhysicalStations()
    form.station.choices = choices
    if form.group.data:
        candidates = [candidate.id.split("/")[1] for candidate in Candidate.query.filter_by(group_id=int(form.group.data)).all() if candidate.status != "פרש"]
    else:
        candidates = [int(candidate.id.split("/")[1]) for candidate in Candidate.query.filter_by(group_id=1).all() if candidate.status != "פרש"]
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

@app.route("/candidates/", methods=["GET", "POST"])
def showCandidate():
    form = selectCandidate()
    update_avgs_nf()
    all_reviews = []
    candidates = Candidate.query.filter_by(group_id=current_user.id).all()
    candidate_nums = []
    clean_reviews = []
    for candidate in candidates:
        if candidate.status != "פרש":
            candidate_nums.append(int(candidate.id.split("/")[1]))
    candidate_nums.sort()
    candidate_nums.append("הכל")
    form.id.choices = candidate_nums
    if form.validate_on_submit():
        if form.id.data == "הכל":
            for candidate_num in candidate_nums[:-1]:
                candidate = Candidate.query.filter_by(id=str(current_user.id) + "/" + str(candidate_num)).first()

                reviews = Review.query.filter_by(subject_id=candidate.id).all()
                clean_reviews = [review for review in reviews if
                                 "אקט" not in review.station and review.station != "זחילות" and (
                                             "ODT" not in review.station or review.station == "ODT סיכום")]
                all_reviews.append(clean_reviews)
            if len(candidate_nums) == 1:
                return render_template('candidate.html', form=form)
            return render_template('candidate.html', reviews=clean_reviews, candidate_id=candidate.id.split("/")[1], form=form, all_reviews=all_reviews)
        candidate = Candidate.query.filter_by(id=str(current_user.id) + "/" + str(form.id.data)).first()
        reviews = Review.query.filter_by(subject_id=candidate.id).all()
        clean_reviews = [review for review in reviews if review.station != "ספרינטים" and review.station != "זחילות" and ("ODT" not in review.station or review.station == "ODT סיכום")]
        return render_template('candidate.html', reviews=clean_reviews, candidate_id=candidate.id.split("/")[1], form=form, all_reviews=all_reviews)
    return render_template('candidate.html', form=form)

@app.route("/candidates-admin/", methods=["GET", "POST"])
@admin_only
def showCandidateAdmin():
    form = selectCandidateAdmin()
    update_avgs_nf()
    form.group.choices = get_groups()
    clean_reviews = []
    candidates = []
    if form.group.data:
        candidates = [int(candidate.id.split("/")[1]) for candidate in Candidate.query.filter_by(group_id=int(form.group.data)).all() if candidate.status != "פרש"]
        candidates.sort()
        candidates.append("הכל")
        form.id.choices = candidates
    elif len(get_groups()) > 0:
        candidates = [int(candidate.id.split("/")[1]) for candidate in Candidate.query.filter_by(group_id=get_groups()[0]).all() if candidate.status != "פרש"]
        candidates.sort()
        candidates.append("הכל")
        form.id.choices = candidates
    if request.method == "POST":
        if form.id.data == "הכל":
            all_reviews = []
            for candidate_num in candidates[:-1]:
                candidate = Candidate.query.filter_by(id=str(form.group.data) + "/" + str(candidate_num)).first()
                reviews = Review.query.filter_by(subject_id=candidate.id).all()
                clean_reviews = [review for review in reviews if
                                 "אקט" not in review.station and review.station != "זחילות" and (
                                             "ODT" not in review.station or review.station == "ODT סיכום")]
                all_reviews.append(clean_reviews)
            if len(candidates) == 1 :
                return render_template('candidate-admin.html', form=form)
            return render_template('candidate-admin.html', reviews=clean_reviews, candidate_id=candidate.id.split("/")[1], form=form, all_reviews=all_reviews, group = form.group.data)
        candidate = Candidate.query.filter_by(id=str(form.group.data) + "/" + str(form.id.data)).first()
        if not candidate:
            return render_template('candidate-admin.html', form=form)
        reviews = Review.query.filter_by(subject_id=candidate.id).all()
        clean_reviews = [review for review in reviews if review.station != "ספרינטים" and review.station != "זחילות" and ("ODT" not in review.station or review.station == "ODT סיכום")]
        clean_reviews.sort(key=lambda x: x.grade, reverse=True)
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
    form.final_status.choices = ["לא לגעת - קו אדום", "בלית ברירה", "כן, אבל", "להתאבד"]
    if form.validate_on_submit():
        candidate = Candidate.query.filter_by(id=str(current_user.id) + "/" + str(form.id.data)).first()
        candidate.final_status = form.final_status.data
        candidate.final_note = form.final_note.data
        db.session.commit()
        return redirect(url_for('AddStatus'))
    return render_template('add-status.html', form=form)

@app.route("/interview/", methods=["GET", "POST"])
def Interview():
    form = InterviewForm()
    candidates = Candidate.query.filter_by(group_id=current_user.id).all()
    candidate_nums = []
    for candidate in candidates:
        if candidate.status != "פרש":
            candidate_nums.append(int(candidate.id.split("/")[1]))
    candidate_nums.sort()
    form.id.choices = candidate_nums
    form.grade.choices = ["לא לגעת - קו אדום", "בלית ברירה", "כן, אבל", "להתאבד"]
    if form.validate_on_submit():
        candidate = Candidate.query.filter_by(id=str(current_user.id) + "/" + str(form.id.data)).first()
        candidate.interviewer = form.interviewer.data
        candidate.interview_grade = form.grade.data
        candidate.interview_note = form.note.data
        candidate.tash_prob = form.tash.data
        candidate.medical_prob = form.medical.data
        db.session.commit()
        return redirect(url_for('Interview'))
    return render_template('interview.html', form=form)

@app.route("/show-interview/", methods=["GET", "POST"])
def showInterview():
    form = selectCandidate()
    candidates = Candidate.query.filter_by(group_id=current_user.id).all()
    candidate_nums = []
    for candidate in candidates:
        if candidate.status != "פרש":
            candidate_nums.append(int(candidate.id.split("/")[1]))
    candidate_nums.sort()
    form.id.choices = candidate_nums
    if form.validate_on_submit():
        candidate = Candidate.query.filter_by(id=str(current_user.id) + "/" + str(form.id.data)).first()
        return render_template('show-interview.html', form=form, candidate=candidate, candidate_id=candidate.id.split("/")[1])
    return render_template('show-interview.html', form=form)


@app.route("/show-interview-admin/", methods=["GET", "POST"])
@admin_only
def showInterviewAdmin():
    form = selectCandidateAdmin()
    form.group.choices = get_groups()
    if form.group.data:
        candidates = [candidate.id.split("/")[1] for candidate in Candidate.query.filter_by(group_id=int(form.group.data)).all() if candidate.status != "פרש"]
        candidates.sort()
        form.id.choices = candidates
    elif len(get_groups()) >0:
        candidates = [int(candidate.id.split("/")[1]) for candidate in Candidate.query.filter_by(group_id=get_groups()[0]).all() if candidate.status != "פרש"]
        candidates.sort()
        form.id.choices = candidates
    if form.validate_on_submit():
        candidate = Candidate.query.filter_by(id=str(form.group.data) + "/" + str(form.id.data)).first()
        return render_template('show-interview-admin.html', form=form, candidate=candidate, candidate_id=candidate.id.split("/")[1])
    return render_template('show-interview-admin.html', form=form)

@app.route("/station-reviews-admin/", methods=["GET", "POST"])
@admin_only
def showStationReviewsAdmin():
    form = ShowStaionFormAdmin()
    form.group.choices = get_groups()
    unique_stations = db.session.query(distinct(Review.station)).all()
    unique_station_values = [station[0] for station in unique_stations]
    stations = ["ספרינטים", "זחילות", "משימת מחשבה", "פירוק והרכבת נשק", "מסע", "שקים", "ODT", "מעגל זנבות",
                "אלונקה סוציומטרית", "הרצאות", "בניית שוח","חפירת בור","חפירת בור מכשול קבוצתי","בניית ערימת חול","נאסא"]
    unique_station_values = [station for station in unique_station_values if "אקט" not in station and "סיכום" not in station]
    final_stations = [station for station in unique_station_values if station not in stations]
    unique_station_values = stations + final_stations
    if form.group.data:
        form.station.choices = unique_station_values + getPhysicalStationsGroup(int(form.group.data))
    if len(form.group.choices) > 0:
        form.station.choices = unique_station_values + getPhysicalStationsGroup(int(form.group.choices[0]))
    # form.station.choices = unique_station_values
    if form.validate_on_submit():
        # form.station.choices = unique_station_values
        form.group.choices = get_groups()
        form.station.choices = unique_station_values + getPhysicalStationsGroup(int(form.group.data))
        reviews = Review.query.filter_by(author_id=form.group.data, station=form.station.data).all()
        reviews.sort(key=lambda x: x.grade)
        if form.station.data == "זחילות" or form.station.data == "ספרינטים" or form.station.data in getPhysicalStationsGroup(form.group.data) + ["אלונקה סוציומטרית"]:
            reviews = Review.query.filter_by(author_id=form.group.data, station=form.station.data + " סיכום").all()
            reviews.sort(key=lambda x: x.grade * -1)
        if "ODT" == form.station.data:
            reviews = Review.query.filter_by(author_id=form.group.data, station="ODT סיכום").all()
            reviews.sort(key=lambda x: x.grade * -1)
        return render_template('rankings-admin.html', reviews=reviews, form=form, stations=unique_station_values)
    return render_template('rankings-admin.html', form=form, stations=unique_station_values)

@app.route("/station-reviews/", methods=["GET", "POST"])
def showStationReviews():
    form = ShowStaionForm()
    update_avgs_nf()
    unique_stations = db.session.query(distinct(Review.station)).filter(Review.author_id == current_user.id).all()
    unique_station_values = [station[0] for station in unique_stations]
    stations = ["ספרינטים", "זחילות", "משימת מחשבה", "פירוק והרכבת נשק", "מסע", "שקים", "ODT", "מעגל זנבות",
                "אלונקה סוציומטרית", "הרצאות", "בניית שוח", "חפירת בור","חפירת בור מכשול קבוצתי","בניית ערימת חול","נאסא"] + getPhysicalStations()
    unique_station_values = [station for station in unique_station_values if "אקט" not in station and "סיכום" not in station]
    final_stations = [station for station in unique_station_values if station not in stations]
    unique_station_values = stations + final_stations
    form.station.choices = unique_station_values
    if form.validate_on_submit():
        reviews = Review.query.filter_by(author_id=current_user.id, station=form.station.data).all()
        reviews.sort(key=lambda x: x.grade)
        if(form.station.data == "זחילות" or form.station.data == "ספרינטים" or form.station.data in getPhysicalStations() +["אלונקה סוציומטרית"]):
            reviews = Review.query.filter_by(station=form.station.data + " סיכום").all()
            reviews = [review for review in reviews if str(review.author_id) == str(current_user.id)]
            reviews.sort(key=lambda x: x.grade * -1)
        if "ODT" == form.station.data:
            reviews = Review.query.filter_by(station="ODT סיכום").all()
            reviews = [review for review in reviews if str(review.author_id) == str(current_user.id)]
            reviews.sort(key=lambda x: x.grade * -1)
        return render_template('rankings.html', reviews=reviews, form=form)
    return render_template('rankings.html', form=form)

@app.route("/edit-review/<int:review_id>", methods=["GET", "POST"])
def edit_review(review_id):
    unique_stations = db.session.query(distinct(Review.station)).filter(Review.author_id == current_user.id).all()
    unique_station_values = [station[0] for station in unique_stations]
    stations = ["ספרינטים", "זחילות", "משימת מחשבה", "פירוק והרכבת נשק", "מסע", "שקים", "ODT", "מעגל זנבות",
                "אלונקה סוציומטרית", "הרצאות", "בניית שוח", "חפירת בור","חפירת בור מכשול קבוצתי","בניית ערימת חול","נאסא"]
    unique_station_values = [station for station in unique_station_values if "אקט" not in station and "סיכום" not in station]
    final_stations = [station for station in unique_station_values if station not in stations]
    unique_station_values = stations + final_stations
    review = Review.query.get(review_id)
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
        return redirect(url_for("showCandidate"))
    return render_template("make-post.html", form=form, current_user=current_user)



@app.route("/edit-physical-review/<int:review_id>", methods=["GET", "POST"])
def edit_physical_review(review_id):
    stations = ["ספרינטים", "זחילות", "ODT", "משימת מחשבה", "פירוק והרכבת נשק", "מסע", "שקים", "מעגל זנבות", "אלונקה סוציומטרית", "הרצאות", "בניית שוח", "חפירת בור","חפירת בור מכשול קבוצתי","בניית ערימת חול", "נאסא", "אחר"]
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
    stations = ["ספרינטים", "זחילות", "ODT", "משימת מחשבה", "פירוק והרכבת נשק", "מסע", "שקים", "מעגל זנבות", "אלונקה סוציומטרית", "הרצאות", "בניית שוח", "חפירת בור","חפירת בור מכשול קבוצתי","בניית ערימת חול", "נאסא", "אחר"]
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
    if form.validate_on_submit():
        review.station = form.station.data + " " + form.odt.data
        review.subject_id = str(current_user.id) + "/" + str(form.subject.data)
        review.grade = form.grade.data
        review.note = form.note.data
        db.session.commit()
        update_avgs(form)
        return redirect(url_for("showODTReviews"))
    return render_template("make-post.html", form=form, current_user=current_user)


@app.route("/delete-review/<int:review_id>")
def delete_review(review_id):
    review_to_delete = Review.query.get(review_id)
    db.session.delete(review_to_delete)
    db.session.commit()
    update_avgs_nf()
    return redirect(url_for("showCandidate"))

@app.route("/delete-physical-review/<int:review_id>")
def delete_physical_review(review_id):
    review_to_delete = Review.query.get(review_id)
    db.session.delete(review_to_delete)
    db.session.commit()
    update_avgs_nf()
    return redirect(url_for("showPhysicalReviews"))

@app.route("/delete-odt-review/<int:review_id>")
def delete_odt_review(review_id):
    review_to_delete = Review.query.get(review_id)
    db.session.delete(review_to_delete)
    db.session.commit()
    update_avgs_nf()
    return redirect(url_for("showODTReviews"))



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
    physical_stations = [station for station in physical_stations if "ספרינטים" not in station and "זחילות" not in station and "אלונקה סוציומטרית" not in station]
    physical_stations = [station.split(" סיכום")[0] for station in physical_stations]
    physical_stations = [station for station in physical_stations if station != '"' and station != " " and "סיכום" not in station.split()]
    physical_stations = list(set(physical_stations))
    physical_stations = physical_stations
    return physical_stations

def getPhysicalStationsGroup(group):
    reviews = Review.query.filter_by(author_id=group).filter(Review.station.like(f'%אקט%')).all()
    physical_stations = [review.station for review in reviews]
    physical_stations = [station.split(" - ")[0] for station in physical_stations if "אקט" in station]
    physical_stations = [station for station in physical_stations if "ספרינטים" not in station and "זחילות" not in station and "אלונקה סוציומטרית" not in station]
    physical_stations = [station.split(" סיכום")[0] for station in physical_stations]
    physical_stations = [station for station in physical_stations if station != '"' and station != " " and "סיכום" not in station.split()]
    physical_stations = list(set(physical_stations))
    physical_stations = physical_stations
    return physical_stations

def updateActAvgs():
    physical_stations = getPhysicalStations()
    physical_stations = physical_stations + ["ספרינטים", "זחילות", "אלונקה סוציומטרית"]
    for station in physical_stations:
        reviews = Review.query.filter_by(author_id=current_user.id).filter(Review.station.like(f'%{station}%')).all()
        reviews = [review for review in reviews if
                   "סיכום" in review.station.split() and "אקט" in review.station.split()]
        reviews = [review for review in reviews if getStationName(review) == station]
        if len(reviews) > 0:
            if len(reviews) > 0:
                acts = [int(review.station.split("אקט ")[1]) for review in reviews]
                act_num = max(acts, default=0) + 1
            else:
                act_num = 1
                # station = f"{station} - אקט {act_num}"
        else:
            act_num = 1
            # station = f"{station} - אקט {act_num}"
        for i in range(1, act_num + 1):
            act_sum = 0
            act_count = 0
            curr_station = f"{station} - אקט {i}"
            avg_station = f"סיכום {curr_station}"
            for candidate in Candidate.query.filter_by(group_id=current_user.id).all():
                act_count = 0
                act_sum = 0
                avg_review = Review.query.filter_by(station=avg_station, subject_id=candidate.id).first()
                for review in Review.query.filter_by(station=curr_station, subject_id=candidate.id).all():
                    act_sum += review.grade
                    act_count += 1
                if act_count != 0:
                    act_avg = act_sum / act_count
                    act_avg = round(act_avg, 2)
                    if avg_review is not None:
                        avg_review.grade = act_avg
                        db.session.commit()
                    else:
                        review = Review(author_id=current_user.id, station=avg_station, grade=act_avg, note="אקט",
                                        subject_id=candidate.id)
                        db.session.add(review)
                        db.session.commit()

        #
        # if station == "ספרינטים":
        #     for i in range(1, User.query.get(current_user.id).sprint_num + 1):
        #         act_sum = 0
        #         act_count = 0
        #         avg_station = f" סיכום ספרינטים - אקט {i}"
        #         station = f"ספרינטים - אקט {i}"
        #         for candidate in Candidate.query.filter_by(group_id=current_user.id).all():
        #             act_count = 0
        #             act_sum = 0
        #             avg_review = Review.query.filter_by(station=avg_station, subject_id=candidate.id).first()
        #             for review in Review.query.filter_by(station=station, subject_id= candidate.id).all():
        #                 act_sum += review.grade
        #                 act_count += 1
        #             if act_count != 0:
        #                 act_avg = act_sum / act_count
        #                 act_avg = round(act_avg, 2)
        #                 if avg_review is not None:
        #                     avg_review.grade = act_avg
        #                     db.session.commit()
        #                 else:
        #                     review = Review(author_id=current_user.id, station=avg_station, grade=act_avg, note="אקט", subject_id=candidate.id)
        #                     db.session.add(review)
        #                     db.session.commit()
        # elif station == "זחילות":
        #     for i in range(1, User.query.get(current_user.id).crawl_num + 1):
        #         act_sum = 0
        #         act_count = 0
        #         avg_station = f"סיכום זחילות - אקט {i}"
        #         station = f"זחילות - אקט {i}"
        #         for candidate in Candidate.query.filter_by(group_id=current_user.id).all():
        #             act_sum = 0
        #             act_count = 0
        #             avg_review = Review.query.filter_by(station=avg_station, subject_id=candidate.id).first()
        #             for review in Review.query.filter_by(station=station, subject_id=candidate.id).all():
        #                 act_sum += review.grade
        #                 act_count += 1
        #             if act_count != 0:
        #                 act_avg = act_sum / act_count
        #                 act_avg = round(act_avg, 2)
        #                 if avg_review is not None:
        #                     avg_review.grade = act_avg
        #                     db.session.commit()
        #                 else:
        #                     review = Review(author_id=current_user.id, station=avg_station, grade=act_avg, note="אקט",
        #                                      subject_id=candidate.id)
        #                     db.session.add(review)
        #                     db.session.commit()
        # else:
        #     for i in range(1, User.query.get(current_user.id).alonka_num + 1):
        #         act_sum = 0
        #         act_count = 0
        #         avg_station = f"סיכום אלונקה סוציומטרית - אקט {i}"
        #         station = f"אלונקה סוציומטרית - אקט {i}"
        #         for candidate in Candidate.query.filter_by(group_id=current_user.id).all():
        #             act_sum = 0
        #             act_count = 0
        #             avg_review = Review.query.filter_by(station=avg_station, subject_id=candidate.id).first()
        #             for review in Review.query.filter_by(station=station, subject_id=candidate.id).all():
        #                 act_sum += review.grade
        #                 act_count += 1
        #             if act_count != 0:
        #                 act_avg = act_sum / act_count
        #                 act_avg = round(act_avg, 2)
        #                 if avg_review is not None:
        #                     avg_review.grade = act_avg
        #                     db.session.commit()
        #                 else:
        #                     review = Review(author_id=current_user.id, station=avg_station, grade=act_avg, note="אקט",
        #                                  subject_id=candidate.id)
        #                     db.session.add(review)
        #                     db.session.commit()



@app.route('/circles', methods=['GET', 'POST'])
def circles():
    physical_stations = []
    if request.method == 'POST':
        circle_numbers = request.json['circle_numbers']
        # Process the circle numbers as desired
        print(circle_numbers)
        return redirect(url_for("circles"))
    # Prepare data for the circles
    candidates = Candidate.query.filter_by(group_id=current_user.id).all()
    reviews = Review.query.filter_by(author_id=current_user.id).filter(Review.station.like(f'%אקט%')).all()
    if len(reviews) > 0:
        physical_stations = getPhysicalStations()
    candidates = [candidate.id.split("/")[1] for candidate in candidates if candidate.status != "פרש"]
    circles = [{'id': i, 'clicked': False, 'finished': False} for i in candidates]
    return render_template('test.html', circles=circles, physical_stations = physical_stations)


@app.route('/circles/finished', methods=['POST'])
def circles_finished():
    circle_numbers = request.json['circle_numbers']
    station = request.json['movement_type']
    other_flag = False
    if station == "אחר":
        station = request.json['other']
        other_flag = True
    num_of_circles = len(circle_numbers) - 1
    counter = -1
    penalty = 4 / num_of_circles
    not_participated_idx = 0
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
    # if station == "ספרינטים":
    #     sprint_num = User.query.get(current_user.id).sprint_num
    #     station = f"ספרינטים - אקט {sprint_num}"
    # if station == "זחילות":
    #     crawl_num = User.query.get(current_user.id).crawl_num
    #     station = f"זחילות - אקט {crawl_num}"
    # if station == "אלונקה סוציומטרית":
    #     alonka_num = User.query.get(current_user.id).alonka_num
    #     station = f"אלונקה סוציומטרית - אקט {alonka_num}"
    for circle_number in circle_numbers:
        counter += 1
        if circle_number == 0:
            not_participated_idx = counter + 1
            break
        candidate = Candidate.query.get(str(current_user.id) + "/" + str(circle_number))
        review = Review(station=station, author=current_user, subject_id=str(current_user.id) + "/" + str(circle_number), grade=4 - counter * penalty, subject=Candidate.query.filter_by(id=str(current_user.id) + "/" + str(circle_number)).first())
        db.session.add(review)
        db.session.commit()
    for circle_number in circle_numbers[not_participated_idx:]:
        candidate = Candidate.query.get(str(current_user.id) + "/" + str(circle_number))
        review = Review(station=station, author=current_user, subject_id=str(current_user.id) + "/" + str(circle_number), grade= 1, subject=Candidate.query.filter_by(id=str(current_user.id) + "/" + str(circle_number)).first())
        db.session.add(review)
        db.session.commit()
    update_avgs_nf()
    # Process the finished circle numbers as desired
    physical_stations = getPhysicalStations()
    candidates = Candidate.query.filter_by(group_id=current_user.id).all()
    candidates = [candidate.id.split("/")[1] for candidate in candidates if candidate.status != "פרש"]
    circles = [{'id': i, 'clicked': False, 'finished': False} for i in candidates]
    return redirect(url_for('reset_circles', other_flag=other_flag, new_station=station))


@app.route('/circles/finished-act', methods=['POST'])
def circles_finished_act():
    circle_numbers = request.json['circle_numbers']
    station = request.json['movement_type']
    other_flag = False
    if station == "אחר":
        station = request.json['other']
        other_flag = True
    original_station = station
    num_of_circles = len(circle_numbers) - 1
    counter = -1
    penalty = 4 / num_of_circles
    not_participated_idx = 0
    reviews = Review.query.filter_by(author_id=current_user.id).filter(Review.station.like(f'%{station}%')).all()
    reviews = [review for review in reviews if "סיכום" in review.station.split() and "אקט" in review.station.split()]
    reviews = [review for review in reviews if getStationName(review) == station]
    if len(reviews) > 0:
        if len(reviews) > 0:
            acts = [int(review.station.split("אקט ")[1]) for review in reviews]
            act_num = max(acts, default=0) + 1
            station = f"{station} - אקט {act_num}"
        else:
            act_num = 1
            station = f"{station} - אקט {act_num}"
    else:
        act_num = 1
        station = f"{station} - אקט {act_num}"
    # if station == "ספרינטים":
    #     sprint_num = User.query.get(current_user.id).sprint_num
    #     station = f"ספרינטים - אקט {sprint_num}"
    # if station == "זחילות":
    #     crawl_num = User.query.get(current_user.id).crawl_num
    #     station = f"זחילות - אקט {crawl_num}"
    # if station == "אלונקה סוציומטרית":
    #     alonka_num = User.query.get(current_user.id).alonka_num
    #     station = f"אלונקה סוציומטרית - אקט {alonka_num}"
    for circle_number in circle_numbers:
        counter += 1
        if circle_number == 0:
            not_participated_idx = counter + 1
            break
        candidate = Candidate.query.get(str(current_user.id) + "/" + str(circle_number))
        review = Review(station=station, author=current_user, subject_id=str(current_user.id) + "/" + str(circle_number), grade=4 - counter * penalty, subject=Candidate.query.filter_by(id=str(current_user.id) + "/" + str(circle_number)).first())
        db.session.add(review)
        db.session.commit()
    for circle_number in circle_numbers[not_participated_idx:]:
        candidate = Candidate.query.get(str(current_user.id) + "/" + str(circle_number))
        review = Review(station=station, author=current_user, subject_id=str(current_user.id) + "/" + str(circle_number), grade= 1, subject=Candidate.query.filter_by(id=str(current_user.id) + "/" + str(circle_number)).first())
        db.session.add(review)
        db.session.commit()
    updateActAvgs()
    # if original_station == "ספרינטים":
    #     current_user.sprint_num += 1
    #     db.session.commit()
    # if original_station == "זחילות":
    #     current_user.crawl_num += 1
    #     db.session.commit()
    # if original_station == "אלונקה סוציומטרית":
    #     current_user.alonka_num += 1
    #     db.session.commit()

    # Process the finished circle numbers as desired
    candidates = Candidate.query.filter_by(group_id=current_user.id).all()
    candidates = [candidate.id.split("/")[1] for candidate in candidates if candidate.status != "פרש"]
    circles = [{'id': i, 'clicked': False, 'finished': False} for i in candidates]
    return redirect(url_for('reset_circles'))



@app.route('/circles/reset', methods=['GET'])
def reset_circles():
    candidates = Candidate.query.filter_by(group_id=current_user.id).all()
    physical_stations = []
    candidates = [candidate.id.split("/")[1] for candidate in candidates if candidate.status != "פרש"]
    circles = [{'id': i, 'clicked': False, 'finished': False} for i in candidates]
    reviews = Review.query.filter_by(author_id=current_user.id).filter(Review.station.like(f'%אקט%')).all()
    if len(reviews) > 0:
        physical_stations = getPhysicalStations()
    return render_template('test.html', circles=circles, physical_stations=physical_stations)

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
        form.text.data = ""
        return render_template("make-note.html", form=form, current_user=current_user)
    return render_template("make-note.html", form=form, current_user=current_user)

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
    candidate_nums.append("הכל")
    candidate = ""
    form.id.choices = candidate_nums
    if form.validate_on_submit():
        if form.id.data == "הכל":
            for candidate_num in candidate_nums[:-1]:
                candidate = Candidate.query.filter_by(id=str(current_user.id) + "/" + str(candidate_num)).first()
                notes = Note.query.filter_by(subject_id=candidate.id).all()
                all_notes.append(notes)
            if len(candidate_nums) == 1:
                return render_template('show-notes.html', form=form)
            return render_template('show-notes.html', notes=all_notes, candidate_id=candidate.id.split("/")[1], form=form, all_notes=all_notes, everyone=True)
        candidate = Candidate.query.filter_by(id=str(current_user.id) + "/" + str(form.id.data)).first()
        notes = Note.query.filter_by(subject_id=candidate.id).all()
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
        candidates.append("הכל")
        form.id.choices = candidates
    elif len(get_groups()) > 0:
        candidates = [int(candidate.id.split("/")[1]) for candidate in Candidate.query.filter_by(group_id=get_groups()[0]).all() if candidate.status != "פרש"]
        candidates.sort()
        candidates.append("הכל")
        form.id.choices = candidates
    if request.method == "POST":
        if form.id.data == "הכל":
            all_notes = []
            notes = []
            for candidate_num in candidates[:-1]:
                candidate = Candidate.query.filter_by(id=str(form.group.data) + "/" + str(candidate_num)).first()
                notes = Note.query.filter_by(subject_id=candidate.id).all()
                all_notes.append(notes)
            if len(candidates) == 1:
                return render_template('notes-admin.html', form=form)
            return render_template('notes-admin.html', notes=notes, candidate_id=candidate.id.split("/")[1], form=form, all_notes=all_notes, group=form.group.data)
        candidate = Candidate.query.filter_by(id=str(form.group.data) + "/" + str(form.id.data)).first()
        if not candidate:
            return render_template('notes-admin.html', form=form)
        notes = Note.query.filter_by(subject_id=candidate.id).all()
        return render_template('notes-admin.html', notes=notes, candidate_id=candidate.id.split("/")[1], form=form, group = form.group.data)
    return render_template('notes-admin.html', form=form)


@app.route('/download-sheet/')
@admin_only
def downloadb():
    wb = Workbook()
    # candidates_query = db.query(Candidate)
    candidates = Candidate.query.all()
    engine = sqlalchemy.create_engine(app.config['SQLALCHEMY_DATABASE_URI'])
    df1 = pd.read_sql(db.session.query(Candidate).statement, db.session.bind)
    df1 = df1[df1["status"] != "פרש"]
    df1.drop(['status'], axis=1, inplace=True)
    df1.columns = ["מספר מגובש", "מספר קבוצה", "שם", "סטטוס סיכום", "הערת סיכום", "שם מראיין", "ציון ראיון", "סיכום ראיון", "בעיות תש", "בעיות רפואיות"]
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
    for value in df1.index:
        df1.loc[value,"מגבש"] = User.query.filter_by(id=int(df1.loc[value,"מספר קבוצה"])).first().name
    df2 = pd.DataFrame(columns=["שם","מספר בגיבוש", "מספר אישי", "שם מראיין", "מגבש", "ציון ממוצע בתחנות הגיבוש", 'חו"ד מראיין', 'חו"ד מגבש', "מצב עדכני במסלול(שליש)", "מתאם(קבוצת ליבה)"])
    df2.index = df2['מספר אישי']
    df2.drop(['מספר אישי'], axis=1, inplace=True)
    ws1 = wb.add_sheet('תוצאות גיבוש')
    ws2 = wb.add_sheet('מצב נוכחי')
    writer = pd.ExcelWriter('multiple.xlsx', engine='xlsxwriter')
    df1.to_excel(writer, 'תוצאות גיבוש')
    df2.to_excel(writer, 'מצב נוכחי')
    writer.save()
    # file_stream = BytesIO()
    # file_stream.seek(0)
    return send_file("multiple.xlsx", as_attachment=True, attachment_filename="data.xlsx", cache_timeout=5, )


if __name__ == "__main__":
    app.run(host='0.0.0.0', port=5000)
