import os
from flask import Flask, render_template, redirect, url_for, flash, abort
from flask_bootstrap import Bootstrap
from flask_ckeditor import CKEditor
from datetime import date, datetime
from functools import wraps
from werkzeug.security import generate_password_hash, check_password_hash
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.orm import relationship
from flask_login import UserMixin, login_user, LoginManager, login_required, current_user, logout_user
from forms import LoginForm, RegisterForm, CreateReviewForm, EditUserForm, Search_review, EditReviewForm, \
    UpdateDateForm, NewCandidateForm, SelectPhysicalReviewsForm, ShowStaionForm, selectCandidate
from flask_gravatar import Gravatar
import sys
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

import logging

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
    candidates = relationship("Candidate", back_populates="group")

class Candidate(db.Model):
    __tablename__ = "candidates"
    id = db.Column(db.String(250), primary_key=True)
    group_id = db.Column(db.Integer, db.ForeignKey("users.id"))
    group = relationship("User", back_populates="candidates")
    name = db.Column(db.String(1000), nullable=False)
    final_status = db.Column(db.String(1000))
    reviews = relationship("Review", back_populates="subject")

class Review(db.Model):
    __tablename__ = "reviews"
    id = db.Column(db.Integer, primary_key=True)
    author_id = db.Column(db.Integer, db.ForeignKey("users.id"))
    author = relationship("User", back_populates="reviews")
    station = db.Column(db.String(1000), nullable=False)
    subject_id = db.Column(db.String(250), db.ForeignKey("candidates.id"))
    subject = relationship("Candidate", back_populates="reviews")
    grade = db.Column(db.Integer, nullable=False)
    note = db.Column(db.String(1000))


db.create_all()


