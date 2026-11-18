import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import type { DepartmentAnalyticsPublic, RevenueByDayEntry } from "@/types/analytics";

// Chart components only - no data fetching here (AnalyticsPage owns
// that). Money/count values are parsed to numbers purely for plotting;
// the underlying decimal-string values from the API are what every
// stat card elsewhere on this page still displays and are the only
// thing that would ever be sent back to the API (types/analytics.ts's
// own note).

export function RevenueByDayChart({ data }: { data: RevenueByDayEntry[] }) {
  if (data.length === 0) {
    return <p className="text-sm text-foreground/70">No payments recorded in this period.</p>;
  }
  const points = data.map((entry) => ({ date: entry.date, amount: Number(entry.amount) }));
  return (
    <ResponsiveContainer width="100%" height={240}>
      <LineChart data={points} margin={{ top: 8, right: 16, bottom: 8, left: 0 }}>
        <CartesianGrid strokeDasharray="3 3" stroke="var(--color-border)" />
        <XAxis dataKey="date" tick={{ fontSize: 12 }} />
        <YAxis tick={{ fontSize: 12 }} />
        <Tooltip />
        <Line type="monotone" dataKey="amount" name="Revenue" stroke="var(--color-primary)" strokeWidth={2} dot={false} />
      </LineChart>
    </ResponsiveContainer>
  );
}

const STATUS_COLORS: Record<string, string> = {
  draft: "var(--color-border)",
  sent: "var(--color-secondary)",
  partially_paid: "var(--color-warning)",
  paid: "var(--color-success)",
  overdue: "var(--color-destructive)",
  cancelled: "var(--color-border)",
};

export function InvoiceDistributionChart({ distribution }: { distribution: Record<string, number> }) {
  const entries = Object.entries(distribution).filter(([, count]) => count > 0);
  if (entries.length === 0) {
    return <p className="text-sm text-foreground/70">No invoices issued in this period.</p>;
  }
  const points = entries.map(([status, count]) => ({ status, count }));
  return (
    <ResponsiveContainer width="100%" height={240}>
      <BarChart data={points} margin={{ top: 8, right: 16, bottom: 8, left: 0 }}>
        <CartesianGrid strokeDasharray="3 3" stroke="var(--color-border)" />
        <XAxis dataKey="status" tick={{ fontSize: 12 }} />
        <YAxis tick={{ fontSize: 12 }} allowDecimals={false} />
        <Tooltip />
        <Bar dataKey="count" name="Invoices">
          {points.map((point) => (
            <Cell key={point.status} fill={STATUS_COLORS[point.status] ?? "var(--color-primary)"} />
          ))}
        </Bar>
      </BarChart>
    </ResponsiveContainer>
  );
}

export function DepartmentComparisonChart({ departments }: { departments: DepartmentAnalyticsPublic[] }) {
  if (departments.length === 0) {
    return <p className="text-sm text-foreground/70">No departments to compare.</p>;
  }
  const points = departments.map((department) => ({
    name: department.department_name ?? "Unassigned",
    active: department.active_tasks,
    completed: department.completed_tasks,
    overdue: department.overdue_tasks,
  }));
  return (
    <ResponsiveContainer width="100%" height={260}>
      <BarChart data={points} margin={{ top: 8, right: 16, bottom: 8, left: 0 }}>
        <CartesianGrid strokeDasharray="3 3" stroke="var(--color-border)" />
        <XAxis dataKey="name" tick={{ fontSize: 12 }} />
        <YAxis tick={{ fontSize: 12 }} allowDecimals={false} />
        <Tooltip />
        <Bar dataKey="active" name="Active" fill="var(--color-secondary)" />
        <Bar dataKey="completed" name="Completed" fill="var(--color-success)" />
        <Bar dataKey="overdue" name="Overdue" fill="var(--color-destructive)" />
      </BarChart>
    </ResponsiveContainer>
  );
}
