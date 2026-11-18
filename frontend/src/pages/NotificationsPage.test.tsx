import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { afterEach, describe, expect, it, vi } from "vitest";
import { createMemoryRouter, RouterProvider } from "react-router-dom";

import * as authApi from "@/api/auth";
import * as notificationsApi from "@/api/notifications";
import * as organizationsApi from "@/api/organizations";
import { AuthProvider } from "@/contexts/AuthContext";
import { OrganizationProvider } from "@/contexts/OrganizationContext";
import { NotificationsPage } from "@/pages/NotificationsPage";
import type { MembershipPublic, OrganizationPublic } from "@/types/organization";
import type { NotificationPublic } from "@/types/notification";
import type { UserPublic } from "@/types/user";

const USER: UserPublic = { id: "u1", name: "Ada", email: "ada@example.com", status: "active", created_at: "now" };
const ORG: OrganizationPublic = {
  id: "org-1",
  name: "Acme Inc",
  slug: "acme-inc",
  logo: null,
  email: null,
  phone: null,
  address: null,
  currency: "USD",
  timezone: "UTC",
  date_format: null,
  created_at: "now",
};

const UNREAD_NOTIFICATION: NotificationPublic = {
  id: "n1",
  organization_id: "org-1",
  recipient_membership_id: "m1",
  type: "task_assigned",
  title: "You were assigned a task",
  body: 'You were assigned the task "Ship it".',
  entity_type: "task",
  entity_id: "t1",
  read_at: null,
  created_at: "2026-01-01T00:00:00Z",
};

const READ_NOTIFICATION: NotificationPublic = {
  ...UNREAD_NOTIFICATION,
  id: "n2",
  title: "Invoice paid",
  body: "Invoice INV-0001 was paid in full.",
  entity_type: "invoice",
  entity_id: "inv1",
  read_at: "2026-01-02T00:00:00Z",
};

function membership(role: MembershipPublic["role"] = "owner"): MembershipPublic {
  return { organization: ORG, role, status: "active", joined_at: "now" };
}

function renderPage() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const router = createMemoryRouter(
    [
      { path: "/notifications", element: <NotificationsPage /> },
      { path: "/tasks/:taskId", element: <div>Task detail page</div> },
      { path: "/", element: <div>Home page</div> },
    ],
    { initialEntries: ["/notifications"] },
  );

  render(
    <QueryClientProvider client={queryClient}>
      <AuthProvider>
        <OrganizationProvider>
          <RouterProvider router={router} />
        </OrganizationProvider>
      </AuthProvider>
    </QueryClientProvider>,
  );
}

function mockAuthenticated() {
  vi.spyOn(authApi, "getCurrentUser").mockResolvedValue(USER);
  vi.spyOn(organizationsApi, "listOrganizations").mockResolvedValue([membership()]);
  sessionStorage.setItem("flowdesk:csrf_token", "csrf-abc");
}

describe("NotificationsPage", () => {
  afterEach(() => {
    vi.restoreAllMocks();
    sessionStorage.clear();
    localStorage.clear();
  });

  it("lists the caller's own notifications with an unread indicator", async () => {
    mockAuthenticated();
    vi.spyOn(notificationsApi, "listNotifications").mockResolvedValue({
      notifications: [UNREAD_NOTIFICATION, READ_NOTIFICATION],
      meta: { page: 1, per_page: 20, total: 2, total_pages: 1 },
    });

    renderPage();

    expect(await screen.findByText("You were assigned a task")).toBeInTheDocument();
    expect(screen.getByText("Invoice paid")).toBeInTheDocument();
    expect(screen.getByText("(unread)")).toBeInTheDocument();
  });

  it("shows an empty state when there are no notifications", async () => {
    mockAuthenticated();
    vi.spyOn(notificationsApi, "listNotifications").mockResolvedValue({
      notifications: [],
      meta: { page: 1, per_page: 20, total: 0, total_pages: 0 },
    });

    renderPage();

    expect(await screen.findByText("No notifications yet.")).toBeInTheDocument();
  });

  it("links a notification to its related record", async () => {
    mockAuthenticated();
    vi.spyOn(notificationsApi, "listNotifications").mockResolvedValue({
      notifications: [UNREAD_NOTIFICATION],
      meta: { page: 1, per_page: 20, total: 1, total_pages: 1 },
    });

    renderPage();

    const link = await screen.findByRole("link", { name: "You were assigned a task" });
    expect(link).toHaveAttribute("href", "/tasks/t1");
  });

  it("marks a single notification read", async () => {
    mockAuthenticated();
    vi.spyOn(notificationsApi, "listNotifications").mockResolvedValue({
      notifications: [UNREAD_NOTIFICATION],
      meta: { page: 1, per_page: 20, total: 1, total_pages: 1 },
    });
    const markReadSpy = vi.spyOn(notificationsApi, "markNotificationRead").mockResolvedValue({
      ...UNREAD_NOTIFICATION,
      read_at: "2026-01-03T00:00:00Z",
    });

    const user = userEvent.setup();
    renderPage();

    await user.click(await screen.findByRole("button", { name: "Mark read" }));

    await waitFor(() => expect(markReadSpy).toHaveBeenCalledWith("org-1", "n1", "csrf-abc"));
  });

  it("marks every notification read", async () => {
    mockAuthenticated();
    vi.spyOn(notificationsApi, "listNotifications").mockResolvedValue({
      notifications: [UNREAD_NOTIFICATION],
      meta: { page: 1, per_page: 20, total: 1, total_pages: 1 },
    });
    const markAllReadSpy = vi.spyOn(notificationsApi, "markAllNotificationsRead").mockResolvedValue({ updated_count: 1 });

    const user = userEvent.setup();
    renderPage();

    await user.click(await screen.findByRole("button", { name: "Mark all read (1)" }));

    await waitFor(() => expect(markAllReadSpy).toHaveBeenCalledWith("org-1", "csrf-abc"));
  });

  it("disables mark-all-read when nothing is unread", async () => {
    mockAuthenticated();
    vi.spyOn(notificationsApi, "listNotifications").mockResolvedValue({
      notifications: [READ_NOTIFICATION],
      meta: { page: 1, per_page: 20, total: 0, total_pages: 0 },
    });

    renderPage();

    expect(await screen.findByRole("button", { name: "Mark all read" })).toBeDisabled();
  });

  it("toggles the unread-only filter", async () => {
    mockAuthenticated();
    const listSpy = vi.spyOn(notificationsApi, "listNotifications").mockResolvedValue({
      notifications: [UNREAD_NOTIFICATION],
      meta: { page: 1, per_page: 20, total: 1, total_pages: 1 },
    });

    const user = userEvent.setup();
    renderPage();

    await screen.findByText("You were assigned a task");
    await user.click(screen.getByRole("button", { name: "Show unread only" }));

    await waitFor(() => expect(listSpy).toHaveBeenCalledWith("org-1", { unreadOnly: true, page: 1, perPage: 20 }));
  });
});
