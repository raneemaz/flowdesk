import { useQuery } from "@tanstack/react-query";

import { getFinancialAnalytics } from "@/api/analytics";
import { RevenueByDayChart } from "@/features/analytics/charts";
import { Loading, QueryError, Section, StatCard } from "@/features/analytics/widgets";

const CURRENT_MONTH = { period: "current_month" } as const;

// Spec Section 12.3's Accountant dashboard: "invoices, outstanding
// balances, payments, monthly collections" - every one of these is a
// field already on FD-052's own financial analytics response
// (LIMITED+Accountant scope, honored server-side), so this dashboard
// is a single call, not four.
export function AccountantDashboard({ organizationId }: { organizationId: string }) {
  const financeQuery = useQuery({
    queryKey: ["dashboard-finance", organizationId],
    queryFn: () => getFinancialAnalytics(organizationId, CURRENT_MONTH),
    enabled: Boolean(organizationId),
  });

  return (
    <div className="flex flex-col gap-6">
      <Section title="Finance (this month)">
        {financeQuery.isPending && <Loading />}
        {financeQuery.isError && <QueryError error={financeQuery.error} />}
        {financeQuery.data && (
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
            <StatCard label="Invoiced" value={financeQuery.data.total_invoiced} />
            <StatCard label="Collected" value={financeQuery.data.total_collected} />
            <StatCard label="Outstanding" value={financeQuery.data.outstanding_balance} />
            <StatCard label="Monthly collections" value={financeQuery.data.monthly_revenue_collected} />
          </div>
        )}
      </Section>

      <Section title="Payments over time">
        {financeQuery.data && <RevenueByDayChart data={financeQuery.data.revenue_by_day} />}
      </Section>

      <Section title="Recent payments">
        {financeQuery.data && financeQuery.data.recent_payments.length === 0 && (
          <p className="text-sm text-foreground/70">No payments recorded yet.</p>
        )}
        {financeQuery.data && financeQuery.data.recent_payments.length > 0 && (
          <ul className="flex flex-col gap-2">
            {financeQuery.data.recent_payments.map((payment) => (
              <li key={payment.id} className="flex items-center justify-between rounded-md border border-border bg-card p-3 text-sm">
                <span>{payment.payment_date}</span>
                <span className="font-medium">{payment.amount}</span>
              </li>
            ))}
          </ul>
        )}
      </Section>
    </div>
  );
}
