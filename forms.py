from datetime import date
from flask import g, request
from flask_wtf import FlaskForm
from wtforms import StringField, SubmitField, PasswordField, SelectField, IntegerField, BooleanField, FloatField, TextAreaField, HiddenField
from wtforms.fields import RadioField
from wtforms.validators import DataRequired, URL, NumberRange, InputRequired, Optional, Length, StopValidation
from wtforms.fields.html5 import DateField

REQUIRED = "זהו סעיף חובה"
CSRF_EXPIRED = "פג תוקף הטופס — רענן את הדף ונסה שוב"
CANDIDATE_GONE = "המגובש כבר לא פעיל (פרש או הוסר) — בחר מגובש אחר"


def mark_form_errors(messages):
    """Remember why this POST was refused. main.py sends it back in the
    X-Form-Errors header, so the phone's outbox can tell a refusal from a
    save even when the page is a plain 200 re-render."""
    g.setdefault("form_errors", []).extend(messages)


def form_error_messages(form):
    """One "label: message" line per invalid field, last message first-class
    (a missing choice also fails "Not a valid choice" — the required message
    is the useful one and always comes last)."""
    lines = []
    for field in form:
        if not field.errors:
            continue
        if field.name == "csrf_token":
            lines.append(CSRF_EXPIRED)
        else:
            lines.append(f"{field.label.text}: {field.errors[-1]}")
    return lines


class AppForm(FlaskForm):
    """Base for every form: Hebrew validator messages, and a refused POST is
    recorded for the X-Form-Errors header (see main.flag_refused_forms)."""

    class Meta:
        locales = ("he",)

    def validate(self, *args, **kwargs):
        ok = super().validate(*args, **kwargs)
        if not ok:
            # "Not a valid choice" on a candidate picker almost always means
            # the candidate retired (or was removed) after the page loaded —
            # e.g. a grade replayed from the offline outbox. Say so.
            for name in ("subject", "id"):
                field = self._fields.get(name)
                if field is not None and field.data not in (None, "") and field.errors:
                    gone = field.gettext("Not a valid choice")
                    field.errors[:] = [CANDIDATE_GONE if e == gone else e for e in field.errors]
            if request.method == "POST":
                mark_form_errors(form_error_messages(self))
        return ok


class RequiredWhen:
    """Required only while another field holds one of `values` — the custom
    station name is needed only when the station is "אחר" (or ODT)."""

    def __init__(self, other, values, message=REQUIRED):
        self.other = other
        self.values = tuple(values)
        self.message = message

    def __call__(self, form, field):
        if form[self.other].data in self.values:
            if not (field.data or "").strip():
                raise StopValidation(self.message)
        else:
            raise StopValidation()  # not needed: skip the rest of the chain


class CreateReviewForm(AppForm):
    station = SelectField("תחנה", validators=[DataRequired("בחר תחנה")])
    odt = StringField("שם תחנה", validators=[RequiredWhen("station", ("ODT", "אחר"), "כתוב את שם התחנה"),
                                             Length(max=100, message="שם התחנה ארוך מדי")])
    subject = SelectField("מספר מגובש", validators=[DataRequired("בחר מגובש")])
    # No default: a grade nobody tapped must not be saved as 1.
    grade = SelectField("ציון", choices=[(1, '1'), (2, '2'), (3, '3'), (4, '4')], validators=[DataRequired("בחר ציון")])
    note = TextAreaField("הערות")
    submit = SubmitField("הוסף תוצאה")

class CreateNoteForm(AppForm):
    # Same fields, order and rules as the quick-note sheet (/notes/quick).
    subject = SelectField("מגובש", validators=[DataRequired("בחר מגובש")])
    type = RadioField("סוג הערה", choices=[('טובה', 'טובה'),('ניטרלית', 'ניטרלית'), ('רעה', 'רעה')], validators=[DataRequired("בחר סוג הערה")])
    text = TextAreaField("הערה", validators=[DataRequired("כתוב את ההערה"), Length(max=4000, message="ההערה ארוכה מדי")])
    location = StringField("מיקום / תחנה", validators=[Optional(), Length(max=200, message="המיקום ארוך מדי")])
    submit = SubmitField("שמור הערה")


