import os
import time
from datetime import datetime
from intent_router import classify_intent
from analytics_queries import run_analytics_query
from report_generator import generate_text_summary

# Thread-safe in-memory cache for aggregation results
# Structure: { cache_key: (timestamp, analytics_data) }
analytics_cache = {}

def get_cache_key(user_id, intent, question):
    """
    Formulates a key unique to the user, intent, and reporting period.
    """
    from analytics_queries import parse_date_range
    _, _, period_label, _ = parse_date_range(question)
    return f"{user_id}:{intent}:{period_label}"

def handle_chatbot_query(user_id, user_email, role, question):
    """
    Orchestrates the chatbot pipeline:
    1. Detect intent and check for off-topic queries.
    2. Check cache.
    3. Run MongoDB aggregation pipelines.
    4. Call local Ollama Llama3 model for natural language summary.
    """
    # Dynamic import to log actions
    from backend_app import log_activity
    
    is_admin = (role == "admin")
    
    # 1. Intent routing & off-topic filtering
    print(f"[CHAT] Received request: '{question}' from user {user_email} (role: {role})")
    intent, refusal_msg = classify_intent(question, is_admin=is_admin)
    
    if intent == "unsupported":
        print(f"[CHAT] Query unsupported or refused: '{refusal_msg}'")
        return {
            "success": True,
            "answer": refusal_msg,
            "intent": "unsupported",
            "data": {}
        }
        
    # 2. Check analytics caching
    cache_ttl_seconds = int(os.environ.get("CHAT_CACHE_TTL_MINUTES", 5)) * 60
    cache_key = get_cache_key(user_id, intent, question)
    now = time.time()
    
    cached_data = analytics_cache.get(cache_key)
    if cached_data:
        cache_time, data = cached_data
        if now - cache_time < cache_ttl_seconds:
            print(f"[CHAT] Cache HIT for key {cache_key}. Serving cached data.")
            # Serve cached, generate summary
            summary = generate_text_summary(intent, data)
            
            # Log successful query
            log_activity("chatbot_query", metadata={"intent": intent, "question": question, "cached": True})
            
            return {
                "success": True,
                "answer": summary,
                "intent": intent,
                "data": data
            }
            
    # 3. Run MongoDB Aggregation Query
    print(f"[CHAT] Cache MISS. Executing database aggregations for intent '{intent}'...")
    analytics_data = run_analytics_query(intent, user_id, is_admin, question)
    
    if "error" in analytics_data:
        return {
            "success": False,
            "answer": "Failed to connect to database.",
            "intent": intent,
            "data": {}
        }
        
    # Store in cache
    analytics_cache[cache_key] = (now, analytics_data)
    
    # 4. Generate summary using Ollama
    print(f"[CHAT] Invoking LLM summary generation using model {os.environ.get('OLLAMA_MODEL', 'llama3:latest')}...")
    summary = generate_text_summary(intent, analytics_data)
    
    # Log successful query
    log_activity("chatbot_query", metadata={"intent": intent, "question": question, "cached": False})
    
    return {
        "success": True,
        "answer": summary,
        "intent": intent,
        "data": analytics_data
    }
