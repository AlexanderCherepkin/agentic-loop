from __future__ import annotations

import os

from flask import Flask, flash, redirect, render_template, request, url_for
from flask_login import LoginManager, login_required, login_user, logout_user
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.orm import DeclarativeBase
from werkzeug.security import check_password_hash, generate_password_hash

from config import Config
from forms import LoginForm


class Base(DeclarativeBase):
    pass


db = SQLAlchemy(model_class=Base)
login_manager = LoginManager()


def create_app() -> Flask:
    app = Flask(__name__)
    app.config.from_object(Config)

    db.init_app(app)
    login_manager.init_app(app)
    login_manager.login_view = "index"

    with app.app_context():
        db.create_all()

    return app


app = create_app()


class User(db.Model):
    __tablename__ = "users"

    id: db.Column = db.Column(db.Integer, primary_key=True)
    username: db.Column = db.Column(db.String(80), unique=True, nullable=False)
    password_hash: db.Column = db.Column(db.String(256), nullable=False)

    @property
    def is_authenticated(self) -> bool:
        return True

    @property
    def is_active(self) -> bool:
        return True

    @property
    def is_anonymous(self) -> bool:
        return False

    def get_id(self) -> str:
        return str(self.id)


@login_manager.user_loader
def load_user(user_id: int) -> User | None:
    return db.session.get(User, int(user_id))


@app.route("/", methods=["GET", "POST"])
def index():
    form = LoginForm()
    if form.validate_on_submit():
        user = User.query.filter_by(username=form.username.data).first()
        if user and check_password_hash(user.password_hash, form.password.data):
            login_user(user)
            return redirect(url_for("dashboard"))
        flash("Invalid username or password")
    return render_template("index.html", form=form)


@app.route("/dashboard")
@login_required
def dashboard():
    return render_template("dashboard.html")


@app.route("/logout")
@login_required
def logout():
    logout_user()
    return redirect(url_for("index"))


@app.route("/health")
def health():
    return {"status": "ok"}


@app.cli.command("create-user")
def create_user_command():
    """Create a default user for testing."""
    username = os.getenv("DEFAULT_USERNAME", "admin")
    password = os.getenv("DEFAULT_PASSWORD", "admin")
    if User.query.filter_by(username=username).first():
        print("User already exists")
        return
    user = User(username=username, password_hash=generate_password_hash(password))
    db.session.add(user)
    db.session.commit()
    print(f"Created user {username}")


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("FLASK_PORT", "5000")))
