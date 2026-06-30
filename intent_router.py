import re

# Off-topic/refusal keyword lists to immediately catch unrelated topics
OFF_TOPIC_KEYWORDS = [
    "joke", "poem", "prime minister", "poetry", "write a story", "song", "weather", 
    "sports", "soccer", "cricket", "recipe", "cook", "movie", "actor", "sing",
    "machine learning", "explain quantum", "programming", "javascript", "python code"
]

def classify_intent(question, is_admin=False):
    """
    Classifies a user query into a supported business intelligence/invoice intent.
    
    :param question: The raw string query from the user.
    :param is_admin: Whether the user has admin role privileges.
    :return: (intent_name, clean_explanation_if_refused)
    """
    q_lower = question.lower().strip()
    
    # 1. Broad safety check for off-topic/creative requests
    for kw in OFF_TOPIC_KEYWORDS:
        if kw in q_lower:
            return "unsupported", "InvoiceAI Assistant only supports invoice, OCR, GST, vendor, reporting, analytics, and user activity related questions."
            
    # Check if the query is completely unrelated to billing, invoices, vendors, GST, reports, activity
    allowed_terms = [
        "invoice", "bill", "gst", "tax", "cgst", "sgst", "igst", "revenue", 
        "sale", "vendor", "supplier", "company", "customer", "buyer", "amount", 
        "report", "summary", "analysis", "analytic", "correction", "error", 
        "accuracy", "history", "active", "uploader", "audit", "trend", "month", 
        "quarter", "year", "annual", "gstin", "search", "find", "list", "show"
    ]
    
    has_allowed_term = any(term in q_lower for term in allowed_terms)
    if not has_allowed_term:
        return "unsupported", "InvoiceAI Assistant only supports invoice, OCR, GST, vendor, reporting, analytics, and user activity related questions."
        
    # 2. Check for Admin Only Intents
    # User Activity Analysis
    if "user activity" in q_lower or "active user" in q_lower or "activity trend" in q_lower or "activity log" in q_lower:
        if is_admin:
            return "user_activity_analysis", None
        else:
            return "unsupported", "Activity logs and user activity analysis are restricted to Administrator accounts."
            
    # Top Uploaders
    if "top uploader" in q_lower or "most active uploader" in q_lower:
        if is_admin:
            return "top_uploaders", None
        else:
            return "unsupported", "Top uploader metrics are restricted to Administrator accounts."
            
    # Most Corrected Invoices / Users modifying OCR
    if "most corrected" in q_lower or "modify ocr" in q_lower or "correct invoice" in q_lower or "change history" in q_lower:
        if is_admin:
            return "most_corrected_invoices", None
        else:
            # Standard users might ask about their own ocr correction analysis
            return "ocr_correction_analysis", None

    # 3. Check for Standard & Common Intents
    # Quarterly Report
    if "quarterly report" in q_lower or "quarter report" in q_lower or any(q in q_lower for q in ["q1 report", "q2 report", "q3 report", "q4 report"]):
        return "quarterly_report", None
        
    # Yearly/Annual Report
    if "yearly report" in q_lower or "yearly summary" in q_lower or "annual report" in q_lower or "annual summary" in q_lower:
        return "yearly_report", None
        
    # Monthly Report
    if "monthly report" in q_lower or "report this month" in q_lower or "report for" in q_lower or re.search(r'(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]* \d{4} report', q_lower):
        return "monthly_report", None
        
    # GST Analysis
    if "gst" in q_lower or "tax summary" in q_lower or "cgst" in q_lower or "sgst" in q_lower or "igst" in q_lower:
        return "gst_analysis", None
        
    # Vendor Analysis
    if "vendor" in q_lower or "supplier" in q_lower or "seller" in q_lower:
        return "vendor_analysis", None
        
    # OCR Correction Analysis
    if "ocr" in q_lower or "correction" in q_lower or "accuracy" in q_lower or "acceptance" in q_lower:
        return "ocr_correction_analysis", None
        
    # Revenue Analysis
    if "revenue" in q_lower or "sales" in q_lower or "earnings" in q_lower or "total amount" in q_lower or "total value" in q_lower:
        return "revenue_analysis", None
        
    # Invoice Search
    if "search" in q_lower or "find" in q_lower or "locate" in q_lower or "get invoice" in q_lower:
        return "invoice_search", None
        
    # Default fallback: If it mentions reports/summaries, map to general revenue or monthly report
    if "report" in q_lower or "summary" in q_lower:
        return "monthly_report", None
        
    # If it is allowed but fuzzy, route to general revenue analysis
    return "revenue_analysis", None
