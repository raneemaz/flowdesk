"""FD-054: CSV/PDF export for the four analytics categories FD-052
already exposes as JSON (FR-035). Every export route in
`app.analytics.routes` re-runs the exact same service call, scope
check, and query-schema validation its JSON sibling already does -
the only new thing here is rendering that same already-authorized
data as a CSV or PDF file instead of a JSON body. This module does no
authorization or period-resolution of its own, and takes only
already-computed service-layer results as input.

**CSV injection defense** (`_sanitize_csv_cell`): a cell whose text
starts with `=`, `+`, `-`, `@`, a tab, or a CR is prefixed with a
leading `'` - the standard defusing prefix spreadsheet programs
(Excel, Google Sheets, LibreOffice) treat as "this is text, not a
formula" before evaluating a cell. Every value this module writes to
a CSV originates from server-computed analytics data (counts,
decimals, dates) or a membership/department's own display name -
FD-019/FD-020 impose no character restriction on those names, so a
name is organization-controlled free text and gets the same
sanitization as everything else rather than being special-cased as
"probably safe."

**PDF rendering** reuses the exact same lazy-WeasyPrint-import pattern
`app.invoices.pdf.generate_invoice_pdf` already established (FD-045) -
so the rest of the application still starts, and every other test
still runs, on a machine without WeasyPrint's native GTK3 dependency;
only actually building a PDF needs it. This module needs none of that
other module's URL-fetcher SSRF defense, since nothing rendered here
ever embeds an organization-supplied URL (no logo, no free-text HTML)."""

import csv
import html as html_escape
import io
from datetime import date
from decimal import Decimal

_CSV_INJECTION_PREFIXES = ("=", "+", "-", "@", "\t", "\r")

# A leading UTF-8 BOM so Excel (which otherwise guesses the system
# codepage) recognizes the file as UTF-8 rather than mangling any
# non-ASCII character in an organization/department/employee name.
_CSV_BOM = "﻿"


def _sanitize_csv_cell(value) -> str:
    text = "" if value is None else str(value)
    if text.startswith(_CSV_INJECTION_PREFIXES):
        return "'" + text
    return text


def _csv_from_sections(sections: list[tuple[str, list[str], list[list]]]) -> str:
    """`sections` is a list of `(title, headers, rows)` triples - one
    table per section, a title row then a header row then data rows,
    separated by a blank line. Every category but Finance has exactly
    one section; Finance has four (summary/revenue-by-day/invoice-
    distribution/recent-payments)."""
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    for index, (title, headers, rows) in enumerate(sections):
        if index > 0:
            writer.writerow([])
        writer.writerow([title])
        writer.writerow(headers)
        for row in rows:
            writer.writerow([_sanitize_csv_cell(cell) for cell in row])
    return _CSV_BOM + buffer.getvalue()


def _escape(value) -> str:
    return html_escape.escape(str(value)) if value is not None else ""


def _html_table(title: str, headers: list[str], rows: list[list]) -> str:
    header_html = "".join(f"<th>{_escape(header)}</th>" for header in headers)
    if rows:
        body_html = "".join(
            "<tr>" + "".join(f"<td>{_escape(cell)}</td>" for cell in row) + "</tr>" for row in rows
        )
    else:
        body_html = f'<tr><td colspan="{len(headers)}" class="muted">No data for this period.</td></tr>'
    return f"""
    <h2>{_escape(title)}</h2>
    <table>
        <thead><tr>{header_html}</tr></thead>
        <tbody>{body_html}</tbody>
    </table>
    """


_PDF_STYLE = """
    body { font-family: "DejaVu Sans", Arial, sans-serif; font-size: 10pt; color: #1a1a1a; }
    h1 { font-size: 16pt; margin-bottom: 2px; }
    .muted { color: #666666; font-size: 9pt; }
    h2 { font-size: 12pt; margin-top: 20px; margin-bottom: 4px; }
    table { width: 100%; border-collapse: collapse; margin-top: 4px; }
    th { text-align: left; border-bottom: 2px solid #333333; padding: 4px; font-size: 9pt; }
    td { padding: 4px; border-bottom: 1px solid #dddddd; font-size: 9.5pt; }
    td.muted { color: #888888; }
"""


def _report_pdf_html(
    report_title: str,
    organization_name: str,
    period_start: date,
    period_end: date,
    sections: list[tuple[str, list[str], list[list]]],
) -> str:
    tables_html = "".join(_html_table(title, headers, rows) for title, headers, rows in sections)
    return f"""
    <!DOCTYPE html>
    <html>
    <head><meta charset="utf-8"><style>{_PDF_STYLE}</style></head>
    <body>
        <h1>{_escape(organization_name)} &mdash; {_escape(report_title)}</h1>
        <div class="muted">Period: {period_start.isoformat()} to {period_end.isoformat()}</div>
        {tables_html}
    </body>
    </html>
    """


def _render_pdf(html_content: str) -> bytes:
    """Imported lazily, same reason as `app.invoices.pdf.generate_invoice_pdf`."""
    from weasyprint import HTML

    return HTML(string=html_content).write_pdf()


