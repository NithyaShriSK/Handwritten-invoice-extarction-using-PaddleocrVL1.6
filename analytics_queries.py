import os
import re
from datetime import datetime, timedelta

def parse_date_range(question):
    """
    Parses a query string to extract year, month, or quarter.
    Defaults to current month if no specific details are found.
    Returns (start_date, end_date, period_label, report_type)
    """
    now = datetime.utcnow()
    q_lower = question.lower()
    
    # Extract year (default to current year)
    year = now.year
    year_match = re.search(r'\b(20\d{2})\b', q_lower)
    if year_match:
        year = int(year_match.group(1))
        
    # Check for quarter
    quarter_match = re.search(r'\b(q[1-4])\b', q_lower)
    if quarter_match:
        q_num = int(quarter_match.group(1)[1])
        if q_num == 1:
            start = datetime(year, 1, 1)
            end = datetime(year, 4, 1)
        elif q_num == 2:
            start = datetime(year, 4, 1)
            end = datetime(year, 7, 1)
        elif q_num == 3:
            start = datetime(year, 7, 1)
            end = datetime(year, 10, 1)
        else:
            start = datetime(year, 10, 1)
            end = datetime(year + 1, 1, 1)
        return start, end, f"Q{q_num} {year}", "quarterly_report"
        
    # Check for month
    months = [
        ("january", "jan", 1), ("february", "feb", 2), ("march", "mar", 3),
        ("april", "apr", 4), ("may", "may", 5), ("june", "jun", 6),
        ("july", "jul", 7), ("august", "aug", 8), ("september", "sep", 9),
        ("october", "oct", 10), ("november", "nov", 11), ("december", "dec", 12)
    ]
    
    for m_full, m_short, m_num in months:
        if m_full in q_lower or m_short in q_lower:
            start = datetime(year, m_num, 1)
            if m_num == 12:
                end = datetime(year + 1, 1, 1)
            else:
                end = datetime(year, m_num + 1, 1)
            return start, end, f"{m_short.capitalize()} {year}", "monthly_report"
            
    # Check if yearly report
    if "year" in q_lower or "annual" in q_lower:
        start = datetime(year, 1, 1)
        end = datetime(year + 1, 1, 1)
        return start, end, f"Year {year}", "yearly_report"
        
    # Default: Current month
    start = datetime(now.year, now.month, 1)
    if now.month == 12:
        end = datetime(now.year + 1, 1, 1)
    else:
        end = datetime(now.year, now.month + 1, 1)
        
    months_list = ["", "Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
    return start, end, f"{months_list[now.month]} {now.year}", "monthly_report"

def run_analytics_query(intent, user_id, is_admin, question=""):
    """
    Runs MongoDB aggregation queries matching user role and intent.
    Enforces dataset size limits using MAX_REPORT_RECORDS environment variable.
    """
    # Dynamic imports to avoid circular reference on startup
    from backend_app import collection as invoices_col, users_collection as users_col, logs_collection as logs_col
    
    max_records = int(os.environ.get("MAX_REPORT_RECORDS", 5000))
    start_date, end_date, period_label, report_type = parse_date_range(question)
    
    # 1. Base Match Queries
    # Standard user gets restricted to their own invoices
    base_match = {"is_deleted": {"$ne": True}}
    if not is_admin:
        base_match["user_id"] = user_id
        
    # Time-bounded match
    time_match = base_match.copy()
    time_match["created_at"] = {"$gte": start_date, "$lt": end_date}
    
    # 2. Dataset Size Protection
    try:
        match_count = invoices_col.count_documents(time_match)
    except Exception as ce:
        print(f"[ERROR] Database access failed: {ce}")
        return {"error": "Database connection unavailable."}
        
    force_summary_only = False
    if match_count > max_records:
        print(f"[WARNING] Large dataset protection triggered: count {match_count} > limit {max_records}. Aggregating summaries only.")
        force_summary_only = True
        
    result_data = {
        "period": period_label,
        "report_type": report_type,
        "total_invoices_in_period": match_count,
        "large_dataset_warning": force_summary_only
    }
    
    # Execute query based on intent
    if intent in ["monthly_report", "quarterly_report", "yearly_report", "revenue_analysis"]:
        # Aggregate Revenue
        rev_pipeline = [
            {"$match": time_match},
            {"$group": {
                "_id": None,
                "total_revenue": {"$sum": {"$toDouble": {"$ifNull": ["$edited_invoice_data.total_amount", 0]}}},
                "average_amount": {"$avg": {"$toDouble": {"$ifNull": ["$edited_invoice_data.total_amount", 0]}}}
            }}
        ]
        rev_res = list(invoices_col.aggregate(rev_pipeline))
        result_data["total_revenue"] = round(rev_res[0]["total_revenue"], 2) if rev_res else 0.0
        result_data["average_invoice_value"] = round(rev_res[0]["average_amount"], 2) if rev_res else 0.0
        
        # Monthly Revenue Trend (Only for yearly/quarterly)
        trend_pipeline = [
            {"$match": time_match},
            {"$group": {
                "_id": {
                    "year": {"$year": "$created_at"},
                    "month": {"$month": "$created_at"}
                },
                "revenue": {"$sum": {"$toDouble": {"$ifNull": ["$edited_invoice_data.total_amount", 0]}}},
                "count": {"$sum": 1}
            }},
            {"$sort": {"_id.year": 1, "_id.month": 1}}
        ]
        trend_res = []
        months_list = ["", "Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
        for item in invoices_col.aggregate(trend_pipeline):
            trend_res.append({
                "month": f"{months_list[item['_id']['month']]} {item['_id']['year']}",
                "revenue": round(item["revenue"], 2),
                "count": item["count"]
            })
        result_data["revenue_trend"] = trend_res
        
    if intent in ["monthly_report", "quarterly_report", "yearly_report", "gst_analysis"]:
        # Aggregate GST Distribution
        gst_pipeline = [
            {"$match": time_match},
            {"$group": {
                "_id": None,
                "total_cgst": {"$sum": {"$toDouble": {"$ifNull": ["$edited_invoice_data.cgst_amount", 0]}}},
                "total_sgst": {"$sum": {"$toDouble": {"$ifNull": ["$edited_invoice_data.sgst_amount", 0]}}},
                "total_igst": {"$sum": {"$toDouble": {"$ifNull": ["$edited_invoice_data.igst_amount", 0]}}}
            }}
        ]
        gst_res = list(invoices_col.aggregate(gst_pipeline))
        result_data["gst_summary"] = {
            "cgst": round(gst_res[0]["total_cgst"], 2) if gst_res else 0.0,
            "sgst": round(gst_res[0]["total_sgst"], 2) if gst_res else 0.0,
            "igst": round(gst_res[0]["total_igst"], 2) if gst_res else 0.0,
            "total_gst": round((gst_res[0]["total_cgst"] + gst_res[0]["total_sgst"] + gst_res[0]["total_igst"]), 2) if gst_res else 0.0
        }
        
    if intent in ["monthly_report", "quarterly_report", "yearly_report", "vendor_analysis"]:
        # Aggregate Top Vendors
        vendor_pipeline = [
            {"$match": time_match},
            {"$group": {
                "_id": "$edited_invoice_data.company_name",
                "revenue": {"$sum": {"$toDouble": {"$ifNull": ["$edited_invoice_data.total_amount", 0]}}},
                "count": {"$sum": 1}
            }},
            {"$sort": {"revenue": -1}},
            {"$limit": 5}
        ]
        top_vendors = []
        for item in invoices_col.aggregate(vendor_pipeline):
            top_vendors.append({
                "vendor_name": item["_id"] or "Unknown Vendor",
                "revenue": round(item["revenue"], 2),
                "count": item["count"]
            })
        result_data["top_vendors"] = top_vendors
        
    if intent in ["monthly_report", "quarterly_report", "yearly_report", "ocr_correction_analysis"]:
        # OCR Quality Metrics (reviewed vs corrected)
        ocr_pipeline = [
            {"$match": time_match},
            {"$group": {
                "_id": "$review_status",
                "count": {"$sum": 1}
            }}
        ]
        ocr_counts = {"Reviewed": 0, "Corrected": 0, "Pending Review": 0}
        for item in invoices_col.aggregate(ocr_pipeline):
            ocr_counts[item["_id"]] = item["count"]
            
        total = sum(ocr_counts.values())
        result_data["ocr_metrics"] = {
            "total_invoices": total,
            "reviewed_count": ocr_counts.get("Reviewed", 0),
            "corrected_count": ocr_counts.get("Corrected", 0),
            "pending_count": ocr_counts.get("Pending Review", 0),
            "acceptance_rate_percent": round((ocr_counts.get("Reviewed", 0) / total * 100), 1) if total > 0 else 0.0,
            "correction_rate_percent": round((ocr_counts.get("Corrected", 0) / total * 100), 1) if total > 0 else 0.0
        }
        
    if intent == "invoice_search":
        # Search for details
        search_kw = question.lower().replace("search", "").replace("find", "").replace("invoice", "").strip()
        search_match = time_match.copy()
        if search_kw:
            search_match["$or"] = [
                {"edited_invoice_data.company_name": {"$regex": search_kw, "$options": "i"}},
                {"edited_invoice_data.invoice_number": {"$regex": search_kw, "$options": "i"}},
                {"edited_invoice_data.buyer_name": {"$regex": search_kw, "$options": "i"}}
            ]
            
        search_pipeline = [
            {"$match": search_match},
            {"$sort": {"created_at": -1}},
            {"$limit": 5},
            {"$project": {
                "invoice_number": "$edited_invoice_data.invoice_number",
                "company_name": "$edited_invoice_data.company_name",
                "buyer_name": "$edited_invoice_data.buyer_name",
                "invoice_date": "$edited_invoice_data.invoice_date",
                "total_amount": "$edited_invoice_data.total_amount",
                "review_status": "$review_status"
            }}
        ]
        results = []
        for item in invoices_col.aggregate(search_pipeline):
            results.append({
                "id": str(item["_id"]),
                "invoice_number": item.get("invoice_number", "N/A"),
                "vendor": item.get("company_name", "N/A"),
                "buyer": item.get("buyer_name", "N/A"),
                "date": item.get("invoice_date", "N/A"),
                "amount": item.get("total_amount", 0.0),
                "status": item.get("review_status", "N/A")
            })
        result_data["search_results"] = results
        
    # 4. Admin Only Aggregations
    if is_admin:
        if intent == "user_activity_analysis":
            # Group activity logs
            activity_pipeline = [
                {"$group": {
                    "_id": "$action",
                    "count": {"$sum": 1}
                }},
                {"$sort": {"count": -1}}
            ]
            act_counts = {}
            for item in logs_col.aggregate(activity_pipeline):
                act_counts[item["_id"]] = item["count"]
            result_data["global_activity_summary"] = act_counts
            
            # Daily active users trend (last 7 days)
            days_ago = datetime.utcnow() - timedelta(days=7)
            trend_pipeline = [
                {"$match": {"timestamp": {"$gte": days_ago}}},
                {"$group": {
                    "_id": {
                        "year": {"$year": "$timestamp"},
                        "month": {"$month": "$timestamp"},
                        "day": {"$day": "$timestamp"}
                    },
                    "count": {"$sum": 1},
                    "unique_users": {"$addToSet": "$user_id"}
                }},
                {"$sort": {"_id.year": 1, "_id.month": 1, "_id.day": 1}}
            ]
            daily_trend = []
            for item in logs_col.aggregate(trend_pipeline):
                y = item["_id"]["year"]
                m = item["_id"]["month"]
                d = item["_id"]["day"]
                daily_trend.append({
                    "date": f"{d:02d}-{m:02d}-{y}",
                    "actions_count": item["count"],
                    "active_users_count": len(item["unique_users"])
                })
            result_data["daily_activity_trend"] = daily_trend
            
        if intent == "top_uploaders":
            # Group invoices by user
            uploader_pipeline = [
                {"$match": {"is_deleted": {"$ne": True}}},
                {"$group": {
                    "_id": "$user_id",
                    "email": {"$first": "$user_email"},
                    "uploaded_by": {"$first": "$uploaded_by"},
                    "count": {"$sum": 1}
                }},
                {"$sort": {"count": -1}},
                {"$limit": 5}
            ]
            uploaders = []
            for item in invoices_col.aggregate(uploader_pipeline):
                uploaders.append({
                    "email": item["email"] or "system@invoiceocr.com",
                    "name": item["uploaded_by"] or "System",
                    "count": item["count"]
                })
            result_data["top_uploaders"] = uploaders
            
        if intent == "most_corrected_invoices":
            # Sort by change history length
            corrected_pipeline = [
                {"$match": {"is_deleted": {"$ne": True}}},
                {"$project": {
                    "invoice_number": "$edited_invoice_data.invoice_number",
                    "company_name": "$edited_invoice_data.company_name",
                    "user_email": "$user_email",
                    "change_count": {"$size": {"$ifNull": ["$change_history", []]}},
                    "last_modified_at": "$last_modified_at"
                }},
                {"$sort": {"change_count": -1}},
                {"$limit": 5}
            ]
            corrected_list = []
            for item in invoices_col.aggregate(corrected_pipeline):
                corrected_list.append({
                    "id": str(item["_id"]),
                    "invoice_number": item.get("invoice_number", "N/A"),
                    "vendor": item.get("company_name", "N/A"),
                    "email": item.get("user_email", "N/A"),
                    "correction_count": item.get("change_count", 0),
                    "last_modified": item.get("last_modified_at", "N/A")
                })
            result_data["most_corrected_invoices"] = corrected_list
            
    return result_data
