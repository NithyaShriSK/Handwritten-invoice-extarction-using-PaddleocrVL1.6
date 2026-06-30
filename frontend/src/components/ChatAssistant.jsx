import React, { useState, useEffect, useRef } from "react";
import { api } from "../services/api";
import { toast } from "react-toastify";
import {
  MessageSquare,
  X,
  Send,
  Loader2,
  Download,
  HelpCircle,
  FileText,
  User,
  Sparkles,
  RefreshCw
} from "lucide-react";

const ChatAssistant = () => {
  const [isOpen, setIsOpen] = useState(false);
  const [messages, setMessages] = useState([
    {
      id: "welcome",
      sender: "bot",
      text: "Hello! I am NiBo, your AI BOT for InvoiceAI. I can help you analyze invoices, generate business reports, review GST data, track revenue trends, and answer invoice-related questions.",
      timestamp: new Date()
    }
  ]);
  const [inputValue, setInputValue] = useState("");
  const [loading, setLoading] = useState(false);
  const [generatingReport, setGeneratingReport] = useState(false);
  const messagesEndRef = useRef(null);

  const [maxHistory, setMaxHistory] = useState(50);

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages, loading, generatingReport]);

  useEffect(() => {
    api.getChatConfig()
      .then(res => {
        if (res.success && res.chat_max_history) {
          setMaxHistory(res.chat_max_history);
        }
      })
      .catch(err => {
        console.error("Failed to load chat config:", err);
      });
  }, []);

  const addMessage = (sender, text, extra = {}) => {
    setMessages(prev => {
      const newMsg = {
        id: Math.random().toString(36).substring(7),
        sender,
        text,
        timestamp: new Date(),
        ...extra
      };
      const updated = [...prev, newMsg];
      // Limit history count to prevent memory growth (constraint 5)
      if (updated.length > maxHistory) {
        return updated.slice(updated.length - maxHistory);
      }
      return updated;
    });
  };

  const handleSendMessage = async (textToSend) => {
    if (!textToSend.trim() || loading || generatingReport) return;
    
    const prompt = textToSend.trim();
    setInputValue("");
    addMessage("user", prompt);
    
    setLoading(true);
    
    // Check if the prompt requests generating a PDF report
    const isReportPrompt = prompt.toLowerCase().includes("generate") && prompt.toLowerCase().includes("report");
    
    if (isReportPrompt) {
      setGeneratingReport(true);
      try {
        const res = await api.chatReport(prompt);
        if (res.success && res.pdf_url) {
          const filename = res.pdf_url.split("/").pop();
          addMessage("bot", `I have successfully generated the requested intelligence report PDF. You can download the release file below.`, {
            pdfUrl: res.pdf_url,
            pdfFilename: filename,
            isReport: true
          });
          toast.success("Intelligence report compiled successfully!");
        } else {
          addMessage("bot", res.message || "Failed to generate the requested report.");
        }
      } catch (err) {
        console.error("Report generation error:", err);
        const errMsg = err.response?.data?.message || "NiBo AI BOT is temporarily offline. Could not generate PDF.";
        addMessage("bot", errMsg);
        toast.error("Report compilation failed.");
      } finally {
        setGeneratingReport(false);
        setLoading(false);
      }
    } else {
      // General chatbot query
      try {
        const res = await api.chatQuery(prompt);
        if (res.success) {
          addMessage("bot", res.answer);
        } else {
          addMessage("bot", res.message || "Something went wrong.");
        }
      } catch (err) {
        console.error("Chat error:", err);
        const errMsg = err.response?.data?.message || "InvoiceAI Assistant is temporarily unavailable. Please try again later.";
        addMessage("bot", errMsg);
      } finally {
        setLoading(false);
      }
    }
  };

  const handleDownloadPDF = (filename) => {
    if (!filename) {
      toast.error("Download filename is invalid.");
      return;
    }
    const token = localStorage.getItem("token");
    const downloadUrl = `http://localhost:5000/reports/${filename}`;
    
    fetch(downloadUrl, {
      headers: {
        "Authorization": `Bearer ${token}`
      }
    })
    .then(response => {
      if (!response.ok) {
        throw new Error("Access Denied or report file not found.");
      }
      return response.blob();
    })
    .then(blob => {
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = filename;
      document.body.appendChild(a);
      a.click();
      a.remove();
      window.URL.revokeObjectURL(url);
      toast.success("Report downloaded.");
    })
    .catch(err => {
      console.error("Download error:", err);
      toast.error("Unauthorized: Failed to download report file.");
    });
  };

  let suggestedPrompts = [];
  try {
    const userJson = localStorage.getItem("user");
    if (userJson) {
      const user = JSON.parse(userJson);
      if (user.role === "admin") {
        suggestedPrompts = [
          "Generate June 2026 report",
          "System revenue summary",
          "Show GST summary",
          "Most corrected invoices",
          "Top vendors this month"
        ];
      } else {
        suggestedPrompts = [
          "Generate June 2026 report",
          "What is my total revenue this month?",
          "Show GST summary",
          "Which invoices required corrections?",
          "Top buyers this month"
        ];
      }
    } else {
      suggestedPrompts = [
        "Generate June 2026 report",
        "What is my total revenue this month?",
        "Show GST summary",
        "Which invoices required corrections?",
        "Top buyers this month"
      ];
    }
  } catch (e) {
    console.error("Failed to parse user role for quick prompts:", e);
    suggestedPrompts = [
      "Generate June 2026 report",
      "What is my total revenue this month?",
      "Show GST summary",
      "Which invoices required corrections?",
      "Top buyers this month"
    ];
  }

  return (
    <div className="fixed bottom-6 right-6 z-50 font-sans select-none">
      {/* Floating Toggle Button */}
      {!isOpen && (
        <button
          onClick={() => setIsOpen(true)}
          className="p-4 bg-emerald-600 hover:bg-emerald-500 text-white rounded-full shadow-xl transition-all duration-300 hover:scale-110 flex items-center justify-center border border-emerald-500/20"
          title="Open Assistant"
        >
          <MessageSquare size={24} className="animate-pulse" />
        </button>
      )}

      {/* Expanded Chat Window */}
      {isOpen && (
        <div className="w-[380px] sm:w-[420px] h-[550px] bg-slate-900/95 dark:bg-slate-950/98 border border-slate-800 rounded-2xl shadow-2xl flex flex-col overflow-hidden backdrop-blur-md animate-fade-in">
          {/* Header */}
          <div className="p-4 bg-gradient-to-r from-emerald-950/40 to-slate-900 border-b border-slate-800 flex items-center justify-between">
            <div className="flex items-center gap-2.5">
              <div className="relative w-8 h-8 flex items-center justify-center bg-white dark:bg-[#1E293B] rounded-lg border border-slate-200 dark:border-slate-800 shadow-md p-1.5 shrink-0 select-none">
                <svg 
                  viewBox="0 0 24 24" 
                  fill="none" 
                  className="w-5 h-5 text-[#0D9488] dark:text-[#2DD4BF] transition-colors duration-300"
                  stroke="currentColor" 
                  strokeWidth="2" 
                  strokeLinecap="round" 
                  strokeLinejoin="round"
                >
                  {/* Outer OCR Scanner Bracket Corners */}
                  <path d="M3 8V3h5M16 3h5v5M3 16v5h5M16 21h5v-5" strokeWidth="1.5" className="opacity-60 dark:opacity-80" />
                  
                  {/* Invoice Document outline inside the brackets */}
                  <path d="M14 6H8a1 1 0 0 0-1 1v10a1 1 0 0 0 1 1h8a1 1 0 0 0 1-1v-7z" strokeWidth="1.8" />
                  <path d="M13 6v4h4" strokeWidth="1.8" />
                  
                  {/* Table / Invoice data lines inside document */}
                  <line x1="9.5" y1="11.5" x2="14.5" y2="11.5" strokeWidth="1.2" />
                  <line x1="9.5" y1="14.5" x2="12.5" y2="14.5" strokeWidth="1.2" />
                </svg>
                {/* Pulsing horizontal scan laser overlay */}
                <div className="absolute left-1 right-1 h-[1px] bg-[#0D9488] dark:bg-[#2DD4BF] shadow-[0_0_8px_#2DD4BF] rounded-full top-[52%] -translate-y-1/2 animate-pulse" />
              </div>
              <div>
                <h4 className="text-sm font-bold text-white tracking-wide">NiBo</h4>
                <p className="text-[10px] text-emerald-500 font-semibold flex items-center gap-1">
                  <span className="w-1.5 h-1.5 bg-emerald-500 rounded-full animate-pulse"></span>
                  AI BOT
                </p>
              </div>
            </div>
            <button
              onClick={() => setIsOpen(false)}
              className="text-slate-400 hover:text-white p-1 hover:bg-slate-800/50 rounded-lg transition-colors"
            >
              <X size={18} />
            </button>
          </div>

          {/* Messages Log */}
          <div className="flex-1 p-4 overflow-y-auto space-y-4 scrollbar-thin scrollbar-thumb-slate-800">
            {messages.map((m) => (
              <div
                key={m.id}
                className={`flex gap-2.5 ${m.sender === "user" ? "flex-row-reverse" : "flex-row"}`}
              >
                {/* Avatar */}
                <div className={`w-8 h-8 rounded-lg flex items-center justify-center shrink-0 border ${
                  m.sender === "user" 
                    ? "bg-slate-800 border-slate-700 text-slate-300" 
                    : "bg-emerald-950/30 border-emerald-900/30 text-emerald-500"
                }`}>
                  {m.sender === "user" ? <User size={14} /> : <Sparkles size={14} />}
                </div>

                {/* Message Body */}
                <div className="max-w-[75%] space-y-2">
                  <div className={`p-3 rounded-2xl text-xs leading-relaxed ${
                    m.sender === "user"
                      ? "bg-emerald-600 text-white rounded-tr-none"
                      : "bg-slate-900 border border-slate-800 text-slate-300 rounded-tl-none"
                  }`}>
                    {/* Render breaklines */}
                    {m.text.split("\n").map((line, i) => (
                      <p key={i} className={i > 0 ? "mt-1.5" : ""}>{line}</p>
                    ))}

                    {/* PDF Report Download Button Component */}
                    {m.isReport && m.pdfFilename && (
                      <button
                        onClick={() => handleDownloadPDF(m.pdfFilename)}
                        className="mt-3 w-full flex items-center justify-center gap-2 px-3 py-2 bg-emerald-500 hover:bg-emerald-400 text-slate-950 font-bold rounded-xl transition-all shadow-md"
                      >
                        <Download size={14} />
                        <span>Download PDF Report</span>
                      </button>
                    )}
                  </div>
                  
                  <span className={`text-[9px] text-slate-500 font-mono block ${
                    m.sender === "user" ? "text-right" : "text-left"
                  }`}>
                    {m.timestamp.toLocaleTimeString("en-IN", { hour: '2-digit', minute: '2-digit' })}
                  </span>
                </div>
              </div>
            ))}

            {/* Typing Indicator */}
            {loading && (
              <div className="flex gap-2.5 items-center text-slate-500 text-xs">
                <div className="w-8 h-8 rounded-lg bg-emerald-950/10 border border-emerald-900/10 text-emerald-600 flex items-center justify-center shrink-0">
                  <Loader2 className="animate-spin" size={14} />
                </div>
                <span>
                  {generatingReport 
                    ? "Compiling MongoDB aggregations & rendering ReportLab PDF..." 
                    : "AI Assistant is analyzing database metrics..."}
                </span>
              </div>
            )}
            
            <div ref={messagesEndRef} />
          </div>

          {/* Quick suggestions block (hidden during active operations) */}
          {!loading && !generatingReport && messages.length <= 2 && (
            <div className="p-3 bg-slate-950/50 border-t border-slate-800/50 space-y-2">
              <span className="text-[10px] font-bold text-slate-500 tracking-wider uppercase px-1">Suggested Queries</span>
              <div className="flex flex-wrap gap-1.5">
                {suggestedPrompts.map((p, idx) => (
                  <button
                    key={idx}
                    onClick={() => handleSendMessage(p)}
                    className="text-[10px] font-medium px-2.5 py-1.5 bg-slate-900 hover:bg-slate-800 border border-slate-800 text-slate-300 rounded-lg transition-colors"
                  >
                    {p}
                  </button>
                ))}
              </div>
            </div>
          )}

          {/* Chat Input form */}
          <form
            onSubmit={(e) => {
              e.preventDefault();
              handleSendMessage(inputValue);
            }}
            className="p-3 bg-slate-950 border-t border-slate-800 flex gap-2 items-center"
          >
            <input
              type="text"
              value={inputValue}
              onChange={(e) => setInputValue(e.target.value)}
              disabled={loading || generatingReport}
              placeholder={generatingReport ? "Compiling PDF report..." : "Ask about revenue, GST, reports..."}
              className="flex-1 px-3 py-2 bg-slate-900 border border-slate-800 text-xs text-white rounded-xl placeholder-slate-500 focus:outline-none focus:ring-1 focus:ring-emerald-500 disabled:opacity-50"
            />
            <button
              type="submit"
              disabled={!inputValue.trim() || loading || generatingReport}
              className="p-2 bg-emerald-600 hover:bg-emerald-500 text-white rounded-xl disabled:opacity-50 disabled:bg-slate-800 transition-colors flex items-center justify-center"
            >
              <Send size={14} />
            </button>
          </form>
        </div>
      )}
    </div>
  );
};

export default ChatAssistant;