def _money(value: Decimal) -> str:
    return f"{value:.2f}"


def _build(report_title: str, organization_name: str, period_start: date, period_end: date, sections, fmt: str):
    if fmt == "csv":
        return _csv_from_sections(sections)
    return _render_pdf(_report_pdf_html(report_title, organization_name, period_start, period_end, sections))


def build_overview_export(metrics: dict, organization_name: str, fmt: str):
    """FR-030/FR-035. `metrics` is `get_overview_metrics`'s own return
    value - one row of the same fields the JSON endpoint returns."""
    headers = [
        "Employee count",
        "Active tasks",
        "Completed tasks",
        "Overdue tasks",
        "Open requests",
        "Monthly invoiced",
        "Monthly collected",
    ]
    row = [
        metrics["employee_count"],
        metrics["active_tasks"],
        metrics["completed_tasks"],
        metrics["overdue_tasks"],
        metrics["open_requests"],
        _money(metrics["monthly_invoiced"]),
        _money(metrics["monthly_collected"]),
    ]
    sections = [("Overview", headers, [row])]
    return _build("Overview Report", organization_name, metrics["period_start"], metrics["period_end"], sections, fmt)


def build_employee_export(results: list[dict], organization_name: str, period_start: date, period_end: date, fmt: str):
    """FR-031/FR-035. `results` is `get_employee_performance`'s own
    return value - `completion_rate`/`avg_completion_time_hours` render
    as blank, never a fabricated `0%`/`0.0`, when there's no signal to
    report yet (same "`None`, not `0`" rule the service layer itself
    documents)."""
    headers = [
        "Employee",
        "Assigned tasks",
        "Completed tasks",
        "Overdue tasks",
        "Completion rate",
        "Avg completion time (hours)",
    ]
    rows = [
        [
            row["name"],
            row["assigned_tasks"],
            row["completed_tasks"],
            row["overdue_tasks"],
            f"{row['completion_rate']:.0%}" if row["completion_rate"] is not None else "",
            f"{row['avg_completion_time_hours']:.1f}" if row["avg_completion_time_hours"] is not None else "",
        ]
        for row in results
    ]
    sections = [("Employee performance", headers, rows)]
    return _build("Employee Performance Report", organization_name, period_start, period_end, sections, fmt)


def build_department_export(results: list[dict], organization_name: str, period_start: date, period_end: date, fmt: str):
    """FR-032/FR-035. `results` is `get_department_analytics`'s own
    return value - the trailing `department_id: None` entry (genuinely
    department-less tasks) renders as "No department", never blank."""
    headers = ["Department", "Active tasks", "Completed tasks", "Overdue tasks", "Request volume"]
    rows = [
        [
            row["department_name"] if row["department_name"] is not None else "No department",
            row["active_tasks"],
            row["completed_tasks"],
            row["overdue_tasks"],
            row["request_volume"],
        ]
        for row in results
    ]
    sections = [("Department analytics", headers, rows)]
    return _build("Department Analytics Report", organization_name, period_start, period_end, sections, fmt)


def build_finance_export(analytics: dict, organization_name: str, fmt: str):
    """FR-033/FR-035. `analytics` is `get_financial_analytics`'s own
    return value. Four sections, mirroring the JSON response's own
    shape rather than flattening it into one table: a single-row
    summary, then the two genuinely period-scoped time series
    (`revenue_by_day`/`invoice_distribution`), then the fixed-size
    `recent_payments` list (FD-044's own "a dashboard widget, not a
    payments browser" - unchanged here)."""
    summary_headers = [
        "Total invoiced",
        "Total collected",
        "Outstanding balance",
        "Overdue invoices",
        "Monthly revenue collected",
    ]
    summary_row = [
        _money(analytics["total_invoiced"]),
        _money(analytics["total_collected"]),
        _money(analytics["outstanding_balance"]),
        analytics["overdue_invoice_count"],
        _money(analytics["monthly_revenue_collected"]),
    ]

    revenue_headers = ["Date", "Amount"]
    revenue_rows = [[row["date"].isoformat(), _money(row["amount"])] for row in analytics["revenue_by_day"]]

    distribution_headers = ["Invoice status", "Invoice count"]
    distribution_rows = [[status, count] for status, count in analytics["invoice_distribution"].items()]

    payments_headers = ["Payment date", "Amount", "Method", "Reference"]
    payments_rows = [
        [payment.payment_date.isoformat(), _money(payment.amount), payment.method, payment.reference or ""]
        for payment in analytics["recent_payments"]
    ]

    sections = [
        ("Financial summary", summary_headers, [summary_row]),
        ("Revenue by day", revenue_headers, revenue_rows),
        ("Invoice distribution", distribution_headers, distribution_rows),
        ("Recent payments", payments_headers, payments_rows),
    ]
    return _build(
        "Financial Report", organization_name, analytics["period_start"], analytics["period_end"], sections, fmt
    )
