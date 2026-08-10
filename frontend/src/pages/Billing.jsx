import React, { useState, useEffect } from "react";
import { useForm, useFieldArray } from "react-hook-form";
import { Plus, Trash2, Save, FileText, Landmark, RefreshCw, Sparkles } from "lucide-react";
import { api } from "../services/api";
import { toast } from "react-toastify";

// Helper to convert number to words (Indian Rupees format)
const numberToWords = (num) => {
  if (num === 0) return "Zero Rupees Only";
  const a = [
    "", "One", "Two", "Three", "Four", "Five", "Six", "Seven", "Eight", "Nine", "Ten",
    "Eleven", "Twelve", "Thirteen", "Fourteen", "Fifteen", "Sixteen", "Seventeen", "Eighteen", "Nineteen"
  ];
  const b = ["", "", "Twenty", "Thirty", "Forty", "Fifty", "Sixty", "Seventy", "Eighty", "Ninety"];
  
  const g = ["", "Thousand", "Lakh", "Crore"];
  
  const convertGroup = (n) => {
    let s = "";
    if (n >= 100) {
      s += a[Math.floor(n / 100)] + " Hundred ";
      n %= 100;
    }
    if (n >= 20) {
      s += b[Math.floor(n / 10)] + " ";
      n %= 10;
    }
    if (n > 0) {
      s += a[n] + " ";
    }
    return s.trim();
  };

  let numStr = Math.floor(num).toString();
  if (numStr.length > 9) return "Amount Too Large";
  
  numStr = numStr.padStart(9, "0");
  
  const c = parseInt(numStr.substr(0, 2)); // crore
  const l = parseInt(numStr.substr(2, 2)); // lakh
  const t = parseInt(numStr.substr(4, 2)); // thousand
  const h = parseInt(numStr.substr(6, 3)); // hundred/tens
  
  let result = "";
  if (c > 0) result += convertGroup(c) + " Crore ";
  if (l > 0) result += convertGroup(l) + " Lakh ";
  if (t > 0) result += convertGroup(t) + " Thousand ";
  if (h > 0) result += convertGroup(h) + " ";
  
  result = result.trim();
  return result ? `${result} Rupees Only` : "";
};

