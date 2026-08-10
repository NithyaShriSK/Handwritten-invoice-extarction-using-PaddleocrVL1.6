import React, { useState, useEffect } from "react";
import { api, API_URL } from "../services/api";
import { toast } from "react-toastify";
import { 
  FileText, 
  Search, 
  Trash2, 
  Download, 
  RefreshCw, 
  AlertCircle,
  FileSpreadsheet,
  Calendar,
  User,
  ShieldAlert
} from "lucide-react";

const ReportHistory = () => {
  const [reports, setReports] = useState([]);
  const [loading, setLoading] = useState(true);
  const [searchQuery, setSearchQuery] = useState("");
  const [typeFilter, setTypeFilter] = useState("all");
  const [actionLoadingId, setActionLoadingId] = useState(null);

  const currentUser = JSON.parse(localStorage.getItem("user") || "{}");
  const isAdmin = currentUser.role === "admin";

  const fetchReports = async () => {
    try {
      setLoading(true);
      const res = await api.getReports();
      if (res.success) {
        setReports(res.data);
      } else {
        toast.error(res.message || "Failed to load reports history.");
      }
    } catch (error) {
      console.error("Error fetching reports:", error);
      toast.error("Connection to reports server failed.");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchReports();
  }, []);

  const handleDelete = async (reportId) => {
    if (!window.confirm("Are you sure you want to permanently delete this report?")) {
      return;
    }
    setActionLoadingId(reportId);
    try {
      const res = await api.deleteReport(reportId);
      if (res.success) {
        toast.success("Report deleted successfully.");
        setReports(prev => prev.filter(r => r.id !== reportId));
      } else {
        toast.error(res.message || "Failed to delete report.");
      }
    } catch (error) {
      console.error("Error deleting report:", error);
      toast.error("Connection failed. Could not delete report.");
    } finally {
      setActionLoadingId(null);
    }
  };

  const handleDownload = (filename) => {
    if (!filename) {
      toast.error("PDF file path is invalid.");
      return;
    }
    const token = localStorage.getItem("token");
    const downloadUrl = `${API_URL}/reports/${filename}`;
    
    // Create an anchor and download using token or native download if route is protected
    // Standard secure way: fetch with auth headers or open with token query param
    // Since our backend endpoint serve_report_file uses JWT token_required (via login_required),
    // we can fetch the blob using headers and download it to prevent exposing token in URL:
    fetch(downloadUrl, {
      headers: {
        "Authorization": `Bearer ${token}`
      }
    })
    .then(response => {
      if (!response.ok) {
        throw new Error("Unauthorized or file not found.");
      }
      return response.blob();
    })
    .then(blob => {
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = filename;
      document.body.appendChild(a);
      a.click();
      a.remove();
      window.URL.revokeObjectURL(url);
      toast.success("Download started.");
    })
    .catch(err => {
      console.error("Download error:", err);
      toast.error("Failed to download PDF report. Access Denied.");
    });
  };

  // Helper to get type label
  const getReportTypeLabel = (type) => {
    const mapping = {
      "monthly_report": "Monthly Report",
      "quarterly_report": "Quarterly Report",
      "yearly_report": "Yearly Report",
      "revenue_analysis": "Revenue Analysis",
      "gst_analysis": "GST Analysis",
      "vendor_analysis": "Vendor Analysis"
    };
    return mapping[type] || type.replace("_", " ").toUpperCase();
  };

  // Helper to format date
  const formatDate = (dateStr) => {
    if (!dateStr) return "N/A";
    try {
      const date = new Date(dateStr);
      return date.toLocaleDateString("en-IN", {
        day: "2-digit",
        month: "short",
        year: "numeric",
        hour: "2-digit",
        minute: "2-digit"
      });
    } catch (e) {
      return dateStr;
    }
  };

  // Filtering Logic
  const filteredReports = reports.filter(r => {
    const titleMatch = r.report_title?.toLowerCase().includes(searchQuery.toLowerCase());
    const typeMatch = r.report_type?.toLowerCase().includes(searchQuery.toLowerCase());
    const matchSearch = titleMatch || typeMatch;
    const matchType = typeFilter === "all" ? true : r.report_type === typeFilter;
    return matchSearch && matchType;
  });

  return (
    <div className="space-y-8 pb-12">
      {/* Header section */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <h1 className="text-2xl md:text-3xl font-extrabold text-slate-900 dark:text-white flex items-center gap-3">
            <FileSpreadsheet className="text-emerald-600" />
            Intelligence Reports History
          </h1>
          <p className="text-slate-500 dark:text-slate-400 mt-1">
            {isAdmin 
              ? "System-wide saved business intelligence reports and audit metrics." 
              : "Access and review your previously generated AI business intelligence reports."}
          </p>
        </div>

        <button
          onClick={fetchReports}
          disabled={loading}
          className="flex items-center justify-center gap-2 px-4 py-2.5 bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-xl hover:bg-slate-50 dark:hover:bg-slate-800/80 text-sm font-medium text-slate-700 dark:text-slate-300 transition-colors shadow-sm disabled:opacity-50"
        >
          <RefreshCw size={16} className={loading ? "animate-spin" : ""} />
          <span>Refresh List</span>
        </button>
      </div>

      {/* Search and Filters card */}
      <div className="glass-card p-6 border border-slate-200 dark:border-slate-800 rounded-2xl flex flex-col md:flex-row gap-4 items-center">
        {/* Search Input */}
        <div className="relative w-full md:flex-1">
          <Search className="absolute left-3.5 top-1/2 -translate-y-1/2 text-slate-400 dark:text-slate-500" size={18} />
          <input
            type="text"
            placeholder="Search reports by title or type..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className="w-full pl-11 pr-4 py-2.5 rounded-xl border border-slate-200 dark:border-slate-800 bg-slate-50/50 dark:bg-slate-900/50 text-sm placeholder-slate-400 dark:placeholder-slate-500 focus:outline-none focus:ring-1 focus:ring-emerald-500 transition-all text-slate-800 dark:text-white"
          />
        </div>

        {/* Type Filter Dropdown */}
        <div className="w-full md:w-64">
          <select
            value={typeFilter}
            onChange={(e) => setTypeFilter(e.target.value)}
            className="w-full px-3.5 py-2.5 rounded-xl border border-slate-200 dark:border-slate-800 bg-slate-50/50 dark:bg-slate-900/50 text-sm focus:outline-none focus:ring-1 focus:ring-emerald-500 transition-all text-slate-700 dark:text-slate-300"
          >
            <option value="all">All Report Types</option>
            <option value="monthly_report">Monthly Reports</option>
            <option value="quarterly_report">Quarterly Reports</option>
            <option value="yearly_report">Yearly Reports</option>
            <option value="revenue_analysis">Revenue Analysis</option>
            <option value="gst_analysis">GST Analysis</option>
            <option value="vendor_analysis">Vendor Analysis</option>
          </select>
        </div>
      </div>

      {/* Main Table Card */}
      <div className="glass-card border border-slate-200 dark:border-slate-800 rounded-2xl overflow-hidden">
        {loading ? (
          <div className="flex flex-col items-center justify-center py-20 space-y-4">
            <div className="w-10 h-10 border-4 border-emerald-600 border-t-transparent rounded-full animate-spin"></div>
            <span className="text-sm text-slate-500 dark:text-slate-400 font-medium">Loading saved reports...</span>
          </div>
        ) : filteredReports.length === 0 ? (
          <div className="text-center py-20 text-slate-500 dark:text-slate-400 flex flex-col items-center justify-center space-y-2">
            <AlertCircle size={32} className="text-slate-300 dark:text-slate-700 mb-2" />
            <span className="font-bold text-slate-700 dark:text-slate-300">No Reports Found</span>
            <p className="text-xs text-slate-400 mt-1 max-w-xs">
              Generate a business report using the Invoice Intelligence Chatbot in the dashboard to see historical records here.
            </p>
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full border-collapse text-left text-sm">
              <thead>
                <tr className="bg-slate-50 dark:bg-slate-900/30 text-xs font-semibold text-slate-500 dark:text-slate-400 border-b border-slate-200 dark:border-slate-800 uppercase tracking-wider">
                  <th className="py-4 px-6">Report Title</th>
                  <th className="py-4 px-6">Type</th>
                  <th className="py-4 px-6">Generated Date</th>
                  {isAdmin && <th className="py-4 px-6">Creator</th>}
                  <th className="py-4 px-6 text-right">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-200 dark:divide-slate-800/80">
                {filteredReports.map((r) => {
                  const isActionLoading = actionLoadingId === r.id;
                  return (
                    <tr
                      key={r.id}
                      className="hover:bg-slate-50/50 dark:hover:bg-slate-900/10 transition-colors text-slate-700 dark:text-slate-300"
                    >
                      {/* Title & File */}
                      <td className="py-4 px-6 font-medium">
                        <div className="flex items-center gap-3">
                          <span className="p-2 bg-emerald-500/10 text-emerald-600 rounded-lg shrink-0">
                            <FileText size={18} />
                          </span>
                          <div>
                            <p className="text-slate-800 dark:text-white font-semibold">{r.report_title}</p>
                            <p className="text-[10px] text-slate-400 dark:text-slate-500 font-mono mt-0.5">{r.pdf_filename}</p>
                          </div>
                        </div>
                      </td>

                      {/* Type */}
                      <td className="py-4 px-6 text-xs font-semibold">
                        <span className="inline-block whitespace-nowrap min-w-[120px] text-center px-2.5 py-1 bg-slate-100 dark:bg-slate-800 text-slate-600 dark:text-slate-300 rounded-full border border-slate-200 dark:border-slate-700/50">
                          {getReportTypeLabel(r.report_type)}
                        </span>
                      </td>

                      {/* Date */}
                      <td className="py-4 px-6 text-slate-500">
                        <div className="flex items-center gap-2">
                          <Calendar size={14} className="text-slate-400" />
                          <span>{formatDate(r.generated_at)}</span>
                        </div>
                      </td>

                      {/* Creator (Admin Only) */}
                      {isAdmin && (
                        <td className="py-4 px-6 text-slate-500 font-medium">
                          <div className="flex items-center gap-2">
                            <User size={14} className="text-slate-400" />
                            <span>{r.user_email || "System"}</span>
                          </div>
                        </td>
                      )}

                      {/* Actions */}
                      <td className="py-4 px-6 text-right">
                        <div className="flex items-center justify-end gap-2">
                          <button
                            onClick={() => handleDownload(r.pdf_filename)}
                            className="p-2 bg-emerald-500/10 hover:bg-emerald-500/20 text-emerald-600 dark:text-emerald-400 rounded-lg transition-all"
                            title="Download PDF"
                          >
                            <Download size={15} />
                          </button>
                          
                          <button
                            onClick={() => handleDelete(r.id)}
                            disabled={isActionLoading}
                            className="p-2 bg-rose-500/10 hover:bg-rose-500/20 text-rose-600 dark:text-rose-400 rounded-lg transition-all disabled:opacity-50"
                            title="Delete Report"
                          >
                            <Trash2 size={15} />
                          </button>
                        </div>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
};

export default ReportHistory;
