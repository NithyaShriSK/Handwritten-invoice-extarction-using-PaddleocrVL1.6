import Papa from "papaparse";

/**
 * Exports invoice data to CSV format.
 * Flattens the invoice details and product list.
 * @param {Object|Array} invoiceData - A single invoice object or an array of invoice objects.
 * @param {string} filename - The target file name for the download.
 */
export const exportToCSV = (invoiceData, filename = "invoice.csv") => {
  const invoices = Array.isArray(invoiceData) ? invoiceData : [invoiceData];
  const csvRows = [];

  invoices.forEach((inv) => {
    // Export edited data if it exists, otherwise fall back to root properties
    const data = inv.edited_invoice_data || inv;
    const products = data.products_list || [];

    if (products.length === 0) {
      csvRows.push({
        "Company Name": data.company_name || "",
        "Company GST": data.company_gst_no || "",
        "Invoice Number": data.invoice_number || "",
        "Invoice Date": data.invoice_date || "",
        "State Code": data.state_code || "",
        "Vehicle Number": data.vehicle_number || "",
        "Transportation Mode": data.transportation_mode || "",
        "Buyer Name": data.buyer_name || "",
        "Buyer GST": data.buyer_gst_no || "",
        "CGST": data.cgst_amount || "",
        "SGST": data.sgst_amount || "",
        "IGST": data.igst_amount || "",
        "Total Amount": data.total_amount || "",
        "Amount In Words": data.total_amount_in_words || "",
        "Product Name": "",
        "HSN Code": "",
        "Quantity": "",
        "Rate": "",
        "Amount": "",
      });
    } else {
      products.forEach((prod) => {
        csvRows.push({
          "Company Name": data.company_name || "",
          "Company GST": data.company_gst_no || "",
          "Invoice Number": data.invoice_number || "",
          "Invoice Date": data.invoice_date || "",
          "State Code": data.state_code || "",
          "Vehicle Number": data.vehicle_number || "",
          "Transportation Mode": data.transportation_mode || "",
          "Buyer Name": data.buyer_name || "",
          "Buyer GST": data.buyer_gst_no || "",
          "CGST": data.cgst_amount || "",
          "SGST": data.sgst_amount || "",
          "IGST": data.igst_amount || "",
          "Total Amount": data.total_amount || "",
          "Amount In Words": data.total_amount_in_words || "",
          "Product Name": prod.product_name || "",
          "HSN Code": prod.hsn_code || "",
          "Quantity": prod.quantity || "",
          "Rate": prod.rate || "",
          "Amount": prod.amount || "",
        });
      });
    }
  });

  const csv = Papa.unparse(csvRows);
  const blob = new Blob([csv], { type: "text/csv;charset=utf-8;" });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.setAttribute("href", url);
  
  // Enforce correct filename
  const cleanFilename = filename.endsWith(".csv") ? filename : `${filename}.csv`;
  link.setAttribute("download", cleanFilename);
  link.style.visibility = "hidden";
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
};

/**
 * Exports invoice data to JSON format.
 * @param {Object} invoiceData - The invoice object containing the edited version.
 * @param {string} filename - The target file name for the download.
 */
export const exportToJSON = (invoiceData, filename = "invoice.json") => {
  // Only export corrected/edited version
  const data = invoiceData.edited_invoice_data || invoiceData;
  const jsonString = JSON.stringify(data, null, 2);
  const blob = new Blob([jsonString], { type: "application/json;charset=utf-8;" });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.setAttribute("href", url);
  
  // Enforce correct filename
  const cleanFilename = filename.endsWith(".json") ? filename : `${filename}.json`;
  link.setAttribute("download", cleanFilename);
  link.style.visibility = "hidden";
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
};
