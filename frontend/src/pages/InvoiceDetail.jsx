import React, { useState, useEffect } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { useForm, useFieldArray } from "react-hook-form";
import {
  ArrowLeft,
  Save,
  Download,
  Trash2,
  Calendar,
  History,
  Image as ImageIcon,
  Sparkles,
  CheckCircle,
  FileSpreadsheet,
  AlertTriangle,
  Plus
} from "lucide-react";
import { api } from "../services/api";
import { exportToCSV, exportToJSON } from "../utils/csvExport";
import { toast } from "react-toastify";

const sanitizeInvoiceData = (data) => {
  if (!data) return {};
  
  const sanitizeNumber = (val) => {
    if (val === null || val === undefined || isNaN(Number(val))) {
      return 0;
    }
    return Number(val);
  };

  const sanitizedProducts = (data.products_list || []).map(prod => ({
    ...prod,
    product_name: prod.product_name || "",
    hsn_code: prod.hsn_code || "",
    quantity: sanitizeNumber(prod.quantity),
    rate: sanitizeNumber(prod.rate),
    amount: sanitizeNumber(prod.amount),
  }));

  return {
    ...data,
    company_name: data.company_name || "",
    company_gst_no: data.company_gst_no || "",
    invoice_number: data.invoice_number || "",
    invoice_date: data.invoice_date || "",
    state_code: data.state_code || "",
    vehicle_number: data.vehicle_number || "",
    transportation_mode: data.transportation_mode || "",
    buyer_name: data.buyer_name || "",
    buyer_gst_no: data.buyer_gst_no || "",
    total_amount_in_words: data.total_amount_in_words || "",
    cgst_amount: sanitizeNumber(data.cgst_amount),
    sgst_amount: sanitizeNumber(data.sgst_amount),
    igst_amount: sanitizeNumber(data.igst_amount),
    total_amount: sanitizeNumber(data.total_amount),
    products_list: sanitizedProducts
  };
};

