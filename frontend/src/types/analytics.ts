// Mirrors backend/openapi.yaml's OverviewAnalyticsPublic/
// EmployeePerformancePublic/DepartmentAnalyticsPublic/
// FinancialAnalyticsPublic schemas exactly (FD-052). Money fields are
// decimal strings, never numbers - same convention as types/invoice.ts -
// except where a chart genuinely needs to plot one as a number (see
// features/analytics/charts.tsx), which is a display-only parse, never
// something submitted back to the API.
import type { PaymentPublic } from "@/types/payment";

export type AnalyticsPeriod = "last_7_days" | "last_30_days" | "last_90_days" | "current_month" | "previous_month" | "custom";

export interface OverviewAnalyticsPublic {
  period_start: string;
  period_end: string;
  employee_count: number;
  active_tasks: number;
  completed_tasks: number;
  overdue_tasks: number;
  open_requests: number;
  monthly_invoiced: string;
  monthly_collected: string;
}

export interface EmployeePerformancePublic {
  membership_id: string;
  name: string;
  assigned_tasks: number;
  completed_tasks: number;
  overdue_tasks: number;
  completion_rate: number | null;
  avg_completion_time_hours: number | null;
}

export interface DepartmentAnalyticsPublic {
  department_id: string | null;
  department_name: string | null;
  active_tasks: number;
  completed_tasks: number;
  overdue_tasks: number;
  request_volume: number;
}

export interface RevenueByDayEntry {
  date: string;
  amount: string;
}

export interface FinancialAnalyticsPublic {
  total_invoiced: string;
  total_collected: string;
  outstanding_balance: string;
  overdue_invoice_count: number;
  period_start: string;
  period_end: string;
  monthly_revenue_collected: string;
  recent_payments: PaymentPublic[];
  revenue_by_day: RevenueByDayEntry[];
  invoice_distribution: Record<string, number>;
}
