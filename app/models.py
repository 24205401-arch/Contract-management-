"""
Thin data-access layer over MongoDB collections. There's no ORM here —
each function takes/returns plain dicts, which is the natural way to
work with pymongo. current_app.db is the pymongo Database, set up in
app/__init__.py (and swappable for a mongomock database in tests).
"""
from datetime import datetime, timezone

from bson import ObjectId
from bson.errors import InvalidId
from flask import current_app
from flask_login import UserMixin
from werkzeug.security import check_password_hash, generate_password_hash

# --- Company roles -----------------------------------------------------
ROLE_CLIENT = "client"
ROLE_PARTNER = "partner"
ROLE_BOTH = "both"
COMPANY_ROLE_LABELS = {
    ROLE_CLIENT: "Client (places orders with us)",
    ROLE_PARTNER: "Partner (we subcontract work to them)",
    ROLE_BOTH: "Both",
}

# --- Work order types / statuses ---------------------------------------
TYPE_PLUMBING = "plumbing"
TYPE_BUILDING = "building"
TYPE_OTHER = "other"
WORK_TYPE_LABELS = {
    TYPE_PLUMBING: "Plumbing",
    TYPE_BUILDING: "Building / Construction",
    TYPE_OTHER: "Other",
}

STATUS_NEW = "new"
STATUS_QUOTED = "quoted"
STATUS_ACCEPTED = "accepted"
STATUS_SUBCONTRACTED = "subcontracted"
STATUS_IN_PROGRESS = "in_progress"
STATUS_COMPLETED = "completed"
STATUS_CANCELLED = "cancelled"
STATUS_LABELS = {
    STATUS_NEW: "New",
    STATUS_QUOTED: "Quoted",
    STATUS_ACCEPTED: "Accepted",
    STATUS_SUBCONTRACTED: "Subcontracted Out",
    STATUS_IN_PROGRESS: "In Progress",
    STATUS_COMPLETED: "Completed",
    STATUS_CANCELLED: "Cancelled",
}

QUOTE_PENDING = "pending"
QUOTE_ACCEPTED = "accepted"
QUOTE_REJECTED = "rejected"

SUB_OFFERED = "offered"
SUB_ACCEPTED = "accepted"
SUB_DECLINED = "declined"
SUB_COMPLETED = "completed"


def db():
    return current_app.db


def now():
    return datetime.now(timezone.utc)


def to_oid(value):
    """Safely convert a string/ObjectId to ObjectId, or None if invalid."""
    if isinstance(value, ObjectId):
        return value
    try:
        return ObjectId(value)
    except (InvalidId, TypeError):
        return None


def next_sequence(name):
    """Simple auto-increment counter, e.g. for human-friendly work order refs."""
    doc = db().counters.find_one_and_update(
        {"_id": name},
        {"$inc": {"seq": 1}},
        upsert=True,
        return_document=True,
    )
    return doc["seq"]


# --- User ---------------------------------------------------------------

class User(UserMixin):
    """Wraps a `users` document for Flask-Login."""

    def __init__(self, doc):
        self.doc = doc

    def get_id(self):
        return str(self.doc["_id"])

    @property
    def id(self):
        return self.doc["_id"]

    @property
    def username(self):
        return self.doc["username"]

    @property
    def email(self):
        return self.doc.get("email", "")

    @property
    def company_id(self):
        return self.doc.get("company_id")

    @property
    def role(self):
        return self.doc.get("role", "staff")

    @property
    def is_internal_staff(self):
        return self.doc.get("company_id") is None

    @property
    def company(self):
        if self.company_id is None:
            return None
        return get_company(self.company_id)


def find_user_by_id(user_id):
    oid = to_oid(user_id)
    if oid is None:
        return None
    doc = db().users.find_one({"_id": oid})
    return User(doc) if doc else None


def find_user_by_username(username):
    doc = db().users.find_one({"username": username})
    return User(doc) if doc else None


def find_user_by_google_id(google_id):
    doc = db().users.find_one({"google_id": google_id})
    return User(doc) if doc else None


def find_user_by_email(email):
    doc = db().users.find_one({"email": email})
    return User(doc) if doc else None


def username_exists(username):
    return db().users.find_one({"username": username}) is not None


