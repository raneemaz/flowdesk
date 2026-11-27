import { lazy, Suspense, type ReactNode } from "react";
import { createBrowserRouter } from "react-router-dom";

import { DashboardLayout } from "@/components/DashboardLayout";
import { AuthPageSkeleton } from "@/components/PageSkeleton";
import { ProtectedRoute } from "@/routes/ProtectedRoute";

// Every page is its own code-split chunk, fetched the first time its
// route is visited - so a first load only downloads the shell plus the
// one page being opened, not all 22 pages and the chart library.
// DashboardLayout wraps its <Outlet> in a Suspense boundary with a
// skeleton (the sidebar and top bar stay on screen); login and
// register get their own boundary below since they sit outside it.
const AIReportDetailPage = lazy(() => import("@/pages/AIReportDetailPage").then((m) => ({ default: m.AIReportDetailPage })));
const AIReportsPage = lazy(() => import("@/pages/AIReportsPage").then((m) => ({ default: m.AIReportsPage })));
const AnalyticsPage = lazy(() => import("@/pages/AnalyticsPage").then((m) => ({ default: m.AnalyticsPage })));
const CreateOrganizationPage = lazy(() => import("@/pages/CreateOrganizationPage").then((m) => ({ default: m.CreateOrganizationPage })));
const CustomerDetailPage = lazy(() => import("@/pages/CustomerDetailPage").then((m) => ({ default: m.CustomerDetailPage })));
const CustomerListPage = lazy(() => import("@/pages/CustomerListPage").then((m) => ({ default: m.CustomerListPage })));
const DepartmentsPage = lazy(() => import("@/pages/DepartmentsPage").then((m) => ({ default: m.DepartmentsPage })));
const EmployeeDirectoryPage = lazy(() => import("@/pages/EmployeeDirectoryPage").then((m) => ({ default: m.EmployeeDirectoryPage })));
const EmployeeProfilePage = lazy(() => import("@/pages/EmployeeProfilePage").then((m) => ({ default: m.EmployeeProfilePage })));
const HomePage = lazy(() => import("@/pages/HomePage").then((m) => ({ default: m.HomePage })));
const InvoiceDetailPage = lazy(() => import("@/pages/InvoiceDetailPage").then((m) => ({ default: m.InvoiceDetailPage })));
const InvoiceFormPage = lazy(() => import("@/pages/InvoiceFormPage").then((m) => ({ default: m.InvoiceFormPage })));
const InvoiceListPage = lazy(() => import("@/pages/InvoiceListPage").then((m) => ({ default: m.InvoiceListPage })));
const LoginPage = lazy(() => import("@/pages/LoginPage").then((m) => ({ default: m.LoginPage })));
const MyTasksPage = lazy(() => import("@/pages/MyTasksPage").then((m) => ({ default: m.MyTasksPage })));
const NotificationsPage = lazy(() => import("@/pages/NotificationsPage").then((m) => ({ default: m.NotificationsPage })));
const ActivityPage = lazy(() => import("@/pages/ActivityPage").then((m) => ({ default: m.ActivityPage })));
const LandingPage = lazy(() => import("@/pages/LandingPage").then((m) => ({ default: m.LandingPage })));
const SettingsPage = lazy(() => import("@/pages/SettingsPage").then((m) => ({ default: m.SettingsPage })));
const RegisterPage = lazy(() => import("@/pages/RegisterPage").then((m) => ({ default: m.RegisterPage })));
const RequestDetailPage = lazy(() => import("@/pages/RequestDetailPage").then((m) => ({ default: m.RequestDetailPage })));
const RequestListPage = lazy(() => import("@/pages/RequestListPage").then((m) => ({ default: m.RequestListPage })));
const TaskBoardPage = lazy(() => import("@/pages/TaskBoardPage").then((m) => ({ default: m.TaskBoardPage })));
const TaskCalendarPage = lazy(() => import("@/pages/TaskCalendarPage").then((m) => ({ default: m.TaskCalendarPage })));
const TaskDetailPage = lazy(() => import("@/pages/TaskDetailPage").then((m) => ({ default: m.TaskDetailPage })));
const TaskListPage = lazy(() => import("@/pages/TaskListPage").then((m) => ({ default: m.TaskListPage })));

function standalone(page: ReactNode) {
  return <Suspense fallback={<AuthPageSkeleton />}>{page}</Suspense>;
}

export const router = createBrowserRouter([
  { path: "/welcome", element: standalone(<LandingPage />) },
  { path: "/login", element: standalone(<LoginPage />) },
  { path: "/register", element: standalone(<RegisterPage />) },
  {
    element: <ProtectedRoute />,
    children: [
      {
        element: <DashboardLayout />,
        children: [
          { path: "/", element: <HomePage /> },
          { path: "/organizations/new", element: <CreateOrganizationPage /> },
          { path: "/employees", element: <EmployeeDirectoryPage /> },
          { path: "/employees/:membershipId", element: <EmployeeProfilePage /> },
          { path: "/departments", element: <DepartmentsPage /> },
          { path: "/tasks", element: <TaskListPage /> },
          { path: "/tasks/board", element: <TaskBoardPage /> },
          { path: "/tasks/calendar", element: <TaskCalendarPage /> },
          { path: "/tasks/mine", element: <MyTasksPage /> },
          { path: "/tasks/:taskId", element: <TaskDetailPage /> },
          { path: "/customers", element: <CustomerListPage /> },
          { path: "/customers/:customerId", element: <CustomerDetailPage /> },
          { path: "/requests", element: <RequestListPage /> },
          { path: "/requests/:requestId", element: <RequestDetailPage /> },
          { path: "/invoices", element: <InvoiceListPage /> },
          { path: "/invoices/new", element: <InvoiceFormPage /> },
          { path: "/invoices/:invoiceId", element: <InvoiceDetailPage /> },
          { path: "/invoices/:invoiceId/edit", element: <InvoiceFormPage /> },
          { path: "/notifications", element: <NotificationsPage /> },
          { path: "/analytics", element: <AnalyticsPage /> },
          { path: "/ai-reports", element: <AIReportsPage /> },
          { path: "/ai-reports/:reportId", element: <AIReportDetailPage /> },
          { path: "/activity", element: <ActivityPage /> },
          { path: "/settings", element: <SettingsPage /> },
        ],
      },
    ],
  },
]);