def admin_only(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if current_user.id != 1:
            return abort(403)
        return f(*args, **kwargs)
    return decorated_function


@app.route('/')
def home():
    if not current_user.is_authenticated:
        return redirect(url_for("login"))
    candidates = Candidate.query.filter_by(group_id=current_user.id).all()
    tiz_avgs = []
    total_avg = []
    if candidates:
        for candidate in candidates:
            avg = 0
            count = 0
            tiz_avg = 0
            tiz_count = 0
            crawl_avg = 0
            crawl_count = 0
            sprint_avg = 0
            sprint_count = 0
            odt_avg = 0
            odt_count = 0
            for review in candidate.reviews:
                if review.station == "זחילות" or review.station == "ספרינטים" or review.station == "ODT":
                    if review.station == "זחילות":
                        crawl_count += 1
                        crawl_avg += review.grade
                    if review.station == "ספרינטים":
                        sprint_count += 1
                        sprint_avg += review.grade
                    tiz_avg += review.grade
                    tiz_count += 1
                    if review.station == "ODT":
                        odt_avg += review.grade
                        odt_count += 1
                else:
                    avg += review.grade
                    count += 1
            if tiz_count != 0:
                tiz_avg /= tiz_count
            if crawl_count != 0:
                crawl_avg /= crawl_count
            if sprint_count != 0:
                sprint_avg /= sprint_count
            if odt_count != 0:
                odt_avg /= odt_count
            avg += crawl_avg + sprint_avg + odt_avg
            count += 3
            avg = avg/count
            tiz_avgs.append(round(tiz_avg,2))
            total_avg.append(round(avg,2))
    if candidates:
        return render_template("home.html", current_user=current_user, candidates = enumerate(candidates), tiz_avg = tiz_avgs, total_avg = total_avg)
    return render_template("home.html", current_user=current_user, candidates = candidates, tiz_avg = tiz_avgs, total_avg = total_avg)


@app.route('/register', methods=["GET", "POST"])
def register():
    form = RegisterForm()
    if form.validate_on_submit():
        if User.query.filter_by(id=form.id.data).first():
            print(User.query.filter_by(id=form.id.data).first())
            #User already exists
            flash("משתמש כבר קיים!")
            return redirect(url_for('manage'))

        # hash_and_salted_password = generate_password_hash(
        #     form.password.data,
        #     method='pbkdf2:sha256',
        #     salt_length=8
        # )
        new_user = User(
            id=form.id.data,
            name=form.name.data,
            password=form.password.data,
        )
        db.session.add(new_user)
        db.session.commit()
        # if current_user.id == 1:
        #     return redirect(url_for('manage'))
        # else:
        return redirect(url_for('login'))
    return render_template("register.html", form=form, current_user=current_user)


@app.route('/add-candidate', methods=["GET", "POST"])
def addCandidate():
    form = NewCandidateForm()
    if form.validate_on_submit():
        if Candidate.query.filter_by(id=form.id.data, group_id=current_user.id).first():
            # print(User.query.filter_by(id=form.id.data).first())
            #User already exists
            flash("מגובש כבר קיים!")
            return redirect(url_for('addCandidate'))

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
    return render_template("register.html", form=form, current_user=current_user)

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


@app.route('/logout')
def logout():
    logout_user()
    return redirect(url_for('home'))

stations = ["ספרינטים", "זחילות", "משימת מחשבה", "פירוק והרכבת נשק", "מסע", "שקים", "ODT", "מעגל זנבות", "אלונקה סוציומטרית", "הרצאות", "בניית שוח", "חפירת בור"]

@app.route("/new-review", methods=["GET", "POST"])
def add_new_review():
    stations = ["ספרינטים", "זחילות", "משימת מחשבה", "פירוק והרכבת נשק", "מסע", "שקים", "ODT", "מעגל זנבות", "אלונקה סוציומטרית", "הרצאות", "בניית שוח", "חפירת בור"]
    form = CreateReviewForm()
    form.station.choices = stations
    candidates = Candidate.query.filter_by(group_id=current_user.id).all()
    candidate_nums = []
    for candidate in candidates:
        candidate_nums.append(candidate.id.split("/")[1])
    candidate_nums.sort()
    form.subject.choices = candidate_nums
    if form.validate_on_submit():
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
        if form.station.data == "ספרינטים":
            if not Review.query.filter_by(station = "ספרינטים סיכום").first():
                new_review = Review(station = "ספרינטים סיכום",  subject_id=str(current_user.id) + "/" + str(form.subject.data),grade=form.grade.data,  note=form.note.data,  author=current_user,   subject=Candidate.query.filter_by(id=str(current_user.id) + "/" + str(form.subject.data)).first())
                db.session.add(new_review)
                db.session.commit()
            else:
                count = len(Review.query.filter_by(station = "ספרינטים").all())
                review = Review.query.filter_by(station = "ספרינטים סיכום").first()
                review.grade = (int(form.grade.data) * (count-1) + int(form.grade.data)) / count
                db.session.commit()
        if form.station.data == "זחילות":
            if not Review.query.filter_by(station = "זחילות סיכום").first():
                new_review = Review(station = "זחילות סיכום",  subject_id=str(current_user.id) + "/" + str(form.subject.data),grade=form.grade.data,  note=form.note.data,  author=current_user,   subject=Candidate.query.filter_by(id=str(current_user.id) + "/" + str(form.subject.data)).first())
                db.session.add(new_review)
                db.session.commit()
            else:
                count = len(Review.query.filter_by(station = "זחילות").all())
                review = Review.query.filter_by(station = "זחילות סיכום").first()
                review.grade = (form.grade.data * (count-1) + form.grade.data) / count
                db.session.commit()
        if form.station.data == "ODT":
            if not Review.query.filter_by(station = "ODT סיכום").first():
                new_review = Review(station = "ODT סיכום",  subject_id=str(current_user.id) + "/" + str(form.subject.data),grade=form.grade.data,  note=form.note.data,  author=current_user,   subject=Candidate.query.filter_by(id=str(current_user.id) + "/" + str(form.subject.data)).first())
                db.session.add(new_review)
                db.session.commit()
            else:
                count = len(Review.query.filter_by(station = "ODT").all())
                review = Review.query.filter_by(station = "ODT סיכום").first()
                review.grade = (form.grade.data * (count-1) + form.grade.data) / count
                db.session.commit()
        return redirect(url_for("home"))
    return render_template("make-post.html", form=form, current_user=current_user)


@app.route('/panel')
@admin_only
def manage():
    users = User.query.all()
    return render_template('panel.html', users=users)

@app.route("/edit-user/<int:user_id>", methods=["GET", "POST"])
@admin_only
def edit_user(user_id):
    user = User.query.get(user_id)
    edit_form = EditUserForm(
        name=user.name,
        op_flight_time=user.op_flight_time,
        tr_flight_time=user.tr_flight_time,
        last_flight_date=user.last_flight_date,
        qualified=user.qualified,
        madrat=user.madrat,
        coach=user.coach,
        qualified_assist=user.qualified_assist,
        op_flight_time_goal = user.op_flight_time_goal,
        tr_flight_time_goal=user.tr_flight_time_goal,
        guide_flight_time = user.guide_flight_time,
        last_15_date = user.last_15_date,
        status = user.status,
        qualified_status=user.qualified_status,
    )
    if edit_form.validate_on_submit():
        user.name = edit_form.name.data
        user.op_flight_time = edit_form.op_flight_time.data
        user.tr_flight_time = edit_form.tr_flight_time.data
        user.last_flight_date = edit_form.last_flight_date.data
        user.qualified = edit_form.qualified.data
        user.madrat = edit_form.madrat.data
        user.coach = edit_form.coach.data
        user.qualified_assist = edit_form.qualified_assist.data
        user.op_flight_time_goal = edit_form.op_flight_time_goal.data
        user.tr_flight_time_goal = edit_form.tr_flight_time_goal.data
        user.guide_flight_time = edit_form.guide_flight_time.data
        user.last_15_date = edit_form.last_15_date.data
        db.session.commit()
        return redirect(url_for("manage"))
    return render_template("register.html", form=edit_form, is_edit=True, current_user=current_user)


@app.route("/delete/<int:user_id>")
@admin_only
def delete_post(user_id):
    user_to_delete = User.query.get(user_id)
    db.session.delete(user_to_delete)
    db.session.commit()
    return redirect(url_for('home'))

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
    form = SelectPhysicalReviewsForm()
    form.station.choices = ["ספרינטים", "גם וגם","זחילות"]
    candidates = Candidate.query.filter_by(group_id=current_user.id).all()
    candidate_nums = []
    for candidate in candidates:
        candidate_nums.append(candidate.id.split("/")[1])
    candidate_nums.sort()
    form.subject.choices = candidate_nums
    if form.validate_on_submit():
        form = SelectPhysicalReviewsForm()
        form.station.choices = ["ספרינטים", "גם וגם","זחילות"]
        candidates = Candidate.query.filter_by(group_id=current_user.id).all()
        candidate_nums = []
        for candidate in candidates:
            candidate_nums.append(candidate.id.split("/")[1])
        candidate_nums.sort()
        form.subject.choices = candidate_nums
        candidate = Candidate.query.filter_by(id=str(current_user.id) + "/" + str(form.subject.data)).first()
        if(form.station.data == "גם וגם"):
            reviews = Review.query.filter_by(subject_id=candidate.id, station="ספרינטים").all()
            reviews += Review.query.filter_by(subject_id=candidate.id, station="זחילות").all()
        else:
            reviews = Review.query.filter_by(subject_id=candidate.id, station = form.station.data).all()
        return render_template('physical-reviews.html', reviews=reviews, candidate_id=candidate.id.split("/")[1], form=form)
    return render_template('physical-reviews.html', form=form)

@app.route("/odt-reviews/", methods=["GET", "POST"])
def showODTReviews():
    form = selectCandidate()
    candidates = Candidate.query.filter_by(group_id=current_user.id).all()
    candidate_nums = []
    for candidate in candidates:
        candidate_nums.append(candidate.id.split("/")[1])
    candidate_nums.sort()
    form.id.choices = candidate_nums
    if form.validate_on_submit():
        form = selectCandidate()
        candidates = Candidate.query.filter_by(group_id=current_user.id).all()
        candidate_nums = []
        for candidate in candidates:
            candidate_nums.append(candidate.id.split("/")[1])
        candidate_nums.sort()
        form.id.choices = candidate_nums
        candidate = Candidate.query.filter_by(id=str(current_user.id) + "/" + str(form.id.data)).first()
        reviews = Review.query.filter_by(subject_id=candidate.id, station = "ODT").all()
        return render_template('ODT-sum.html', reviews=reviews, candidate_id=candidate.id.split("/")[1], form=form)
    return render_template('ODT-sum.html', form=form)

@app.route("/station-reviews/", methods=["GET", "POST"])
def showStationReviews():
    form = ShowStaionForm()
    form.station.choices = stations
    if form.validate_on_submit():
        form = ShowStaionForm()
        form.station.choices = stations
        reviews = Review.query.filter_by(author_id=current_user.id, station=form.station.data).all()
        reviews.sort(key=lambda x: x.grade)
        if(form.station.data == "זחילות" or form.station.data == "ספרינטים" or form.station.data == "ODT"):
            reviews = Review.query.filter_by(author_id=current_user.id, station=form.station.data + " סיכום").all()
            reviews.sort(key=lambda x: x.grade)
        return render_template('rankings.html', reviews=reviews, form=form)
    return render_template('rankings.html', form=form)

@app.route("/edit-review/<int:review_id>", methods=["GET", "POST"])
@admin_only
def edit_review(review_id):
    review = Review.query.get(review_id)
    id = User.query.filter_by(name=review.subject).first().id
    edit_form = EditReviewForm(
        keep_pts=review.keep_pts,
        improve_pts=review.improve_pts,
        op_level=review.op_level,
        co_op_level=review.co_op_level
    )
    if edit_form.validate_on_submit():
        review.keep_pts = edit_form.keep_pts.data
        review.improve_pts = edit_form.improve_pts.data
        review.op_level = edit_form.op_level.data
        review.co_op_level = edit_form.co_op_level.data
        db.session.commit()
        return redirect(url_for("search_reviews"))
    return render_template("make-post.html", form=edit_form, is_edit=True, current_user=current_user)


@app.route("/delete-review/<int:review_id>")
@admin_only
def delete_review(review_id):
    review_to_delete = Review.query.get(review_id)
    id = User.query.filter_by(name=review_to_delete.subject).first().id
    db.session.delete(review_to_delete)
    db.session.commit()
    return redirect(url_for("search_reviews"))


@app.route("/update-date", methods=["GET", "POST"])
def update_date():
    form = UpdateDateForm(last_15_date=current_user.last_15_date)
    if form.validate_on_submit():
        last_15 = form.last_15_date.data
        current_user.last_15_date = last_15
        db.session.commit()
        return render_template("index.html", current_user=current_user)
    return render_template("update-date.html", form=form, current_user=current_user)


if __name__ == "__main__":
    app.run(host='0.0.0.0', port=5000)
