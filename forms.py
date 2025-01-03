from datetime import date
from flask_wtf import FlaskForm
from wtforms import StringField, SubmitField, PasswordField, SelectField, IntegerField, BooleanField, FloatField, TextAreaField
from wtforms.fields import RadioField
from wtforms.validators import DataRequired, URL, NumberRange, InputRequired
from wtforms.fields.html5 import DateField


class CreateReviewForm(FlaskForm):
    station = SelectField("תחנה", validators=[DataRequired()])
    odt = StringField("שם ODT:")
    subject = SelectField("מספר מגובש", validators=[DataRequired()])
    grade = SelectField("ציון", choices=[(1, '1'), (2, '2'), (3, '3'), (4, '4')], validators=[DataRequired()])
    note = TextAreaField("הערות")
    submit = SubmitField("הוסף תוצאה")

class CreateNoteForm(FlaskForm):
    subject = SelectField("מספר מגובש", validators=[DataRequired()])
    type = RadioField("סוג הערה", choices=[('טובה', 'טובה'), ('רעה', 'רעה')], validators=[DataRequired()])
    text = TextAreaField("הערה")
    location = StringField("מיקום")
    submit = SubmitField("הוסף הערה")


class CounterReviewForm(FlaskForm):
    station = SelectField("תחנה", validators=[DataRequired()])
    subject = SelectField("מספר מגובש", validators=[DataRequired()])
    counter = IntegerField("כמות", validators=[DataRequired()], default=0)
    note = TextAreaField("הערה")
    submit = SubmitField("הצג תוצאה")


class SelectPhysicalReviewsForm(FlaskForm):
    station = SelectField("תחנה", validators=[DataRequired()])
    subject = SelectField("מספר מגובש", validators=[DataRequired()])
    submit = SubmitField("הצג תוצאה")

class SelectPhysicalReviewsFormAdmin(FlaskForm):
    group = SelectField("קבוצה", validators=[DataRequired()])
    station = SelectField("תחנה", validators=[DataRequired()])
    subject = SelectField("מספר מגובש", validators=[DataRequired()])
    submit = SubmitField("הצג תוצאה")



class ShowStaionForm(FlaskForm):
    station = SelectField("תחנה", validators=[DataRequired()])
    submit = SubmitField("הצג תוצאה")

class ShowStaionFormAdmin(FlaskForm):
    group = SelectField("קבוצה", validators=[DataRequired()])
    station = SelectField("תחנה", validators=[DataRequired()])
    submit = SubmitField("הצג תוצאה")

class EditReviewForm(FlaskForm):
    keep_pts = StringField("נקודות לשימור", validators=[DataRequired()])
    improve_pts = StringField("נקודות לשיפור", validators=[DataRequired()])
    op_level = SelectField("רמת הפעלה", choices=[(4, '4'), (5, '5'),(6, '6'),(7, '7'),(8, '8'),(9, '9'),(10, '10')], validators=[DataRequired()])
    co_op_level = SelectField("עבודת צוות", choices=[(4, '4'), (5, '5'),(6, '6'),(7, '7'),(8, '8'),(9, '9'),(10, '10')], validators=[DataRequired()])
    last_flight_date = DateField("תאריך טיסה ",render_kw={'max':date.today()}, validators=[DataRequired("זהו סעיף חובה")])
    flight_type = SelectField("סוג טיסה", choices=[("op", 'מבצעית'), ("tr", 'אימון'),("gu", 'הדרכה')], validators=[DataRequired()])
    flight_time = SelectField("שעות טיסה", choices=[(0, '0'),(0.5, '0.5'), (1, '1'), (1.5, '1.5'),(2, '2'),(2.5, '2.5'),(3, '3'),(3.5, '3.5'),(4, '4'),(4.5, '4.5'),(5, '5'),(5.5, '5.5'),(6, '6'),(6.5, '6.5'), (7,'7'), (7.5,'7.5'),(8,'8'), (8.5,'8.5'),(9,'9'),(9.5,'9.5'),(10,'10'),(10.5,'10.5'), (11,'11'), (11.5,'11.5'), (12, '12')], validators=[DataRequired()])
    submit = SubmitField("סיים טיסה")

