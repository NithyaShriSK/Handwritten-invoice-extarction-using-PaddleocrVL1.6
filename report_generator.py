import os
import json
import time
import requests

def generate_text_summary(intent, analytics_data):
    """
    Sends structured analytics data to local Ollama (Llama3) to generate
    a professional natural language business summary.
    Enforces strict LLM safety rules to prevent hallucinations.
    """
    # 1. Data Scarcity Guard
    # Check if we have 0 invoices for this period
    total_invoices = analytics_data.get("total_invoices_in_period", 0)
    if total_invoices == 0:
        return "Insufficient invoice data is available to generate this report."
        
    # Check for empty search results
    if intent == "invoice_search" and not analytics_data.get("search_results"):
        return "Insufficient invoice data is available to generate this report."
        
    model = os.environ.get("OLLAMA_MODEL", "llama3:latest")
    
    # 2. Formulate Prompt with strict constraints
    system_instruction = (
        "You are the InvoiceAI Business Intelligence Assistant. Your role is to write a highly professional, "
        "concise executive summary report based ONLY on the provided JSON database analytics. "
        "DO NOT guess, invent, or extrapolate any figures, totals, percentages, names, or date ranges. "
        "Rely strictly on the facts in the JSON. If a number is not in the JSON, do not mention it. "
        "Keep the summary short, structured, and enterprise-focused.\n\n"
    )
    
    data_json = json.dumps(analytics_data, indent=2)
    
    prompt = (
        f"{system_instruction}"
        f"Intent/Topic: {intent.replace('_', ' ').title()}\n"
        f"Structured JSON Analytics Data:\n"
        f"```json\n{data_json}\n```\n\n"
        f"Provide a structured response: "
        f"1. Executive Summary (Highlighting total invoices and overall status)\n"
        f"2. Financial Highlights (Summarize revenue and GST if present in the data)\n"
        f"3. Key Insights (Top vendors, activity levels, or OCR correction accuracy if present in the data)\n"
        f"4. Recommendations (Provide 2 action points based strictly on the metrics)."
    )
    
    # 3. Call local Ollama
    try:
        url = "http://localhost:11434/api/generate"
        payload = {
            "model": model,
            "prompt": prompt,
            "stream": False,
            "options": {
                "temperature": 0.2  # Low temperature to restrict creativity
            }
        }
        
        try:
            timeout_val = int(os.environ.get("OLLAMA_TIMEOUT_SECONDS", 120))
        except (ValueError, TypeError):
            timeout_val = 120
            
        timeout = (30, timeout_val)
        
        start_time = time.time()
        print(f"[OLLAMA] Request started")
        
        response = requests.post(url, json=payload, timeout=timeout)
        
        print(f"[OLLAMA] Response received")
        end_time = time.time()
        generation_duration = end_time - start_time
        print(f"[OLLAMA] Generation took {generation_duration:.1f} seconds")
        
        if response.status_code == 200:
            try:
                res_json = response.json()
                return res_json.get("response", "No response text generated from model.")
            except ValueError as je:
                print(f"[OLLAMA ERROR] Invalid JSON response: {je}")
                return "InvoiceAI Assistant is temporarily unavailable. Please ensure Ollama is running."
        elif response.status_code == 404 or "not found" in response.text.lower():
            print(f"[OLLAMA ERROR] Model missing or not found status {response.status_code}: {response.text}")
            return "Configured Ollama model could not be found."
        else:
            print(f"[OLLAMA ERROR] Received status code {response.status_code}: {response.text}")
            return "InvoiceAI Assistant is temporarily unavailable. Please ensure Ollama is running."
            
    except requests.exceptions.Timeout as te:
        print(f"[OLLAMA TIMEOUT] Ollama did not respond within {timeout_val} seconds.")
        return "InvoiceAI Assistant is generating the report. The request exceeded the configured timeout."
    except requests.exceptions.ConnectionError as ce:
        print(f"[OLLAMA OFFLINE] Connection failed: Connection refused.")
        return "InvoiceAI Assistant cannot connect to Ollama."
    except requests.exceptions.RequestException as re:
        print(f"[OLLAMA ERROR] Request failed: {re}")
        return "InvoiceAI Assistant is temporarily unavailable. Please ensure Ollama is running."
