from decimal import Decimal

import pytest

from app.extensions import db
from app.invoices.pdf import _is_safe_host, build_invoice_pdf_html
from app.invoices.service import build_line_item, recalculate_invoice
from app.models import (
    Customer,
    DiscountType,
    Invoice,
    InvoiceLineItem,
    InvoiceStatus,
    Membership,
    MembershipRole,
    Organization,
    Payment,
    User,
)


@pytest.fixture(autouse=True)
def _clean(app):
    yield
    with app.app_context():
        db.session.query(Payment).delete()
        db.session.query(InvoiceLineItem).delete()
        db.session.query(Invoice).delete()
        db.session.query(Customer).delete()
        db.session.query(Membership).delete()
        db.session.query(Organization).delete()
        db.session.query(User).delete()
        db.session.commit()


@pytest.fixture
def db_session(app):
    with app.app_context():
        yield db.session


def _make_user(email="creator@example.com"):
    user = User(name="A Creator", email=email)
    user.set_password("correct horse battery staple")
    return user


def _make_org(**kwargs):
    kwargs.setdefault("name", "Acme Inc")
    kwargs.setdefault("slug", "acme-inc")
    return Organization(**kwargs)


def _make_membership(org, user, role=MembershipRole.OWNER):
    return Membership(organization_id=org.id, user_id=user.id, role=role)


def _make_customer(org, **kwargs):
    kwargs.setdefault("name", "Jane Customer")
    return Customer(organization_id=org.id, **kwargs)


def _make_invoice(db_session, org, customer, creator, **kwargs):
    kwargs.setdefault("invoice_number", "INV-0001")
    kwargs.setdefault("currency", "USD")
    invoice = Invoice(organization_id=org.id, customer_id=customer.id, created_by=creator.id, **kwargs)
    db_session.add(invoice)
    db_session.flush()
    return invoice


def test_build_html_includes_organization_and_customer_names(db_session):
    user = _make_user()
    org = _make_org()
    db_session.add_all([user, org])
    db_session.flush()
    creator = _make_membership(org, user)
    customer = _make_customer(org, name="Northwind Traders")
    db_session.add_all([creator, customer])
    db_session.flush()
    invoice = _make_invoice(db_session, org, customer, creator)

    html = build_invoice_pdf_html(invoice, org)

    assert "Acme Inc" in html
    assert "Northwind Traders" in html
    assert invoice.invoice_number in html


def test_build_html_includes_line_items(db_session):
    user = _make_user()
    org = _make_org()
    db_session.add_all([user, org])
    db_session.flush()
    creator = _make_membership(org, user)
    customer = _make_customer(org)
    db_session.add_all([creator, customer])
    db_session.flush()
    invoice = _make_invoice(db_session, org, customer, creator)
    invoice.line_items.append(
        build_line_item(
            org.id, invoice.id, description="Consulting hours", quantity=Decimal("3"), unit_price=Decimal("50.00"), tax_rate=Decimal("10")
        )
    )
    recalculate_invoice(invoice)
    db_session.flush()

    html = build_invoice_pdf_html(invoice, org)

    assert "Consulting hours" in html
    assert "150.00" in html  # line_total
    assert "10%" in html  # tax_rate


def test_build_html_shows_a_message_when_there_are_no_line_items(db_session):
    user = _make_user()
    org = _make_org()
    db_session.add_all([user, org])
    db_session.flush()
    creator = _make_membership(org, user)
    customer = _make_customer(org)
    db_session.add_all([creator, customer])
    db_session.flush()
    invoice = _make_invoice(db_session, org, customer, creator)

    html = build_invoice_pdf_html(invoice, org)

    assert "No line items" in html


def test_build_html_includes_totals_and_discount_label(db_session):
    user = _make_user()
    org = _make_org()
    db_session.add_all([user, org])
    db_session.flush()
    creator = _make_membership(org, user)
    customer = _make_customer(org)
    db_session.add_all([creator, customer])
    db_session.flush()
    invoice = _make_invoice(
        db_session, org, customer, creator, discount_type=DiscountType.PERCENTAGE, discount_value=Decimal("10.00")
    )
    invoice.line_items.append(
        build_line_item(org.id, invoice.id, description="Widget", quantity=Decimal("1"), unit_price=Decimal("100.00"), tax_rate=None)
    )
    recalculate_invoice(invoice)
    db_session.flush()

    html = build_invoice_pdf_html(invoice, org)

    assert "Discount (10.00%)" in html
    assert "90.00" in html  # total after 10% discount
    assert "100.00" in html  # subtotal


