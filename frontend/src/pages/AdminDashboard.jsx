import React, { useState, useEffect } from "react";
import { api } from "../services/api";
import { toast } from "react-toastify";
import { Link } from "react-router-dom";
import {
  Shield,
  Users,
  FileText,
  TrendingUp,
  Percent,
  Calendar,
  Layers,
  ArrowUpRight,
  RefreshCw,
  Activity,
  AlertCircle,
  FileEdit,
  Clock
} from "lucide-react";

const AdminDashboard = () => {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);

  const fetchAnalytics = async () => {
    setLoading(true);
    try {
      const res = await api.adminGetAnalytics();
      if (res.success) {
        setData(res.data);
      } else {
        toast.error(res.message || "Failed to load admin analytics");
      }
    } catch (error) {
      console.error("Error loading admin stats:", error);
      toast.error(error.response?.data?.message || "Failed to contact analytics server.");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchAnalytics();
  }, []);

  if (loading) {
    return (
      <div className="flex flex-col items-center justify-center py-32 space-y-4">
        <div className="w-12 h-12 border-4 border-emerald-600 border-t-transparent rounded-full animate-spin"></div>
        <span className="text-sm text-slate-500 dark:text-slate-400 font-medium">Computing system-wide analytics...</span>
      </div>
    );
  }

  if (!data) {
    return (
      <div className="text-center py-20 text-slate-500 dark:text-slate-400 flex flex-col items-center justify-center space-y-2">
        <AlertCircle size={32} className="text-rose-500" />
        <span className="font-semibold text-lg">Failed to Load Dashboard Data</span>
        <p className="text-sm">Please refresh the dashboard or contact system support.</p>
        <button onClick={fetchAnalytics} className="mt-4 px-4 py-2 bg-emerald-600 text-white rounded-xl text-sm font-medium">
          Retry
        </button>
      </div>
    );
  }

  return (
    <div className="space-y-8 pb-12">
      {/* Header section */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <h1 className="text-2xl md:text-3xl font-extrabold text-slate-900 dark:text-white flex items-center gap-3">
            <Shield className="text-emerald-600" />
            Admin Operations Center
          </h1>
          <p className="text-slate-500 dark:text-slate-400 mt-1">
            System performance dashboard monitoring Google authentication, user usage levels, OCR error rates, and corrections.
          </p>
        </div>

        <button
          onClick={fetchAnalytics}
          className="flex items-center justify-center gap-2 px-4 py-2.5 bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-xl hover:bg-slate-50 dark:hover:bg-slate-800/80 text-sm font-medium text-slate-700 dark:text-slate-300 transition-colors shadow-sm"
        >
          <RefreshCw size={16} />
          <span>Refresh Metrics</span>
        </button>
      </div>

      {/* Main Core Statistics Grid */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-6 gap-5">
        {/* Total Users */}
        <div className="glass-card p-6 border border-slate-200 dark:border-slate-800 rounded-2xl flex flex-col justify-between">
          <div className="flex items-center justify-between">
            <span className="text-xs font-semibold text-slate-400 uppercase tracking-wider">Total Users</span>
            <span className="p-2 bg-emerald-500/10 text-emerald-600 rounded-lg"><Users size={18} /></span>
          </div>
          <div className="mt-4">
            <h3 className="text-3xl font-extrabold text-slate-800 dark:text-white">{data.total_users}</h3>
            <p className="text-xs text-slate-400 mt-1 font-medium flex items-center gap-1">
              <span className="text-emerald-500 font-bold">{data.active_users}</span> active sessions enabled
            </p>
          </div>
        </div>

        {/* Total Invoices */}
        <div className="glass-card p-6 border border-slate-200 dark:border-slate-800 rounded-2xl flex flex-col justify-between">
          <div className="flex items-center justify-between">
            <span className="text-xs font-semibold text-slate-400 uppercase tracking-wider">Total Invoices</span>
            <span className="p-2 bg-emerald-500/10 text-emerald-600 rounded-lg"><FileText size={18} /></span>
          </div>
          <div className="mt-4">
            <h3 className="text-3xl font-extrabold text-slate-800 dark:text-white">{data.total_invoices}</h3>
            <p className="text-xs text-slate-400 mt-1 font-medium">
              Across all user accounts and system uploads
            </p>
          </div>
        </div>

        {/* Invoices Today / Month */}
        <div className="glass-card p-6 border border-slate-200 dark:border-slate-800 rounded-2xl flex flex-col justify-between">
          <div className="flex items-center justify-between">
            <span className="text-xs font-semibold text-slate-400 uppercase tracking-wider">Upload Activity</span>
            <span className="p-2 bg-emerald-500/10 text-emerald-600 rounded-lg"><Calendar size={18} /></span>
          </div>
          <div className="mt-4">
            <h3 className="text-3xl font-extrabold text-slate-800 dark:text-white">{data.invoices_uploaded_today}</h3>
            <p className="text-xs text-slate-400 mt-1 font-medium flex items-center gap-1">
              <span className="text-emerald-500 font-bold">+{data.invoices_uploaded_this_month}</span> uploaded this month
            </p>
          </div>
        </div>

        {/* Overall Correction Rate */}
        <div className="glass-card p-6 border border-slate-200 dark:border-slate-800 rounded-2xl flex flex-col justify-between">
          <div className="flex items-center justify-between">
            <span className="text-xs font-semibold text-slate-400 uppercase tracking-wider">System Correction Rate</span>
            <span className="p-2 bg-amber-500/10 text-amber-600 rounded-lg"><Percent size={18} /></span>
          </div>
          <div className="mt-4">
            <h3 className="text-3xl font-extrabold text-slate-800 dark:text-white">{data.correction_rate}%</h3>
            <p className="text-xs text-slate-400 mt-1 font-medium">
              Average across users: <strong className="text-emerald-600 dark:text-emerald-400">{data.average_correction_rate}%</strong>
            </p>
          </div>
        </div>

        {/* OCR Acceptance Rate */}
        <div className="glass-card p-6 border border-slate-200 dark:border-slate-800 rounded-2xl flex flex-col justify-between">
          <div className="flex items-center justify-between">
            <span className="text-xs font-semibold text-slate-400 uppercase tracking-wider">OCR Acceptance Rate</span>
            <span className="p-2 bg-emerald-500/10 text-emerald-600 rounded-lg"><TrendingUp size={18} /></span>
          </div>
          <div className="mt-4">
            <h3 className="text-3xl font-extrabold text-slate-800 dark:text-white">{data.acceptance_rate}%</h3>
            <p className="text-xs text-slate-400 mt-1 font-medium">
              No manual adjustments required
            </p>
          </div>
        </div>

        {/* Saved Reports Count */}
        <div className="glass-card p-6 border border-slate-200 dark:border-slate-800 rounded-2xl flex flex-col justify-between">
          <div className="flex items-center justify-between">
            <span className="text-xs font-semibold text-slate-400 uppercase tracking-wider">Saved Reports</span>
            <span className="p-2 bg-emerald-500/10 text-emerald-600 rounded-lg"><Layers size={18} /></span>
          </div>
          <div className="mt-4">
            <h3 className="text-3xl font-extrabold text-slate-800 dark:text-white">{data.reports_count || 0}</h3>
            <p className="text-xs text-slate-400 mt-1 font-medium">
              Saved intelligence report files
            </p>
          </div>
        </div>
      </div>

      {/* Graphical Trends Section */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Upload Trend by Month */}
        <div className="glass-card p-6 border border-slate-200 dark:border-slate-800 rounded-2xl">
          <div className="flex items-center justify-between mb-6">
            <div>
              <h4 className="font-bold text-slate-800 dark:text-white text-md">Monthly Upload Trend</h4>
              <p className="text-xs text-slate-400">Total invoice documents uploaded monthly (last 6 months)</p>
            </div>
            <TrendingUp className="text-emerald-600" size={20} />
          </div>
          
          {data.upload_trend_by_month.length === 0 ? (
            <div className="h-40 flex items-center justify-center text-xs text-slate-400">No monthly data available</div>
          ) : (
            <div className="flex items-end justify-between h-40 pt-4 border-b border-slate-200 dark:border-slate-800">
              {data.upload_trend_by_month.map((item, idx) => {
                const maxVal = Math.max(...data.upload_trend_by_month.map(x => x.count), 1);
                const heightPercent = (item.count / maxVal) * 100;
                return (
                  <div key={idx} className="flex flex-col items-center flex-1 group">
                    <span className="text-[10px] font-semibold text-slate-500 dark:text-slate-400 mb-1 opacity-0 group-hover:opacity-100 transition-opacity">
                      {item.count}
                    </span>
                    <div 
                      className="w-8 bg-gradient-to-t from-emerald-500 to-teal-600 rounded-t-md hover:from-emerald-600 hover:to-teal-700 transition-all duration-300"
                      style={{ height: `${heightPercent}%` }}
                    ></div>
                    <span className="text-[10px] text-slate-400 mt-2 font-medium">
                      {item.label}
                    </span>
                  </div>
                );
              })}
            </div>
          )}
        </div>

        {/* User Activity Daily Trend */}
        <div className="glass-card p-6 border border-slate-200 dark:border-slate-800 rounded-2xl">
          <div className="flex items-center justify-between mb-6">
            <div>
              <h4 className="font-bold text-slate-800 dark:text-white text-md">User Activity Trend (Last 7 Days)</h4>
              <p className="text-xs text-slate-400">Total logged activity events dynamically recorded daily</p>
            </div>
            <Activity className="text-emerald-500" size={20} />
          </div>

          {data.user_activity_trend.length === 0 ? (
            <div className="h-40 flex items-center justify-center text-xs text-slate-400">No activity trend logged</div>
          ) : (
            <div className="flex items-end justify-between h-40 pt-4 border-b border-slate-200 dark:border-slate-800">
              {data.user_activity_trend.map((item, idx) => {
                const maxVal = Math.max(...data.user_activity_trend.map(x => x.count), 1);
                const heightPercent = (item.count / maxVal) * 100;
                return (
                  <div key={idx} className="flex flex-col items-center flex-1 group">
                    <span className="text-[10px] font-semibold text-slate-500 dark:text-slate-400 mb-1 opacity-0 group-hover:opacity-100 transition-opacity">
                      {item.count}
                    </span>
                    <div 
                      className="w-8 bg-gradient-to-t from-emerald-500 to-teal-600 rounded-t-md hover:from-emerald-600 hover:to-teal-700 transition-all duration-300"
                      style={{ height: `${heightPercent}%` }}
                    ></div>
                    <span className="text-[10px] text-slate-400 mt-2 font-medium">
                      {item.label}
                    </span>
                  </div>
                );
              })}
            </div>
          )}
        </div>
      </div>

      {/* User Leaderboards & Most Corrected Invoices */}
      <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-4 gap-6">
        {/* Top Uploaders Leaderboard */}
        <div className="glass-card p-5 border border-slate-200 dark:border-slate-800 rounded-2xl flex flex-col justify-between">
          <div>
            <h4 className="font-bold text-slate-800 dark:text-white text-sm mb-4 flex items-center gap-2">
              <Layers size={16} className="text-emerald-500" />
              Top Uploaders
            </h4>
            
            {data.top_uploaders.length === 0 ? (
              <p className="text-xs text-slate-400 py-6 text-center">No uploaders logged yet</p>
            ) : (
              <div className="divide-y divide-slate-100 dark:divide-slate-800/80">
                {data.top_uploaders.map((u, i) => (
                  <div key={i} className="py-2.5 flex items-center justify-between">
                    <div>
                      <p className="text-xs font-semibold text-slate-800 dark:text-white truncate max-w-[120px]">{u.name}</p>
                      <p className="text-[9px] text-slate-400 truncate max-w-[120px]">{u.email}</p>
                    </div>
                    <span className="px-2 py-0.5 bg-emerald-100 dark:bg-emerald-950/40 text-emerald-600 dark:text-emerald-400 font-bold text-[10px] rounded-full">
                      {u.count} docs
                    </span>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>

        {/* Most Active Users Leaderboard */}
        <div className="glass-card p-5 border border-slate-200 dark:border-slate-800 rounded-2xl flex flex-col justify-between">
          <div>
            <h4 className="font-bold text-slate-800 dark:text-white text-sm mb-4 flex items-center gap-2">
              <Activity size={16} className="text-emerald-500" />
              Most Active Users
            </h4>
            
            {data.most_active_users.length === 0 ? (
              <p className="text-xs text-slate-400 py-6 text-center">No activity records logged</p>
            ) : (
              <div className="divide-y divide-slate-100 dark:divide-slate-800/80">
                {data.most_active_users.map((u, i) => (
                  <div key={i} className="py-2.5 flex items-center justify-between">
                    <div>
                      <p className="text-xs font-semibold text-slate-800 dark:text-white truncate max-w-[120px]">{u.name}</p>
                      <p className="text-[9px] text-slate-400 truncate max-w-[120px]">{u.email}</p>
                    </div>
                    <span className="px-2 py-0.5 bg-emerald-100 dark:bg-emerald-950/40 text-emerald-600 dark:text-emerald-400 font-bold text-[10px] rounded-full">
                      {u.count} acts
                    </span>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>

        {/* Most Active Admins Leaderboard */}
        <div className="glass-card p-5 border border-slate-200 dark:border-slate-800 rounded-2xl flex flex-col justify-between">
          <div>
            <h4 className="font-bold text-slate-800 dark:text-white text-sm mb-4 flex items-center gap-2">
              <Shield size={16} className="text-emerald-500" />
              Most Active Admins
            </h4>
            
            {!data.most_active_admins || data.most_active_admins.length === 0 ? (
              <p className="text-xs text-slate-400 py-6 text-center">No admin activity logged</p>
            ) : (
              <div className="divide-y divide-slate-100 dark:divide-slate-800/80">
                {data.most_active_admins.map((u, i) => (
                  <div key={i} className="py-2.5 flex items-center justify-between">
                    <div>
                      <p className="text-xs font-semibold text-slate-800 dark:text-white truncate max-w-[120px]">{u.name}</p>
                      <p className="text-[9px] text-slate-400 truncate max-w-[120px]">{u.email}</p>
                    </div>
                    <span className="px-2 py-0.5 bg-amber-100 dark:bg-amber-950/40 text-amber-600 dark:text-amber-400 font-bold text-[10px] rounded-full">
                      {u.count} acts
                    </span>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>

        {/* Correction Rates Leaderboard */}
        <div className="glass-card p-5 border border-slate-200 dark:border-slate-800 rounded-2xl flex flex-col justify-between">
          <div>
            <h4 className="font-bold text-slate-800 dark:text-white text-sm mb-4 flex items-center gap-2">
              <FileEdit size={16} className="text-amber-500" />
              Correction Rate per User
            </h4>
            
            {data.top_users_correction.length === 0 ? (
              <p className="text-xs text-slate-400 py-6 text-center">No statistics logged yet</p>
            ) : (
              <div className="divide-y divide-slate-100 dark:divide-slate-800/80">
                {data.top_users_correction.map((u, i) => (
                  <div key={i} className="py-2.5 flex items-center justify-between">
                    <div>
                      <p className="text-xs font-semibold text-slate-800 dark:text-white truncate max-w-[120px]">{u.name}</p>
                      <p className="text-[9px] text-slate-400 truncate max-w-[120px]">{u.email}</p>
                    </div>
                    <div className="text-right">
                      <span className={`px-1.5 py-0.5 text-[10px] font-bold rounded-md ${
                        u.correction_rate > 50
                          ? "bg-amber-100 dark:bg-amber-950/30 text-amber-600"
                          : "bg-slate-100 dark:bg-slate-800 text-slate-600 dark:text-slate-400"
                      }`}>
                        {u.correction_rate}%
                      </span>
                      <p className="text-[8px] text-slate-400 mt-0.5">({u.corrected_invoices}/{u.total_invoices})</p>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      </div>

      {/* Most Corrected Invoices table */}
      <div className="glass-card border border-slate-200 dark:border-slate-800 rounded-2xl overflow-hidden">
        <div className="p-5 border-b border-slate-200 dark:border-slate-800 flex items-center justify-between bg-slate-50 dark:bg-slate-900/30">
          <div>
            <h4 className="font-bold text-slate-900 dark:text-white text-md">Most Corrected Invoices</h4>
            <p className="text-xs text-slate-400">Invoices requiring the highest number of manual corrections after OCR extraction</p>
          </div>
          <span className="p-2 bg-amber-500/10 text-amber-600 rounded-lg"><Clock size={16} /></span>
        </div>

        {data.most_corrected_invoices.length === 0 ? (
          <div className="text-center py-10 text-slate-400 text-sm">No corrected invoices logged yet.</div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full border-collapse text-left text-sm">
              <thead>
                <tr className="text-xs font-semibold text-slate-500 dark:text-slate-400 border-b border-slate-200 dark:border-slate-800 uppercase tracking-wider bg-slate-50 dark:bg-slate-900/10">
                  <th className="py-3 px-6">Invoice Number</th>
                  <th className="py-3 px-6">Company Name</th>
                  <th className="py-3 px-6">Uploaded By</th>
                  <th className="py-3 px-6 text-center">Correction Count</th>
                  <th className="py-3 px-6 text-right">Last Modified Date</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-200 dark:divide-slate-800/80">
                {data.most_corrected_invoices.map((inv) => (
                  <tr key={inv.invoice_id} className="hover:bg-slate-50/50 dark:hover:bg-slate-900/10 transition-colors">
                    <td className="py-4 px-6 font-semibold text-slate-900 dark:text-white">
                      <Link to={`/invoice/${inv.invoice_id}`} className="hover:underline flex items-center gap-1 text-emerald-600 dark:text-emerald-400">
                        {inv.invoice_number}
                        <ArrowUpRight size={14} />
                      </Link>
                    </td>
                    <td className="py-4 px-6 text-slate-700 dark:text-slate-300 font-medium">{inv.company_name}</td>
                    <td className="py-4 px-6 text-slate-500 dark:text-slate-400">{inv.uploaded_by}</td>
                    <td className="py-4 px-6 text-center">
                      <span className="inline-flex px-2.5 py-1 bg-amber-500/10 text-amber-600 dark:text-amber-400 font-bold text-xs rounded-full border border-amber-500/20">
                        {inv.correction_count} edits
                      </span>
                    </td>
                    <td className="py-4 px-6 text-right text-xs text-slate-400">
                      {inv.last_modified_at ? new Date(inv.last_modified_at).toLocaleString() : "N/A"}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
};

export default AdminDashboard;
