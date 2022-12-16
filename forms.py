from datetime import date
from flask_wtf import FlaskForm
from wtforms import StringField, SubmitField, PasswordField, SelectField, IntegerField, BooleanField, FloatField, TextAreaField
from wtforms.validators import DataRequired, URL, NumberRange, InputRequired
from wtforms.fields.html5 import DateField


class CreateReviewForm(FlaskForm):
    station = SelectField("תחנה", validators=[DataRequired()])
    subject = SelectField("מספר מגובש", validators=[DataRequired()])
    grade = SelectField("ציון", choices=[1, 2, 3, 4], validators=[DataRequired()])
    note = TextAreaField("הערות")
    submit = SubmitField("הוסף תוצאה")


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
    name = StringField("שם", validators=[DataRequired("זהו סעיף חובה")])
    password = PasswordField("סיסמה", validators=[DataRequired("זהו סעיף חובה")])
    submit = SubmitField("הוסף מגבש")

class NewCandidateForm(FlaskForm):
    id = IntegerField("מספר מגובש", validators=[DataRequired("זהו סעיף חובה")])
    name = StringField("שם", validators=[DataRequired("זהו סעיף חובה")])
    submit = SubmitField("הוסף מגובש")

class AddFinalStatusForm(FlaskForm):
    id = SelectField("מספר מגובש", validators=[DataRequired("זהו סעיף חובה")])
    final_status = SelectField("סטטוס סיכום", validators=[DataRequired("זהו סעיף חובה")])
    final_note = StringField("הערת סיכום", validators=[DataRequired("זהו סעיף חובה")])
    submit = SubmitField("הזן סיכום")

class EditUserForm(FlaskForm):
    name = StringField("שם מלא", validators=[DataRequired("זהו סעיף חובה")])
    status = StringField("סטטוס", validators=[DataRequired("זהו סעיף חובה")])
    qualified = StringField("כשירות", validators=[DataRequired("זהו סעיף חובה")])
    qualified_status = StringField("סטטוס הסמכה", validators=[DataRequired("זהו סעיף חובה")])
    op_flight_time = FloatField("שעות טיסה מבצעיות", validators=[InputRequired("זהו סעיף חובה"), NumberRange(min=-1, max=100000)])
    op_flight_time_goal = FloatField("יעד שעות טיסה מבצעיות", validators=[InputRequired("זהו סעיף חובה"), NumberRange(min=-1, max=100000)])
    tr_flight_time = FloatField("שעות טיסת אימון", validators=[InputRequired("זהו סעיף חובה"), NumberRange(min=-1, max=100000)])
    tr_flight_time_goal = FloatField("יעד שעות טיסת אימון", validators=[InputRequired("זהו סעיף חובה"), NumberRange(min=-1, max=100000)])
    guide_flight_time = FloatField("שעות טיסת הדרכה", validators=[InputRequired("זהו סעיף חובה"), NumberRange(min=-1, max=100000)])
    last_15_date = DateField("כוננות 15' אחרונה ",render_kw={'max':date.today()}, validators=[DataRequired("זהו סעיף חובה")])
    last_flight_date = DateField("תאריך טיסה אחרונה ",render_kw={'max':date.today()}, validators=[DataRequired("זהו סעיף חובה")])
    coach = BooleanField( "ביצע מאמן" ,render_kw={'style':'margin:10px'})
    qualified_assist = BooleanField("כשירות סיוע",render_kw={'style':'margin:10px'})
    madrat = BooleanField('מדר"ט',render_kw={'style':'margin:10px'})
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