def test_build_html_includes_payment_status_amount_paid_and_balance_due(db_session):
    user = _make_user()
    org = _make_org()
    db_session.add_all([user, org])
    db_session.flush()
    creator = _make_membership(org, user)
    customer = _make_customer(org)
    db_session.add_all([creator, customer])
    db_session.flush()
    invoice = _make_invoice(db_session, org, customer, creator, status=InvoiceStatus.SENT)
    invoice.line_items.append(
        build_line_item(org.id, invoice.id, description="Widget", quantity=Decimal("1"), unit_price=Decimal("100.00"), tax_rate=None)
    )
    recalculate_invoice(invoice)
    db_session.flush()
    payment = Payment(
        organization_id=org.id,
        invoice_id=invoice.id,
        amount=Decimal("40.00"),
        payment_date="2026-01-15",
        method="cash",
        recorded_by=creator.id,
        idempotency_key="key-1",
    )
    db_session.add(payment)
    db_session.flush()

    html = build_invoice_pdf_html(invoice, org)

    assert "Payment status: Sent" in html
    assert "Amount paid: USD 40.00" in html
    assert "Balance due: USD 60.00" in html


def test_build_html_escapes_customer_supplied_text(db_session):
    user = _make_user()
    org = _make_org()
    db_session.add_all([user, org])
    db_session.flush()
    creator = _make_membership(org, user)
    customer = _make_customer(org, name="<script>alert(1)</script>")
    db_session.add_all([creator, customer])
    db_session.flush()
    invoice = _make_invoice(db_session, org, customer, creator)

    html = build_invoice_pdf_html(invoice, org)

    assert "<script>alert(1)</script>" not in html
    assert "&lt;script&gt;" in html


def test_build_html_omits_logo_when_none(db_session):
    user = _make_user()
    org = _make_org()
    db_session.add_all([user, org])
    db_session.flush()
    creator = _make_membership(org, user)
    customer = _make_customer(org)
    db_session.add_all([creator, customer])
    db_session.flush()
    invoice = _make_invoice(db_session, org, customer, creator)

    html = build_invoice_pdf_html(invoice, org)

    assert "<img" not in html


def test_build_html_includes_logo_when_an_http_url(db_session):
    user = _make_user()
    org = _make_org(logo="https://example.com/logo.png")
    db_session.add_all([user, org])
    db_session.flush()
    creator = _make_membership(org, user)
    customer = _make_customer(org)
    db_session.add_all([creator, customer])
    db_session.flush()
    invoice = _make_invoice(db_session, org, customer, creator)

    html = build_invoice_pdf_html(invoice, org)

    assert '<img src="https://example.com/logo.png"' in html


@pytest.mark.parametrize("logo", ["file:///etc/passwd", "javascript:alert(1)", "data:text/html,<script>"])
def test_build_html_omits_logo_for_a_non_http_scheme(db_session, logo):
    user = _make_user()
    org = _make_org(logo=logo)
    db_session.add_all([user, org])
    db_session.flush()
    creator = _make_membership(org, user)
    customer = _make_customer(org)
    db_session.add_all([creator, customer])
    db_session.flush()
    invoice = _make_invoice(db_session, org, customer, creator)

    html = build_invoice_pdf_html(invoice, org)

    assert "<img" not in html


@pytest.mark.parametrize(
    "hostname",
    [
        "169.254.169.254",  # cloud metadata (AWS/GCP)
        "127.0.0.1",
        "localhost",
        "10.0.0.5",
        "192.168.1.1",
        "172.16.0.1",
        "0.0.0.0",
    ],
)
def test_is_safe_host_rejects_internal_and_private_addresses(hostname):
    assert _is_safe_host(hostname) is False


def test_is_safe_host_allows_a_public_address():
    assert _is_safe_host("8.8.8.8") is True


def test_is_safe_host_rejects_an_unresolvable_hostname():
    assert _is_safe_host("this-host-does-not-exist.invalid") is False


# ---------------------------------------------------------------------------
# Route-level: exercises the real WeasyPrint rendering pipeline end to end,
# not just the HTML template above. Requires WeasyPrint's native GTK3
# dependency to actually be importable in this process (see pdf.py's own
# module docstring for how that's set up on this Windows dev machine).
# ---------------------------------------------------------------------------


def _login(client, email, password="correct horse battery"):
    login_response = client.post("/api/v1/auth/login", json={"email": email, "password": password})
    return login_response.get_json()["data"]["csrf_token"]


def _register_and_login(client, email, name="Test User", password="correct horse battery"):
    client.post("/api/v1/auth/register", json={"name": name, "email": email, "password": password})
    return _login(client, email, password)


def _create_org_via_api(client, csrf_token, name="Org One"):
    return client.post("/api/v1/organizations", json={"name": name}, headers={"X-CSRF-Token": csrf_token}).get_json()[
        "data"
    ]


def _give_role(app, organization_id, email, role):
    from app.models import MembershipStatus

    with app.app_context():
        user = db.session.query(User).filter_by(email=email).one()
        membership = Membership(organization_id=organization_id, user_id=user.id, role=role, status=MembershipStatus.ACTIVE)
        db.session.add(membership)
        db.session.commit()


