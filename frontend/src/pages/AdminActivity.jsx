import React, { useState, useEffect } from "react";
import { api } from "../services/api";
import { toast } from "react-toastify";
import {
  ClipboardList,
  Search,
  Filter,
  RefreshCw,
  LogIn,
  LogOut,
  UploadCloud,
  FileEdit,
  Save,
  Trash2,
  FileSpreadsheet,
  Download,
  AlertCircle
} from "lucide-react";

const AdminActivity = () => {
  const [logs, setLogs] = useState([]);
  const [loading, setLoading] = useState(true);
  const [limit, setLimit] = useState(100);
  const [filterAction, setFilterAction] = useState("");
  const [searchQuery, setSearchQuery] = useState("");

  const fetchLogs = async () => {
    setLoading(true);
    try {
      const res = await api.adminGetActivityLogs(limit);
      if (res.success) {
        setLogs(res.data || []);
      } else {
        toast.error(res.message || "Failed to fetch activity logs");
      }
    } catch (error) {
      console.error("Error fetching activity logs:", error);
      toast.error(error.response?.data?.message || "Failed to load activity logs.");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchLogs();
  }, [limit]);

  // Map action labels to custom styles/icons
  const getActionConfig = (action) => {
    switch (action) {
      case "login":
        return { icon: LogIn, color: "text-emerald-500 bg-emerald-500/10 border-emerald-500/20", label: "User Login" };
      case "logout":
        return { icon: LogOut, color: "text-slate-500 bg-slate-500/10 border-slate-500/20", label: "User Logout" };
      case "invoice_uploaded":
        return { icon: UploadCloud, color: "text-emerald-500 bg-emerald-500/10 border-emerald-500/20", label: "Invoice Uploaded" };
      case "invoice_corrected":
        return { icon: FileEdit, color: "text-amber-500 bg-amber-500/10 border-amber-500/20", label: "Invoice Corrected" };
      case "invoice_saved":
        return { icon: Save, color: "text-emerald-600 bg-emerald-600/10 border-emerald-600/20", label: "Invoice Saved" };
      case "invoice_deleted":
        return { icon: Trash2, color: "text-rose-500 bg-rose-500/10 border-rose-500/20", label: "Invoice Deleted" };
      case "invoice_exported_csv":
        return { icon: FileSpreadsheet, color: "text-teal-500 bg-teal-500/10 border-teal-500/20", label: "Exported CSV" };
      case "invoice_exported_json":
        return { icon: Download, color: "text-purple-500 bg-purple-500/10 border-purple-500/20", label: "Exported JSON" };
      default:
        return { icon: ClipboardList, color: "text-slate-500 bg-slate-500/10 border-slate-500/20", label: action };
    }
  };

  // Filter logs by selected actions or user email search
  const filteredLogs = logs.filter((log) => {
    const actionMatches = filterAction ? log.action === filterAction : true;
    const searchMatches = searchQuery
      ? log.user_email?.toLowerCase().includes(searchQuery.toLowerCase()) ||
        log.invoice_id?.toLowerCase().includes(searchQuery.toLowerCase()) ||
        JSON.stringify(log.metadata || {}).toLowerCase().includes(searchQuery.toLowerCase())
      : true;
    return actionMatches && searchMatches;
  });

  const availableActions = [
    { value: "", label: "All Actions" },
    { value: "login", label: "Logins" },
    { value: "logout", label: "Logouts" },
    { value: "invoice_uploaded", label: "Uploads" },
    { value: "invoice_corrected", label: "Corrections" },
    { value: "invoice_saved", label: "Saves" },
    { value: "invoice_deleted", label: "Deletions" },
    { value: "invoice_exported_csv", label: "CSV Exports" },
    { value: "invoice_exported_json", label: "JSON Exports" }
  ];

  return (
    <div className="space-y-6">
      {/* Header section */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <h1 className="text-2xl md:text-3xl font-extrabold text-slate-900 dark:text-white flex items-center gap-3">
            <ClipboardList className="text-brand-500" />
            System Activity Audit Logs
          </h1>
          <p className="text-slate-500 dark:text-slate-400 mt-1">
            Real-time visual timeline of user events, invoice processing actions, modifications, and exports.
          </p>
        </div>

        <div className="flex items-center gap-2">
          <select
            value={limit}
            onChange={(e) => setLimit(Number(e.target.value))}
            className="px-3 py-2 bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-xl text-sm font-medium text-slate-700 dark:text-slate-300"
          >
            <option value={50}>Last 50 logs</option>
            <option value={100}>Last 100 logs</option>
            <option value={250}>Last 250 logs</option>
            <option value={500}>Last 500 logs</option>
          </select>

          <button
            onClick={fetchLogs}
            disabled={loading}
            className="flex items-center justify-center gap-2 px-4 py-2 bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-xl hover:bg-slate-50 dark:hover:bg-slate-800/80 text-sm font-medium text-slate-700 dark:text-slate-300 transition-colors shadow-sm disabled:opacity-50"
          >
            <RefreshCw size={16} className={loading ? "animate-spin" : ""} />
            <span>Refresh</span>
          </button>
        </div>
      </div>

      {/* Filter and search bar */}
      <div className="glass-card p-4 border border-slate-200 dark:border-slate-800 rounded-2xl flex flex-col md:flex-row gap-4 items-center">
        {/* Search */}
        <div className="relative flex-1 w-full">
          <Search className="absolute left-3.5 top-1/2 -translate-y-1/2 text-slate-400 dark:text-slate-500" size={16} />
          <input
            type="text"
            placeholder="Search logs by email, invoice ID or metadata fields..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className="w-full pl-10 pr-4 py-2 text-sm rounded-xl border border-slate-200 dark:border-slate-800 bg-slate-50/50 dark:bg-slate-900/50 focus:outline-none focus:ring-1 focus:ring-brand-500 dark:focus:ring-brand-500 transition-all placeholder:text-slate-400 dark:placeholder:text-slate-500"
          />
        </div>

        {/* Action Filter dropdown */}
        <div className="flex items-center gap-2 w-full md:w-auto">
          <Filter size={16} className="text-slate-400 dark:text-slate-500 shrink-0" />
          <select
            value={filterAction}
            onChange={(e) => setFilterAction(e.target.value)}
            className="w-full md:w-48 px-3 py-2 bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-xl text-sm font-medium text-slate-700 dark:text-slate-300 focus:outline-none focus:ring-1 focus:ring-brand-500"
          >
            {availableActions.map((opt) => (
              <option key={opt.value} value={opt.value}>
                {opt.label}
              </option>
            ))}
          </select>
        </div>
      </div>

      {/* Activity Timeline / Table */}
      <div className="glass-card border border-slate-200 dark:border-slate-800 rounded-2xl overflow-hidden">
        {loading ? (
          <div className="flex flex-col items-center justify-center py-20 space-y-4">
            <div className="w-10 h-10 border-4 border-brand-500 border-t-transparent rounded-full animate-spin"></div>
            <span className="text-sm text-slate-500 dark:text-slate-400 font-medium">Loading system events...</span>
          </div>
        ) : filteredLogs.length === 0 ? (
          <div className="text-center py-20 text-slate-500 dark:text-slate-400 flex flex-col items-center justify-center space-y-2">
            <AlertCircle size={28} className="text-slate-400" />
            <span>No activity logs matched your current filters.</span>
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full border-collapse text-left">
              <thead>
                <tr className="bg-slate-50 dark:bg-slate-900/30 text-xs font-semibold text-slate-500 dark:text-slate-400 border-b border-slate-200 dark:border-slate-800 uppercase tracking-wider">
                  <th className="py-4 px-6">Event</th>
                  <th className="py-4 px-6">User Email</th>
                  <th className="py-4 px-6">Invoice ID</th>
                  <th className="py-4 px-6">Action Details</th>
                  <th className="py-4 px-6 text-right">Timestamp</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-200 dark:divide-slate-800/80">
                {filteredLogs.map((log) => {
                  const cfg = getActionConfig(log.action);
                  const Icon = cfg.icon;
                  return (
                    <tr
                      key={log.id}
                      className="hover:bg-slate-50/50 dark:hover:bg-slate-900/10 transition-colors text-slate-700 dark:text-slate-300 text-sm"
                    >
                      {/* Action Event Badge */}
                      <td className="py-4 px-6">
                        <div className="flex items-center gap-2">
                          <span className={`inline-flex p-1.5 rounded-lg border ${cfg.color} shrink-0`}>
                            <Icon size={14} />
                          </span>
                          <span className="font-semibold text-slate-900 dark:text-white">
                            {cfg.label}
                          </span>
                        </div>
                      </td>

                      {/* User Email */}
                      <td className="py-4 px-6">
                        <span className="font-medium text-slate-600 dark:text-slate-300">{log.user_email || "System"}</span>
                        {log.user_id && log.user_id !== "system" && (
                          <p className="text-[10px] text-slate-400 font-mono mt-0.5">{log.user_id}</p>
                        )}
                      </td>

                      {/* Invoice ID */}
                      <td className="py-4 px-6 font-mono text-xs text-slate-500">
                        {log.invoice_id ? log.invoice_id : <span className="text-slate-400 italic">None</span>}
                      </td>

                      {/* Metadata Details */}
                      <td className="py-4 px-6">
                        {log.metadata && Object.keys(log.metadata).length > 0 ? (
                          <div className="flex flex-wrap gap-1.5 max-w-sm">
                            {Object.entries(log.metadata).map(([key, val]) => (
                              <span
                                key={key}
                                className="inline-flex items-center text-[10px] bg-slate-100 dark:bg-slate-800 text-slate-500 dark:text-slate-400 px-2 py-0.5 rounded-md border border-slate-200/40 dark:border-slate-700/40"
                              >
                                <strong className="font-semibold mr-1">{key}:</strong>
                                <span className="truncate max-w-[150px]">{String(val)}</span>
                              </span>
                            ))}
                          </div>
                        ) : (
                          <span className="text-xs text-slate-400 italic">No metadata logged</span>
                        )}
                      </td>

                      {/* Timestamp */}
                      <td className="py-4 px-6 text-right text-xs text-slate-400">
                        {log.timestamp ? new Date(log.timestamp).toLocaleString() : "N/A"}
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

export default AdminActivity;
