import React, { useState, useEffect } from "react";
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
import { api } from "../services/api";
import { toast } from "react-toastify";
import {
  BarChart3,
  TrendingUp,
  FileText,
  Coins,
  Building,
  Users,
  PieChart as PieIcon,
  ShieldCheck,
  AlertCircle
} from "lucide-react";

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

export const Analytics = () => {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const fetchAnalytics = async () => {
      try {
        setLoading(true);
        const response = await api.getAnalytics();
        if (response.success) {
          setData(response.data);
        }
      } catch (err) {
        console.error(err);
        toast.error("Failed to load analytics reports from database.");
      } finally {
        setLoading(false);
      }
    };
    fetchAnalytics();
  }, []);

  const formatCurrency = (val) => {
    return new Intl.NumberFormat("en-IN", {
      style: "currency",
      currency: "INR",
      maximumFractionDigits: 0
    }).format(val || 0);
  };

  if (loading) {
    return (
      <div className="flex flex-col items-center justify-center py-20 space-y-4">
        <div className="w-10 h-10 border-4 border-emerald-600 border-t-transparent rounded-full animate-spin"></div>
        <span className="text-sm text-slate-500 dark:text-slate-400 font-medium">Computing database aggregations and rendering charts...</span>
      </div>
    );
  }

  if (!data) {
    return (
      <div className="py-20 text-center text-slate-400 text-sm flex flex-col items-center justify-center">
        <AlertCircle size={32} className="text-slate-300 mb-2" />
        <p className="font-bold">Analytics Data Unavailable</p>
        <p className="text-xs text-slate-400 mt-1">Please ensure your MongoDB has active invoice documents.</p>
      </div>
    );
  }

  // Monthly Invoice Count Data
  const monthlyCountData = {
    labels: data.monthly_data?.map((d) => d.label) || [],
    datasets: [
      {
        label: "Invoice Count",
        data: data.monthly_data?.map((d) => d.count) || [],
        backgroundColor: "rgba(14, 144, 233, 0.75)",
        borderColor: "rgba(14, 144, 233, 1)",
        borderWidth: 1,
        borderRadius: 6
      }
    ]
  };

  // Monthly Revenue Data
  const monthlyRevenueData = {
    labels: data.monthly_data?.map((d) => d.label) || [],
    datasets: [
      {
        label: "Billing Revenue (Rs)",
        data: data.monthly_data?.map((d) => d.revenue) || [],
        backgroundColor: "rgba(16, 185, 129, 0.1)",
        borderColor: "rgba(16, 185, 129, 1)",
        borderWidth: 2.5,
        fill: true,
        tension: 0.3,
        pointBackgroundColor: "rgba(16, 185, 129, 1)",
        pointHoverRadius: 6
      }
    ]
  };

  // OCR Correction Analysis Data
  const totalInvoicesCount = (data.status_counts?.["Reviewed"] || 0) +
                              (data.status_counts?.["Corrected"] || 0) +
                              (data.status_counts?.["Pending Review"] || 0);

  const getPercentage = (count) => {
    if (totalInvoicesCount === 0) return 0;
    return Math.round((count / totalInvoicesCount) * 100);
  };

  const ocrCorrectionData = {
    labels: [
      `Reviewed: ${getPercentage(data.status_counts?.["Reviewed"] || 0)}% (${data.status_counts?.["Reviewed"] || 0})`,
      `Corrected: ${getPercentage(data.status_counts?.["Corrected"] || 0)}% (${data.status_counts?.["Corrected"] || 0})`,
      `Pending Review: ${getPercentage(data.status_counts?.["Pending Review"] || 0)}% (${data.status_counts?.["Pending Review"] || 0})`
    ],
    datasets: [
      {
        data: [
          data.status_counts?.["Reviewed"] || 0,
          data.status_counts?.["Corrected"] || 0,
          data.status_counts?.["Pending Review"] || 0
        ],
        backgroundColor: [
          "rgba(16, 185, 129, 0.75)", // Reviewed - Emerald/Green
          "rgba(14, 144, 233, 0.75)", // Corrected - Blue
          "rgba(245, 158, 11, 0.75)"  // Pending Review - Amber/Orange
        ],
        borderWidth: 0
      }
    ]
  };

  // Top 5 Buyers
  const topBuyersData = {
    labels: data.top_buyers?.map((b) => b.buyer_name) || [],
    datasets: [
      {
        label: "Billing Value (Rs)",
        data: data.top_buyers?.map((b) => b.total_value) || [],
        backgroundColor: "rgba(139, 92, 246, 0.75)",
        borderRadius: 6
      }
    ]
  };

  // GST Distribution Breakdown Data
  const gstValues = Object.values(data.gst_distribution || {});
  const totalGst = gstValues.reduce((acc, val) => acc + val, 0);

  const getGstPercentage = (val) => {
    if (totalGst === 0) return 0;
    return Math.round((val / totalGst) * 100);
  };

  const gstPieData = {
    labels: Object.keys(data.gst_distribution || {}).map(
      (key) => `${key}: ${getGstPercentage(data.gst_distribution?.[key] || 0)}%`
    ),
    datasets: [
      {
        data: Object.values(data.gst_distribution || {}),
        backgroundColor: [
          "rgba(14, 144, 233, 0.75)", // CGST - Blue
          "rgba(16, 185, 129, 0.75)", // SGST - Emerald
          "rgba(236, 72, 153, 0.75)"  // IGST - Pink
        ],
        borderWidth: 0
      }
    ]
  };

  // Revenue Contribution by Buyer (%) Data
  const buyersDataList = data.top_buyers || [];
  const totalBuyerRevenue = buyersDataList.reduce((sum, b) => sum + (b.total_value || 0), 0);
  const hasBuyerRevenue = totalBuyerRevenue > 0;

  let contributionBarData = null;
  let sortedBuyersByPct = [];

  if (hasBuyerRevenue) {
    const buyersWithPct = buyersDataList.map((b) => {
      const percentage = (b.total_value / totalBuyerRevenue) * 100;
      return {
        ...b,
        percentage
      };
    });

    sortedBuyersByPct = [...buyersWithPct].sort((a, b) => b.percentage - a.percentage);

    const contributionColors = [
      "rgba(16, 185, 129, 0.75)", // Emerald
      "rgba(14, 144, 233, 0.75)", // Blue
      "rgba(245, 158, 11, 0.75)",  // Amber
      "rgba(139, 92, 246, 0.75)"  // Purple
    ];
    const contributionHoverColors = [
      "rgba(16, 185, 129, 1)",
      "rgba(14, 144, 233, 1)",
      "rgba(245, 158, 11, 1)",
      "rgba(139, 92, 246, 1)"
    ];

    contributionBarData = {
      labels: ["Revenue Share"],
      datasets: sortedBuyersByPct.map((b, idx) => ({
        label: b.buyer_name,
        data: [Number(b.percentage.toFixed(1))],
        backgroundColor: contributionColors[idx % contributionColors.length],
        hoverBackgroundColor: contributionHoverColors[idx % contributionHoverColors.length]
      }))
    };
  }

  const chartOptions = {
    responsive: true,
    maintainAspectRatio: false,
    plugins: {
      legend: {
        position: "bottom",
        labels: {
          boxWidth: 12,
          font: { size: 10 },
          color: "rgb(156, 163, 175)"
        }
      }
    },
    scales: {
      x: {
        grid: { display: false },
        ticks: { color: "rgb(156, 163, 175)", font: { size: 10 } }
      },
      y: {
        grid: { color: "rgba(156, 163, 175, 0.1)" },
        ticks: { color: "rgb(156, 163, 175)", font: { size: 10 } }
      }
    }
  };

  const pieOptions = {
    responsive: true,
    maintainAspectRatio: false,
    plugins: {
      legend: {
        position: "bottom",
        labels: {
          boxWidth: 12,
          font: { size: 10 },
          color: "rgb(156, 163, 175)"
        }
      }
    }
  };

  const gstPieOptions = {
    responsive: true,
    maintainAspectRatio: false,
    plugins: {
      legend: {
        position: "bottom",
        labels: {
          boxWidth: 12,
          font: { size: 10 },
          color: "rgb(156, 163, 175)"
        }
      },
      tooltip: {
        callbacks: {
          label: (context) => {
            const label = context.label.split(":")[0] || '';
            const value = context.parsed || 0;
            const total = context.dataset.data.reduce((acc, val) => acc + val, 0);
            const percentage = total > 0 ? Math.round((value / total) * 100) : 0;
            const formattedVal = new Intl.NumberFormat("en-IN", {
              style: "currency",
              currency: "INR",
              maximumFractionDigits: 0
            }).format(value);
            return ` ${label}: ${formattedVal} (${percentage}%)`;
          }
        }
      }
    }
  };

  const contributionBarOptions = {
    indexAxis: 'y',
    responsive: true,
    maintainAspectRatio: false,
    plugins: {
      legend: {
        position: "bottom",
        labels: {
          boxWidth: 12,
          font: { size: 10 },
          color: "rgb(156, 163, 175)"
        }
      },
      tooltip: {
        callbacks: {
          label: (context) => {
            const buyerName = context.dataset.label;
            const percentage = context.raw;
            const buyer = sortedBuyersByPct.find(b => b.buyer_name === buyerName);
            const valueFormatted = buyer ? formatCurrency(buyer.total_value) : '';
            return ` ${buyerName}: ${percentage}% (${valueFormatted})`;
          }
        }
      }
    },
    scales: {
      x: {
        stacked: true,
        max: 100,
        grid: { color: "rgba(156, 163, 175, 0.1)" },
        ticks: {
          color: "rgb(156, 163, 175)",
          font: { size: 10 },
          callback: (value) => `${value}%`
        }
      },
      y: {
        stacked: true,
        grid: { display: false },
        ticks: { color: "rgb(156, 163, 175)", font: { size: 10 } }
      }
    }
  };

  return (
    <div className="space-y-8 animate-fade-in pb-16">
      {/* Header */}
      <div>
        <h2 className="text-3xl font-extrabold text-slate-800 dark:text-white tracking-tight flex items-center gap-2">
          <BarChart3 className="text-brand-500" />
          <span>Interactive Analytics</span>
        </h2>
        <p className="text-slate-500 dark:text-slate-400 text-sm mt-1">
          Aggregated visual reports of invoice tax spreads, volume counts, and client billings.
        </p>
      </div>

      {/* KPI Stats widgets */}
      <div className="grid grid-cols-1 md:grid-cols-3 lg:grid-cols-6 gap-4">
        {/* Processed */}
        <div className="glass-card p-5 rounded-2xl">
          <span className="text-[10px] font-bold text-slate-400 uppercase tracking-wider">Processed</span>
          <h4 className="text-xl font-extrabold text-slate-800 dark:text-white mt-1">
            {data.total_invoices || 0}
          </h4>
        </div>

        {/* Revenue */}
        <div className="glass-card p-5 rounded-2xl lg:col-span-2">
          <span className="text-[10px] font-bold text-slate-400 uppercase tracking-wider">Total Billing Value</span>
          <h4 className="text-xl font-extrabold text-slate-850 dark:text-white mt-1 truncate">
            {formatCurrency(data.total_revenue)}
          </h4>
        </div>

        {/* Companies */}
        <div className="glass-card p-5 rounded-2xl">
          <span className="text-[10px] font-bold text-slate-400 uppercase tracking-wider">Vendors</span>
          <h4 className="text-xl font-extrabold text-slate-800 dark:text-white mt-1">
            {data.unique_companies_count || 0}
          </h4>
        </div>

        {/* Buyers */}
        <div className="glass-card p-5 rounded-2xl">
          <span className="text-[10px] font-bold text-slate-400 uppercase tracking-wider">Buyers</span>
          <h4 className="text-xl font-extrabold text-slate-800 dark:text-white mt-1">
            {data.unique_buyers_count || 0}
          </h4>
        </div>

        {/* Pending Review */}
        <div className="glass-card p-5 rounded-2xl">
          <span className="text-[10px] font-bold text-amber-500 uppercase tracking-wider">Pending Review</span>
          <h4 className="text-xl font-extrabold text-amber-500 mt-1">
            {data.status_counts?.["Pending Review"] || 0}
          </h4>
        </div>
      </div>

      {/* Primary Graphs Grid */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Monthly Invoice Volume */}
        <div className="glass-card p-6 rounded-2xl space-y-4">
          <h3 className="text-sm font-bold text-slate-700 dark:text-slate-200">Monthly Invoice Volume</h3>
          <div className="h-64">
            <Bar data={monthlyCountData} options={chartOptions} />
          </div>
        </div>

        {/* Monthly Revenue Billing */}
        <div className="glass-card p-6 rounded-2xl space-y-4">
          <h3 className="text-sm font-bold text-slate-700 dark:text-slate-200">Monthly Billing Revenue</h3>
          <div className="h-64">
            <Line data={monthlyRevenueData} options={chartOptions} />
          </div>
        </div>

        {/* OCR Correction Analysis */}
        <div className="glass-card p-6 rounded-2xl space-y-4">
          <h3 className="text-sm font-bold text-slate-700 dark:text-slate-200">OCR Correction Analysis</h3>
          <div className="h-64">
            <Doughnut data={ocrCorrectionData} options={pieOptions} />
          </div>
        </div>

        {/* Top 5 Buyers by Value */}
        <div className="glass-card p-6 rounded-2xl space-y-4">
          <h3 className="text-sm font-bold text-slate-700 dark:text-slate-200">Top 5 Buyers by Billing</h3>
          <div className="h-64">
            <Bar data={topBuyersData} options={chartOptions} />
          </div>
        </div>

        {/* GST Distribution Breakdown */}
        <div className="glass-card p-6 rounded-2xl space-y-4">
          <h3 className="text-sm font-bold text-slate-700 dark:text-slate-200">GST Distribution Breakdown</h3>
          <div className="h-64">
            <Pie data={gstPieData} options={gstPieOptions} />
          </div>
        </div>

        {/* Revenue Contribution by Buyer (%) */}
        <div className="glass-card p-6 rounded-2xl space-y-4">
          <h3 className="text-sm font-bold text-slate-700 dark:text-slate-200">Revenue Contribution by Buyer (%)</h3>
          <div className="h-64">
            {hasBuyerRevenue ? (
              <Bar data={contributionBarData} options={contributionBarOptions} />
            ) : (
              <div className="flex items-center justify-center h-full text-slate-400 text-xs">
                No buyer revenue data available.
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
};

export default Analytics;