def _make_customer_via_api(app, organization_id, name="Jane Customer"):
    import uuid as uuid_module

    with app.app_context():
        customer = Customer(organization_id=uuid_module.UUID(organization_id), name=name)
        db.session.add(customer)
        db.session.commit()
        return str(customer.id)


def _create_invoice_via_api(client, csrf_token, org_id, customer_id):
    return client.post(
        f"/api/v1/organizations/{org_id}/invoices",
        json={
            "customer_id": customer_id,
            "currency": "USD",
            "line_items": [{"description": "Widget", "quantity": "1", "unit_price": "100.00"}],
        },
        headers={"X-CSRF-Token": csrf_token},
    ).get_json()["data"]


def test_pdf_endpoint_returns_a_real_pdf(client, app):
    csrf_token = _register_and_login(client, "owner@example.com")
    org = _create_org_via_api(client, csrf_token)
    customer_id = _make_customer_via_api(app, org["id"])
    invoice = _create_invoice_via_api(client, csrf_token, org["id"], customer_id)

    response = client.get(f"/api/v1/organizations/{org['id']}/invoices/{invoice['id']}/pdf")

    assert response.status_code == 200
    assert response.content_type == "application/pdf"
    assert response.data.startswith(b"%PDF")
    assert len(response.data) > 100


def test_pdf_unauthenticated_request_returns_401(client):
    response = client.get(
        "/api/v1/organizations/00000000-0000-0000-0000-000000000000/invoices/"
        "00000000-0000-0000-0000-000000000000/pdf"
    )
    assert response.status_code == 401


@pytest.mark.parametrize("role", [MembershipRole.MANAGER, MembershipRole.EMPLOYEE, MembershipRole.CUSTOMER_SUPPORT])
def test_pdf_roles_without_invoice_payment_manage_cannot_download(client, app, role):
    csrf_token = _register_and_login(client, f"owner-{role.value}@example.com")
    org = _create_org_via_api(client, csrf_token)
    customer_id = _make_customer_via_api(app, org["id"])
    invoice = _create_invoice_via_api(client, csrf_token, org["id"], customer_id)
    other_email = f"{role.value}@example.com"
    other_csrf = _register_and_login(client, other_email)
    _give_role(app, org["id"], other_email, role)

    response = client.get(f"/api/v1/organizations/{org['id']}/invoices/{invoice['id']}/pdf")

    assert response.status_code == 403


def test_pdf_for_a_cross_org_invoice_returns_404(client, app):
    owner_a_csrf = _register_and_login(client, "ownera@example.com")
    org_a = _create_org_via_api(client, owner_a_csrf, name="Org A")
    customer_a = _make_customer_via_api(app, org_a["id"])
    invoice_a = _create_invoice_via_api(client, owner_a_csrf, org_a["id"], customer_a)

    owner_b_csrf = _register_and_login(client, "ownerb@example.com")
    org_b = _create_org_via_api(client, owner_b_csrf, name="Org B")

    response = client.get(f"/api/v1/organizations/{org_b['id']}/invoices/{invoice_a['id']}/pdf")

    assert response.status_code == 404


def test_safe_url_fetcher_refuses_a_private_address_without_delegating(monkeypatch):
    """Requires the real WeasyPrint import (GTK3 on PATH) just to
    build the fetcher - the check itself (`_is_safe_host`) is already
    covered network-free above; this proves the fetcher actually
    refuses *before* ever delegating to the base `URLFetcher.fetch`,
    by making that base method raise if it's ever reached."""
    from weasyprint.urls import URLFetcher

    from app.invoices.pdf import _build_safe_url_fetcher

    def _fail_if_reached(self, url, headers=None):
        raise AssertionError("must not delegate to the real fetcher for an unsafe host")

    monkeypatch.setattr(URLFetcher, "fetch", _fail_if_reached)

    fetcher = _build_safe_url_fetcher()
    with pytest.raises(ValueError):
        fetcher("http://169.254.169.254/latest/meta-data/")


def test_pdf_generation_tolerates_a_logo_pointing_at_a_private_address(client, app):
    """End-to-end: an org whose logo is a metadata/internal address
    doesn't crash PDF generation (WeasyPrint catches the fetcher's
    ValueError and just renders without that image) or leak a 500 -
    the request still succeeds with a real PDF, proving the refusal
    is graceful, not just internally correct."""
    csrf_token = _register_and_login(client, "ownerssrf@example.com")
    org = _create_org_via_api(client, csrf_token)
    with app.app_context():
        import uuid as uuid_module

        db.session.query(Organization).filter_by(id=uuid_module.UUID(org["id"])).update({"logo": "http://169.254.169.254/latest/meta-data/"})
        db.session.commit()
    customer_id = _make_customer_via_api(app, org["id"])
    invoice = _create_invoice_via_api(client, csrf_token, org["id"], customer_id)

    response = client.get(f"/api/v1/organizations/{org['id']}/invoices/{invoice['id']}/pdf")

    assert response.status_code == 200
    assert response.data.startswith(b"%PDF")
