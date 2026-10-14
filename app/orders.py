from flask import Blueprint, abort, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required
  
from . import models as m

orders_bp = Blueprint("orders", __name__)


def _enrich_order(order):
    order["client_company"] = m.get_company(order["client_company_id"])
    quotes = m.list_quotes(order["_id"])
    for q in quotes:
        pass
    order["quotes"] = quotes
    subs = m.list_subcontracts(work_order_id=order["_id"])
    for s in subs:
        s["partner_company"] = m.get_company(s["partner_company_id"])
    order["subcontracts"] = subs
    return order


@orders_bp.route("/")
@login_required
def dashboard():
    if current_user.company_id is not None:
        my_orders = [_enrich_order(o) for o in m.list_work_orders(client_company_id=current_user.company_id)]
        subs = m.list_subcontracts(partner_company_id=current_user.company_id)
        for s in subs:
            s["work_order"] = m.get_work_order(s["work_order_id"])
            s["work_order"]["client_company"] = m.get_company(s["work_order"]["client_company_id"])
        return render_template("workorders/dashboard_client.html", orders=my_orders, subcontracts=subs)

    orders = [_enrich_order(o) for o in m.list_work_orders()]
    return render_template("workorders/dashboard_staff.html", orders=orders)


@orders_bp.route("/orders")
@login_required
def order_list():
    company_id = current_user.company_id if current_user.company_id is not None else None
    orders = [_enrich_order(o) for o in m.list_work_orders(client_company_id=company_id)]
    return render_template("workorders/order_list.html", orders=orders)


@orders_bp.route("/orders/new", methods=["GET", "POST"])
@login_required
def order_create():
    if current_user.company_id is None:
        flash("Only a client company account can raise a work order.", "error")
        return redirect(url_for("orders.dashboard"))
    if current_user.company["role"] == m.ROLE_PARTNER:
        flash("Partner accounts can only manage work offered to them.", "error")
        return redirect(url_for("orders.dashboard"))

    if request.method == "POST":
        title = request.form.get("title", "").strip()
        description = request.form.get("description", "").strip()
        work_type = request.form.get("work_type", m.TYPE_OTHER)
        budget_raw = request.form.get("budget", "").strip()
        deadline = request.form.get("deadline", "").strip() or None

        errors = []
        if not title:
            errors.append("Title is required.")
        budget = None
        if budget_raw:
            try:
                budget = float(budget_raw)
            except ValueError:
                errors.append("Budget must be a number.")

        if errors:
            for e in errors:
                flash(e, "error")
        else:
            order = m.create_work_order(
                current_user.company_id, title, description, work_type, budget, deadline
            )
            flash("Work order submitted.", "success")
            return redirect(url_for("orders.order_detail", order_id=order["_id"]))

    return render_template(
        "workorders/order_form.html", work_types=m.WORK_TYPE_LABELS
    )


@orders_bp.route("/orders/<order_id>")
@login_required
def order_detail(order_id):
    order = m.get_work_order(order_id)
    if order is None:
        abort(404)
    order = _enrich_order(order)
    partner_companies = m.list_companies(role_in=[m.ROLE_PARTNER, m.ROLE_BOTH])
    return render_template(
        "workorders/order_detail.html",
        order=order,
        partner_companies=partner_companies,
    )


@orders_bp.route("/orders/<order_id>/quote", methods=["POST"])
@login_required
def quote_create(order_id):
    order = m.get_work_order(order_id)
    if order is None:
        abort(404)
    if current_user.company_id is not None:
        flash("Only our own staff can add a quote.", "error")
        return redirect(url_for("orders.order_detail", order_id=order_id))

    amount_raw = request.form.get("amount", "").strip()
    notes = request.form.get("notes", "").strip()
    try:
        amount = float(amount_raw)
    except ValueError:
        flash("Quote amount must be a number.", "error")
        return redirect(url_for("orders.order_detail", order_id=order_id))

    m.create_quote(order_id, amount, notes)
    m.set_work_order_status(order_id, m.STATUS_QUOTED)
    flash("Quote added.", "success")
    return redirect(url_for("orders.order_detail", order_id=order_id))


