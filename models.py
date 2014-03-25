from datetime import datetime, timedelta

from werkzeug.security import check_password_hash, generate_password_hash
from sqlalchemy import Column, DateTime, ForeignKey, Integer, Interval, String
from sqlalchemy.ext.hybrid import hybrid_property
from sqlalchemy.orm import backref, relationship

from database import Base


class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True)
    email = Column(String, nullable=False)
    password = Column(String, nullable=False)

    projects = relationship("Project", order_by="Project.name", backref="user")

    def __init__(self, email, password):
        self.email = email
        self.password = generate_password_hash(password)

    def __repr__(self):
        return "<User {0} (hashed password: {1})>".\
                format(self.email, self.password)

    def is_authenticated(self):
        return True

    def is_active(self):
        return True

    def is_anonymous(self):
        return False

    def get_id(self):
        return unicode(self.id)

    def check_password(self, entered_password):
        return check_password_hash(self.password, entered_password)


class Project(Base):
    __tablename__ = "projects"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    name = Column(String, nullable=False)

    spells = relationship("Spell", order_by="Spell.start", backref="project")

    def __init__(self, user_id, name):
        self.user_id = user_id
        self.name = name

    def __repr__(self):
        return "<Project {0} (id {1}) for user {2}>".\
                format(self.name, self.id, self.user_id)


class Spell(Base):
    __tablename__ = "spells"
    id = Column(Integer, primary_key=True)
    project_id = Column(Integer, ForeignKey("projects.id"))
    start = Column(DateTime, nullable=False)
    end = Column(DateTime)

    @hybrid_property
    def duration(self):
        if self.end:
            return self.end - self.start
        else:
            return datetime.now() - self.start
    
    def __init__(self, project_id):
        self.project_id = project_id
        # Assign start time based on when the spell is initialized
        self.start = datetime.now()

    def __repr__(self):
        return "<Spell from {0} to {1} for project {2}>".\
                format(self.start, self.end, self.project_id)
