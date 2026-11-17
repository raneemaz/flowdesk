"""FD-045: invoice PDF generation (FR-027: logo, business info,
customer info, items, taxes/discounts, total, payment status).

Split into two functions deliberately:
- `build_invoice_pdf_html` is pure (no I/O, no native dependency) and
  does all the actual decision-making - it's what every test below
  can exercise directly and cheaply, asserting on the real rendered
  content rather than just trusting the PDF pipeline ran.
- `generate_invoice_pdf` is the thin wrapper that hands that HTML to
  WeasyPrint. WeasyPrint needs a system-level GTK3 runtime (Pango/
  Cairo/GDK-Pixbuf) that plain `pip install` cannot provide - on this
  project's Windows dev environment that meant installing it via
  MSYS2 (`pacman -S mingw-w64-x86_64-pango mingw-w64-x86_64-gdk-pixbuf2`)
  and adding `C:\\msys64\\mingw64\\bin` to `PATH` (see
  `backend/README.md`'s own setup section) - a one-time environment
  step, not something this code can do for itself. Production
  (Linux) typically gets these from system packages instead.

`organization.logo` (FD-012's own column, a bare `String(2048)` with
no format/scheme validation at the model level, settable by any role
with `LIMITED` org-settings access - not just Owner) is attacker
input from this function's own point of view, and embedding it as a
live `<img src="...">` fetch target is a two-layer SSRF risk, closed
in two different ways because one alone doesn't cover the other:
1. **Scheme smuggling** (`file://`, `data:`, `javascript:`, ...) -
   `_logo_html` only ever emits the `<img>` tag for a `http(s)://`
   URL; anything else renders with no image at all.
2. **A *legitimate* http(s) URL pointing at an internal/private
   address** (cloud metadata at `169.254.169.254`, `localhost`,
   RFC1918 ranges, ...) - a scheme check alone does nothing about
   this (a tenant-security review caught exactly this gap). Closed by
   `_SafeURLFetcher`, a custom WeasyPrint `url_fetcher` that resolves
   the hostname and refuses to fetch anything private/loopback/
   link-local/reserved/multicast/unspecified *before* any request is
   made, and disables HTTP redirects entirely (simpler, and no less
   safe for a logo image, which has no legitimate reason to redirect,
   than re-validating every hop). This does **not** close a DNS-rebinding
   race (resolve-safe, then reconnect-to-a-different-IP) - closing that
   fully would mean connecting directly to the resolved IP rather than
   letting urllib re-resolve the hostname itself, which this function
   doesn't do; the threat model here (an in-tenant admin planting a
   URL in their own org's settings, not a sophisticated external
   attacker racing DNS) doesn't call for that extra complexity, but
   it's a real, named residual gap, not something this module claims
   to fully close.
"""

import html as html_escape
import socket
from decimal import Decimal
from ipaddress import ip_address
from urllib.parse import urlparse

from app.models import DiscountType, Invoice, Organization
from app.payments.service import get_invoice_balance

_STATUS_LABELS = {
    "draft": "Draft",
    "sent": "Sent",
    "partially_paid": "Partially Paid",
    "paid": "Paid",
    "overdue": "Overdue",
    "cancelled": "Cancelled",
}

