import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select } from "@/components/ui/select";
import type { AnalyticsPeriod } from "@/types/analytics";

// FR-034's own named date-filter taxonomy (backend/app/analytics/schemas.py) -
// period_start/period_end only ever matter, and are only ever shown,
// when period is "custom".
const PERIOD_OPTIONS: { value: AnalyticsPeriod; label: string }[] = [
  { value: "last_7_days", label: "Last 7 days" },
  { value: "last_30_days", label: "Last 30 days" },
  { value: "last_90_days", label: "Last 90 days" },
  { value: "current_month", label: "Current month" },
  { value: "previous_month", label: "Previous month" },
  { value: "custom", label: "Custom range" },
];

export interface PeriodValue {
  period: AnalyticsPeriod;
  periodStart: string;
  periodEnd: string;
}

export function PeriodSelector({ value, onChange }: { value: PeriodValue; onChange: (next: PeriodValue) => void }) {
  return (
    <div className="flex flex-wrap items-end gap-3">
      <div className="flex flex-col gap-1.5">
        <Label htmlFor="analytics-period">Period</Label>
        <Select
          id="analytics-period"
          value={value.period}
          onChange={(event) => onChange({ ...value, period: event.target.value as AnalyticsPeriod })}
        >
          {PERIOD_OPTIONS.map((option) => (
            <option key={option.value} value={option.value}>
              {option.label}
            </option>
          ))}
        </Select>
      </div>
      {value.period === "custom" && (
        <>
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="analytics-period-start">From</Label>
            <Input
              id="analytics-period-start"
              type="date"
              value={value.periodStart}
              onChange={(event) => onChange({ ...value, periodStart: event.target.value })}
            />
          </div>
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="analytics-period-end">To</Label>
            <Input
              id="analytics-period-end"
              type="date"
              value={value.periodEnd}
              onChange={(event) => onChange({ ...value, periodEnd: event.target.value })}
            />
          </div>
        </>
      )}
    </div>
  );
}
