import React from "react";
import { BrowserRouter as Router, Routes, Route, Navigate } from "react-router-dom";
import { ToastContainer } from "react-toastify";
import "react-toastify/dist/ReactToastify.css";

// Import components
import Layout from "./components/Layout";
import ProtectedRoute from "./components/ProtectedRoute";

// Import Pages
import Login from "./pages/Login";
import Dashboard from "./pages/Dashboard";
import ExtractInvoice from "./pages/ExtractInvoice";
import InvoiceHistory from "./pages/InvoiceHistory";
import InvoiceDetail from "./pages/InvoiceDetail";
import ReportHistory from "./pages/ReportHistory";
import Billing from "./pages/Billing";

// Admin Pages
import AdminDashboard from "./pages/AdminDashboard";
import UserManagement from "./pages/UserManagement";
import AdminActivity from "./pages/AdminActivity";

// Root redirection based on role
const RootRedirect = () => {
  const token = localStorage.getItem("token");
  const userJson = localStorage.getItem("user");
  if (!token || !userJson) {
    return <Navigate to="/login" replace />;
  }
  try {
    const user = JSON.parse(userJson);
    if (user.role === "admin") {
      return <Navigate to="/admin/dashboard" replace />;
    } else {
      return <Navigate to="/dashboard" replace />;
    }
  } catch (error) {
    localStorage.removeItem("token");
    localStorage.removeItem("user");
    return <Navigate to="/login" replace />;
  }
};

function App() {
  return (
    <Router>
      <Routes>
        {/* Unprotected Login route */}
        <Route path="/login" element={<Login />} />

        {/* Root Redirect handler */}
        <Route path="/" element={<RootRedirect />} />

        {/* Protected User Routes wrapped with Layout (only accessible to role="user") */}
        <Route
          path="/dashboard"
          element={
            <ProtectedRoute requiredRole="user">
              <Layout>
                <Dashboard />
              </Layout>
            </ProtectedRoute>
          }
        />
        <Route
          path="/billing"
          element={
            <ProtectedRoute requiredRole="user">
              <Layout>
                <Billing />
              </Layout>
            </ProtectedRoute>
          }
        />
        <Route
          path="/extract"
          element={
            <ProtectedRoute requiredRole="user">
              <Layout>
                <ExtractInvoice />
              </Layout>
            </ProtectedRoute>
          }
        />
        <Route
          path="/history"
          element={
            <ProtectedRoute requiredRole="user">
              <Layout>
                <InvoiceHistory />
              </Layout>
            </ProtectedRoute>
          }
        />
        <Route
          path="/invoice/:id"
          element={
            <ProtectedRoute requiredRole="user">
              <Layout>
                <InvoiceDetail />
              </Layout>
            </ProtectedRoute>
          }
        />
        <Route
          path="/reports"
          element={
            <ProtectedRoute>
              <Layout>
                <ReportHistory />
              </Layout>
            </ProtectedRoute>
          }
        />

        {/* Protected Admin-Only Routes wrapped with Layout (only accessible to role="admin") */}
        <Route
          path="/admin/dashboard"
          element={
            <ProtectedRoute requiredRole="admin">
              <Layout>
                <AdminDashboard />
              </Layout>
            </ProtectedRoute>
          }
        />
        <Route
          path="/admin/users"
          element={
            <ProtectedRoute requiredRole="admin">
              <Layout>
                <UserManagement />
              </Layout>
            </ProtectedRoute>
          }
        />
        <Route
          path="/admin/activity"
          element={
            <ProtectedRoute requiredRole="admin">
              <Layout>
                <AdminActivity />
              </Layout>
            </ProtectedRoute>
          }
        />
      </Routes>
      
      <ToastContainer
        position="bottom-right"
        autoClose={3000}
        hideProgressBar={false}
        newestOnTop={false}
        closeOnClick
        rtl={false}
        pauseOnFocusLoss
        draggable
        pauseOnHover
        theme="colored"
      />
    </Router>
  );
}

export default App;