_STYLE = """
    body { font-family: "DejaVu Sans", Arial, sans-serif; font-size: 11pt; color: #1a1a1a; margin: 0; }
    .header { display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 24px; }
    .header img { max-height: 64px; max-width: 220px; }
    .business-name { font-size: 16pt; font-weight: bold; }
    .muted { color: #555555; font-size: 9.5pt; }
    h1 { font-size: 20pt; margin: 0 0 4px 0; }
    .status-badge { display: inline-block; padding: 2px 10px; border-radius: 4px; font-size: 9.5pt; font-weight: bold; background: #e8e8e8; }
    .parties { display: flex; justify-content: space-between; margin: 24px 0; }
    .parties .block { width: 48%; }
    .parties .label { font-size: 9pt; color: #777777; text-transform: uppercase; margin-bottom: 4px; }
    table.items { width: 100%; border-collapse: collapse; margin-top: 16px; }
    table.items th { text-align: left; border-bottom: 2px solid #333333; padding: 6px 4px; font-size: 9.5pt; }
    table.items td { padding: 6px 4px; border-bottom: 1px solid #dddddd; }
    table.items th.num, table.items td.num { text-align: right; }
    table.totals { width: 280px; margin-left: auto; margin-top: 16px; border-collapse: collapse; }
    table.totals td { padding: 4px 4px; }
    table.totals td.num { text-align: right; }
    table.totals tr.grand-total td { border-top: 2px solid #333333; font-weight: bold; font-size: 12pt; }
    .payment-status { margin-top: 24px; padding: 12px; background: #f5f5f5; border-radius: 4px; }
    .payment-status .label { font-size: 9pt; color: #777777; text-transform: uppercase; }
    .notes { margin-top: 24px; font-size: 9.5pt; color: #333333; }
"""


def _escape(value) -> str:
    return html_escape.escape(str(value)) if value is not None else ""


def _money(value: Decimal) -> str:
    return f"{value:,.2f}"


def _logo_html(organization: Organization) -> str:
    logo = organization.logo
    if not logo or not logo.lower().startswith(("http://", "https://")):
        return ""
    return f'<img src="{_escape(logo)}" alt="{_escape(organization.name)} logo">'


def _discount_label(invoice: Invoice) -> str:
    if invoice.discount_type == DiscountType.PERCENTAGE:
        return f"Discount ({invoice.discount_value}%)"
    return "Discount"


