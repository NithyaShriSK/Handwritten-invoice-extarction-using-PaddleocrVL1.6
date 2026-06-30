import React from "react";
import { Navigate } from "react-router-dom";

export const ProtectedRoute = ({ children, requiredRole }) => {
  const token = localStorage.getItem("token");
  const userJson = localStorage.getItem("user");
  
  if (!token || !userJson) {
    // Not authenticated, redirect to login
    return <Navigate to="/login" replace />;
  }

  try {
    const user = JSON.parse(userJson);
    
    // Enforce role checks
    if (requiredRole && user.role !== requiredRole) {
      if (user.role === "admin") {
        // Admins trying to access user-only pages are redirected to admin panel
        return <Navigate to="/admin/dashboard" replace />;
      } else {
        // Standard users trying to access admin-only pages are redirected to user dashboard
        return <Navigate to="/dashboard" replace />;
      }
    }
  } catch (error) {
    // Clear storage and redirect on parsing error
    localStorage.removeItem("token");
    localStorage.removeItem("user");
    return <Navigate to="/login" replace />;
  }

  return children;
};

export default ProtectedRoute;