export const Billing = () => {
  const [saving, setSaving] = useState(false);
  const [taxMode, setTaxMode] = useState("intra"); // "intra" (CGST+SGST) or "inter" (IGST)
  const [gstPercent, setGstPercent] = useState(5); // Default 5% for textile/garment trade

  const { register, control, handleSubmit, setValue, getValues, reset } = useForm({
    defaultValues: {
      company_name: "Naganna Raajaa Silk Industries",
      company_gst_no: "33DCRPK0145Q1Z5",
      invoice_number: "",
      invoice_date: new Date().toISOString().split("T")[0],
      state_code: "33",
      vehicle_number: "",
      transportation_mode: "Hand Delivery",
      buyer_name: "",
      buyer_gst_no: "",
      purchase_order_number: "",
      cgst_amount: 0,
      sgst_amount: 0,
      igst_amount: 0,
      total_amount: 0,
      total_amount_in_words: "",
      bank_account_no: "120026402797",
      bank_ifsc: "CNRB0004377",
      bank_name: "Canara Bank Ltd.",
      products_list: [{ product_name: "", hsn_code: "", quantity: "", rate: "", amount: 0 }]
    }
  });

  const { fields, append, remove } = useFieldArray({
    control,
    name: "products_list"
  });

  // Calculate totals instantly on every keystroke
  const calculateTotals = (productsToUse = null, activeTaxMode = null, activeGstPercent = null) => {
    const products = productsToUse || getValues("products_list") || [];
    const mode = activeTaxMode || taxMode;
    const percent = activeGstPercent !== null ? activeGstPercent : gstPercent;
    
    let subtotal = 0;
    products.forEach((item, idx) => {
      const q = parseFloat(item.quantity) || 0;
      const r = parseFloat(item.rate) || 0;
      const amt = Math.round(q * r * 100) / 100;
      setValue(`products_list.${idx}.amount`, amt);
      subtotal += amt;
    });

    let cgst = 0;
    let sgst = 0;
    let igst = 0;

    if (mode === "intra") {
      const halfRate = percent / 2;
      cgst = Math.round((subtotal * halfRate / 100) * 100) / 100;
      sgst = Math.round((subtotal * halfRate / 100) * 100) / 100;
    } else {
      igst = Math.round((subtotal * percent / 100) * 100) / 100;
    }

    const total = Math.round(subtotal + cgst + sgst + igst);
    
    setValue("cgst_amount", cgst);
    setValue("sgst_amount", sgst);
    setValue("igst_amount", igst);
    setValue("total_amount", total);
    setValue("total_amount_in_words", numberToWords(total));
  };

  const handleAddProduct = () => {
    append({ product_name: "", hsn_code: "", quantity: "", rate: "", amount: 0 });
    setTimeout(() => calculateTotals(), 0);
  };

  const handleRemoveProduct = (index) => {
    remove(index);
    setTimeout(() => calculateTotals(), 0);
  };

  const onSubmit = async (data) => {
    setSaving(true);
    try {
      const payloadEdited = {
        ...data,
        source_filename: "manual_billing",
        source_page_number: 1,
        total_pages: 1,
        document_type: "manual"
      };

      const response = await api.saveInvoice(payloadEdited, payloadEdited, "", true);
      if (response.success) {
        toast.success("Manual bill saved successfully to database!");
        reset({
          company_name: "Naganna Raajaa Silk Industries",
          company_gst_no: "33DCRPK0145Q1Z5",
          invoice_number: "",
          invoice_date: new Date().toISOString().split("T")[0],
          state_code: "33",
          vehicle_number: "",
          transportation_mode: "Hand Delivery",
          buyer_name: "",
          buyer_gst_no: "",
          purchase_order_number: "",
          cgst_amount: 0,
          sgst_amount: 0,
          igst_amount: 0,
          total_amount: 0,
          total_amount_in_words: "",
          bank_account_no: "120026402797",
          bank_ifsc: "CNRB0004377",
          bank_name: "Canara Bank Ltd.",
          products_list: [{ product_name: "", hsn_code: "", quantity: "", rate: "", amount: 0 }]
        });
      }
    } catch (err) {
      console.error(err);
      toast.error(err.response?.data?.message || "Failed to save bill.");
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="space-y-8 animate-fade-in pb-12">
      {/* Decorative Silk Title Area */}
      <div className="relative p-6 bg-gradient-to-r from-violet-900 via-indigo-900 to-slate-900 rounded-3xl overflow-hidden shadow-2xl border border-amber-500/20">
        <div className="absolute top-0 right-0 w-64 h-64 bg-amber-500/5 rounded-full blur-3xl" />
        <div className="absolute bottom-0 left-0 w-48 h-48 bg-violet-500/5 rounded-full blur-2xl" />
        <div className="relative z-10 space-y-2">
          <div className="flex items-center gap-2 text-amber-400 font-bold text-xs tracking-wider uppercase">
            <Sparkles size={14} className="animate-pulse" />
            <span>Royal Silk & Textile Loom Registry</span>
          </div>
          <h2 className="text-3xl font-extrabold text-white tracking-tight">
            Manual Billing Invoice
          </h2>
          <p className="text-slate-300 text-sm max-w-xl">
            Type quantities and rates below to update calculations in real-time. Automatically converts amounts to words.
          </p>
        </div>
      </div>

      <form onSubmit={handleSubmit(onSubmit)} className="space-y-6">
        {/* Vendor & Buyer details */}
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          {/* Vendor Box */}
          <div className="glass-card p-6 rounded-2xl border-l-4 border-l-amber-500 space-y-4">
            <h3 className="text-sm font-bold text-slate-800 dark:text-white border-b border-slate-200 dark:border-slate-800 pb-3 flex items-center gap-2">
              <Landmark size={14} className="text-amber-500" />
              <span>Seller/Vendor Details (Silk Mills)</span>
            </h3>
            
            <div className="grid grid-cols-2 gap-4">
              <div className="col-span-2 flex flex-col gap-1.5">
                <label className="text-xs font-semibold text-slate-500">Company Name</label>
                <input
                  type="text"
                  {...register("company_name", { required: true })}
                  className="glass-input text-xs"
                />
              </div>

              <div className="flex flex-col gap-1.5">
                <label className="text-xs font-semibold text-slate-500">GSTIN No</label>
                <input
                  type="text"
                  {...register("company_gst_no", { required: true })}
                  className="glass-input text-xs"
                />
              </div>

              <div className="flex flex-col gap-1.5">
                <label className="text-xs font-semibold text-slate-500">State Code</label>
                <input
                  type="text"
                  {...register("state_code", { required: true })}
                  className="glass-input text-xs"
                />
              </div>
            </div>
          </div>

          {/* Customer / Buyer Box */}
          <div className="glass-card p-6 rounded-2xl border-l-4 border-l-violet-500 space-y-4">
            <h3 className="text-sm font-bold text-slate-800 dark:text-white border-b border-slate-200 dark:border-slate-800 pb-3 flex items-center gap-2">
              <FileText size={14} className="text-violet-500" />
              <span>Buyer / Customer Details</span>
            </h3>
            
            <div className="grid grid-cols-2 gap-4">
              <div className="col-span-2 flex flex-col gap-1.5">
                <label className="text-xs font-semibold text-slate-500">Customer Name</label>
                <input
                  type="text"
                  placeholder="Enter buyer brand or name..."
                  {...register("buyer_name", { required: true })}
                  className="glass-input text-xs"
                />
              </div>

              <div className="flex flex-col gap-1.5">
                <label className="text-xs font-semibold text-slate-500">Buyer GSTIN</label>
                <input
                  type="text"
                  placeholder="33XXXXX..."
                  {...register("buyer_gst_no")}
                  className="glass-input text-xs"
                />
              </div>

              <div className="flex flex-col gap-1.5">
                <label className="text-xs font-semibold text-slate-500">PO Number</label>
                <input
                  type="text"
                  placeholder="Optional Purchase Order No"
                  {...register("purchase_order_number")}
                  className="glass-input text-xs"
                />
              </div>
            </div>
          </div>
        </div>

        {/* Invoice Info Bar */}
        <div className="glass-card p-6 rounded-2xl space-y-4">
          <h3 className="text-sm font-bold text-slate-800 dark:text-white border-b border-slate-200 dark:border-slate-800 pb-3">
            Invoice Info & Transport Details
          </h3>
          
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            <div className="flex flex-col gap-1.5">
              <label className="text-xs font-semibold text-slate-500">Invoice Number</label>
              <input
                type="text"
                placeholder="e.g. 1024"
                {...register("invoice_number", { required: true })}
                className="glass-input text-xs font-bold"
              />
            </div>
            
            <div className="flex flex-col gap-1.5">
              <label className="text-xs font-semibold text-slate-500">Invoice Date</label>
              <input
                type="date"
                {...register("invoice_date", { required: true })}
                className="glass-input text-xs"
              />
            </div>

            <div className="flex flex-col gap-1.5">
              <label className="text-xs font-semibold text-slate-500">Transportation Mode</label>
              <input
                type="text"
                {...register("transportation_mode")}
                className="glass-input text-xs"
              />
            </div>

            <div className="flex flex-col gap-1.5">
              <label className="text-xs font-semibold text-slate-500">Vehicle Number</label>
              <input
                type="text"
                placeholder="e.g. TN-33-AA-1234"
                {...register("vehicle_number")}
                className="glass-input text-xs"
              />
            </div>
          </div>
        </div>

        {/* Product Items Table */}
        <div className="glass-card p-6 rounded-2xl space-y-4">
          <div className="flex items-center justify-between border-b border-slate-200 dark:border-slate-800 pb-3">
            <h3 className="text-sm font-bold text-slate-800 dark:text-white">Product Rows</h3>
            <button
              type="button"
              onClick={handleAddProduct}
              className="flex items-center gap-1 bg-amber-500 hover:bg-amber-600 text-white font-bold text-[10px] px-3.5 py-2 rounded-xl transition-all shadow-md shadow-amber-500/10"
            >
              <Plus size={12} />
              <span>Add Product Row</span>
            </button>
          </div>

          <div className="overflow-x-auto">
            <table className="w-full text-xs">
              <thead>
                <tr className="text-slate-400 font-semibold border-b border-slate-200 dark:border-slate-800 text-left">
                  <th className="pb-3 w-[40%]">Product Name / Silk Type</th>
                  <th className="pb-3 w-[15%] text-center">HSN Code</th>
                  <th className="pb-3 w-[12%] text-center">Quantity (kg/m)</th>
                  <th className="pb-3 w-[12%] text-right">Rate (Rs)</th>
                  <th className="pb-3 w-[15%] text-right">Amount (Rs)</th>
                  <th className="pb-3 w-[6%] text-center">Delete</th>
                </tr>
              </thead>
              <tbody>
                {fields.map((field, index) => (
                  <tr key={field.id} className="border-b border-slate-100 dark:border-slate-800/40 align-middle">
                    <td className="py-2 pr-2">
                      <input
                        type="text"
                        placeholder="e.g. Job Work - Warp Silk"
                        {...register(`products_list.${index}.product_name`, { required: true })}
                        className="w-full bg-transparent border-0 focus:ring-1 focus:ring-brand-500 focus:bg-white dark:focus:bg-slate-900 rounded px-1.5 py-1 text-slate-700 dark:text-slate-200"
                      />
                    </td>
                    <td className="py-2 px-1 text-center">
                      <input
                        type="text"
                        placeholder="9988"
                        {...register(`products_list.${index}.hsn_code`)}
                        className="w-full bg-transparent border-0 text-center focus:ring-1 focus:ring-brand-500 focus:bg-white dark:focus:bg-slate-900 rounded px-1.5 py-1 text-slate-700 dark:text-slate-200"
                      />
                    </td>
                    <td className="py-2 px-1 text-center">
                      <input
                        type="text"
                        placeholder="0.00"
                        {...register(`products_list.${index}.quantity`, {
                          required: true,
                          onChange: () => calculateTotals()
                        })}
                        className="w-full bg-transparent border-0 text-center focus:ring-1 focus:ring-brand-500 focus:bg-white dark:focus:bg-slate-900 rounded px-1.5 py-1 text-slate-700 dark:text-slate-200 font-semibold"
                      />
                    </td>
                    <td className="py-2 px-1 text-right">
                      <input
                        type="text"
                        placeholder="0.00"
                        {...register(`products_list.${index}.rate`, {
                          required: true,
                          onChange: () => calculateTotals()
                        })}
                        className="w-full bg-transparent border-0 text-right focus:ring-1 focus:ring-brand-500 focus:bg-white dark:focus:bg-slate-900 rounded px-1.5 py-1 text-slate-700 dark:text-slate-200 font-semibold"
                      />
                    </td>
                    <td className="py-2 pl-2 text-right">
                      <input
                        type="number"
                        step="any"
                        readOnly
                        {...register(`products_list.${index}.amount`)}
                        className="w-full bg-transparent border-0 text-right text-slate-700 dark:text-slate-300 font-bold outline-none"
                      />
                    </td>
                    <td className="py-2 text-center">
                      {fields.length > 1 && (
                        <button
                          type="button"
                          onClick={() => handleRemoveProduct(index)}
                          className="text-slate-400 hover:text-rose-500 p-1 rounded-lg transition-colors"
                        >
                          <Trash2 size={14} />
                        </button>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>

        {/* Taxes & Totals */}
        <div className="glass-card p-6 rounded-2xl space-y-4">
          <div className="flex flex-wrap items-center justify-between border-b border-slate-200 dark:border-slate-800 pb-3">
            <h3 className="text-sm font-bold text-slate-800 dark:text-white">Taxes & Grand Totals</h3>
            <div className="flex items-center gap-4 text-xs">
              <div className="flex items-center gap-2">
                <span className="text-slate-500 font-medium">GST Mode:</span>
                <select
                  value={taxMode}
                  onChange={(e) => {
                    setTaxMode(e.target.value);
                    calculateTotals(null, e.target.value, null);
                  }}
                  className="glass-input py-1 px-2.5 text-xs font-bold border-indigo-100"
                >
                  <option value="intra">Intra-state (CGST + SGST)</option>
                  <option value="inter">Inter-state (IGST)</option>
                </select>
              </div>
              <div className="flex items-center gap-2">
                <span className="text-slate-500 font-medium">Tax Rate:</span>
                <select
                  value={gstPercent}
                  onChange={(e) => {
                    const val = parseFloat(e.target.value);
                    setGstPercent(val);
                    calculateTotals(null, null, val);
                  }}
                  className="glass-input py-1 px-2.5 text-xs font-bold border-indigo-100"
                >
                  <option value={5}>5% (Garment/Silk standard)</option>
                  <option value={12}>12%</option>
                  <option value={18}>18%</option>
                  <option value={0}>Exempt (0%)</option>
                </select>
              </div>
            </div>
          </div>

          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            <div className="flex flex-col gap-1.5">
              <label className="text-xs font-semibold text-slate-500">CGST Amount (Rs)</label>
              <input
                type="number"
                step="any"
                readOnly
                {...register("cgst_amount")}
                className="glass-input text-xs font-bold text-right bg-slate-50/50"
              />
            </div>

            <div className="flex flex-col gap-1.5">
              <label className="text-xs font-semibold text-slate-500">SGST Amount (Rs)</label>
              <input
                type="number"
                step="any"
                readOnly
                {...register("sgst_amount")}
                className="glass-input text-xs font-bold text-right bg-slate-50/50"
              />
            </div>

            <div className="flex flex-col gap-1.5">
              <label className="text-xs font-semibold text-slate-500">IGST Amount (Rs)</label>
              <input
                type="number"
                step="any"
                readOnly
                {...register("igst_amount")}
                className="glass-input text-xs font-bold text-right bg-slate-50/50"
              />
            </div>

            <div className="flex flex-col gap-1.5 bg-gradient-to-br from-amber-500/10 to-orange-500/10 p-2.5 rounded-xl border border-amber-500/30">
              <label className="text-[10px] font-bold text-amber-600 dark:text-amber-400 uppercase tracking-wider">Grand Total (Rs)</label>
              <input
                type="number"
                step="any"
                readOnly
                {...register("total_amount")}
                className="bg-transparent border-0 text-slate-900 dark:text-slate-100 font-extrabold text-sm text-right p-0 outline-none"
              />
            </div>

            <div className="col-span-2 md:col-span-4 flex flex-col gap-1.5">
              <label className="text-xs font-semibold text-slate-500">Amount in Words</label>
              <input
                type="text"
                readOnly
                {...register("total_amount_in_words")}
                className="glass-input text-xs font-semibold bg-slate-50/50 italic text-amber-700 dark:text-amber-400"
              />
            </div>
          </div>
        </div>

        {/* Bank Details */}
        <div className="glass-card p-6 rounded-2xl space-y-4">
          <h3 className="text-sm font-bold text-slate-800 dark:text-white border-b border-slate-200 dark:border-slate-800 pb-3 flex items-center gap-2">
            <Landmark size={14} className="text-brand-500" />
            <span>Bank Remittance Details</span>
          </h3>
          
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            <div className="flex flex-col gap-1.5">
              <label className="text-xs font-semibold text-slate-500">Bank Name</label>
              <input
                type="text"
                {...register("bank_name")}
                className="glass-input text-xs"
              />
            </div>

            <div className="flex flex-col gap-1.5">
              <label className="text-xs font-semibold text-slate-500">Account Number</label>
              <input
                type="text"
                {...register("bank_account_no")}
                className="glass-input text-xs"
              />
            </div>

            <div className="flex flex-col gap-1.5">
              <label className="text-xs font-semibold text-slate-500">IFSC Code</label>
              <input
                type="text"
                {...register("bank_ifsc")}
                className="glass-input text-xs"
              />
            </div>
          </div>
        </div>

        {/* Save button */}
        <div className="flex justify-end pt-4">
          <button
            type="submit"
            disabled={saving}
            className="flex items-center gap-2 bg-gradient-to-r from-violet-600 to-indigo-600 hover:from-violet-750 hover:to-indigo-750 text-white font-bold text-xs px-6 py-3 rounded-xl shadow-lg shadow-indigo-600/20 transition-all duration-200"
          >
            {saving ? <RefreshCw size={14} className="animate-spin" /> : <Save size={14} />}
            <span>Save & Generate Invoice</span>
          </button>
        </div>
      </form>
    </div>
  );
};

export default Billing;