def build_invoice_pdf_html(invoice: Invoice, organization: Organization) -> str:
    """Pure HTML string, no rendering engine involved - everything
    FR-027 asks for (logo, business info, customer info, items,
    taxes/discounts, total, payment status), nothing from the request
    body: every value comes from already-server-computed columns
    (`Invoice.total` et al., FD-041) or a fresh balance query
    (FD-043's `get_invoice_balance`), never trusted client input."""
    customer = invoice.customer
    amount_paid, balance_due = get_invoice_balance(invoice)
    status_label = _STATUS_LABELS[invoice.status.value]

    line_item_rows = "".join(
        f"""
        <tr>
            <td>{_escape(item.description)}</td>
            <td class="num">{item.quantity}</td>
            <td class="num">{_money(item.unit_price)}</td>
            <td class="num">{f"{item.tax_rate}%" if item.tax_rate is not None else "-"}</td>
            <td class="num">{_money(item.line_total)}</td>
        </tr>
        """
        for item in invoice.line_items
    )
    if not line_item_rows:
        line_item_rows = '<tr><td colspan="5" class="muted">No line items.</td></tr>'

    notes_html = f'<div class="notes"><strong>Notes</strong><br>{_escape(invoice.notes)}</div>' if invoice.notes else ""
    payment_terms_html = f" &middot; {_escape(invoice.payment_terms)}" if invoice.payment_terms else ""

    return f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="utf-8">
        <style>{_STYLE}</style>
    </head>
    <body>
        <div class="header">
            <div>
                <div class="business-name">{_escape(organization.name)}</div>
                <div class="muted">
                    {_escape(organization.email) or ""}
                    {" &middot; " + _escape(organization.phone) if organization.phone else ""}
                </div>
                <div class="muted">{_escape(organization.address) or ""}</div>
            </div>
            {_logo_html(organization)}
        </div>

        <h1>Invoice {_escape(invoice.invoice_number)}</h1>
        <span class="status-badge">{_escape(status_label)}</span>

        <div class="parties">
            <div class="block">
                <div class="label">Billed to</div>
                <div><strong>{_escape(customer.name)}</strong></div>
                <div class="muted">{_escape(customer.company) or ""}</div>
                <div class="muted">{_escape(customer.email) or ""}</div>
                <div class="muted">{_escape(customer.phone) or ""}</div>
                <div class="muted">{_escape(customer.address) or ""}</div>
            </div>
            <div class="block">
                <div class="label">Invoice details</div>
                <div class="muted">Issue date: {invoice.issue_date.isoformat() if invoice.issue_date else "-"}</div>
                <div class="muted">Due date: {invoice.due_date.isoformat() if invoice.due_date else "-"}</div>
                <div class="muted">Currency: {_escape(invoice.currency)}{payment_terms_html}</div>
            </div>
        </div>

        <table class="items">
            <thead>
                <tr>
                    <th>Description</th>
                    <th class="num">Qty</th>
                    <th class="num">Unit price</th>
                    <th class="num">Tax</th>
                    <th class="num">Line total</th>
                </tr>
            </thead>
            <tbody>
                {line_item_rows}
            </tbody>
        </table>

        <table class="totals">
            <tr><td>Subtotal</td><td class="num">{_money(invoice.subtotal)}</td></tr>
            <tr><td>Tax</td><td class="num">{_money(invoice.tax_total)}</td></tr>
            <tr><td>{_escape(_discount_label(invoice))}</td><td class="num">-{_money(invoice.discount_total)}</td></tr>
            <tr class="grand-total"><td>Total</td><td class="num">{invoice.currency} {_money(invoice.total)}</td></tr>
        </table>

        <div class="payment-status">
            <div class="label">Payment status: {_escape(status_label)}</div>
            <div>Amount paid: {invoice.currency} {_money(amount_paid)} &middot; Balance due: {invoice.currency} {_money(balance_due)}</div>
        </div>

        {notes_html}
    </body>
    </html>
    """


def generate_invoice_pdf(invoice: Invoice, organization: Organization) -> bytes:
    """Renders `build_invoice_pdf_html`'s output to PDF bytes via
    WeasyPrint. Imported lazily (not at module load time) so the rest
    of the application still starts and every other test still runs
    on a machine where WeasyPrint's native GTK3 dependency isn't
    installed - only this specific call path needs it."""
    from weasyprint import HTML

    html_content = build_invoice_pdf_html(invoice, organization)
    return HTML(string=html_content, url_fetcher=_build_safe_url_fetcher()).write_pdf()


def _is_safe_host(hostname: str) -> bool:
    """`False` for a hostname that resolves to any private/loopback/
    link-local/reserved/multicast/unspecified address - the actual
    fetch is refused if any resolved address is unsafe, not just the
    first one, since a hostname can resolve to several. `False` on a
    DNS failure too (nothing to fetch, nothing to risk)."""
    try:
        resolved = socket.getaddrinfo(hostname, None)
    except socket.gaierror:
        return False
    for *_, sockaddr in resolved:
        try:
            ip = ip_address(sockaddr[0])
        except ValueError:
            return False
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_multicast or ip.is_reserved or ip.is_unspecified:
            return False
    return True


def _build_safe_url_fetcher():
    """Builds a WeasyPrint `url_fetcher` - a `URLFetcher` subclass,
    not just an arbitrary callable, since WeasyPrint's own internals
    read attributes (e.g. `_fail_on_errors`) directly off whatever
    object is passed, duck-typing on the real class rather than just
    calling it. Defined *inside* this function, not at module level,
    so importing `app.invoices.pdf` still never needs
    `weasyprint.urls` (and therefore never needs WeasyPrint's native
    GTK3 dependency) - only actually generating a PDF does.

    Adds the internal/private-address check `_is_safe_host` performs
    *before* any request is made, on top of the base `URLFetcher` -
    see this module's own docstring for why the scheme check in
    `_logo_html` alone isn't enough. `allow_redirects=False` - a logo
    image has no legitimate reason to redirect, and disabling it
    entirely is simpler than re-validating every hop."""
    from weasyprint.urls import URLFetcher

    class _SafeURLFetcher(URLFetcher):
        def __init__(self):
            super().__init__(allowed_protocols={"http", "https"}, allow_redirects=False, timeout=5)

        def fetch(self, url, headers=None):
            hostname = urlparse(url).hostname
            if not hostname or not _is_safe_host(hostname):
                raise ValueError(f"Refusing to fetch an internal/private address: {url}")
            return super().fetch(url, headers)

    return _SafeURLFetcher()
