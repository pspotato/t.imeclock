from datetime import datetime
from operator import itemgetter

from flask import Flask, Response, g, redirect, render_template, request,\
        url_for
from flask.ext.login import LoginManager, current_user, login_required,\
        login_user, logout_user
from sqlalchemy import Date, cast, distinct

from database import session
from models import User, Project, Spell
from forms import RegisterForm, LoginForm, SwitchProjectForm, HistoryDateForm


# Set application constants, and create application
DATABASE = "/tmp/timeclock.db"
# Issue: after development this DEBUG needs to get turned off, for security
DEBUG = True
SECRET_KEY = "qmTcssHWNArLzQP9LmBJq7Y4hvdfc4"

app = Flask(__name__)
app.config.from_object(__name__)

# Configure login manager
lm = LoginManager()
lm.init_app(app)
lm.login_view = "login"

# Remove the database session at the end of a request or at shutdown
@app.teardown_appcontext
def shutdown_session(exception=None):
    session.remove()

# Allow login manager to load a user from the database
@lm.user_loader
def load_user(id):
    if id is not None:
        return User.query.get(int(id))
    else:
        return None

# Remember the current user
@app.before_request
def before_request():
    g.user = current_user

# Utility function to convert duration objects into human-readable form
def duration_to_plain_english(duration):
    duration_mins, duration_secs = divmod(duration.seconds, 60)
    duration_hours, duration_mins = divmod(duration_mins, 60)

    duration_text = ""

    if duration.days > 0:
        if duration.days == 1:
            duration_text += "1 day, "
        else:
            duration_text += str(duration.days) + " days, "

    if duration_hours > 0:
        if duration_hours == 1:
            duration_text += "1 hour, "
        else:
            duration_text += str(duration_hours) + " hours, "

    if duration_mins == 1:
        duration_text += "1 minute"
    else:
        duration_text += str(duration_mins) + " minutes"

    return duration_text


@app.route("/")
def no_route():
    if current_user.is_authenticated():
        return redirect("/current")
    else:
        return redirect("/login")

@app.route("/register", methods=["POST", "GET"])
def register():
    form = RegisterForm()
    if form.validate_on_submit():
        # Issue: set up an email verification system to confirm this
        # Issue: implement a CAPTCHA to protect against illicit accounts
        user = User(email=form.email.data, password=form.password.data)
        session.add(user)
        session.commit()
        login_user(user, remember=True)
        return redirect("/user_list")
    return render_template("register.html", form=form)

@app.route("/login", methods=["POST", "GET"])
def login():
    form = LoginForm()
    if form.validate_on_submit():
        user = User.query.filter(User.email == form.email.data).first()
        if user.check_password(form.password.data):
            login_user(user, remember=True)
            return redirect("/")
    return render_template("login.html", form=form)

@app.route("/logout")
@login_required
def logout():
    logout_user()
    return redirect("/")

@app.route("/current", methods=["POST", "GET"])
@login_required
def current():
    form = SwitchProjectForm()
    current_spell = Spell.query.\
            filter(Spell.project.user == current_user).\
            filter(Spell.duration == None).\
            first()

    # Generate a list of existing projects from which user can choose
    DEFAULT_CHOICE_NO_PROJECT = (-1, "")
    # Issue: allow user to take a break, not working on any project
    # Issue: allow user to stop working for the day
    form_choices = [DEFAULT_CHOICE_NO_PROJECT]
    for project in current_user.projects:
        # Remove current project from the set of choices
        if project != current_spell.project:
            form_choices.append((project.id, project.name))
    form.existing_project.choices = form_choices

    if form.validate_on_submit():
        # Close the current project, if one exists
        if current_spell:
            current_spell.duration = datetime.now() - current_spell.start
            # Add this project to the form selection drop-down
            form.existing_project.choices.append(
                    (current_spell.project.id, current_spell.project.name))

        # If user selected an existing project, retrieve that project's name
        if form.existing_project.data != DEFAULT_CHOICE_NO_PROJECT[0]:
            current_project = Project.query.\
                    filter(Project.id == form.existing_project.data).\
                    first()
            # Remove this project from the form selection drop-down
            form.existing_project.choices.remove(
                    (current_project.id, current_project.name))

        # If the user wants to start on a new project, use that name instead
        # Issue: need to forbid user from using one of their existing names
        else:
            current_project = Project(
                    user_id=current_user.id, 
                    name=form.new_project.data)
            # Add this to the projects table
            session.add(current_project)

        # Create a new database record for that project name
        current_spell = Spell(project_id=current_project.id)
        session.add(current_spell)

        session.commit()

    # Sort choices alphabetically by project name
    form.existing_project.choices.sort(key=itemgetter(1))

    return render_template(
            "current.html",
            form=form,
            current_spell=current_spell)

@app.route("/history", methods=["POST", "GET"])
@login_required
def history():
    form = HistoryDateForm()

    start_date = form.start_date.data
    end_date = form.end_date.data

    # Include the currently-onling spell in the summed durations
    current_spell = Spell.query.\
        filter(Spell.duration == None).\
        join(Project).join(User).filter(User.id == current_user.id).\
        first()

    if current_spell:
        current_spell.duration = datetime.now() - current_spell.start

        # Sum the durations by project
        durations = {}
        for project in current_user.projects:
            durations[project.name] = 0
            for spell in project.spells:
                if spell.start >= start_date and spell.start <= end_date:
                    durations[project.name] = \
                            durations[project.name] + spell.duration
            # Convert summed durations to plain English
            durations[project.name] = \
                    duration_to_plain_english(durations[project.name])

        session.rollback()

    # Sort output alphabetically by project name
    sorted_durations = sorted(durations.iteritems(), key=itemgetter(0))

    return render_template(
            "history.html",
            form=form,
            durations=sorted_durations)

# Return a file containing all of the current user's data
@app.route("/user_complete_history.csv")
@login_required
def generate_csv():
    COLUMNS = ["name", "start", "duration"]
    def generate():
        yield ",".join(COLUMNS) + "\n"
        for project in current_user.projects:
            for spell in project.spells:
                attributes = []
                attributes.append(spell.project.name)
                attributes.append(str(spell.start))
                attributes.append(str(spell.duration))
                yield ",".join(attributes) + "\n"
    return Response(generate(), mimetype="txt/csv")

@app.route("/about")
def about():
    return render_template("about.html")

# For development purposes, print a list of all users and their passwords
@app.route("/user_list")
def user_list():
    return render_template("user_list.html", users=User.query.all())

# For development purposes, print a list of all the projects of a user
@app.route("/project_list")
@login_required
def project_list():
    return render_template(
            "project_list.html",
            current_user=current_user)

if __name__ == "__main__":
    app.run()
