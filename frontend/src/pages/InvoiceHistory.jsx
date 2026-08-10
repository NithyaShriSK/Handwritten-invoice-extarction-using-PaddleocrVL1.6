import React, { useState, useEffect } from "react";
import { useSearchParams, useNavigate } from "react-router-dom";
import {
  Search,
  Filter,
  ArrowUpDown,
  Eye,
  Edit2,
  Trash2,
  Download,
  Calendar,
  AlertTriangle,
  ChevronLeft,
  ChevronRight,
  ImageIcon,
  Sparkles
} from "lucide-react";
import { api, API_URL } from "../services/api";
import { exportToCSV, exportToJSON } from "../utils/csvExport";
import { toast } from "react-toastify";
import axios from "axios";

export const InvoiceHistory = () => {
  const [searchParams, setSearchParams] = useSearchParams();
  const navigate = useNavigate();

  // Search & Filter States
  const [search, setSearch] = useState(searchParams.get("search") || "");
  const [reviewStatus, setReviewStatus] = useState("");
  const [startDate, setStartDate] = useState("");
  const [endDate, setEndDate] = useState("");
  const [sortBy, setSortBy] = useState("created_at");
  const [sortOrder, setSortOrder] = useState("desc");
  const [page, setPage] = useState(1);
  
  // Data States
  const [invoices, setInvoices] = useState([]);
  const [totalCount, setTotalCount] = useState(0);
  const [totalPages, setTotalPages] = useState(1);
  const [loading, setLoading] = useState(true);

  // Sync global search from URL parameters
  useEffect(() => {
    const urlSearch = searchParams.get("search");
    if (urlSearch !== null) {
      setSearch(urlSearch);
    }
  }, [searchParams]);

  // Fetch paginated invoices when filters change
  const fetchInvoices = async () => {
    try {
      setLoading(true);
      const params = {
        search: search.trim(),
        review_status: reviewStatus,
        start_date: startDate,
        end_date: endDate,
        sort_by: sortBy,
        sort_order: sortOrder,
        page,
        limit: 10
      };
      
      const response = await api.getInvoices(params);
      if (response.success) {
        setInvoices(response.data.invoices);
        setTotalCount(response.data.total);
        setTotalPages(response.data.pages);
      }
    } catch (err) {
      console.error(err);
      toast.error("Failed to load invoice history from server.");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchInvoices();
  }, [search, reviewStatus, startDate, endDate, sortBy, sortOrder, page]);

  // Handle pagination triggers
  const handlePageChange = (newPage) => {
    if (newPage >= 1 && newPage <= totalPages) {
      setPage(newPage);
    }
  };

  // Trigger sorting
  const handleSort = (field) => {
    if (sortBy === field) {
      setSortOrder(sortOrder === "asc" ? "desc" : "asc");
    } else {
      setSortBy(field);
      setSortOrder("desc");
    }
    setPage(1);
  };

  // soft delete invoice handler
  const handleDelete = async (id) => {
    if (window.confirm("Are you sure you want to delete this invoice? (Data recovery is possible via soft delete)")) {
      try {
        const response = await api.deleteInvoice(id);
        if (response.success) {
          toast.success("Invoice deleted successfully.");
          fetchInvoices();
        }
      } catch (err) {
        toast.error("Delete failed. Server offline.");
      }
    }
  };

  // Download raw uploaded image
  const handleDownloadImage = (imagePath, invNumber) => {
    if (!imagePath) {
      toast.error("No image available for this invoice.");
      return;
    }
    const cleanNum = invNumber || "invoice";
    const ext = imagePath.split(".").pop().toLowerCase();
    const cleanExt = ["png", "jpg", "jpeg"].includes(ext) ? ext : "png";
    const filename = `${cleanNum}_original.${cleanExt}`;
    const url = imagePath.startsWith("/") ? `${API_URL}${imagePath}` : imagePath;

    // Trigger download in new tab
    const link = document.createElement("a");
    link.href = url;
    link.download = filename;
    link.target = "_blank";
    link.click();
    toast.success("Original image open request dispatched.");
  };

  // Export ALL currently filtered invoices
  const handleExportAll = async (format) => {
    try {
      toast.info(`Preparing ${format.toUpperCase()} export for all filtered items...`);
      // Request all matches by setting limit = 10000000
      const params = {
        search: search.trim(),
        review_status: reviewStatus,
        start_date: startDate,
        end_date: endDate,
        sort_by: sortBy,
        sort_order: sortOrder,
        page: 1,
        limit: 1000000
      };
      
      const response = await api.getInvoices(params);
      if (response.success && response.data.invoices.length > 0) {
        const list = response.data.invoices;
        if (format === "csv") {
          exportToCSV(list, "all_filtered_invoices.csv");
        } else {
          // Export JSON of all corrected versions in the list
          const correctedList = list.map(inv => inv.edited_invoice_data);
          const jsonString = JSON.stringify(correctedList, null, 2);
          const blob = new Blob([jsonString], { type: "application/json;charset=utf-8;" });
          const url = URL.createObjectURL(blob);
          const link = document.createElement("a");
          link.href = url;
          link.download = "all_filtered_invoices.json";
          link.click();
        }
        toast.success(`Exported ${list.length} invoices successfully.`);
      } else {
        toast.warn("No invoices found matching current filters.");
      }
    } catch (err) {
      toast.error("Export all failed.");
    }
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

  const formatCurrency = (val) => {
    return new Intl.NumberFormat("en-IN", {
      style: "currency",
      currency: "INR",
      maximumFractionDigits: 0
    }).format(val || 0);
  };

  return (
    <div className="space-y-8 animate-fade-in pb-16">
      {/* Page Header & Bulk Export utility */}
      <div className="flex flex-col md:flex-row md:items-center md:justify-between gap-4">
        <div>
          <h2 className="text-3xl font-extrabold text-slate-800 dark:text-white tracking-tight">
            Invoice History Log
          </h2>
          <p className="text-slate-500 dark:text-slate-400 text-sm mt-1">
            Search, sort, filter, and audit all invoice documents stored in MongoDB Atlas.
          </p>
        </div>
        
        {/* Export All Controls */}
        <div className="flex items-center gap-2">
          <button
            onClick={() => handleExportAll("csv")}
            className="flex items-center gap-1.5 bg-white hover:bg-slate-100 dark:bg-slate-900 dark:hover:bg-slate-800 text-slate-700 dark:text-slate-200 border border-slate-200 dark:border-slate-800 text-xs font-bold px-4 py-2.5 rounded-xl transition-all"
          >
            <Download size={14} />
            <span>Export All CSV</span>
          </button>
          
          <button
            onClick={() => handleExportAll("json")}
            className="flex items-center gap-1.5 bg-white hover:bg-slate-100 dark:bg-slate-900 dark:hover:bg-slate-800 text-slate-700 dark:text-slate-200 border border-slate-200 dark:border-slate-800 text-xs font-bold px-4 py-2.5 rounded-xl transition-all"
          >
            <Download size={14} />
            <span>Export All JSON</span>
          </button>
        </div>
      </div>

      {/* Advanced Filter Panel */}
      <div className="glass-card p-6 rounded-2xl grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4 items-end">
        {/* Search */}
        <div className="flex flex-col gap-1.5">
          <label className="text-xs font-semibold text-slate-400">Search Invoices</label>
          <div className="relative">
            <span className="absolute left-3 top-2.5 text-slate-400">
              <Search size={14} />
            </span>
            <input
              type="text"
              value={search}
              onChange={(e) => {
                setSearch(e.target.value);
                setPage(1);
              }}
              placeholder="Company, Buyer, Invoice #..."
              className="w-full pl-9 pr-3 py-2 text-xs rounded-xl glass-input placeholder-slate-400 focus:outline-none"
            />
          </div>
        </div>

        {/* Review Status Filter */}
        <div className="flex flex-col gap-1.5">
          <label className="text-xs font-semibold text-slate-400">Review Status</label>
          <select
            value={reviewStatus}
            onChange={(e) => {
              setReviewStatus(e.target.value);
              setPage(1);
            }}
            className="glass-input text-xs"
          >
            <option value="">All Statuses</option>
            <option value="Pending Review">Pending Review</option>
            <option value="Reviewed">Reviewed</option>
            <option value="Corrected">Corrected</option>
          </select>
        </div>

        {/* Date filters */}
        <div className="flex flex-col gap-1.5">
          <label className="text-xs font-semibold text-slate-400">Start Date</label>
          <div className="relative">
            <span className="absolute left-3 top-2.5 text-slate-400">
              <Calendar size={14} />
            </span>
            <input
              type="date"
              value={startDate}
              onChange={(e) => {
                setStartDate(e.target.value);
                setPage(1);
              }}
              className="w-full pl-9 pr-3 py-2 text-xs rounded-xl glass-input placeholder-slate-400 focus:outline-none"
            />
          </div>
        </div>

        <div className="flex flex-col gap-1.5">
          <label className="text-xs font-semibold text-slate-400">End Date</label>
          <div className="relative">
            <span className="absolute left-3 top-2.5 text-slate-400">
              <Calendar size={14} />
            </span>
            <input
              type="date"
              value={endDate}
              onChange={(e) => {
                setEndDate(e.target.value);
                setPage(1);
              }}
              className="w-full pl-9 pr-3 py-2 text-xs rounded-xl glass-input placeholder-slate-400 focus:outline-none"
            />
          </div>
        </div>
      </div>

      {/* Main Table Card */}
      <div className="glass-card rounded-2xl overflow-hidden">
        {loading ? (
          <div className="flex flex-col items-center justify-center py-20 space-y-4">
            <div className="w-10 h-10 border-4 border-emerald-600 border-t-transparent rounded-full animate-spin"></div>
            <span className="text-sm text-slate-500 dark:text-slate-400 font-medium">Fetching active invoice records from MongoDB...</span>
          </div>
        ) : invoices.length === 0 ? (
          <div className="py-20 text-center text-slate-400 text-sm flex flex-col items-center justify-center">
            <AlertTriangle className="text-slate-300 dark:text-slate-700 mb-2" size={32} />
            <p className="font-bold text-slate-600 dark:text-slate-300">No records found</p>
            <p className="text-xs text-slate-400 mt-1 max-w-xs">
              Try adjusting your query, search criteria, or date parameters.
            </p>
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-left border-collapse text-xs">
              <thead>
                <tr className="text-slate-400 dark:text-slate-500 border-b border-slate-200 dark:border-slate-800 bg-slate-100/30 dark:bg-slate-900/30">
                  <th className="p-4 font-bold cursor-pointer" onClick={() => handleSort("company_name")}>
                    <div className="flex items-center gap-1">
                      <span>Company Name</span>
                      <ArrowUpDown size={12} />
                    </div>
                  </th>
                  <th className="p-4 font-bold cursor-pointer" onClick={() => handleSort("invoice_number")}>
                    <div className="flex items-center gap-1">
                      <span>Invoice #</span>
                      <ArrowUpDown size={12} />
                    </div>
                  </th>
                  <th className="p-4 font-bold">Buyer Name</th>
                  <th className="p-4 font-bold cursor-pointer text-right" onClick={() => handleSort("total_amount")}>
                    <div className="flex items-center justify-end gap-1">
                      <span>Total Amount</span>
                      <ArrowUpDown size={12} />
                    </div>
                  </th>
                  <th className="p-4 font-bold cursor-pointer" onClick={() => handleSort("invoice_date")}>
                    <div className="flex items-center gap-1">
                      <span>Invoice Date</span>
                      <ArrowUpDown size={12} />
                    </div>
                  </th>
                  <th className="p-4 font-bold cursor-pointer" onClick={() => handleSort("created_at")}>
                    <div className="flex items-center gap-1">
                      <span>Created Date</span>
                      <ArrowUpDown size={12} />
                    </div>
                  </th>
                  <th className="p-4 font-bold">Status</th>
                  <th className="p-4 text-center font-bold">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100 dark:divide-slate-800/40">
                {invoices.map((inv) => {
                  const data = inv.edited_invoice_data;
                  return (
                    <tr key={inv._id} className="hover:bg-slate-100/50 dark:hover:bg-slate-800/10 transition-colors">
                      <td className="p-4 font-bold text-slate-700 dark:text-slate-200">
                        {data.company_name || "Unknown Company"}
                      </td>
                      <td className="p-4 font-mono font-semibold text-slate-600 dark:text-slate-400">
                        {data.invoice_number || "N/A"}
                      </td>
                      <td className="p-4 text-slate-600 dark:text-slate-400">
                        {data.buyer_name || "Unknown Buyer"}
                      </td>
                      <td className="p-4 text-right font-extrabold text-slate-700 dark:text-slate-200">
                        {formatCurrency(data.total_amount)}
                      </td>
                      <td className="p-4 text-slate-500 font-semibold">
                        {data.invoice_date || "N/A"}
                      </td>
                      <td className="p-4 text-slate-400">
                        {new Date(inv.created_at).toLocaleDateString()}
                      </td>
                      <td className="p-4">
                        <span className={`px-2.5 py-1 rounded-full text-[10px] font-bold border ${getStatusBadgeClass(inv.review_status)}`}>
                          {inv.review_status}
                        </span>
                      </td>
                      <td className="p-4">
                        <div className="flex items-center justify-center gap-1.5">
                          {/* View Detail Page */}
                          <button
                            onClick={() => {
                              console.log("Invoice ID:", inv._id);
                              navigate(`/invoice/${inv._id}`);
                            }}
                            title="View / Edit details"
                            className="p-1.5 rounded-lg text-slate-400 hover:text-brand-500 hover:bg-brand-500/5 transition-all"
                          >
                            <Eye size={14} />
                          </button>

                          {/* Image download */}
                          <button
                            onClick={() => handleDownloadImage(inv.invoice_image_path, data.invoice_number)}
                            title="Download Original Invoice Image"
                            className="p-1.5 rounded-lg text-slate-400 hover:text-emerald-500 hover:bg-emerald-500/5 transition-all"
                          >
                            <ImageIcon size={14} />
                          </button>

                          {/* CSV Download */}
                          <button
                            onClick={() => exportToCSV(inv, `${data.invoice_number || "invoice"}.csv`)}
                            title="Download CSV"
                            className="p-1.5 rounded-lg text-slate-400 hover:text-emerald-500 hover:bg-emerald-500/5 transition-all"
                          >
                            <Download size={14} />
                          </button>

                          {/* JSON Download */}
                          <button
                            onClick={() => exportToJSON(inv, `${data.invoice_number || "invoice"}.json`)}
                            title="Download JSON"
                            className="p-1.5 rounded-lg text-slate-400 hover:text-pink-500 hover:bg-pink-500/5 transition-all"
                          >
                            <Download size={14} />
                          </button>

                          {/* Soft delete */}
                          <button
                            onClick={() => handleDelete(inv._id)}
                            title="Soft delete"
                            className="p-1.5 rounded-lg text-slate-400 hover:text-rose-500 hover:bg-rose-500/5 transition-all"
                          >
                            <Trash2 size={14} />
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

        {/* Pagination Control bar */}
        {!loading && invoices.length > 0 && (
          <div className="flex items-center justify-between px-6 py-4 border-t border-slate-200 dark:border-slate-800 text-xs">
            <span className="text-slate-400">
              Showing Page <span className="font-semibold text-slate-700 dark:text-slate-300">{page}</span> of{" "}
              <span className="font-semibold text-slate-700 dark:text-slate-300">{totalPages}</span> ({totalCount} total records)
            </span>
            
            <div className="flex items-center gap-1.5">
              <button
                onClick={() => handlePageChange(page - 1)}
                disabled={page === 1}
                className="p-2 rounded-lg border border-slate-200 dark:border-slate-800 text-slate-500 disabled:opacity-50 disabled:cursor-not-allowed hover:bg-slate-100 dark:hover:bg-slate-800 transition-colors"
              >
                <ChevronLeft size={14} />
              </button>
              
              <button
                onClick={() => handlePageChange(page + 1)}
                disabled={page === totalPages}
                className="p-2 rounded-lg border border-slate-200 dark:border-slate-800 text-slate-500 disabled:opacity-50 disabled:cursor-not-allowed hover:bg-slate-100 dark:hover:bg-slate-800 transition-colors"
              >
                <ChevronRight size={14} />
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
};

export default InvoiceHistory;