def create_user(username, email, password, company_id, role, google_id=None):
    doc = {
        "username": username,
        "email": email,
        "password_hash": generate_password_hash(password) if password else None,
        "google_id": google_id,
        "company_id": company_id,
        "role": role,
        "created_at": now(),
    }
    result = db().users.insert_one(doc)
    doc["_id"] = result.inserted_id
    return User(doc)


def check_user_password(user, password):
    if not user.doc.get("password_hash"):
        return False
    return check_password_hash(user.doc["password_hash"], password)


def link_google_id(user, google_id):
    db().users.update_one({"_id": user.id}, {"$set": {"google_id": google_id}})
    user.doc["google_id"] = google_id


# --- Company --------------------------------------------------------------

def create_company(name, role, registration_number="", contact_person="", email="", phone="", address=""):
    doc = {
        "name": name,
        "role": role,
        "registration_number": registration_number,
        "contact_person": contact_person,
        "email": email,
        "phone": phone,
        "address": address,
        "created_at": now(),
    }
    result = db().companies.insert_one(doc)
    doc["_id"] = result.inserted_id
    return doc


def get_company(company_id):
    oid = to_oid(company_id)
    if oid is None:
        return None
    return db().companies.find_one({"_id": oid})


def list_companies(role_in=None):
    query = {}
    if role_in:
        query["role"] = {"$in": role_in}
    return list(db().companies.find(query).sort("name", 1))


# --- Work orders ------------------------------------------------------------

def create_work_order(client_company_id, title, description, work_type, budget, deadline):
    doc = {
        "ref": next_sequence("work_order_ref"),
        "client_company_id": client_company_id,
        "title": title,
        "description": description,
        "work_type": work_type,
        "status": STATUS_NEW,
        "budget": budget,
        "deadline": deadline,
        "created_at": now(),
        "updated_at": now(),
    }
    result = db().work_orders.insert_one(doc)
    doc["_id"] = result.inserted_id
    return doc


def get_work_order(order_id):
    oid = to_oid(order_id)
    if oid is None:
        return None
    return db().work_orders.find_one({"_id": oid})


def list_work_orders(client_company_id=None):
    query = {}
    if client_company_id is not None:
        query["client_company_id"] = client_company_id
    return list(db().work_orders.find(query).sort("created_at", -1))


def set_work_order_status(order_id, status):
    db().work_orders.update_one(
        {"_id": to_oid(order_id)}, {"$set": {"status": status, "updated_at": now()}}
    )


# --- Quotes -----------------------------------------------------------------

def create_quote(work_order_id, amount, notes):
    doc = {
        "work_order_id": to_oid(work_order_id),
        "amount": amount,
        "notes": notes,
        "status": QUOTE_PENDING,
        "created_at": now(),
    }
    result = db().quotes.insert_one(doc)
    doc["_id"] = result.inserted_id
    return doc


def list_quotes(work_order_id):
    return list(db().quotes.find({"work_order_id": to_oid(work_order_id)}).sort("created_at", 1))


def get_quote(quote_id):
    oid = to_oid(quote_id)
    if oid is None:
        return None
    return db().quotes.find_one({"_id": oid})


def set_quote_status(quote_id, status):
    db().quotes.update_one({"_id": to_oid(quote_id)}, {"$set": {"status": status}})


# --- Subcontracts -------------------------------------------------------------

def create_subcontract(work_order_id, partner_company_id, amount, notes):
    doc = {
        "work_order_id": to_oid(work_order_id),
        "partner_company_id": partner_company_id,
        "amount": amount,
        "notes": notes,
        "status": SUB_OFFERED,
        "created_at": now(),
    }
    result = db().subcontracts.insert_one(doc)
    doc["_id"] = result.inserted_id
    return doc


def list_subcontracts(work_order_id=None, partner_company_id=None):
    query = {}
    if work_order_id is not None:
        query["work_order_id"] = to_oid(work_order_id)
    if partner_company_id is not None:
        query["partner_company_id"] = partner_company_id
    return list(db().subcontracts.find(query).sort("created_at", 1))


def get_subcontract(sub_id):
    oid = to_oid(sub_id)
    if oid is None:
        return None
    return db().subcontracts.find_one({"_id": oid})


def set_subcontract_status(sub_id, status):
    db().subcontracts.update_one({"_id": to_oid(sub_id)}, {"$set": {"status": status}})
