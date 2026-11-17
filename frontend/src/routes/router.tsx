import { createBrowserRouter } from "react-router-dom";

import { CreateOrganizationPage } from "@/pages/CreateOrganizationPage";
import { CustomerDetailPage } from "@/pages/CustomerDetailPage";
import { CustomerListPage } from "@/pages/CustomerListPage";
import { DepartmentsPage } from "@/pages/DepartmentsPage";
import { EmployeeDirectoryPage } from "@/pages/EmployeeDirectoryPage";
import { EmployeeProfilePage } from "@/pages/EmployeeProfilePage";
import { HomePage } from "@/pages/HomePage";
import { InvoiceDetailPage } from "@/pages/InvoiceDetailPage";
import { InvoiceFormPage } from "@/pages/InvoiceFormPage";
import { InvoiceListPage } from "@/pages/InvoiceListPage";
import { LoginPage } from "@/pages/LoginPage";
import { MyTasksPage } from "@/pages/MyTasksPage";
import { RegisterPage } from "@/pages/RegisterPage";
import { RequestDetailPage } from "@/pages/RequestDetailPage";
import { RequestListPage } from "@/pages/RequestListPage";
import { TaskBoardPage } from "@/pages/TaskBoardPage";
import { TaskCalendarPage } from "@/pages/TaskCalendarPage";
import { TaskDetailPage } from "@/pages/TaskDetailPage";
import { TaskListPage } from "@/pages/TaskListPage";
import { ProtectedRoute } from "@/routes/ProtectedRoute";

export const router = createBrowserRouter([
  { path: "/login", element: <LoginPage /> },
  { path: "/register", element: <RegisterPage /> },
  {
    element: <ProtectedRoute />,
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
    ],
  },
]);
