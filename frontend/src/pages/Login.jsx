import React, { useEffect, useState, useRef } from "react";
import { toast } from "react-toastify";
import { api } from "../services/api";
import { Shield, User, Lock, Mail, Eye, EyeOff, Sun, Moon } from "lucide-react";
import { motion, AnimatePresence } from "framer-motion";

const Login = () => {
  const [loading, setLoading] = useState(false);
  const [portalType, setPortalType] = useState("user"); // "user" or "admin"
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  
  const [theme, setTheme] = useState(() => {
    return localStorage.getItem("theme") || "dark";
  });

  const loginTypeRef = useRef("user");

  useEffect(() => {
    loginTypeRef.current = portalType;
  }, [portalType]);

  // Sync theme with document class list
  useEffect(() => {
    const root = window.document.documentElement;
    if (theme === "dark") {
      root.classList.add("dark");
    } else {
      root.classList.remove("dark");
    }
    localStorage.setItem("theme", theme);
  }, [theme]);

  useEffect(() => {
    // If user is already logged in, redirect based on role
    const token = localStorage.getItem("token");
    const userJson = localStorage.getItem("user");
    if (token && userJson) {
      try {
        const user = JSON.parse(userJson);
        if (user.role === "admin") {
          window.location.href = "/admin/dashboard";
        } else {
          window.location.href = "/dashboard";
        }
        return;
      } catch (e) {
        localStorage.removeItem("token");
        localStorage.removeItem("user");
      }
    }

    const initializeGoogle = () => {
      if (window.google) {
        const clientId = import.meta.env.VITE_GOOGLE_CLIENT_ID;
        if (!clientId) {
          console.error("Google Client ID not configured in frontend .env");
          return;
        }

        window.google.accounts.id.initialize({
          client_id: clientId,
          callback: handleCredentialResponse,
          auto_select: false,
          cancel_on_tap_outside: true,
        });
      }
    };

    if (window.google) {
      initializeGoogle();
    } else {
      const checkInterval = setInterval(() => {
        if (window.google) {
          initializeGoogle();
          clearInterval(checkInterval);
        }
      }, 100);
      return () => clearInterval(checkInterval);
    }
  }, []);

  useEffect(() => {
    // Render Google Sign-in button dynamically based on portalType and theme
    const renderGoogleBtn = () => {
      const btnEl = document.getElementById("google-signin-btn");
      if (window.google && btnEl) {
        try {
          window.google.accounts.id.renderButton(btnEl, {
            theme: theme === "dark" ? "filled_black" : "outline",
            size: "large",
            shape: "rectangular",
            width: "356", // Fits nicely inside the 420px card minus padding
            text: "continue_with",
            logo_alignment: "left",
          });
        } catch (e) {
          console.error("Error rendering Google button:", e);
        }
      }
    };

    if (window.google) {
      renderGoogleBtn();
    } else {
      const checkInterval = setInterval(() => {
        if (window.google) {
          renderGoogleBtn();
          clearInterval(checkInterval);
        }
      }, 100);
      return () => clearInterval(checkInterval);
    }
  }, [portalType, theme]);

  const handleCredentialResponse = async (response) => {
    setLoading(true);
    const selectedLoginType = loginTypeRef.current;
    try {
      const idToken = response.credential;
      const res = await api.loginGoogle(idToken, selectedLoginType);
      if (res.success) {
        localStorage.setItem("token", res.token);
        localStorage.setItem("user", JSON.stringify(res.user));
        toast.success("Welcome, " + res.user.name + "!");
        if (res.user.role === "admin") {
          window.location.href = "/admin/dashboard";
        } else {
          window.location.href = "/dashboard";
        }
      } else {
        toast.error(res.message || "Google authentication failed");
      }
    } catch (error) {
      console.error("Login callback error:", error);
      const errMsg = error.response?.data?.message || "Connection to auth server failed.";
      toast.error(errMsg);
    } finally {
      setLoading(false);
    }
  };

  const handlePrimaryAction = (e) => {
    e.preventDefault();
    toast.info("Google SSO is enforced. Launching Google login...");
    if (window.google) {
      window.google.accounts.id.prompt();
    }
  };

  const toggleTheme = () => {
    setTheme(prev => prev === "dark" ? "light" : "dark");
  };

  return (
    <div className="min-h-screen w-full flex flex-col items-center justify-center p-4 relative transition-colors duration-300 bg-[#F8FAFC] dark:bg-[#0F172A] text-[#0F172A] dark:text-[#F8FAFC] font-sans">
      {/* Theme Toggle Button */}
      <button
        onClick={toggleTheme}
        className="absolute top-6 right-6 p-2.5 rounded-xl border border-[#E2E8F0] dark:border-[#334155] bg-white dark:bg-[#1E293B] text-[#64748B] dark:text-[#94A3B8] hover:bg-slate-50 dark:hover:bg-slate-800 transition-colors shadow-sm"
        title="Toggle Light/Dark Theme"
      >
        {theme === "dark" ? <Sun size={18} /> : <Moon size={18} />}
      </button>

      {/* Loading Overlay */}
      <AnimatePresence>
        {loading && (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            className="z-50 absolute inset-0 bg-slate-900/60 backdrop-blur-sm flex flex-col items-center justify-center space-y-4"
          >
            <div className="w-10 h-10 border-4 border-[#10B981] dark:border-[#34D399] border-t-transparent rounded-full animate-spin"></div>
            <span className="text-xs font-semibold tracking-wider text-slate-200">Verifying secure credentials...</span>
          </motion.div>
        )}
      </AnimatePresence>

      {/* Header Info */}
      <div className="flex flex-col items-center mb-6 text-center select-none">
        {/* Custom Branded InvoiceAI Logo */}
        <div className="relative w-14 h-14 flex items-center justify-center mb-3">
          {/* Subtle Outer Glow Background */}
          <div className="absolute inset-0 bg-[#10B981]/15 dark:bg-[#34D399]/15 rounded-2xl blur-md scale-95" />
          
          {/* Logo Card Frame */}
          <div className="relative w-14 h-14 flex items-center justify-center p-3 bg-white dark:bg-[#1E293B] rounded-2xl border border-slate-200 dark:border-slate-800 shadow-md">
            <svg 
              viewBox="0 0 24 24" 
              fill="none" 
              className="w-8 h-8 text-[#10B981] dark:text-[#34D399] transition-colors duration-300"
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
            <div className="absolute left-2 right-2 h-[1.5px] bg-[#10B981] dark:bg-[#34D399] shadow-[0_0_8px_#34D399] rounded-full top-[52%] -translate-y-1/2 animate-pulse" />
          </div>
        </div>
        
        <h1 className="text-2xl font-bold text-[#0F172A] dark:text-[#F8FAFC] tracking-tight">InvoiceAI</h1>
        <p className="text-xs text-[#64748B] dark:text-[#94A3B8] mt-1.5 font-semibold tracking-wide">
          AI-Powered Invoice Extraction & Management
        </p>
      </div>

      {/* Auth Card */}
      <motion.div
        initial={{ opacity: 0, y: 12 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.4 }}
        className="w-full max-w-[420px] bg-white dark:bg-[#1E293B] border border-[#E2E8F0] dark:border-[#334155] p-8 rounded-2xl shadow-sm flex flex-col"
      >
        {/* Role Toggle Selector */}
        <div className="relative flex p-1 bg-slate-100 dark:bg-slate-950 border border-[#E2E8F0] dark:border-slate-800 rounded-xl w-full mb-6">
          <div className="absolute inset-y-1 left-1 right-1 w-[calc(50%-4px)] pointer-events-none">
            <motion.div
              className="w-full h-full bg-white dark:bg-[#1E293B] border border-[#E2E8F0] dark:border-slate-800 rounded-lg shadow-sm"
              animate={{
                x: portalType === "admin" ? "100%" : 0,
              }}
              transition={{ type: "spring", stiffness: 380, damping: 30 }}
            />
          </div>
          
          <button
            type="button"
            onClick={() => setPortalType("user")}
            className={`relative z-10 flex-1 py-2 text-xs font-bold transition-colors duration-200 flex items-center justify-center gap-1.5 ${
              portalType === "user"
                ? "text-[#10B981] dark:text-[#34D399]"
                : "text-[#64748B] dark:text-[#94A3B8] hover:text-[#0F172A] dark:hover:text-[#F8FAFC]"
            }`}
          >
            <User size={13} />
            User
          </button>
          
          <button
            type="button"
            onClick={() => setPortalType("admin")}
            className={`relative z-10 flex-1 py-2 text-xs font-bold transition-colors duration-200 flex items-center justify-center gap-1.5 ${
              portalType === "admin"
                ? "text-[#10B981] dark:text-[#34D399]"
                : "text-[#64748B] dark:text-[#94A3B8] hover:text-[#0F172A] dark:hover:text-[#F8FAFC]"
            }`}
          >
            <Shield size={13} />
            Admin
          </button>
        </div>

        {/* Input Fields */}
        <form onSubmit={handlePrimaryAction} className="space-y-4">
          <div>
            <label className="block text-[10px] font-bold tracking-wider text-[#64748B] dark:text-[#94A3B8] uppercase mb-1.5">
              Email
            </label>
            <div className="relative">
              <span className="absolute inset-y-0 left-0 flex items-center pl-3 text-[#64748B] dark:text-[#94A3B8] pointer-events-none">
                <Mail size={14} />
              </span>
              <input
                type="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                placeholder={portalType === "user" ? "user@company.com" : "admin@company.com"}
                className="w-full pl-9 pr-3 py-2 text-sm bg-white dark:bg-[#1E293B] border border-[#E2E8F0] dark:border-[#334155] rounded-xl text-[#0F172A] dark:text-[#F8FAFC] placeholder-[#64748B] dark:placeholder-[#94A3B8] focus:ring-2 focus:ring-[#10B981] dark:focus:ring-[#34D399] focus:border-transparent outline-none transition-all"
              />
            </div>
          </div>

          <div>
            <label className="block text-[10px] font-bold tracking-wider text-[#64748B] dark:text-[#94A3B8] uppercase mb-1.5">
              Password
            </label>
            <div className="relative">
              <span className="absolute inset-y-0 left-0 flex items-center pl-3 text-[#64748B] dark:text-[#94A3B8] pointer-events-none">
                <Lock size={14} />
              </span>
              <input
                type={showPassword ? "text" : "password"}
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                placeholder="Enter your password"
                className="w-full pl-9 pr-10 py-2 text-sm bg-white dark:bg-[#1E293B] border border-[#E2E8F0] dark:border-[#334155] rounded-xl text-[#0F172A] dark:text-[#F8FAFC] placeholder-[#64748B] dark:placeholder-[#94A3B8] focus:ring-2 focus:ring-[#10B981] dark:focus:ring-[#34D399] focus:border-transparent outline-none transition-all"
              />
              <button
                type="button"
                onClick={() => setShowPassword(prev => !prev)}
                className="absolute inset-y-0 right-0 flex items-center pr-3 text-[#64748B] dark:text-[#94A3B8] hover:text-[#0F172A] dark:hover:text-[#F8FAFC] transition-colors"
              >
                {showPassword ? <EyeOff size={14} /> : <Eye size={14} />}
              </button>
            </div>
          </div>

          {/* Dynamic Notice badges */}
          <AnimatePresence mode="wait">
            <motion.div
              key={portalType}
              initial={{ opacity: 0, y: 4 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -4 }}
              transition={{ duration: 0.15 }}
              className="pt-1.5"
            >
              {portalType === "user" ? (
                <div className="p-3 bg-brand-500/5 dark:bg-brand-400/5 border border-brand-500/10 dark:border-brand-400/10 rounded-xl flex items-start gap-2.5 text-xs text-[#10B981] dark:text-[#34D399] font-medium leading-relaxed">
                  <User size={14} className="mt-0.5 flex-shrink-0" />
                  <span>User sessions are secure and encrypted.</span>
                </div>
              ) : (
                <div className="p-3 bg-amber-500/5 dark:bg-amber-400/5 border border-amber-500/20 dark:border-amber-400/20 rounded-xl flex items-start gap-2.5 text-xs text-amber-600 dark:text-amber-400 font-medium leading-relaxed">
                  <Shield size={14} className="mt-0.5 flex-shrink-0" />
                  <span>Admin access is restricted to authorized accounts only.</span>
                </div>
              )}
            </motion.div>
          </AnimatePresence>

          {/* Primary Action Button */}
          <button
            type="submit"
            className="w-full mt-2 py-2.5 bg-[#10B981] dark:bg-[#34D399] hover:bg-[#059669] dark:hover:bg-[#059669] text-white dark:text-[#0F172A] rounded-xl text-sm font-semibold transition-colors duration-200 shadow-sm outline-none focus:ring-2 focus:ring-[#10B981] dark:focus:ring-[#34D399] focus:ring-offset-2"
          >
            {portalType === "user" ? "Continue as User" : "Continue as Admin"}
          </button>
        </form>

        {/* OR Divider */}
        <div className="flex items-center gap-3 w-full my-6">
          <div className="flex-1 h-[1px] bg-[#E2E8F0] dark:bg-[#334155]"></div>
          <span className="text-[10px] font-bold uppercase tracking-wider text-[#64748B] dark:text-[#94A3B8]">or</span>
          <div className="flex-1 h-[1px] bg-[#E2E8F0] dark:bg-[#334155]"></div>
        </div>

        {/* Google Sign-in Element wrapper */}
        <div className="w-full flex justify-center">
          <div id="google-signin-btn" className="w-full flex justify-center"></div>
        </div>
      </motion.div>

      {/* Footer warning */}
      <p className="mt-8 text-[10px] font-bold tracking-widest text-[#64748B] dark:text-[#94A3B8] uppercase text-center">
        Unauthorized access is monitored and logged.
      </p>
    </div>
  );
};

export default Login;