class CounterReviewForm(AppForm):
    station = SelectField("תחנה", validators=[DataRequired()])
    subject = SelectField("מספר מגובש", validators=[DataRequired()])
    counter = IntegerField("כמות", validators=[DataRequired()], default=0)
    note = TextAreaField("הערה")
    submit = SubmitField("הצג תוצאה")


class SelectPhysicalReviewsForm(AppForm):
    station = SelectField("תחנה", validators=[DataRequired()])
    subject = SelectField("מספר מגובש", validators=[DataRequired()])
    submit = SubmitField("הצג תוצאה")

class SelectPhysicalReviewsFormAdmin(AppForm):
    group = SelectField("קבוצה", validators=[DataRequired()])
    station = SelectField("תחנה", validators=[DataRequired()])
    subject = SelectField("מספר מגובש", validators=[DataRequired()])
    submit = SubmitField("הצג תוצאה")



class EditReviewForm(AppForm):
    keep_pts = StringField("נקודות לשימור", validators=[DataRequired()])
    improve_pts = StringField("נקודות לשיפור", validators=[DataRequired()])
    op_level = SelectField("רמת הפעלה", choices=[(4, '4'), (5, '5'),(6, '6'),(7, '7'),(8, '8'),(9, '9'),(10, '10')], validators=[DataRequired()])
    co_op_level = SelectField("עבודת צוות", choices=[(4, '4'), (5, '5'),(6, '6'),(7, '7'),(8, '8'),(9, '9'),(10, '10')], validators=[DataRequired()])
    last_flight_date = DateField("תאריך טיסה ",render_kw={'max':date.today()}, validators=[DataRequired("זהו סעיף חובה")])
    flight_type = SelectField("סוג טיסה", choices=[("op", 'מבצעית'), ("tr", 'אימון'),("gu", 'הדרכה')], validators=[DataRequired()])
    flight_time = SelectField("שעות טיסה", choices=[(0, '0'),(0.5, '0.5'), (1, '1'), (1.5, '1.5'),(2, '2'),(2.5, '2.5'),(3, '3'),(3.5, '3.5'),(4, '4'),(4.5, '4.5'),(5, '5'),(5.5, '5.5'),(6, '6'),(6.5, '6.5'), (7,'7'), (7.5,'7.5'),(8,'8'), (8.5,'8.5'),(9,'9'),(9.5,'9.5'),(10,'10'),(10.5,'10.5'), (11,'11'), (11.5,'11.5'), (12, '12')], validators=[DataRequired()])
    submit = SubmitField("סיים טיסה")

class RegisterForm(AppForm):
    id = IntegerField("מספר קבוצה", validators=[InputRequired("זהו סעיף חובה")])
    name = StringField("שם")
    mitam = IntegerField("מספר מתאם(קבוצת ליבה)", validators=[InputRequired("זהו סעיף חובה")])
    password = PasswordField("סיסמה", validators=[DataRequired("זהו סעיף חובה")])
    candidates_count = IntegerField("מספר מגובשים שייפתחו מראש (1 עד N)", default=25,
                                    validators=[InputRequired("זהו סעיף חובה"),
                                                NumberRange(min=0, max=99, message="בין 0 ל-99")])
    submit = SubmitField("הוסף מגבש")

class AddNameForm(AppForm):
    name = StringField("שם", validators=[DataRequired("זהו סעיף חובה")])
    submit = SubmitField("הוסף שם")

class NewCandidateForm(AppForm):
    # InputRequired, not DataRequired: DataRequired called 0 "missing".
    # 0 itself is refused on purpose — arrival order uses 0 as a separator.
    id = IntegerField("מספר מגובש", validators=[InputRequired("זהו סעיף חובה"),
                                                NumberRange(min=1, message="מספר מגובש מתחיל מ-1")],
                      render_kw={"inputmode": "numeric"})
    name = StringField("שם", validators=[DataRequired("זהו סעיף חובה")])
    submit = SubmitField("הוסף מגובש")