export const InvoiceDetail = () => {
  const { id } = useParams();
  const navigate = useNavigate();
  const [loading, setLoading] = useState(true);
  const [invoice, setInvoice] = useState(null);
  
  // React Hook Form
  const {
    register,
    control,
    handleSubmit,
    setValue,
    watch,
    reset,
    formState: { errors }
  } = useForm();

  const { fields, append, remove } = useFieldArray({
    control,
    name: "products_list"
  });

  const formValues = watch();

  // Fetch Invoice Details on Mount
  const fetchInvoiceDetails = async () => {
    try {
      setLoading(true);
      console.log("Loading invoice:", id);
      const response = await api.getInvoice(id);
      console.log("Invoice response:", response.data);
      if (response.success) {
        setInvoice(response.data);
        const sanitized = sanitizeInvoiceData(response.data.edited_invoice_data);
        reset(sanitized);
      }
    } catch (err) {
      console.error(err);
      toast.error("Failed to retrieve invoice details. Invoice may be deleted.");
      navigate("/history");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    reset({
      company_name: "",
      company_gst_no: "",
      invoice_number: "",
      invoice_date: "",
      state_code: "",
      vehicle_number: "",
      transportation_mode: "",
      cgst_amount: 0,
      sgst_amount: 0,
      igst_amount: 0,
      total_amount: 0,
      buyer_name: "",
      buyer_gst_no: "",
      total_amount_in_words: "",
      products_list: []
    });
    setInvoice(null);
    fetchInvoiceDetails();
  }, [id, reset]);

  // Dynamic Recalculation Handlers (Only triggered on user manual edits)
  const recalculateTotals = (productsList) => {
    let subtotal = 0;
    productsList.forEach((prod) => {
      subtotal += parseFloat(prod.amount) || 0;
    });

    const compGst = watch("company_gst_no") || "";
    const buyerGst = watch("buyer_gst_no") || "";
    const compState = compGst.replace(/\s/g, "").substring(0, 2);
    const buyerState = buyerGst.replace(/\s/g, "").substring(0, 2);

    let cgst = 0;
    let sgst = 0;
    let igst = 0;

    if (compState && buyerState) {
      if (compState === buyerState) {
        cgst = Math.round(subtotal * 0.09 * 100) / 100;
        sgst = Math.round(subtotal * 0.09 * 100) / 100;
        igst = 0;
      } else {
        cgst = 0;
        sgst = 0;
        igst = Math.round(subtotal * 0.18 * 100) / 100;
      }
    } else {
      cgst = Math.round(subtotal * 0.09 * 100) / 100;
      sgst = Math.round(subtotal * 0.09 * 100) / 100;
      igst = 0;
    }

    setValue("cgst_amount", cgst);
    setValue("sgst_amount", sgst);
    setValue("igst_amount", igst);
    setValue("total_amount", Math.round((subtotal + cgst + sgst + igst) * 100) / 100);
  };

  const handleQuantityChange = (index, qty) => {
    const products = watch("products_list") || [];
    const rate = parseFloat(products[index]?.rate) || 0;
    const newAmount = Math.round(qty * rate * 100) / 100;
    setValue(`products_list.${index}.amount`, newAmount);

    const updatedProducts = [...products];
    updatedProducts[index] = { ...updatedProducts[index], quantity: qty, amount: newAmount };
    recalculateTotals(updatedProducts);
  };

  const handleRateChange = (index, rate) => {
    const products = watch("products_list") || [];
    const qty = parseFloat(products[index]?.quantity) || 0;
    const newAmount = Math.round(qty * rate * 100) / 100;
    setValue(`products_list.${index}.amount`, newAmount);

    const updatedProducts = [...products];
    updatedProducts[index] = { ...updatedProducts[index], rate, amount: newAmount };
    recalculateTotals(updatedProducts);
  };

  const handleAmountChange = (index, amt) => {
    const products = watch("products_list") || [];
    const updatedProducts = [...products];
    updatedProducts[index] = { ...updatedProducts[index], amount: amt };
    setValue(`products_list.${index}.amount`, amt);
    recalculateTotals(updatedProducts);
  };

  const handleCgstChange = (val) => {
    const subtotal = (watch("products_list") || []).reduce((acc, p) => acc + (parseFloat(p.amount) || 0), 0);
    const sgst = parseFloat(watch("sgst_amount")) || 0;
    const igst = parseFloat(watch("igst_amount")) || 0;
    setValue("total_amount", Math.round((subtotal + val + sgst + igst) * 100) / 100);
  };

  const handleSgstChange = (val) => {
    const subtotal = (watch("products_list") || []).reduce((acc, p) => acc + (parseFloat(p.amount) || 0), 0);
    const cgst = parseFloat(watch("cgst_amount")) || 0;
    const igst = parseFloat(watch("igst_amount")) || 0;
    setValue("total_amount", Math.round((subtotal + cgst + val + igst) * 100) / 100);
  };

  const handleIgstChange = (val) => {
    const subtotal = (watch("products_list") || []).reduce((acc, p) => acc + (parseFloat(p.amount) || 0), 0);
    const cgst = parseFloat(watch("cgst_amount")) || 0;
    const sgst = parseFloat(watch("sgst_amount")) || 0;
    setValue("total_amount", Math.round((subtotal + cgst + sgst + val) * 100) / 100);
  };

  const handleDeleteProduct = (index) => {
    remove(index);
    const products = watch("products_list") || [];
    const updatedProducts = products.filter((_, i) => i !== index);
    recalculateTotals(updatedProducts);
  };

  // Save changes
  const onSubmit = async (data) => {
    try {
      const response = await api.updateInvoice(id, data, invoice.invoice_image_path);
      if (response.success) {
        toast.success("Invoice updated successfully!");
        setInvoice(response.data); // Update local details with new history & audit
      }
    } catch (err) {
      toast.error(err.response?.data?.message || "Failed to save updates.");
    }
  };

  // Delete invoice
  const handleDelete = async () => {
    if (window.confirm("Are you sure you want to delete this invoice?")) {
      try {
        const response = await api.deleteInvoice(id);
        if (response.success) {
          toast.success("Invoice soft-deleted.");
          navigate("/history");
        }
      } catch (err) {
        toast.error("Delete failed.");
      }
    }
  };

  // Download raw image
  const handleDownloadImage = () => {
    if (!invoice?.invoice_image_path) {
      toast.error("No image available.");
      return;
    }
    const cleanNum = formValues.invoice_number || "invoice";
    const ext = invoice.invoice_image_path.split(".").pop().toLowerCase();
    const cleanExt = ["png", "jpg", "jpeg"].includes(ext) ? ext : "png";
    const filename = `${cleanNum}_original.${cleanExt}`;
    const url = invoice.invoice_image_path.startsWith("/") 
      ? `http://localhost:5000${invoice.invoice_image_path}` 
      : invoice.invoice_image_path;

    const link = document.createElement("a");
    link.href = url;
    link.download = filename;
    link.target = "_blank";
    link.click();
    toast.success("Download link opened.");
  };

  const handleDownloadCSV = () => {
    const filename = `${formValues.invoice_number || "invoice"}.csv`;
    exportToCSV(formValues, filename);
  };

  const handleDownloadJSON = () => {
    const filename = `${formValues.invoice_number || "invoice"}.json`;
    exportToJSON(formValues, filename);
  };

  const formatCurrency = (val) => {
    return new Intl.NumberFormat("en-IN", {
      style: "currency",
      currency: "INR"
    }).format(val || 0);
  };

  if (loading) {
    return (
      <div className="py-20 text-center text-slate-400 text-sm flex flex-col items-center justify-center gap-3">
        <div className="w-8 h-8 border-4 border-brand-500 border-t-transparent rounded-full animate-spin"></div>
        <p className="animate-pulse">Loading invoice details from MongoDB Atlas...</p>
      </div>
    );
  }

  if (!invoice) {
    return (
      <div className="py-20 text-center text-slate-400 text-sm flex flex-col items-center justify-center gap-3">
        <p>Invoice details not found.</p>
        <button
          type="button"
          onClick={() => navigate("/history")}
          className="bg-brand-500 hover:bg-brand-600 text-white px-4 py-2 rounded-xl text-xs font-bold transition-all"
        >
          Back to History
        </button>
      </div>
    );
  }

  return (
    <div className="space-y-8 animate-fade-in pb-16">
      {/* Top Navigation bar */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <button
          onClick={() => navigate("/history")}
          className="flex items-center gap-2 text-slate-500 hover:text-slate-950 dark:text-slate-400 dark:hover:text-white text-xs font-semibold"
        >
          <ArrowLeft size={16} />
          <span>Back to History</span>
        </button>

        {/* Global actions */}
        <div className="flex items-center gap-2">
          <button
            onClick={handleDownloadImage}
            className="flex items-center gap-1 bg-white hover:bg-slate-100 dark:bg-slate-900 dark:hover:bg-slate-800 text-slate-700 dark:text-slate-200 border border-slate-200 dark:border-slate-800 text-[11px] font-bold px-3.5 py-2 rounded-xl transition-all"
          >
            <ImageIcon size={14} />
            <span>Download Image</span>
          </button>
          
          <button
            onClick={handleDownloadCSV}
            className="flex items-center gap-1 bg-white hover:bg-slate-100 dark:bg-slate-900 dark:hover:bg-slate-800 text-slate-700 dark:text-slate-200 border border-slate-200 dark:border-slate-800 text-[11px] font-bold px-3.5 py-2 rounded-xl transition-all"
          >
            <Download size={14} />
            <span>Download CSV</span>
          </button>

          <button
            onClick={handleDownloadJSON}
            className="flex items-center gap-1 bg-white hover:bg-slate-100 dark:bg-slate-900 dark:hover:bg-slate-800 text-slate-700 dark:text-slate-200 border border-slate-200 dark:border-slate-800 text-[11px] font-bold px-3.5 py-2 rounded-xl transition-all"
          >
            <Download size={14} />
            <span>Download JSON</span>
          </button>

          <button
            onClick={handleDelete}
            className="flex items-center gap-1 bg-rose-500/10 hover:bg-rose-500/20 text-rose-500 border border-rose-500/20 text-[11px] font-bold px-3.5 py-2 rounded-xl transition-all"
          >
            <Trash2 size={14} />
            <span>Delete</span>
          </button>
        </div>
      </div>

      {/* Double Pane Layout */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-8 items-start">
        {/* Left Pane: Image (5 Columns) */}
        <div className="lg:col-span-5 space-y-6">
          <div className="glass-card p-6 rounded-2xl sticky top-24">
            <div className="flex items-center justify-between mb-4">
              <h3 className="text-md font-bold text-slate-800 dark:text-white flex items-center gap-2">
                <ImageIcon size={18} className="text-slate-400" />
                <span>Original Invoice Document</span>
              </h3>
            </div>
            
            <div className="rounded-xl border border-slate-200 dark:border-slate-800 overflow-hidden bg-slate-100 dark:bg-slate-900/60 max-h-[500px] flex items-center justify-center">
              {invoice?.invoice_image_path ? (
                <img
                  src={invoice.invoice_image_path.startsWith("/") 
                    ? `http://localhost:5000${invoice.invoice_image_path}` 
                    : invoice.invoice_image_path}
                  alt="Invoice Document"
                  className="max-h-[500px] max-w-full object-contain"
                />
              ) : (
                <div className="p-20 text-center text-slate-400">No Image Path Stored</div>
              )}
            </div>
          </div>
        </div>

        {/* Right Pane: Forms & Audit (7 Columns) */}
        <div className="lg:col-span-7 space-y-6">
          <form onSubmit={handleSubmit(onSubmit)} className="space-y-6">
            {/* Header Status Badge */}
            <div className="glass-card p-4 rounded-xl flex items-center justify-between">
              <span className="text-xs font-semibold text-slate-400">Review Workflow:</span>
              <span className={`px-3 py-1 rounded-full text-xs font-bold border ${
                invoice?.review_status === "Pending Review"
                  ? "bg-amber-100 text-amber-800 dark:bg-amber-950/30 border-amber-200"
                  : invoice?.review_status === "Reviewed"
                  ? "bg-emerald-100 text-emerald-800 dark:bg-emerald-950/30 border-emerald-200"
                  : "bg-brand-100 text-brand-800 dark:bg-brand-950/30 border-brand-200"
              }`}>
                {invoice?.review_status}
              </span>
            </div>

            {/* General Fields Card */}
            <div className="glass-card p-6 rounded-2xl space-y-6">
              <h3 className="text-md font-bold text-slate-800 dark:text-white border-b border-slate-200 dark:border-slate-800 pb-4">
                Metadata Details
              </h3>
              
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                <div className="flex flex-col gap-1.5">
                  <label className="text-xs font-semibold text-slate-500">Company Name *</label>
                  <input
                    type="text"
                    {...register("company_name", { required: "Company Name is required" })}
                    className="glass-input text-xs"
                  />
                  {errors.company_name && <span className="text-[10px] text-rose-500">{errors.company_name.message}</span>}
                </div>

                <div className="flex flex-col gap-1.5">
                  <label className="text-xs font-semibold text-slate-500">Company GSTIN</label>
                  <input
                    type="text"
                    {...register("company_gst_no", {
                      pattern: {
                        value: /^[0-9]{2}[A-Z0-9]{13}$/,
                        message: "Invalid GST format"
                      }
                    })}
                    className="glass-input text-xs font-mono"
                  />
                  {errors.company_gst_no && <span className="text-[10px] text-rose-500">{errors.company_gst_no.message}</span>}
                </div>

                <div className="flex flex-col gap-1.5">
                  <label className="text-xs font-semibold text-slate-500">Invoice Number *</label>
                  <input
                    type="text"
                    {...register("invoice_number", { required: "Invoice Number is required" })}
                    className="glass-input text-xs font-mono"
                  />
                  {errors.invoice_number && <span className="text-[10px] text-rose-500">{errors.invoice_number.message}</span>}
                </div>

                <div className="flex flex-col gap-1.5">
                  <label className="text-xs font-semibold text-slate-500">Invoice Date *</label>
                  <input
                    type="text"
                    {...register("invoice_date", {
                      required: "Invoice Date is required",
                      pattern: {
                        value: /^\d{1,4}[./-]\d{1,2}[./-]\d{2,4}$/,
                        message: "Requires date format DD/MM/YYYY"
                      }
                    })}
                    className="glass-input text-xs"
                  />
                  {errors.invoice_date && <span className="text-[10px] text-rose-500">{errors.invoice_date.message}</span>}
                </div>

                <div className="flex flex-col gap-1.5">
                  <label className="text-xs font-semibold text-slate-500">Buyer Name *</label>
                  <input
                    type="text"
                    {...register("buyer_name", { required: "Buyer Name is required" })}
                    className="glass-input text-xs"
                  />
                  {errors.buyer_name && <span className="text-[10px] text-rose-500">{errors.buyer_name.message}</span>}
                </div>

                <div className="flex flex-col gap-1.5">
                  <label className="text-xs font-semibold text-slate-500">Buyer GSTIN</label>
                  <input
                    type="text"
                    {...register("buyer_gst_no", {
                      pattern: {
                        value: /^[0-9]{2}[A-Z0-9]{13}$/,
                        message: "Invalid GST format"
                      }
                    })}
                    className="glass-input text-xs font-mono"
                  />
                  {errors.buyer_gst_no && <span className="text-[10px] text-rose-500">{errors.buyer_gst_no.message}</span>}
                </div>

                <div className="flex flex-col gap-1.5">
                  <label className="text-xs font-semibold text-slate-500">State Code</label>
                  <input type="text" {...register("state_code")} className="glass-input text-xs font-mono" />
                </div>

                <div className="flex flex-col gap-1.5">
                  <label className="text-xs font-semibold text-slate-500">Vehicle Number</label>
                  <input type="text" {...register("vehicle_number")} className="glass-input text-xs font-mono" />
                </div>

                <div className="flex flex-col gap-1.5">
                  <label className="text-xs font-semibold text-slate-500">Transportation Mode</label>
                  <input type="text" {...register("transportation_mode")} className="glass-input text-xs" />
                </div>

                <div className="flex flex-col gap-1.5 sm:col-span-2">
                  <label className="text-xs font-semibold text-slate-500">Total Amount in Words</label>
                  <input type="text" {...register("total_amount_in_words")} className="glass-input text-xs" />
                </div>
              </div>
            </div>

            {/* Products Table Card */}
            <div className="glass-card p-6 rounded-2xl space-y-4">
              <div className="flex items-center justify-between border-b border-slate-200 dark:border-slate-800 pb-3">
                <h3 className="text-sm font-bold text-slate-800 dark:text-white">Product Entries</h3>
                <button
                  type="button"
                  onClick={() => append({ product_name: "", hsn_code: "", quantity: 0, rate: 0, amount: 0 })}
                  className="flex items-center gap-1 text-xs text-brand-500 font-bold bg-brand-500/5 hover:bg-brand-500/10 px-3 py-1.5 rounded-lg border border-brand-500/20 transition-colors"
                >
                  <Plus size={14} />
                  <span>Add Product</span>
                </button>
              </div>

              <div className="overflow-x-auto">
                <table className="w-full text-left border-collapse text-xs table-fixed min-w-[700px]">
                  <thead>
                    <tr className="text-slate-400 border-b border-slate-200 dark:border-slate-800">
                      <th className="pb-2 font-semibold w-[35%] text-left px-1.5">Product Name</th>
                      <th className="pb-2 font-semibold w-[12%] text-left px-1.5">HSN</th>
                      <th className="pb-2 font-semibold w-[12%] text-center px-1.5">Qty</th>
                      <th className="pb-2 font-semibold w-[15%] text-right px-1.5">Rate</th>
                      <th className="pb-2 font-semibold w-[18%] text-right px-1.5">Amount</th>
                      <th className="pb-2 font-semibold w-[8%] text-center px-1.5">Delete</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-100 dark:divide-slate-800/40">
                    {fields.map((field, index) => {
                      const { ref: nameRef, ...nameRest } = register(`products_list.${index}.product_name`, { required: true });
                      return (
                        <tr key={field.id} className="hover:bg-slate-50/50 dark:hover:bg-slate-950/20">
                          <td className="w-[35%] px-0 py-1.5">
                            <textarea
                              rows={1}
                              required
                              {...nameRest}
                              ref={(el) => {
                                nameRef(el);
                                if (el) {
                                  el.style.height = 'auto';
                                  el.style.height = `${el.scrollHeight}px`;
                                }
                              }}
                              className="w-full bg-transparent border-0 focus:ring-1 focus:ring-brand-500 focus:bg-white dark:focus:bg-slate-900 rounded px-1.5 py-1 text-slate-700 dark:text-slate-200 resize-none overflow-hidden whitespace-normal break-words align-middle"
                              onInput={(e) => {
                                e.target.style.height = 'auto';
                                e.target.style.height = `${e.target.scrollHeight}px`;
                              }}
                            />
                          </td>
                          <td className="w-[12%] px-0 py-1.5">
                            <input
                              type="text"
                              {...register(`products_list.${index}.hsn_code`)}
                              className="w-full bg-transparent border-0 focus:ring-1 focus:ring-brand-500 focus:bg-white dark:focus:bg-slate-900 rounded px-1.5 py-1 text-slate-700 dark:text-slate-200 font-mono text-left"
                            />
                          </td>
                          <td className="w-[12%] px-0 py-1.5">
                            <input
                              type="number"
                              step="any"
                              {...register(`products_list.${index}.quantity`, {
                                required: true,
                                valueAsNumber: true,
                                onChange: (e) => handleQuantityChange(index, parseFloat(e.target.value) || 0)
                              })}
                              className="w-full bg-transparent border-0 text-center focus:ring-1 focus:ring-brand-500 focus:bg-white dark:focus:bg-slate-900 rounded px-1.5 py-1 text-slate-700 dark:text-slate-200 font-semibold"
                            />
                          </td>
                          <td className="w-[15%] px-0 py-1.5">
                            <input
                              type="number"
                              step="any"
                              {...register(`products_list.${index}.rate`, {
                                required: true,
                                valueAsNumber: true,
                                onChange: (e) => handleRateChange(index, parseFloat(e.target.value) || 0)
                              })}
                              className="w-full bg-transparent border-0 text-right focus:ring-1 focus:ring-brand-500 focus:bg-white dark:focus:bg-slate-900 rounded px-1.5 py-1 text-slate-700 dark:text-slate-200 font-semibold"
                            />
                          </td>
                          <td className="w-[18%] px-0 py-1.5">
                            <input
                              type="number"
                              step="any"
                              {...register(`products_list.${index}.amount`, {
                                required: true,
                                valueAsNumber: true,
                                onChange: (e) => handleAmountChange(index, parseFloat(e.target.value) || 0)
                              })}
                              className="w-full bg-transparent border-0 text-right focus:ring-1 focus:ring-brand-500 focus:bg-white dark:focus:bg-slate-900 rounded px-1.5 py-1 text-slate-700 dark:text-slate-200 font-semibold"
                            />
                          </td>
                          <td className="w-[8%] px-0 py-1.5 text-center">
                            <button
                              type="button"
                              onClick={() => handleDeleteProduct(index)}
                              className="text-slate-400 hover:text-rose-500 p-1 rounded-lg transition-colors inline-flex items-center justify-center"
                            >
                              <Trash2 size={14} />
                            </button>
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>

              {fields.length === 0 && (
                <p className="text-center py-4 text-xs text-slate-400">No products. Click "Add Product".</p>
              )}
            </div>

            {/* Taxes and Summary Card */}
            <div className="glass-card p-6 rounded-2xl space-y-4">
              <h3 className="text-xs font-bold text-slate-800 dark:text-white border-b border-slate-200 dark:border-slate-800 pb-3">Taxes & Summary</h3>
              
              <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                <div className="flex flex-col gap-1.5">
                  <label className="text-xs font-semibold text-slate-500">CGST Amount (Rs)</label>
                  <input
                    type="number"
                    step="any"
                    {...register("cgst_amount", {
                      valueAsNumber: true,
                      onChange: (e) => handleCgstChange(parseFloat(e.target.value) || 0)
                    })}
                    className="glass-input text-xs font-semibold text-right"
                  />
                </div>

                <div className="flex flex-col gap-1.5">
                  <label className="text-xs font-semibold text-slate-500">SGST Amount (Rs)</label>
                  <input
                    type="number"
                    step="any"
                    {...register("sgst_amount", {
                      valueAsNumber: true,
                      onChange: (e) => handleSgstChange(parseFloat(e.target.value) || 0)
                    })}
                    className="glass-input text-xs font-semibold text-right"
                  />
                </div>

                <div className="flex flex-col gap-1.5">
                  <label className="text-xs font-semibold text-slate-500">IGST Amount (Rs)</label>
                  <input
                    type="number"
                    step="any"
                    {...register("igst_amount", {
                      valueAsNumber: true,
                      onChange: (e) => handleIgstChange(parseFloat(e.target.value) || 0)
                    })}
                    className="glass-input text-xs font-semibold text-right"
                  />
                </div>

                <div className="flex flex-col gap-1.5 bg-slate-100/40 dark:bg-slate-900/60 p-2.5 rounded-xl border border-slate-200/50 dark:border-slate-800">
                  <label className="text-[10px] font-bold text-brand-500 uppercase tracking-wider">Final Total (Rs)</label>
                  <input
                    type="number"
                    step="any"
                    {...register("total_amount", { required: true, valueAsNumber: true })}
                    className="bg-transparent border-0 text-slate-900 dark:text-slate-100 font-extrabold text-sm text-right p-0 outline-none select-all"
                  />
                </div>
              </div>
            </div>

            {/* Bottom action panel */}
            <div className="flex items-center justify-end">
              <button
                type="submit"
                className="flex items-center gap-1.5 bg-brand-500 hover:bg-brand-600 text-white font-semibold text-xs px-5 py-3 rounded-xl shadow-lg shadow-brand-500/10 hover:shadow-brand-500/25 transition-all duration-200"
              >
                <Save size={14} />
                <span>Save Invoice Changes</span>
              </button>
            </div>
          </form>

          {/* Change History Audit Log Card */}
          <div className="glass-card p-6 rounded-2xl space-y-4">
            <h3 className="text-md font-bold text-slate-800 dark:text-white border-b border-slate-200 dark:border-slate-800 pb-4 flex items-center gap-2">
              <History size={16} className="text-slate-400" />
              <span>Correction Tracking History (Audit Trail)</span>
            </h3>

            {invoice?.change_history && invoice.change_history.length > 0 ? (
              <div className="relative border-l border-slate-200 dark:border-slate-800 ml-3.5 pl-5 space-y-5 py-2">
                {invoice.change_history.map((log, idx) => (
                  <div key={idx} className="relative">
                    <span className="absolute -left-[27px] top-1 p-1 bg-brand-500 text-white rounded-full">
                      <CheckCircle size={10} />
                    </span>
                    <div>
                      <p className="text-xs font-semibold text-slate-700 dark:text-slate-300">
                        Modified Field: <span className="font-bold text-brand-500 font-mono">{log.field_name}</span>
                      </p>
                      <div className="grid grid-cols-2 gap-3 mt-1.5 p-2 bg-slate-100/40 dark:bg-slate-950/40 border border-slate-200/50 dark:border-slate-800/40 rounded-lg text-[10px]">
                        <div>
                          <p className="text-slate-400">Original OCR / Value:</p>
                          <p className="text-slate-500 font-semibold truncate mt-0.5" title={log.original_value}>
                            {log.original_value || "Null"}
                          </p>
                        </div>
                        <div>
                          <p className="text-slate-400">Corrected Value:</p>
                          <p className="text-slate-700 dark:text-slate-300 font-bold truncate mt-0.5" title={log.edited_value}>
                            {log.edited_value || "Null"}
                          </p>
                        </div>
                      </div>
                      <span className="text-[9px] text-slate-400 block mt-1">
                        Edited on: {new Date(log.modified_at).toLocaleString()}
                      </span>
                    </div>
                  </div>
                ))}
              </div>
            ) : (
              <p className="text-xs text-slate-400 py-2">No edits recorded. Original OCR details match current saved copy.</p>
            )}
          </div>
        </div>
      </div>
    </div>
  );
};

export default InvoiceDetail;
