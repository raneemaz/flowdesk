import { createBrowserRouter } from "react-router-dom";

import { CreateOrganizationPage } from "@/pages/CreateOrganizationPage";
import { DepartmentsPage } from "@/pages/DepartmentsPage";
import { EmployeeDirectoryPage } from "@/pages/EmployeeDirectoryPage";
import { EmployeeProfilePage } from "@/pages/EmployeeProfilePage";
import { HomePage } from "@/pages/HomePage";
import { LoginPage } from "@/pages/LoginPage";
import { RegisterPage } from "@/pages/RegisterPage";
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
    ],
  },
]);
