import axios from "axios";

export const API_URL = import.meta.env.VITE_API_URL !== undefined && import.meta.env.VITE_API_URL !== "" 
  ? import.meta.env.VITE_API_URL 
  : (window.location.hostname === "localhost" || window.location.hostname === "127.0.0.1" ? "http://localhost:5000" : "");

const apiClient = axios.create({
  baseURL: API_URL,
  headers: {
    "Content-Type": "application/json",
  },
});

// Attach Authorization header if JWT token is stored in localStorage
apiClient.interceptors.request.use(
  (config) => {
    const token = localStorage.getItem("token");
    if (token) {
      config.headers.Authorization = `Bearer ${token}`;
    }
    return config;
  },
  (error) => {
    return Promise.reject(error);
  }
);

export const api = {
  // OCR Extraction
  extractInvoice: async (file) => {
    const formData = new FormData();
    formData.append("file", file);
    return await apiClient.post("/api/extract", formData, {
      headers: {
        "Content-Type": "multipart/form-data",
      },
    });
  },

  // Check Duplicate Invoice
  checkDuplicate: async (companyGst, invoiceNumber) => {
    const response = await apiClient.get("/api/check-duplicate", {
      params: {
        company_gst_no: companyGst,
        invoice_number: invoiceNumber,
      },
    });
    return response.data; // { success, message, data: { duplicate: true/false } }
  },

  // Save New Invoice
  saveInvoice: async (originalData, editedData, imagePath, forceSave = false) => {
    const payload = {
      original_extracted_data: originalData,
      edited_invoice_data: editedData,
      invoice_image_path: imagePath,
      force_save: forceSave,
    };
    console.log("Save Payload:", payload);
    const response = await apiClient.post("/api/save", payload);
    return response.data; // { success, message, data: savedDoc }
  },

  // Fetch Invoices (paginated, sorted, filtered)
  getInvoices: async (params = {}) => {
    const response = await apiClient.get("/api/invoices", { params });
    return response.data; // { success, message, data: { invoices, total, page, pages } }
  },

  // Fetch Single Invoice
  getInvoice: async (id) => {
    const response = await apiClient.get(`/api/invoice/${id}`);
    return response.data; // { success, message, data: invoiceDoc }
  },

  // Update Existing Invoice
  updateInvoice: async (id, editedData, imagePath) => {
    const response = await apiClient.put(`/api/invoice/${id}`, {
      edited_invoice_data: editedData,
      invoice_image_path: imagePath,
    });
    return response.data; // { success, message, data: updatedDoc }
  },

  // Soft Delete Invoice
  deleteInvoice: async (id) => {
    const response = await apiClient.delete(`/api/invoice/${id}`);
    return response.data; // { success, message, data: { _id } }
  },

  // Get Analytics Dashboard Data
  getAnalytics: async (params = {}) => {
    const response = await apiClient.get("/api/analytics", { params });
    return response.data; // { success, message, data: {...} }
  },

  // Google Login
  loginGoogle: async (token, loginType = "user") => {
    const response = await apiClient.post("/api/auth/google", { token, login_type: loginType });
    return response.data; // { success, message, token, user }
  },

  // Logout
  logout: async () => {
    const response = await apiClient.post("/api/auth/logout");
    return response.data;
  },

  // Admin: Get Users List
  adminGetUsers: async () => {
    const response = await apiClient.get("/api/admin/users");
    return response.data;
  },

  // Admin: Update User Role
  adminUpdateUserRole: async (userId, role) => {
    const response = await apiClient.put(`/api/admin/user/${userId}/role`, { role });
    return response.data;
  },

  // Admin: Update User Status (is_active)
  adminUpdateUserStatus: async (userId, isActive) => {
    const response = await apiClient.put(`/api/admin/user/${userId}/status`, { is_active: isActive });
    return response.data;
  },

  // Admin: Get Activity Logs
  adminGetActivityLogs: async (limit = 100) => {
    const response = await apiClient.get("/api/admin/activity-logs", { params: { limit } });
    return response.data;
  },

  // Admin: Get specific user's invoices
  adminGetUserInvoices: async (userId) => {
    const response = await apiClient.get(`/api/admin/user/${userId}/invoices`);
    return response.data;
  },

  // Admin: Get admin-specific aggregate analytics
  adminGetAnalytics: async () => {
    const response = await apiClient.get("/api/admin/analytics");
    return response.data;
  },

  // Saved Reports List
  getReports: async () => {
    const response = await apiClient.get("/api/reports");
    return response.data;
  },

  // Get Single Report
  getReport: async (id) => {
    const response = await apiClient.get(`/api/reports/${id}`);
    return response.data;
  },

  // Delete Report
  deleteReport: async (id) => {
    const response = await apiClient.delete(`/api/reports/${id}`);
    return response.data;
  },

  // Chatbot Query
  chatQuery: async (question) => {
    const response = await apiClient.post("/api/chat/query", { question });
    return response.data;
  },

  // Chatbot PDF Report Trigger
  chatReport: async (question) => {
    const response = await apiClient.post("/api/chat/report", { question });
    return response.data;
  },

  // Admin Cleanup
  adminCleanupReports: async () => {
    const response = await apiClient.post("/api/admin/reports/cleanup");
    return response.data;
  },

  // Chat Configuration
  getChatConfig: async () => {
    const response = await apiClient.get("/api/chat/config");
    return response.data;
  },
};

export default apiClient;
