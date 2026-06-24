import React, { useState, useEffect } from "react";
import { useForm, useFieldArray } from "react-hook-form";
import {
  Upload,
  Sparkles,
  Save,
  RefreshCw,
  Plus,
  Trash2,
  Download,
  AlertTriangle,
  FileCheck,
  Image as ImageIcon
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

export const ExtractInvoice = () => {
  const [file, setFile] = useState(null);
  const [dragActive, setDragActive] = useState(false);
  const [extracting, setExtracting] = useState(false);
  const [imageUrl, setImageUrl] = useState("");
  const [originalOcrData, setOriginalOcrData] = useState(null);
  const [showDuplicateModal, setShowDuplicateModal] = useState(false);
  const [pendingSavePayload, setPendingSavePayload] = useState(null);

  // Initialize React Hook Form
  const {
    register,
    control,
    handleSubmit,
    setValue,
    watch,
    reset,
    formState: { errors }
  } = useForm({
    defaultValues: {
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
    }
  });

  const { fields, append, remove } = useFieldArray({
    control,
    name: "products_list"
  });

  // Watch fields for draft saving
  const formValues = watch();

  // Load draft from localStorage on mount
  useEffect(() => {
    const savedDraft = localStorage.getItem("invoice_draft");
    if (savedDraft) {
      try {
        const { original, edited, imagePath } = JSON.parse(savedDraft);
        if (original && edited && imagePath) {
          const sanitizedOriginal = sanitizeInvoiceData(original);
          const sanitizedEdited = sanitizeInvoiceData(edited);
          setOriginalOcrData(sanitizedOriginal);
          setImageUrl(imagePath);
          reset(sanitizedEdited);
          toast.info("Draft restored successfully");
        }
      } catch (e) {
        console.error("Failed to restore draft", e);
      }
    }
  }, [reset]);

  // Auto-Save Draft to LocalStorage on changes
  useEffect(() => {
    if (originalOcrData && imageUrl) {
      const draft = {
        original: originalOcrData,
        edited: formValues,
        imagePath: imageUrl
      };
      localStorage.setItem("invoice_draft", JSON.stringify(draft));
    }
  }, [formValues, originalOcrData, imageUrl]);

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

  // Handle drag events for upload
  const handleDrag = (e) => {
    e.preventDefault();
    e.stopPropagation();
    if (e.type === "dragenter" || e.type === "dragover") {
      setDragActive(true);
    } else if (e.type === "dragleave") {
      setDragActive(false);
    }
  };

  const handleDrop = (e) => {
    e.preventDefault();
    e.stopPropagation();
    setDragActive(false);
    if (e.dataTransfer.files && e.dataTransfer.files[0]) {
      validateAndSetFile(e.dataTransfer.files[0]);
    }
  };

  const handleFileChange = (e) => {
    if (e.target.files && e.target.files[0]) {
      validateAndSetFile(e.target.files[0]);
    }
  };

  const validateAndSetFile = (selectedFile) => {
    const allowedTypes = ["image/png", "image/jpeg", "image/jpg"];
    const maxSize = 10 * 1024 * 1024; // 10MB

    if (!allowedTypes.includes(selectedFile.type)) {
      toast.error("Unsupported file type. Please upload PNG, JPG, or JPEG.");
      return;
    }
    if (selectedFile.size > maxSize) {
      toast.error("File is too large. Maximum size allowed is 10MB.");
      return;
    }
    setFile(selectedFile);
  };

  // Trigger Backend OCR
  const handleExtract = async () => {
    if (!file) {
      toast.warn("Please select an invoice image first.");
      return;
    }

    try {
      setExtracting(true);
      toast.info("Extracting structured data from invoice... Please wait.");
      
      // Fully reset form state and page variables first to prevent state leakage
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
      setOriginalOcrData(null);
      setImageUrl("");
      localStorage.removeItem("invoice_draft");

      const response = await api.extractInvoice(file);
      console.log("Extract Response:", response.data);

      if (response.data.success) {
        const ocr = response.data.data.ocr_result;
        const imgPath = response.data.data.invoice_image_path;

        const sanitizedOcr = sanitizeInvoiceData(ocr);

        setOriginalOcrData(sanitizedOcr);
        setImageUrl(imgPath);
        
        // Reset form values with extracted fields
        reset(sanitizedOcr);
        
        toast.success("Invoice extraction completed!");
      } else {
        toast.error(response.data.message || "OCR extraction failed.");
      }
    } catch (err) {
      console.error(err);
      toast.error(err.response?.data?.message || "Server error occurred during OCR extraction.");
    } finally {
      setExtracting(false);
    }
  };

  // Submit and Save Invoice
  const onSubmit = async (data) => {
    saveInvoiceToDb(data, false);
  };

  const saveInvoiceToDb = async (data, force) => {
    const payload = {
      original_extracted_data: originalOcrData,
      edited_invoice_data: data,
      invoice_image_path: imageUrl,
      force_save: force
    };
    console.log("Save Payload:", payload);
    try {
      const response = await api.saveInvoice(originalOcrData, data, imageUrl, force);
      if (response.success) {
        toast.success("Invoice saved to database successfully!");
        // Clear draft after success saving
        localStorage.removeItem("invoice_draft");
        handleReset();
      }
    } catch (err) {
      if (err.response?.status === 409) {
        // Duplicate warning trigger
        setPendingSavePayload(data);
        setShowDuplicateModal(true);
      } else {
        toast.error(err.response?.data?.message || "Failed to save invoice.");
      }
    }
  };

  const handleContinueSave = () => {
    setShowDuplicateModal(false);
    if (pendingSavePayload) {
      saveInvoiceToDb(pendingSavePayload, true);
    }
  };

  const handleReset = () => {
    setFile(null);
    setImageUrl("");
    setOriginalOcrData(null);
    localStorage.removeItem("invoice_draft");
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
  };

  const handleDownloadCSV = () => {
    const filename = `${watch("invoice_number") || "extracted_invoice"}.csv`;
    exportToCSV(formValues, filename);
    toast.success("CSV download started.");
  };

  const handleDownloadJSON = () => {
    const filename = `${watch("invoice_number") || "extracted_invoice"}.json`;
    exportToJSON(formValues, filename);
    toast.success("JSON download started.");
  };

  return (
    <div className="space-y-8 animate-fade-in pb-16">
      {/* Page Header */}
      <div>
        <h2 className="text-3xl font-extrabold text-slate-800 dark:text-white tracking-tight">
          AI Invoice Extraction
        </h2>
        <p className="text-slate-500 dark:text-slate-400 text-sm mt-1">
          Upload any business invoice image, run automated data extraction, and review or audit corrections.
        </p>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-12 gap-8 items-start">
        {/* Left Side: Upload Zone & Preview (5 Columns) */}
        <div className="lg:col-span-5 space-y-6">
          {/* Upload Card */}
          <div className="glass-card p-6 rounded-2xl">
            <h3 className="text-md font-bold text-slate-800 dark:text-white mb-4">
              Step 1: Upload Invoice
            </h3>
            
            <div
              onDragEnter={handleDrag}
              onDragOver={handleDrag}
              onDragLeave={handleDrag}
              onDrop={handleDrop}
              className={`border-2 border-dashed rounded-xl p-8 text-center flex flex-col items-center justify-center transition-all ${
                dragActive
                  ? "border-brand-500 bg-brand-500/5"
                  : "border-slate-300 dark:border-slate-700 hover:border-brand-400"
              }`}
            >
              <Upload className="text-slate-400 dark:text-slate-600 mb-3" size={36} />
              <p className="text-xs font-semibold text-slate-600 dark:text-slate-300 mb-1">
                Drag and drop your invoice here
              </p>
              <p className="text-[10px] text-slate-400 mb-4">PNG, JPG, or JPEG up to 10MB</p>
              
              <label className="cursor-pointer bg-slate-100 hover:bg-slate-200 dark:bg-slate-800 dark:hover:bg-slate-700 text-slate-700 dark:text-slate-200 text-xs font-bold px-4 py-2.5 rounded-lg border border-slate-200 dark:border-slate-700 transition-colors">
                Browse Files
                <input
                  type="file"
                  onChange={handleFileChange}
                  accept=".png, .jpg, .jpeg"
                  className="hidden"
                />
              </label>
            </div>

            {file && (
              <div className="mt-4 flex items-center justify-between p-3 bg-slate-100 dark:bg-slate-800/40 rounded-xl">
                <div className="flex items-center gap-2 truncate">
                  <ImageIcon className="text-brand-500 shrink-0" size={16} />
                  <span className="text-xs font-semibold text-slate-700 dark:text-slate-200 truncate">{file.name}</span>
                </div>
                <span className="text-[10px] text-slate-400">{(file.size / (1024 * 1024)).toFixed(2)} MB</span>
              </div>
            )}

            <button
              onClick={handleExtract}
              disabled={extracting || !file}
              className="w-full flex items-center justify-center gap-2 bg-brand-500 hover:bg-brand-600 disabled:bg-slate-300 dark:disabled:bg-slate-800 disabled:text-slate-500 disabled:cursor-not-allowed text-white font-semibold text-sm py-3 px-4 rounded-xl mt-4 shadow-lg shadow-brand-500/10 transition-all"
            >
              {extracting ? (
                <>
                  <RefreshCw className="animate-spin" size={16} />
                  <span>Processing OCR Pipeline...</span>
                </>
              ) : (
                <>
                  <Sparkles size={16} />
                  <span>Extract Invoice Data</span>
                </>
              )}
            </button>
          </div>

          {/* Image Preview Card */}
          {imageUrl && (
            <div className="glass-card p-6 rounded-2xl">
              <h3 className="text-md font-bold text-slate-800 dark:text-white mb-4">
                Invoice Preview
              </h3>
              <div className="rounded-xl border border-slate-200 dark:border-slate-800 overflow-hidden bg-slate-100 dark:bg-slate-900/60 max-h-96 flex items-center justify-center">
                <img
                  src={imageUrl.startsWith("/") ? `http://localhost:5000${imageUrl}` : imageUrl}
                  alt="Invoice Preview"
                  className="max-h-96 max-w-full object-contain"
                />
              </div>
            </div>
          )}
        </div>

        {/* Right Side: Editable Form Panel (7 Columns) */}
        <div className="lg:col-span-7">
          {originalOcrData ? (
            <form onSubmit={handleSubmit(onSubmit)} className="space-y-6">
              {/* Form Metadata Section */}
              <div className="glass-card p-6 rounded-2xl space-y-6">
                <h3 className="text-md font-bold text-slate-800 dark:text-white border-b border-slate-200 dark:border-slate-800 pb-4">
                  Step 2: Review and Correct Extracted Fields
                </h3>

                <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                  {/* Company Name */}
                  <div className="flex flex-col gap-1.5">
                    <label className="text-xs font-semibold text-slate-500">Company Name *</label>
                    <input
                      type="text"
                      {...register("company_name", { required: "Company Name is required" })}
                      className="glass-input text-xs"
                    />
                    {errors.company_name && <span className="text-[10px] text-rose-500">{errors.company_name.message}</span>}
                  </div>

                  {/* Company GST */}
                  <div className="flex flex-col gap-1.5">
                    <label className="text-xs font-semibold text-slate-500">Company GSTIN</label>
                    <input
                      type="text"
                      {...register("company_gst_no", {
                        pattern: {
                          value: /^[0-9]{2}[A-Z0-9]{13}$/,
                          message: "Invalid GST format (15 characters alphanumeric required)"
                        }
                      })}
                      className="glass-input text-xs font-mono"
                    />
                    {errors.company_gst_no && <span className="text-[10px] text-rose-500">{errors.company_gst_no.message}</span>}
                  </div>

                  {/* Invoice Number */}
                  <div className="flex flex-col gap-1.5">
                    <label className="text-xs font-semibold text-slate-500">Invoice Number *</label>
                    <input
                      type="text"
                      {...register("invoice_number", { required: "Invoice Number is required" })}
                      className="glass-input text-xs font-mono"
                    />
                    {errors.invoice_number && <span className="text-[10px] text-rose-500">{errors.invoice_number.message}</span>}
                  </div>

                  {/* Invoice Date */}
                  <div className="flex flex-col gap-1.5">
                    <label className="text-xs font-semibold text-slate-500">Invoice Date (DD/MM/YYYY) *</label>
                    <input
                      type="text"
                      {...register("invoice_date", {
                        required: "Invoice Date is required",
                        pattern: {
                          value: /^\d{1,4}[./-]\d{1,2}[./-]\d{2,4}$/,
                          message: "Requires date format DD/MM/YYYY or YYYY-MM-DD"
                        }
                      })}
                      placeholder="DD/MM/YYYY"
                      className="glass-input text-xs"
                    />
                    {errors.invoice_date && <span className="text-[10px] text-rose-500">{errors.invoice_date.message}</span>}
                  </div>

                  {/* Buyer Name */}
                  <div className="flex flex-col gap-1.5">
                    <label className="text-xs font-semibold text-slate-500">Buyer Name *</label>
                    <input
                      type="text"
                      {...register("buyer_name", { required: "Buyer Name is required" })}
                      className="glass-input text-xs"
                    />
                    {errors.buyer_name && <span className="text-[10px] text-rose-500">{errors.buyer_name.message}</span>}
                  </div>

                  {/* Buyer GST */}
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

                  {/* State Code */}
                  <div className="flex flex-col gap-1.5">
                    <label className="text-xs font-semibold text-slate-500">State Code</label>
                    <input
                      type="text"
                      {...register("state_code")}
                      className="glass-input text-xs font-mono"
                    />
                  </div>

                  {/* Vehicle Number */}
                  <div className="flex flex-col gap-1.5">
                    <label className="text-xs font-semibold text-slate-500">Vehicle Number</label>
                    <input
                      type="text"
                      {...register("vehicle_number")}
                      className="glass-input text-xs font-mono"
                    />
                  </div>

                  {/* Transportation Mode */}
                  <div className="flex flex-col gap-1.5">
                    <label className="text-xs font-semibold text-slate-500">Transportation Mode</label>
                    <input
                      type="text"
                      {...register("transportation_mode")}
                      className="glass-input text-xs"
                    />
                  </div>

                  {/* Amount in words */}
                  <div className="flex flex-col gap-1.5 sm:col-span-2">
                    <label className="text-xs font-semibold text-slate-500">Total Amount in Words</label>
                    <input
                      type="text"
                      {...register("total_amount_in_words")}
                      className="glass-input text-xs"
                    />
                  </div>
                </div>
              </div>

              {/* Products Table Section */}
              <div className="glass-card p-6 rounded-2xl space-y-4">
                <div className="flex items-center justify-between border-b border-slate-200 dark:border-slate-800 pb-3">
                  <h3 className="text-sm font-bold text-slate-800 dark:text-white">Products List</h3>
                  <button
                    type="button"
                    onClick={() => append({ product_name: "", hsn_code: "", quantity: 0, rate: 0, amount: 0 })}
                    className="flex items-center gap-1.5 text-xs text-brand-500 font-bold bg-brand-500/5 hover:bg-brand-500/10 px-3 py-1.5 rounded-lg border border-brand-500/20 transition-colors"
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
                  <p className="text-center py-4 text-xs text-slate-400">No products added. Click "Add Product" above.</p>
                )}
              </div>

              {/* Tax Calculations Section */}
              <div className="glass-card p-6 rounded-2xl space-y-4">
                <h3 className="text-xs font-bold text-slate-800 dark:text-white border-b border-slate-200 dark:border-slate-800 pb-3">Taxes & Totals</h3>
                
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

              {/* Action Buttons Panel */}
              <div className="flex flex-wrap gap-3 items-center justify-between">
                <div className="flex flex-wrap gap-2.5">
                  <button
                    type="submit"
                    className="flex items-center gap-1.5 bg-brand-500 hover:bg-brand-600 text-white font-semibold text-xs px-4 py-2.5 rounded-xl shadow-lg shadow-brand-500/10 transition-all duration-200"
                  >
                    <Save size={14} />
                    <span>Save to DB</span>
                  </button>

                  <button
                    type="button"
                    onClick={handleDownloadCSV}
                    className="flex items-center gap-1.5 bg-white hover:bg-slate-100 dark:bg-slate-900 dark:hover:bg-slate-800 text-slate-700 dark:text-slate-200 border border-slate-200 dark:border-slate-800 font-semibold text-xs px-4 py-2.5 rounded-xl transition-all"
                  >
                    <Download size={14} />
                    <span>Export CSV</span>
                  </button>

                  <button
                    type="button"
                    onClick={handleDownloadJSON}
                    className="flex items-center gap-1.5 bg-white hover:bg-slate-100 dark:bg-slate-900 dark:hover:bg-slate-800 text-slate-700 dark:text-slate-200 border border-slate-200 dark:border-slate-800 font-semibold text-xs px-4 py-2.5 rounded-xl transition-all"
                  >
                    <Download size={14} />
                    <span>Export JSON</span>
                  </button>
                </div>

                <button
                  type="button"
                  onClick={handleReset}
                  className="flex items-center gap-1.5 text-xs text-rose-500 font-semibold bg-rose-500/5 hover:bg-rose-500/10 border border-rose-500/10 px-4 py-2.5 rounded-xl transition-all"
                >
                  <Trash2 size={14} />
                  <span>Reset Form</span>
                </button>
              </div>
            </form>
          ) : (
            <div className="glass-card p-12 text-center text-slate-400 text-sm rounded-2xl flex flex-col items-center justify-center border-dashed border-2">
              <FileCheck size={48} className="text-slate-300 dark:text-slate-700 mb-3" />
              <p className="font-bold text-slate-600 dark:text-slate-300 mb-1">OCR Form Awaiting File</p>
              <p className="text-xs text-slate-400 max-w-xs">
                Upload your invoice image and trigger the extractor on the left to render the interactive corrections editor.
              </p>
            </div>
          )}
        </div>
      </div>

      {/* Duplicate Warning Dialog Modal */}
      {showDuplicateModal && (
        <div className="fixed inset-0 bg-slate-900/60 backdrop-blur-sm z-50 flex items-center justify-center p-4">
          <div className="bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-2xl p-6 max-w-md w-full shadow-2xl animate-scale-up space-y-4">
            <div className="flex items-center gap-3 text-amber-500">
              <AlertTriangle size={24} className="shrink-0 animate-bounce" />
              <h4 className="font-extrabold text-md text-slate-800 dark:text-white">Duplicate Detection Warning</h4>
            </div>
            <p className="text-xs text-slate-500 dark:text-slate-400 leading-relaxed">
              An invoice matching the vendor GST No and invoice number you corrected already exists in the system. Continuing will create a duplicate record.
            </p>
            <div className="flex items-center justify-end gap-3 pt-2">
              <button
                type="button"
                onClick={() => setShowDuplicateModal(false)}
                className="px-4 py-2 text-xs font-bold text-slate-500 hover:text-slate-700 hover:bg-slate-100 dark:hover:bg-slate-800 rounded-lg border border-transparent transition-all"
              >
                Cancel Save
              </button>
              <button
                type="button"
                onClick={handleContinueSave}
                className="px-4 py-2 text-xs font-bold bg-brand-500 hover:bg-brand-600 text-white rounded-lg transition-all shadow-md shadow-brand-500/10"
              >
                Continue Save
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

export default ExtractInvoice;
