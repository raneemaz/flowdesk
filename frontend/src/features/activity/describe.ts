import { ROLE_LABELS } from "@/features/employees/constants";
import type { ActivityLogPublic } from "@/types/activity";
import type { MembershipRole } from "@/types/organization";

// Turns a raw activity-log entry (backend action names + metadata, see
// every `log_activity(...)` call in backend/app) into a sentence and,
// where the record still exists, a link to it. Unknown actions fall
// back to a readable version of the action name rather than breaking.

export interface DescribedActivity {
  text: string;
  link: string | null;
}

const ENTITY_LINKS: Record<string, string> = {
  task: "/tasks",
  customer_request: "/requests",
  invoice: "/invoices",
  membership: "/employees",
};

function str(value: unknown): string | null {
  return typeof value === "string" && value.length > 0 ? value : null;
}

// "task “Payroll”" when the entry carries a title, otherwise "a task".
function named(kind: string, title: unknown): string {
  const text = str(title);
  return text ? `${kind} “${text}”` : `a ${kind}`;
}

function roleLabel(value: unknown): string {
  const role = str(value) as MembershipRole | null;
  return role ? (ROLE_LABELS[role] ?? role) : "a new role";
}

const FIELD_LABELS: Record<string, string> = {
  name: "name",
  email: "contact email",
  phone: "phone",
  address: "address",
  currency: "currency",
  timezone: "timezone",
  date_format: "date format",
  logo: "logo",
};

export function describeActivity(entry: ActivityLogPublic, nameOf: (membershipId: string | null) => string): DescribedActivity {
  const actor = nameOf(entry.actor_membership_id);
  const meta = entry.metadata ?? {};
  const base = ENTITY_LINKS[entry.entity_type];
  const link = base ? `${base}/${entry.entity_id}` : null;

  switch (entry.action) {
    case "task_created":
      return { text: `${actor} created ${named("task", meta.title)}`, link };
    case "task_assigned":
      return {
        text: `${actor} assigned a task to ${nameOf(str(meta.assignee_membership_id))}`,
        link,
      };
    case "task_completed":
      return { text: `${actor} completed ${named("task", meta.title)}`, link };
    case "task_deleted":
      return { text: `${actor} deleted ${named("task", meta.title)}`, link: null };
    case "request_created":
      return { text: `${actor} logged ${named("request", meta.title)}`, link };
    case "request_deleted":
      return { text: `${actor} deleted ${named("request", meta.title)}`, link: null };
    case "request_resolved":
      return { text: `${actor} resolved ${named("request", meta.title)}`, link };
    case "invoice_created":
      return { text: `${actor} created invoice ${str(meta.invoice_number) ?? ""}`.trimEnd(), link };
    case "payment_recorded":
      return {
        text: `${actor} recorded a payment${str(meta.amount) ? ` of ${meta.amount}` : ""}`,
        link: str(meta.invoice_id) ? `/invoices/${meta.invoice_id}` : null,
      };
    case "employee_invited":
      return {
        text: `${actor} invited ${str(meta.email) ?? "someone"} as ${roleLabel(meta.role)}`,
        link: null,
      };
    case "employee_deactivated":
      return { text: `${actor} marked ${nameOf(entry.entity_id)} as inactive`, link };
    case "member_role_changed":
      return {
        text: `${actor} changed ${nameOf(entry.entity_id)}’s role from ${roleLabel(meta.from)} to ${roleLabel(meta.to)}`,
        link,
      };
    case "member_access_removed":
      return { text: `${actor} removed ${nameOf(entry.entity_id)}’s access`, link: null };
    case "member_access_restored":
      return { text: `${actor} restored ${nameOf(entry.entity_id)}’s access`, link };
    case "organization_updated": {
      const fields = Array.isArray(meta.fields)
        ? meta.fields.map((field) => FIELD_LABELS[String(field)] ?? String(field).replace(/_/g, " "))
        : [];
      return {
        text: `${actor} updated the organization’s ${fields.length > 0 ? fields.join(", ") : "settings"}`,
        link: "/settings",
      };
    }
    default: {
      const readable = entry.action.replace(/_/g, " ");
      return { text: `${actor}: ${readable}`, link };
    }
  }
}
