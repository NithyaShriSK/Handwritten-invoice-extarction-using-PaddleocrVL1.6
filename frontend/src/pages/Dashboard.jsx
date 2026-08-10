import React, { useState, useEffect } from "react";
import { Link, useNavigate } from "react-router-dom";
import { Bar, Line, Doughnut, Pie } from "react-chartjs-2";
import {
  Chart as ChartJS,
  CategoryScale,
  LinearScale,
  BarElement,
  PointElement,
  LineElement,
  ArcElement,
  Title,
  Tooltip,
  Legend
} from "chart.js";
import {
  FileText,
  UploadCloud,
  Coins,
  Building,
  Users,
  ArrowUpRight,
  ArrowDownRight,
  Clock,
  ExternalLink,
  Sparkles,
  TrendingUp,
  Landmark,
  PieChart as PieIcon
} from "lucide-react";
import { api } from "../services/api";
import { toast } from "react-toastify";

// Register ChartJS elements
ChartJS.register(
  CategoryScale,
  LinearScale,
  BarElement,
  PointElement,
  LineElement,
  ArcElement,
  Title,
  Tooltip,
  Legend
);

export const Dashboard = () => {
  const [stats, setStats] = useState(null);
  const [recentInvoices, setRecentInvoices] = useState([]);
  const [loading, setLoading] = useState(true);
  const [startDate, setStartDate] = useState("");
  const [endDate, setEndDate] = useState("");
  const navigate = useNavigate();

  useEffect(() => {
    const fetchData = async () => {
      try {
        setLoading(true);
        // Fetch analytics summary metrics with date filters
        const analyticRes = await api.getAnalytics({
          start_date: startDate,
          end_date: endDate
        });
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
        toast.error("Failed to load dashboard metrics.");
      } finally {
        setLoading(false);
      }
    };

    fetchData();
  }, [startDate, endDate]);

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
        return "bg-indigo-100 text-indigo-800 dark:bg-indigo-950/30 dark:text-indigo-400 border-indigo-200 dark:border-indigo-900/30";
      case "Corrected":
        return "bg-violet-100 text-violet-800 dark:bg-violet-950/30 dark:text-violet-400 border-violet-200 dark:border-violet-900/30";
      default:
        return "bg-slate-100 text-slate-800 dark:bg-slate-900 dark:text-slate-400";
    }
  };

  // -----------------------------------------------------------
  // Chart Configs & Datasets derived from stats
  // -----------------------------------------------------------
  const monthlyRevenueData = {
    labels: stats?.monthly_data?.map((d) => d.label) || [],
    datasets: [
      {
        label: "Billing Value (Rs)",
        data: stats?.monthly_data?.map((d) => d.revenue) || [],
        backgroundColor: "rgba(139, 92, 246, 0.15)",
        borderColor: "rgba(139, 92, 246, 1)",
        borderWidth: 2,
        fill: true,
        tension: 0.35,
        pointBackgroundColor: "rgba(139, 92, 246, 1)"
      }
    ]
  };

  const monthlyCountData = {
    labels: stats?.monthly_data?.map((d) => d.label) || [],
    datasets: [
      {
        label: "Invoice count",
        data: stats?.monthly_data?.map((d) => d.count) || [],
        backgroundColor: "rgba(245, 158, 11, 0.75)",
        borderRadius: 4
      }
    ]
  };

  const topVendorsData = {
    labels: stats?.top_companies?.map((v) => v.company_name) || [],
    datasets: [
      {
        data: stats?.top_companies?.map((v) => v.total_value) || [],
        backgroundColor: [
          "rgba(139, 92, 246, 0.75)", // Purple
          "rgba(245, 158, 11, 0.75)",  // Amber/Gold
          "rgba(99, 102, 241, 0.75)",  // Indigo
          "rgba(236, 72, 153, 0.75)",  // Pink
          "rgba(100, 116, 139, 0.75)"  // Slate
        ],
        borderWidth: 0
      }
    ]
  };

  const gstPieData = {
    labels: stats?.gst_distribution ? Object.keys(stats.gst_distribution) : [],
    datasets: [
      {
        data: stats?.gst_distribution ? Object.values(stats.gst_distribution) : [],
        backgroundColor: [
          "rgba(99, 102, 241, 0.75)", // CGST Indigo
          "rgba(139, 92, 246, 0.75)", // SGST Purple
          "rgba(245, 158, 11, 0.75)"   // IGST Amber
        ],
        borderWidth: 0
      }
    ]
  };

  const lineOptions = {
    responsive: true,
    maintainAspectRatio: false,
    plugins: { legend: { display: false } },
    scales: {
      x: { grid: { display: false }, ticks: { color: "rgb(156, 163, 175)", font: { size: 10 } } },
      y: { grid: { color: "rgba(156, 163, 175, 0.08)" }, ticks: { color: "rgb(156, 163, 175)", font: { size: 10 } } }
    }
  };

  const barOptions = {
    responsive: true,
    maintainAspectRatio: false,
    plugins: { legend: { display: false } },
    scales: {
      x: { grid: { display: false }, ticks: { color: "rgb(156, 163, 175)", font: { size: 10 } } },
      y: { grid: { display: false }, ticks: { color: "rgb(156, 163, 175)", font: { size: 10 } } }
    }
  };

  const donutOptions = {
    responsive: true,
    maintainAspectRatio: false,
    plugins: {
      legend: {
        position: "bottom",
        labels: { boxWidth: 10, font: { size: 9 }, color: "rgb(156, 163, 175)" }
      }
    }
  };

  return (
    <div className="space-y-8 animate-fade-in pb-12">
      {/* Silk Loom Banner Header */}
      <div className="relative p-6 md:p-8 bg-gradient-to-r from-violet-900 via-indigo-950 to-slate-900 rounded-3xl overflow-hidden shadow-2xl border border-amber-500/20">
        <div className="absolute top-0 right-0 w-80 h-80 bg-amber-500/5 rounded-full blur-3xl" />
        <div className="absolute bottom-0 left-0 w-64 h-64 bg-violet-500/5 rounded-full blur-2xl" />
        
        <div className="relative z-10 flex flex-col lg:flex-row lg:items-center lg:justify-between gap-6">
          <div className="space-y-2">
            <div className="flex items-center gap-2 text-amber-400 font-bold text-xs tracking-wider uppercase">
              <Sparkles size={14} className="animate-pulse" />
              <span>Royal Silk & Handloom Registry</span>
            </div>
            <h2 className="text-3xl md:text-4xl font-extrabold text-white tracking-tight">
              Dashboard & Analytics
            </h2>
            <p className="text-slate-300 text-sm max-w-xl">
              An all-in-one ledger report monitoring sales volumes, client distributions, tax breakdowns, and AI OCR processing stats.
            </p>
          </div>
          
          <div className="flex items-center gap-3 shrink-0">
            <Link
              to="/extract"
              className="flex items-center gap-2 bg-amber-500 hover:bg-amber-600 text-slate-950 font-bold text-xs px-5 py-3.5 rounded-xl shadow-lg shadow-amber-500/10 transition-all hover:-translate-y-0.5"
            >
              <UploadCloud size={16} />
              <span>AI OCR Extractor</span>
            </Link>
            <Link
              to="/billing"
              className="flex items-center gap-2 bg-white/10 hover:bg-white/15 text-white font-bold text-xs px-5 py-3.5 rounded-xl border border-white/10 transition-all hover:-translate-y-0.5"
            >
              <FileText size={16} />
              <span>New Bill</span>
            </Link>
          </div>
        </div>
      </div>

      {/* Date Filter & Real-Time Statistics Row */}
      <div className="flex flex-wrap items-center justify-between gap-4 bg-white/50 dark:bg-slate-900/40 p-4 rounded-2xl border border-indigo-100/30 dark:border-slate-800">
        <div className="flex items-center gap-2 text-xs font-semibold text-slate-500">
          <span>Filter Ledger:</span>
          <div className="flex items-center gap-2">
            <input
              type="date"
              value={startDate}
              onChange={(e) => setStartDate(e.target.value)}
              className="glass-input py-1 px-3 text-xs focus:ring-brand-500 border-indigo-100"
            />
            <span className="text-slate-300">to</span>
            <input
              type="date"
              value={endDate}
              onChange={(e) => setEndDate(e.target.value)}
              className="glass-input py-1 px-3 text-xs focus:ring-brand-500 border-indigo-100"
            />
          </div>
          {(startDate || endDate) && (
            <button
              onClick={() => {
                setStartDate("");
                setEndDate("");
              }}
              className="text-xs font-bold text-brand-500 hover:underline transition-colors"
            >
              Reset
            </button>
          )}
        </div>

        <div className="text-xs font-medium text-slate-400">
          Showing ledger details: <span className="font-bold text-slate-700 dark:text-slate-200">Real-time</span>
        </div>
      </div>

      {loading ? (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6 animate-pulse">
          {[...Array(4)].map((_, i) => (
            <div key={i} className="glass-card p-6 rounded-2xl h-32" />
          ))}
        </div>
      ) : (
        <>
          {/* 1. Summary Metrics Cards */}
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
            {/* Total Invoices */}
            <div className="glass-card glass-card-hover p-6 rounded-2xl border-l-4 border-l-violet-500 relative overflow-hidden group">
              <div className="flex items-center justify-between">
                <span className="text-xs font-bold text-slate-400 uppercase tracking-wider">Invoices Processed</span>
                <div className="p-3 bg-violet-500/10 text-violet-500 rounded-xl">
                  <FileText size={20} />
                </div>
              </div>
              <div className="mt-4">
                <h3 className="text-2xl font-bold text-slate-800 dark:text-white">
                  {stats?.total_invoices || 0}
                </h3>
                <p className="text-[10px] text-slate-400 mt-2 font-medium">OCR + manually generated bills</p>
              </div>
            </div>

            {/* Total Revenue */}
            <div className="glass-card glass-card-hover p-6 rounded-2xl border-l-4 border-l-amber-500 relative overflow-hidden group">
              <div className="flex items-center justify-between">
                <span className="text-xs font-bold text-slate-400 uppercase tracking-wider">Ledger Turnover</span>
                <div className="p-3 bg-amber-500/10 text-amber-500 rounded-xl">
                  <Coins size={20} />
                </div>
              </div>
              <div className="mt-4">
                <h3 className="text-2xl font-bold text-slate-800 dark:text-white truncate">
                  {formatCurrency(stats?.total_revenue)}
                </h3>
                <p className="text-[10px] text-slate-400 mt-2 font-medium">Total transaction volume</p>
              </div>
            </div>

            {/* Total Companies */}
            <div className="glass-card glass-card-hover p-6 rounded-2xl border-l-4 border-l-indigo-500 relative overflow-hidden group">
              <div className="flex items-center justify-between">
                <span className="text-xs font-bold text-slate-400 uppercase tracking-wider">Active Silk Mills</span>
                <div className="p-3 bg-indigo-500/10 text-indigo-500 rounded-xl">
                  <Building size={20} />
                </div>
              </div>
              <div className="mt-4">
                <h3 className="text-2xl font-bold text-slate-800 dark:text-white">
                  {stats?.unique_companies_count || 0}
                </h3>
                <p className="text-[10px] text-slate-400 mt-2 font-medium">Unique selling mills</p>
              </div>
            </div>

            {/* Total Buyers */}
            <div className="glass-card glass-card-hover p-6 rounded-2xl border-l-4 border-l-pink-500 relative overflow-hidden group">
              <div className="flex items-center justify-between">
                <span className="text-xs font-bold text-slate-400 uppercase tracking-wider">Textile Buyers</span>
                <div className="p-3 bg-pink-500/10 text-pink-500 rounded-xl">
                  <Users size={20} />
                </div>
              </div>
              <div className="mt-4">
                <h3 className="text-2xl font-bold text-slate-800 dark:text-white">
                  {stats?.unique_buyers_count || 0}
                </h3>
                <p className="text-[10px] text-slate-400 mt-2 font-medium">Unique customer brands</p>
              </div>
            </div>
          </div>

          {/* 2. Interactive Charts Section */}
          <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
            {/* Chart 1: Revenue Over Time */}
            <div className="glass-card p-6 rounded-2xl lg:col-span-2 space-y-4">
              <div className="flex items-center justify-between border-b border-slate-100 dark:border-slate-800/40 pb-3">
                <h3 className="text-sm font-bold text-slate-800 dark:text-white">Monthly Sales Revenue</h3>
                <div className="flex items-center gap-1.5 text-[10px] text-slate-400 font-semibold uppercase">
                  <TrendingUp size={12} className="text-violet-500" />
                  <span>Trends</span>
                </div>
              </div>
              <div className="h-64 relative">
                <Line data={monthlyRevenueData} options={lineOptions} />
              </div>
            </div>

            {/* Chart 2: Tax Distribution breakdown */}
            <div className="glass-card p-6 rounded-2xl space-y-4">
              <div className="flex items-center justify-between border-b border-slate-100 dark:border-slate-800/40 pb-3">
                <h3 className="text-sm font-bold text-slate-800 dark:text-white">GST Contribution</h3>
                <PieIcon size={14} className="text-indigo-500" />
              </div>
              <div className="h-64 relative">
                <Pie data={gstPieData} options={donutOptions} />
              </div>
            </div>

            {/* Chart 3: Top Vendor Silk Mills */}
            <div className="glass-card p-6 rounded-2xl space-y-4">
              <div className="flex items-center justify-between border-b border-slate-100 dark:border-slate-800/40 pb-3">
                <h3 className="text-sm font-bold text-slate-800 dark:text-white">Top Silk Mills</h3>
                <Landmark size={14} className="text-amber-500" />
              </div>
              <div className="h-64 relative">
                <Doughnut data={topVendorsData} options={donutOptions} />
              </div>
            </div>

            {/* Chart 4: Invoice counts */}
            <div className="glass-card p-6 rounded-2xl lg:col-span-2 space-y-4">
              <div className="flex items-center justify-between border-b border-slate-100 dark:border-slate-800/40 pb-3">
                <h3 className="text-sm font-bold text-slate-800 dark:text-white">Monthly Volumes</h3>
                <FileText size={14} className="text-orange-500" />
              </div>
              <div className="h-64 relative">
                <Bar data={monthlyCountData} options={barOptions} />
              </div>
            </div>
          </div>

          {/* 3. Workflow status quick widgets */}
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
                <p className="text-xs text-slate-400 font-semibold uppercase tracking-wider">Reviewed</p>
                <h4 className="text-2xl font-bold text-slate-800 dark:text-white mt-1">
                  {stats?.status_counts?.["Reviewed"] || 0}
                </h4>
              </div>
              <div className="w-10 h-10 rounded-xl bg-indigo-500/10 flex items-center justify-center text-indigo-500">
                <FileText size={18} />
              </div>
            </div>

            <div className="glass-card p-5 rounded-2xl flex items-center justify-between">
              <div>
                <p className="text-xs text-slate-400 font-semibold uppercase tracking-wider">Corrected</p>
                <h4 className="text-2xl font-bold text-slate-800 dark:text-white mt-1">
                  {stats?.status_counts?.["Corrected"] || 0}
                </h4>
              </div>
              <div className="w-10 h-10 rounded-xl bg-violet-500/10 flex items-center justify-center text-violet-500">
                <FileText size={18} />
              </div>
            </div>
          </div>

          {/* 4. Recent Invoices Ledger Table */}
          <div className="glass-card p-6 rounded-2xl space-y-4">
            <div className="flex items-center justify-between border-b border-slate-100 dark:border-slate-800/40 pb-3">
              <h3 className="text-sm font-bold text-slate-800 dark:text-white">Recent Loom Invoices</h3>
              <Link
                to="/history"
                className="text-xs text-brand-500 hover:text-brand-650 font-bold flex items-center gap-1"
              >
                <span>View Full Registry</span>
                <ExternalLink size={12} />
              </Link>
            </div>

            <div className="overflow-x-auto">
              <table className="w-full text-xs text-left">
                <thead>
                  <tr className="text-slate-400 font-semibold border-b border-slate-100 dark:border-slate-800/60">
                    <th className="pb-3">Vendor / Mill</th>
                    <th className="pb-3">Buyer Name</th>
                    <th className="pb-3 text-center">Invoice No</th>
                    <th className="pb-3 text-center">Date</th>
                    <th className="pb-3 text-right">Amount (Rs)</th>
                    <th className="pb-3 text-center">Status</th>
                    <th className="pb-3 text-center">Actions</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-100 dark:divide-slate-800/40">
                  {recentInvoices.map((inv) => (
                    <tr key={inv._id} className="hover:bg-slate-50/50 dark:hover:bg-slate-900/20 transition-colors">
                      <td className="py-3 font-semibold text-slate-800 dark:text-slate-200">
                        {inv.edited_invoice_data?.company_name || "N/A"}
                      </td>
                      <td className="py-3 text-slate-500 dark:text-slate-400">
                        {inv.edited_invoice_data?.buyer_name || "N/A"}
                      </td>
                      <td className="py-3 text-center text-slate-600 dark:text-slate-300 font-semibold">
                        {inv.edited_invoice_data?.invoice_number || "N/A"}
                      </td>
                      <td className="py-3 text-center text-slate-500 dark:text-slate-400">
                        {inv.edited_invoice_data?.invoice_date || "N/A"}
                      </td>
                      <td className="py-3 text-right font-bold text-slate-700 dark:text-slate-300">
                        {formatCurrency(inv.edited_invoice_data?.total_amount)}
                      </td>
                      <td className="py-3 text-center">
                        <span className={`px-2 py-1 text-[10px] font-bold rounded-lg border ${getStatusBadgeClass(inv.review_status)}`}>
                          {inv.review_status}
                        </span>
                      </td>
                      <td className="py-3 text-center">
                        <Link
                          to={`/invoice/${inv._id}`}
                          className="text-brand-500 hover:text-brand-600 font-bold hover:underline"
                        >
                          Review
                        </Link>
                      </td>
                    </tr>
                  ))}
                  {recentInvoices.length === 0 && (
                    <tr>
                      <td colSpan={7} className="text-center py-6 text-slate-400">
                        No transactions registered yet. Upload an invoice above to start registry.
                      </td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>
          </div>
        </>
      )}
    </div>
  );
};

export default Dashboard;