class InterviewForm(AppForm):
    id = SelectField("מספר מגובש", validators=[DataRequired("זהו סעיף חובה")])
    interviewer = StringField("שם מראיין", validators=[DataRequired("זהו סעיף חובה")])
    # Choices start with an empty "choose" entry (set in the view): the first
    # real option is the worst grade, and a required select that already
    # holds it can never be "missing".
    grade = SelectField("ציון ראיון", validators=[DataRequired("בחר ציון ראיון")])
    note = TextAreaField("סיכום ראיון", validators=[DataRequired("זהו סעיף חובה")])
    tash = TextAreaField('בעיות ת"ש', default="אין")
    medical = TextAreaField("בעיות רפואיות", default="אין")
    submit = SubmitField("שמור ראיון")

class AddFinalStatusForm(AppForm):
    id = SelectField("מספר מגובש", validators=[DataRequired("זהו סעיף חובה")])
    final_status = SelectField("סטטוס סיכום", validators=[DataRequired("בחר סטטוס סיכום")])
    final_note = TextAreaField("הערת סיכום", validators=[DataRequired("זהו סעיף חובה")])
    submit = SubmitField("הזן סיכום")

class FinalWeightedGradeForm(AppForm):
    # Category only — the final grade carries no free-text note (field feedback).
    id = SelectField("מספר מגובש", validators=[DataRequired("זהו סעיף חובה")])
    grade = SelectField("ציון סופי משוקלל ראיון וגיבוש", validators=[DataRequired("זהו סעיף חובה")])
    submit = SubmitField("שמור ציון")

class EditUserForm(AppForm):
    name = StringField("שם", validators=[DataRequired("זהו סעיף חובה")])
    submit = SubmitField("השלם עריכה")


class LoginForm(AppForm):
    # "group" (group number + password, admin is group 0) or a built-in
    # staff station key ("doctor" / "hr"), which logs in by password only.
    role = HiddenField(default="group")
    id = StringField("מספר קבוצה", validators=[Optional()])
    password = PasswordField("סיסמה", validators=[DataRequired("הזן סיסמה")])
    submit = SubmitField("התחבר")

class Search_review(AppForm):
    name = StringField("הקלד את שם המשתמש עליו תרצה לקרוא חוות דעת (השאר ריק כדי לראות את כל חוות הדעת)")
    submit = SubmitField("חפש")


class selectCandidate(AppForm):
    id = SelectField("בחר מגובש", validators=[DataRequired()])
    submit = SubmitField("הצג")

class GroupReviewForm(AppForm):
    # Station + custom name only; each row's grade/note is read straight from
    # the request (grade-<n> / note-<n>) in /add-all.
    subject = StringField("בחר מגובש", validators=[DataRequired()])
    station = SelectField("בחר תחנה", validators=[DataRequired("בחר תחנה")])
    odt = StringField("שם תחנה", validators=[RequiredWhen("station", ("ODT", "אחר"), "כתוב את שם התחנה"),
                                             Length(max=100, message="שם התחנה ארוך מדי")])
    grade = SelectField(choices=[0,1,2,3,4])
    note = StringField('הערה')
    submit = SubmitField('הזן')

class selectCandidateAdmin(AppForm):
    group = SelectField("בחר קבוצה", validators=[DataRequired()])
    id = SelectField("בחר מגובש", validators=[DataRequired()])
    submit = SubmitField("הצג")

class selectGroup(AppForm):
    group = SelectField("בחר קבוצה", validators=[DataRequired()])
    submit = SubmitField("הצג")

class selectCandidateAdmin(AppForm):
    group = SelectField("בחר קבוצה")
    id = SelectField("מגובש")
    submit = SubmitField("הצג")

class UpdateDateForm (AppForm):
    last_15_date = DateField("כוננות 15' אחרונה",render_kw={'max':date.today()}, validators=[DataRequired("זהו סעיף חובה")])
    submit = SubmitField("עדכן")