@orders_bp.route("/orders/<order_id>/quote/<quote_id>/accept", methods=["POST"])
@login_required
def quote_accept(order_id, quote_id):
    order = m.get_work_order(order_id)
    quote = m.get_quote(quote_id)
    if order is None or quote is None:
        abort(404)
    if current_user.company_id != order["client_company_id"]:
        flash("Only the client company can accept this quote.", "error")
        return redirect(url_for("orders.order_detail", order_id=order_id))

    m.set_quote_status(quote_id, m.QUOTE_ACCEPTED)
    m.set_work_order_status(order_id, m.STATUS_ACCEPTED)
    flash("Quote accepted.", "success")
    return redirect(url_for("orders.order_detail", order_id=order_id))


@orders_bp.route("/orders/<order_id>/subcontract", methods=["POST"])
@login_required
def subcontract_create(order_id):
    order = m.get_work_order(order_id)
    if order is None:
        abort(404)
    if current_user.company_id is not None:
        flash("Only our own staff can offer work to a partner company.", "error")
        return redirect(url_for("orders.order_detail", order_id=order_id))

    partner_company_id = m.to_oid(request.form.get("partner_company"))
    amount_raw = request.form.get("amount", "").strip()
    notes = request.form.get("notes", "").strip()
    partner = m.get_company(partner_company_id) if partner_company_id else None

    if not partner:
        flash("Select a partner company.", "error")
        return redirect(url_for("orders.order_detail", order_id=order_id))

    amount = None
    if amount_raw:
        try:
            amount = float(amount_raw)
        except ValueError:
            flash("Amount must be a number.", "error")
            return redirect(url_for("orders.order_detail", order_id=order_id))

    m.create_subcontract(order_id, partner_company_id, amount, notes)
    m.set_work_order_status(order_id, m.STATUS_SUBCONTRACTED)
    flash(f"Work offered to {partner['name']}.", "success")
    return redirect(url_for("orders.order_detail", order_id=order_id))


@orders_bp.route("/orders/<order_id>/subcontract/<sub_id>/<action>", methods=["POST"])
@login_required
def subcontract_respond(order_id, sub_id, action):
    order = m.get_work_order(order_id)
    sub = m.get_subcontract(sub_id)
    if order is None or sub is None:
        abort(404)
    if current_user.company_id != sub["partner_company_id"]:
        flash("Only the partner company this was offered to can respond.", "error")
        return redirect(url_for("orders.order_detail", order_id=order_id))

    if action == "accept":
        m.set_subcontract_status(sub_id, m.SUB_ACCEPTED)
        m.set_work_order_status(order_id, m.STATUS_IN_PROGRESS)
        flash("Subcontract accepted.", "success")
    elif action == "decline":
        m.set_subcontract_status(sub_id, m.SUB_DECLINED)
        flash("Subcontract declined.", "info")
    else:
        abort(404)
    return redirect(url_for("orders.order_detail", order_id=order_id))


@orders_bp.route("/orders/<order_id>/start-in-house", methods=["POST"])
@login_required
def order_start_in_house(order_id):
    order = m.get_work_order(order_id)
    if order is None:
        abort(404)
    if current_user.company_id is not None:
        flash("Only our own staff can start in-house work.", "error")
        return redirect(url_for("orders.order_detail", order_id=order_id))
    if order["status"] != m.STATUS_ACCEPTED:
        flash("Only an accepted order can be started in-house.", "error")
        return redirect(url_for("orders.order_detail", order_id=order_id))

    m.set_work_order_status(order_id, m.STATUS_IN_PROGRESS)
    flash("Work started in-house.", "success")
    return redirect(url_for("orders.order_detail", order_id=order_id))


@orders_bp.route("/orders/<order_id>/mark-completed", methods=["POST"])
@login_required
def order_mark_completed(order_id):
    order = m.get_work_order(order_id)
    if order is None:
        abort(404)
    if current_user.company_id is not None:
        flash("Only our own staff can mark a job completed.", "error")
        return redirect(url_for("orders.order_detail", order_id=order_id))
    if order["status"] != m.STATUS_IN_PROGRESS:
        flash("Only a job that's in progress can be marked completed.", "error")
        return redirect(url_for("orders.order_detail", order_id=order_id))

    m.set_work_order_status(order_id, m.STATUS_COMPLETED)
    flash("Work order marked completed.", "success")
    return redirect(url_for("orders.order_detail", order_id=order_id))
