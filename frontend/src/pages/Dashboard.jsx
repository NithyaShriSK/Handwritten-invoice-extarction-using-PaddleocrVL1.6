import React, { useState, useEffect } from "react";
import { Link, useNavigate } from "react-router-dom";
import {
  FileText,
  UploadCloud,
  FileCheck,
  Building,
  Users,
  Coins,
  ArrowUpRight,
  ArrowDownRight,
  TrendingUp,
  Clock,
  ExternalLink
} from "lucide-react";
import { api } from "../services/api";
import { toast } from "react-toastify";

export const Dashboard = () => {
  const [stats, setStats] = useState(null);
  const [recentInvoices, setRecentInvoices] = useState([]);
  const [loading, setLoading] = useState(true);
  const navigate = useNavigate();

  useEffect(() => {
    const fetchData = async () => {
      try {
        setLoading(true);
        // Fetch analytics summary metrics
        const analyticRes = await api.getAnalytics();
        if (analyticRes.success) {
          setStats(analyticRes.data);
        }

        // Fetch recent 5 invoices
        const invoiceRes = await api.getInvoices({ limit: 5, page: 1 });
        if (invoiceRes.success) {
          setRecentInvoices(invoiceRes.data.invoices);
        }
      } catch (err) {
        console.error("Dashboard data fetching failed", err);
        toast.error("Failed to load dashboard metrics. Database may be offline.");
      } finally {
        setLoading(false);
      }
    };

    fetchData();
  }, []);

  // Format currency helper
  const formatCurrency = (val) => {
    return new Intl.NumberFormat("en-IN", {
      style: "currency",
      currency: "INR",
      maximumFractionDigits: 0
    }).format(val || 0);
  };

  const getStatusBadgeClass = (status) => {
    switch (status) {
      case "Pending Review":
        return "bg-amber-100 text-amber-800 dark:bg-amber-950/30 dark:text-amber-400 border-amber-200 dark:border-amber-900/30";
      case "Reviewed":
        return "bg-emerald-100 text-emerald-800 dark:bg-emerald-950/30 dark:text-emerald-400 border-emerald-200 dark:border-emerald-900/30";
      case "Corrected":
        return "bg-brand-100 text-brand-800 dark:bg-brand-950/30 dark:text-brand-400 border-brand-200 dark:border-brand-900/30";
      default:
        return "bg-slate-100 text-slate-800 dark:bg-slate-900 dark:text-slate-400";
    }
  };

  return (
    <div className="space-y-8 animate-fade-in">
      {/* Welcome Banner */}
      <div className="flex flex-col md:flex-row md:items-center md:justify-between gap-4">
        <div>
          <h2 className="text-3xl font-extrabold text-slate-800 dark:text-white tracking-tight">
            Dashboard Overview
          </h2>
          <p className="text-slate-500 dark:text-slate-400 text-sm mt-1">
            Real-time analytics and OCR processing status for your business invoices.
          </p>
        </div>
        <div className="flex items-center gap-3">
          <Link
            to="/extract"
            className="flex items-center gap-2 bg-brand-500 hover:bg-brand-600 text-white font-semibold text-sm px-5 py-3 rounded-xl shadow-lg shadow-brand-500/20 hover:shadow-brand-500/30 transition-all duration-200 hover:-translate-y-0.5"
          >
            <UploadCloud size={16} />
            <span>Upload Invoice</span>
          </Link>
        </div>
      </div>

      {loading ? (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
          {[...Array(4)].map((_, i) => (
            <div key={i} className="glass-card p-6 rounded-2xl h-32 animate-pulse" />
          ))}
        </div>
      ) : (
        <>
          {/* Summary Cards */}
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
            {/* Total Invoices */}
            <div className="glass-card glass-card-hover p-6 rounded-2xl relative overflow-hidden group">
              <div className="flex items-center justify-between">
                <span className="text-xs font-semibold text-slate-400 uppercase tracking-wider">Invoices Processed</span>
                <div className="p-3 bg-brand-500/10 text-brand-500 rounded-xl group-hover:scale-110 transition-transform">
                  <FileText size={20} />
                </div>
              </div>
              <div className="mt-4">
                <h3 className="text-2xl font-bold text-slate-800 dark:text-white">
                  {stats?.total_invoices || 0}
                </h3>
                <div className="flex items-center gap-1.5 mt-2">
                  {stats?.trends?.count_trend >= 0 ? (
                    <span className="text-emerald-500 text-xs font-bold flex items-center gap-0.5 bg-emerald-50 dark:bg-emerald-950/30 px-2 py-0.5 rounded-lg">
                      <ArrowUpRight size={12} />
                      {stats?.trends?.count_trend}%
                    </span>
                  ) : (
                    <span className="text-rose-500 text-xs font-bold flex items-center gap-0.5 bg-rose-50 dark:bg-rose-950/30 px-2 py-0.5 rounded-lg">
                      <ArrowDownRight size={12} />
                      {Math.abs(stats?.trends?.count_trend)}%
                    </span>
                  )}
                  <span className="text-[10px] text-slate-400 font-medium">vs last month</span>
                </div>
              </div>
            </div>

            {/* Total Revenue */}
            <div className="glass-card glass-card-hover p-6 rounded-2xl relative overflow-hidden group">
              <div className="flex items-center justify-between">
                <span className="text-xs font-semibold text-slate-400 uppercase tracking-wider">Total Value</span>
                <div className="p-3 bg-emerald-500/10 text-emerald-500 rounded-xl group-hover:scale-110 transition-transform">
                  <Coins size={20} />
                </div>
              </div>
              <div className="mt-4">
                <h3 className="text-2xl font-bold text-slate-800 dark:text-white truncate">
                  {formatCurrency(stats?.total_revenue)}
                </h3>
                <div className="flex items-center gap-1.5 mt-2">
                  {stats?.trends?.revenue_trend >= 0 ? (
                    <span className="text-emerald-500 text-xs font-bold flex items-center gap-0.5 bg-emerald-50 dark:bg-emerald-950/30 px-2 py-0.5 rounded-lg">
                      <ArrowUpRight size={12} />
                      {stats?.trends?.revenue_trend}%
                    </span>
                  ) : (
                    <span className="text-rose-500 text-xs font-bold flex items-center gap-0.5 bg-rose-50 dark:bg-rose-950/30 px-2 py-0.5 rounded-lg">
                      <ArrowDownRight size={12} />
                      {Math.abs(stats?.trends?.revenue_trend)}%
                    </span>
                  )}
                  <span className="text-[10px] text-slate-400 font-medium">vs last month</span>
                </div>
              </div>
            </div>

            {/* Total Companies */}
            <div className="glass-card glass-card-hover p-6 rounded-2xl relative overflow-hidden group">
              <div className="flex items-center justify-between">
                <span className="text-xs font-semibold text-slate-400 uppercase tracking-wider">Vendors</span>
                <div className="p-3 bg-violet-500/10 text-violet-500 rounded-xl group-hover:scale-110 transition-transform">
                  <Building size={20} />
                </div>
              </div>
              <div className="mt-4">
                <h3 className="text-2xl font-bold text-slate-800 dark:text-white">
                  {stats?.unique_companies_count || 0}
                </h3>
                <p className="text-xs text-slate-400 mt-2 font-medium">Unique billing companies</p>
              </div>
            </div>

            {/* Total Buyers */}
            <div className="glass-card glass-card-hover p-6 rounded-2xl relative overflow-hidden group">
              <div className="flex items-center justify-between">
                <span className="text-xs font-semibold text-slate-400 uppercase tracking-wider">Buyers</span>
                <div className="p-3 bg-amber-500/10 text-amber-500 rounded-xl group-hover:scale-110 transition-transform">
                  <Users size={20} />
                </div>
              </div>
              <div className="mt-4">
                <h3 className="text-2xl font-bold text-slate-800 dark:text-white">
                  {stats?.unique_buyers_count || 0}
                </h3>
                <p className="text-xs text-slate-400 mt-2 font-medium">Unique buying companies</p>
              </div>
            </div>
          </div>

          {/* Workflow status quick widgets */}
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-6">
            <div className="glass-card p-5 rounded-2xl flex items-center justify-between">
              <div>
                <p className="text-xs text-slate-400 font-semibold uppercase tracking-wider">Pending Review</p>
                <h4 className="text-2xl font-bold text-slate-800 dark:text-white mt-1">
                  {stats?.status_counts?.["Pending Review"] || 0}
                </h4>
              </div>
              <div className="w-10 h-10 rounded-xl bg-amber-500/10 flex items-center justify-center text-amber-500">
                <Clock size={18} />
              </div>
            </div>
            
            <div className="glass-card p-5 rounded-2xl flex items-center justify-between">
              <div>
                <p className="text-xs text-slate-400 font-semibold uppercase tracking-wider">Corrected Invoices</p>
                <h4 className="text-2xl font-bold text-slate-800 dark:text-white mt-1">
                  {stats?.status_counts?.["Corrected"] || 0}
                </h4>
              </div>
              <div className="w-10 h-10 rounded-xl bg-brand-500/10 flex items-center justify-center text-brand-500">
                <FileText size={18} />
              </div>
            </div>

            <div className="glass-card p-5 rounded-2xl flex items-center justify-between">
              <div>
                <p className="text-xs text-slate-400 font-semibold uppercase tracking-wider">Reviewed Invoices</p>
                <h4 className="text-2xl font-bold text-slate-800 dark:text-white mt-1">
                  {stats?.status_counts?.["Reviewed"] || 0}
                </h4>
              </div>
              <div className="w-10 h-10 rounded-xl bg-emerald-500/10 flex items-center justify-center text-emerald-500">
                <FileCheck size={18} />
              </div>
            </div>
          </div>

          {/* Core Content Split: Recent Activity & Action Panel */}
          <div className="grid grid-cols-1 lg:grid-cols-3 gap-8">
            {/* Recent Activity Table */}
            <div className="glass-card p-6 rounded-2xl lg:col-span-2 space-y-4">
              <div className="flex items-center justify-between border-b border-slate-200 dark:border-slate-800 pb-4">
                <div className="flex items-center gap-2">
                  <Clock className="text-slate-400 dark:text-slate-500" size={18} />
                  <h3 className="text-lg font-bold text-slate-800 dark:text-white">Recent Invoices</h3>
                </div>
                <Link
                  to="/history"
                  className="text-xs text-brand-500 font-semibold hover:text-brand-600 hover:underline flex items-center gap-1 transition-colors"
                >
                  <span>View all</span>
                  <ArrowUpRight size={14} />
                </Link>
              </div>

              {recentInvoices.length === 0 ? (
                <div className="py-8 text-center text-slate-400 text-sm">
                  No invoices found. Click "Upload Invoice" to process your first invoice.
                </div>
              ) : (
                <div className="overflow-x-auto">
                  <table className="w-full border-collapse text-sm table-fixed min-w-[800px]">
                    <thead>
                      <tr className="text-slate-400 border-b border-slate-200 dark:border-slate-800">
                        <th className="pb-3 pt-2 font-semibold w-[44%] text-left px-5 whitespace-nowrap">Vendor</th>
                        <th className="pb-3 pt-2 font-semibold w-[10%] text-left px-5 whitespace-nowrap">Invoice #</th>
                        <th className="pb-3 pt-2 font-semibold w-[12%] text-left px-5 whitespace-nowrap">Date</th>
                        <th className="pb-3 pt-2 font-semibold w-[12%] text-right px-5 whitespace-nowrap">Amount</th>
                        <th className="pb-3 pt-2 font-semibold w-[16%] text-center pl-5 pr-8 whitespace-nowrap">Status</th>
                        <th className="pb-3 pt-2 font-semibold w-[6%] text-center pl-8 pr-5 whitespace-nowrap">Action</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-slate-100 dark:divide-slate-800/50">
                      {recentInvoices.map((inv) => {
                        const data = inv.edited_invoice_data;
                        return (
                          <tr key={inv._id} className="group hover:bg-slate-100/50 dark:hover:bg-slate-800/20 transition-colors">
                            <td className="py-3.5 px-5 font-medium text-slate-700 dark:text-slate-200 break-words whitespace-normal">
                              {data.company_name || "Unknown"}
                            </td>
                            <td className="py-3.5 px-5 font-mono text-xs text-slate-600 dark:text-slate-400 text-left truncate">
                              {data.invoice_number || "N/A"}
                            </td>
                            <td className="py-3.5 px-5 text-slate-500 text-left truncate">
                              {data.invoice_date || "N/A"}
                            </td>
                            <td className="py-3.5 px-5 font-semibold text-slate-700 dark:text-slate-200 text-right truncate">
                              {formatCurrency(data.total_amount)}
                            </td>
                            <td className="py-3.5 pl-5 pr-8 text-center">
                              <span className={`inline-block px-2.5 py-1 rounded-full text-xs font-semibold border ${getStatusBadgeClass(inv.review_status)}`}>
                                {inv.review_status}
                              </span>
                            </td>
                            <td className="py-3.5 pl-8 pr-5 text-center">
                              <button
                                onClick={() => {
                                  console.log("Invoice ID:", inv._id);
                                  navigate(`/invoice/${inv._id}`);
                                }}
                                className="p-1 text-slate-400 hover:text-brand-500 dark:hover:text-brand-400 transition-colors inline-flex items-center justify-center"
                              >
                                <ExternalLink size={16} />
                              </button>
                            </td>
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                </div>
              )}
            </div>

            {/* Quick Actions Panel */}
            <div className="space-y-4">
              <div className="glass-card p-6 rounded-2xl space-y-4">
                <h3 className="text-lg font-bold text-slate-800 dark:text-white border-b border-slate-200 dark:border-slate-800 pb-4">
                  Quick Actions
                </h3>
                <div className="space-y-3">
                  <button
                    onClick={() => navigate("/extract")}
                    className="w-full flex items-center justify-between p-4 rounded-xl border border-slate-200/50 dark:border-slate-800/40 hover:border-brand-500/50 dark:hover:border-brand-500/50 hover:bg-brand-500/5 dark:hover:bg-brand-500/5 transition-all text-left group"
                  >
                    <div>
                      <h4 className="font-bold text-sm text-slate-700 dark:text-slate-200">AI Extraction</h4>
                      <p className="text-xs text-slate-400 mt-1">Upload invoices and convert them into editable, searchable, and analyzable business records.</p>
                    </div>
                    <ArrowUpRight className="text-slate-400 group-hover:text-brand-500 shrink-0" size={18} />
                  </button>

                  <button
                    onClick={() => navigate("/history")}
                    className="w-full flex items-center justify-between p-4 rounded-xl border border-slate-200/50 dark:border-slate-800/40 hover:border-violet-500/50 dark:hover:border-violet-500/50 hover:bg-violet-500/5 dark:hover:bg-violet-500/5 transition-all text-left group"
                  >
                    <div>
                      <h4 className="font-bold text-sm text-slate-700 dark:text-slate-200">Invoice History</h4>
                      <p className="text-xs text-slate-400 mt-1">View, search, edit, download and delete saved logs</p>
                    </div>
                    <ArrowUpRight className="text-slate-400 group-hover:text-violet-500 shrink-0" size={18} />
                  </button>

                  <button
                    onClick={() => navigate("/analytics")}
                    className="w-full flex items-center justify-between p-4 rounded-xl border border-slate-200/50 dark:border-slate-800/40 hover:border-amber-500/50 dark:hover:border-amber-500/50 hover:bg-amber-500/5 dark:hover:bg-amber-500/5 transition-all text-left group"
                  >
                    <div>
                      <h4 className="font-bold text-sm text-slate-700 dark:text-slate-200">Interactive Analytics</h4>
                      <p className="text-xs text-slate-400 mt-1">Check monthly stats, company trends, and GST distributions</p>
                    </div>
                    <ArrowUpRight className="text-slate-400 group-hover:text-amber-500 shrink-0" size={18} />
                  </button>
                </div>
              </div>

              {/* Tips & Recommendations widget */}
              <div className="p-3.5 rounded-xl bg-gradient-to-r from-brand-600/90 to-teal-700/95 text-white shadow-md space-y-1.5">
                <div className="flex items-center gap-1.5">
                  <TrendingUp size={15} className="text-emerald-300 shrink-0 animate-pulse" />
                  <h4 className="font-bold text-xs tracking-wide">Need Help Getting Started?</h4>
                </div>
                <p className="text-[11px] text-slate-100/90 leading-snug">
                  Upload, extract, review, and save invoice data in seconds.
                </p>
              </div>
            </div>
          </div>
        </>
      )}
    </div>
  );
};

export default Dashboard;