class RegisterForm(FlaskForm):
    id = IntegerField("מספר קבוצה", validators=[InputRequired("זהו סעיף חובה")])
    name = StringField("שם")
    mitam = IntegerField("מספר מתאם(קבוצת ליבה)", validators=[InputRequired("זהו סעיף חובה")])
    password = PasswordField("סיסמה", validators=[DataRequired("זהו סעיף חובה")])
    submit = SubmitField("הוסף מגבש")

class AddNameForm(FlaskForm):
    name = StringField("שם", validators=[DataRequired("זהו סעיף חובה")])
    submit = SubmitField("הוסף שם")

class NewCandidateForm(FlaskForm):
    id = IntegerField("מספר מגובש", validators=[DataRequired("זהו סעיף חובה")])
    name = StringField("שם", validators=[DataRequired("זהו סעיף חובה")])
    submit = SubmitField("הוסף מגובש")

class InterviewForm(FlaskForm):
    id = SelectField("מספר מגובש", validators=[DataRequired("זהו סעיף חובה")])
    interviewer = StringField("שם מראיין", validators=[DataRequired("זהו סעיף חובה")])
    grade = SelectField("ציון ראיון", validators=[DataRequired("זהו סעיף חובה")])
    note = TextAreaField("סיכום ראיון", validators=[DataRequired("זהו סעיף חובה")])
    tash = TextAreaField('בעיות ת"ש', default="אין")
    medical = TextAreaField("בעיות רפואיות", default="אין")
    submit = SubmitField("הוסף מגובש")

class AddFinalStatusForm(FlaskForm):
    id = SelectField("מספר מגובש", validators=[DataRequired("זהו סעיף חובה")])
    final_status = SelectField("סטטוס סיכום", validators=[DataRequired("זהו סעיף חובה")])
    final_note = StringField("הערת סיכום", validators=[DataRequired("זהו סעיף חובה")])
    submit = SubmitField("הזן סיכום")

class EditUserForm(FlaskForm):
    name = StringField("שם", validators=[DataRequired("זהו סעיף חובה")])
    submit = SubmitField("השלם עריכה")


class LoginForm(FlaskForm):
    id = StringField("מספר קבוצה", validators=[DataRequired()])
    password = PasswordField("סיסמה", validators=[DataRequired()])
    submit = SubmitField("התחבר")

class Search_review(FlaskForm):
    name = StringField("הקלד את שם המשתמש עליו תרצה לקרוא חוות דעת (השאר ריק כדי לראות את כל חוות הדעת)")
    submit = SubmitField("חפש")


class selectCandidate(FlaskForm):
    id = SelectField("בחר מגובש", validators=[DataRequired()])
    submit = SubmitField("הצג")

class GroupReviewForm(FlaskForm):
    subject = StringField("בחר מגובש", validators=[DataRequired()])
    station = SelectField("בחר תחנה", validators=[DataRequired()])
    odt = StringField("שם ODT:")
    grade = SelectField(choices=[0,1,2,3,4])
    note = StringField('הערה')
    submit = SubmitField('הזן')

class selectCandidateAdmin(FlaskForm):
    group = SelectField("בחר קבוצה", validators=[DataRequired()])
    id = SelectField("בחר מגובש", validators=[DataRequired()])
    submit = SubmitField("הצג")

class selectGroup(FlaskForm):
    group = SelectField("בחר קבוצה", validators=[DataRequired()])
    submit = SubmitField("הצג")

class selectCandidateAdmin(FlaskForm):
    group = SelectField("בחר קבוצה")
    id = SelectField("מגובש")
    submit = SubmitField("הצג")

class UpdateDateForm (FlaskForm):
    last_15_date = DateField("כוננות 15' אחרונה",render_kw={'max':date.today()}, validators=[DataRequired("זהו סעיף חובה")])
    submit = SubmitField("עדכן")