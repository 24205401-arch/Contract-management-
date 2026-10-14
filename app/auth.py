from flask import (
    Blueprint, current_app, flash, redirect, render_template, request, session, url_for,
)
from flask_login import login_required, login_user, logout_user

from .extensions import oauth
from .models import (
    ROLE_CLIENT, ROLE_PARTNER, ROLE_BOTH,
    check_user_password, create_company, create_user, find_user_by_email,
    find_user_by_google_id, find_user_by_username, get_company, link_google_id,
    list_companies, username_exists,
)

auth_bp = Blueprint("auth", __name__)


def _companies_for_signup():
    return list_companies(role_in=[ROLE_CLIENT, ROLE_PARTNER, ROLE_BOTH])


def _google_enabled():
    return bool(current_app.config.get("GOOGLE_CLIENT_ID") and current_app.config.get("GOOGLE_CLIENT_SECRET"))


@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        user = find_user_by_username(username)
        if user is not None and check_user_password(user, password):
            login_user(user)
            return redirect(url_for("orders.dashboard"))
        flash("Invalid username or password.", "error")
    return render_template("registration/login.html", google_enabled=_google_enabled())


@auth_bp.route("/logout", methods=["POST"])
@login_required
def logout():
    logout_user()
    flash("You've been logged out.", "success")
    return redirect(url_for("auth.login"))


def _create_account_from_form(form, password):
    """Shared logic for password signup: validate + create company/user.
    Returns (user_or_none, list_of_errors).
    """
    username = form.get("username", "").strip()
    email = form.get("email", "").strip()
    account_type = form.get("account_type")
    company_name = form.get("company_name", "").strip()
    existing_company_id = form.get("existing_company")

    errors = []
    if not username:
        errors.append("Username is required.")
    elif username_exists(username):
        errors.append("That username is already taken.")

    if password is not None:
        password2 = form.get("password2", "")
        if len(password) < 8:
            errors.append("Password must be at least 8 characters.")
        elif password != password2:
            errors.append("Passwords don't match.")

    company_id = None
    role = "admin"
    role_value = None

    if account_type == "join":
        company = get_company(existing_company_id) if existing_company_id else None
        if not company:
            errors.append("Select a company to join.")
        else:
            company_id = company["_id"]
            role = "staff"
    elif account_type in ("new_client", "new_partner"):
        if not company_name:
            errors.append("Enter a company name.")
        role_value = ROLE_CLIENT if account_type == "new_client" else ROLE_PARTNER
    else:
        errors.append("Choose an account type.")

    if errors:
        return None, errors

    if account_type != "join":
        company = create_company(company_name, role_value)
        company_id = company["_id"]

    user = create_user(username, email, password, company_id, role)
    return user, []


@auth_bp.route("/signup", methods=["GET", "POST"])
def signup():
    if request.method == "POST":
        password1 = request.form.get("password1", "")
        user, errors = _create_account_from_form(request.form, password1)
        if errors:
            for e in errors:
                flash(e, "error")
        else:
            login_user(user)
            flash(f"Account created for {user.company['name'] if user.company else 'our company'}.", "success")
            return redirect(url_for("orders.dashboard"))

    return render_template(
        "registration/signup.html", companies=_companies_for_signup(), google_enabled=_google_enabled()
    )


# --- Google OAuth ---------------------------------------------------------

@auth_bp.route("/auth/google")
def google_login():
    if not _google_enabled():
        flash("Google sign-in isn't configured. Add GOOGLE_CLIENT_ID / GOOGLE_CLIENT_SECRET to .env.", "error")
        return redirect(url_for("auth.signup"))
    redirect_uri = url_for("auth.google_callback", _external=True)
    return oauth.google.authorize_redirect(redirect_uri)


@auth_bp.route("/auth/google/callback")
def google_callback():
    token = oauth.google.authorize_access_token()
    userinfo = token.get("userinfo") if token else None
    if not userinfo:
        flash("Google sign-in failed — no profile info was returned.", "error")
        return redirect(url_for("auth.login"))

    google_id = userinfo["sub"]
    email = userinfo.get("email", "")

    user = find_user_by_google_id(google_id)
    if user is None and email:
        existing = find_user_by_email(email)
        if existing is not None:
            link_google_id(existing, google_id)
            user = existing

    if user is not None:
        login_user(user)
        flash(f"Welcome back, {user.username}.", "success")
        return redirect(url_for("orders.dashboard"))

    # Brand-new Google user — we still need to know which company they
    # represent, so stash their Google identity and ask.
    session["pending_google"] = {
        "google_id": google_id,
        "email": email,
        "name": userinfo.get("name", ""),
    }
    return redirect(url_for("auth.complete_profile"))


@auth_bp.route("/complete-profile", methods=["GET", "POST"])
def complete_profile():
    pending = session.get("pending_google")
    if not pending:
        return redirect(url_for("auth.signup"))

    if request.method == "POST":
        fake_form = request.form.copy()
        fake_form["username"] = pending["email"] or f"google_{pending['google_id'][:8]}"
        fake_form["email"] = pending["email"]
        if username_exists(fake_form["username"]):
            fake_form["username"] = f"{fake_form['username']}_{pending['google_id'][-4:]}"

        user, errors = _create_account_from_form(fake_form, password=None)
        if errors:
            for e in errors:
                flash(e, "error")
        else:
            link_google_id(user, pending["google_id"])
            session.pop("pending_google", None)
            login_user(user)
            flash(f"Account created for {user.company['name'] if user.company else 'our company'}.", "success")
            return redirect(url_for("orders.dashboard"))

    return render_template(
        "registration/complete_profile.html", pending=pending, companies=_companies_for_signup()
    )
