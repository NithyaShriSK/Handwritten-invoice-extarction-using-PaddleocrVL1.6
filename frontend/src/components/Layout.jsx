import React, { useState, useEffect } from "react";
import { Link, useNavigate, useLocation } from "react-router-dom";
import {
  LayoutDashboard,
  FileText,
  History,
  BarChart3,
  Search,
  Sun,
  Moon,
  Menu,
  X,
  Sparkles,
  HeartPulse,
  Users,
  ClipboardList,
  Shield,
  LogOut,
  FileSpreadsheet
} from "lucide-react";
import { api } from "../services/api";
import ChatAssistant from "./ChatAssistant";

export const Layout = ({ children }) => {
  const [darkMode, setDarkMode] = useState(() => {
    const saved = localStorage.getItem("theme");
    return saved === "dark" || (!saved && window.matchMedia("(prefers-color-scheme: dark)").matches);
  });
  
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);
  const [searchVal, setSearchVal] = useState("");
  
  const navigate = useNavigate();
  const location = useLocation();

  // Apply theme class
  useEffect(() => {
    if (darkMode) {
      document.documentElement.classList.add("dark");
      localStorage.setItem("theme", "dark");
    } else {
      document.documentElement.classList.remove("dark");
      localStorage.setItem("theme", "light");
    }
  }, [darkMode]);

  const user = JSON.parse(localStorage.getItem("user") || "{}");
  const isAdmin = user.role === "admin";

  // Sync route path to navigation items
  const menuItems = [
    { name: "Dashboard", path: "/dashboard", icon: LayoutDashboard },
    { name: "Extract Invoice", path: "/extract", icon: FileText },
    { name: "Invoice History", path: "/history", icon: History },
    { name: "Analytics", path: "/analytics", icon: BarChart3 },
    { name: "Reports", path: "/reports", icon: FileSpreadsheet },
  ];

  const adminMenuItems = [
    { name: "Admin Stats", path: "/admin/dashboard", icon: Shield },
    { name: "User Management", path: "/admin/users", icon: Users },
    { name: "Activity Logs", path: "/admin/activity", icon: ClipboardList },
    { name: "Reports", path: "/reports", icon: FileSpreadsheet },
  ];

  // Handle global search submission
  const handleSearchSubmit = (e) => {
    e.preventDefault();
    if (searchVal.trim()) {
      navigate(`/history?search=${encodeURIComponent(searchVal.trim())}`);
      setSearchVal("");
    }
  };

  const handleLogout = async () => {
    try {
      await api.logout();
    } catch (e) {
      console.error("Logout request failed:", e);
    }
    localStorage.removeItem("token");
    localStorage.removeItem("user");
    navigate("/login");
  };

  return (
    <div className="min-h-screen bg-slate-50 dark:bg-[#0F172A] bg-grid-pattern transition-colors duration-300 flex">
      {/* Sidebar for Desktop */}
      <aside className="hidden md:flex flex-col w-64 glass-card border-r border-slate-200 dark:border-slate-800 shrink-0 m-4 rounded-2xl">
        {/* Logo Section */}
        <div className="p-6 flex items-center gap-3 border-b border-slate-200 dark:border-slate-800">
          <div className="relative w-11 h-11 flex items-center justify-center bg-white dark:bg-[#1E293B] rounded-xl border border-slate-200 dark:border-slate-800 shadow-md p-2 shrink-0 select-none">
            <svg 
              viewBox="0 0 24 24" 
              fill="none" 
              className="w-6 h-6 text-[#10B981] dark:text-[#34D399] transition-colors duration-300"
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
            <div className="absolute left-1.5 right-1.5 h-[1px] bg-[#10B981] dark:bg-[#34D399] shadow-[0_0_8px_#34D399] rounded-full top-[52%] -translate-y-1/2 animate-pulse" />
          </div>
          <div>
            <h1 className="font-bold text-slate-800 dark:text-white text-lg tracking-tight">InvoiceAI</h1>
            <span className="text-xs text-brand-500 font-semibold tracking-wide uppercase">OCR SaaS</span>
          </div>
        </div>

        {/* Navigation */}
        <nav className="flex-1 px-4 py-6 space-y-1 overflow-y-auto">
          {!isAdmin && menuItems.map((item) => {
            const Icon = item.icon;
            const isActive = location.pathname === item.path;
            return (
              <Link
                key={item.name}
                to={item.path}
                className={`flex items-center gap-3 px-4 py-3 rounded-xl font-medium text-sm transition-all duration-200 ${
                  isActive
                    ? "bg-brand-500 text-white shadow-lg shadow-brand-500/25"
                    : "text-slate-600 dark:text-slate-400 hover:bg-slate-100 dark:hover:bg-slate-800 hover:text-slate-900 dark:hover:text-white"
                }`}
              >
                <Icon size={18} />
                {item.name}
              </Link>
            );
          })}

          {/* Admin Navigation Section */}
          {isAdmin && adminMenuItems.map((item) => {
            const Icon = item.icon;
            const isActive = location.pathname === item.path;
            return (
              <Link
                key={item.name}
                to={item.path}
                className={`flex items-center gap-3 px-4 py-3 rounded-xl font-medium text-sm transition-all duration-200 ${
                  isActive
                    ? "bg-emerald-600 text-white shadow-lg shadow-emerald-600/25"
                    : "text-slate-600 dark:text-slate-400 hover:bg-slate-100 dark:hover:bg-slate-800 hover:text-slate-900 dark:hover:text-white"
                }`}
              >
                <Icon size={18} />
                {item.name}
              </Link>
            );
          })}
        </nav>

        {/* Sidebar Footer */}
        <div className="p-4 border-t border-slate-200 dark:border-slate-800 flex flex-col gap-3">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              {user.picture ? (
                <img src={user.picture} alt={user.name} className="w-8 h-8 rounded-full object-cover border border-slate-200 dark:border-slate-800" />
              ) : (
                <div className="w-8 h-8 rounded-full bg-slate-200 dark:bg-slate-800 flex items-center justify-center text-slate-600 dark:text-slate-300 font-bold text-sm">
                  {user.name ? user.name.charAt(0).toUpperCase() : "U"}
                </div>
              )}
              <div className="min-w-0">
                <p className="text-xs font-semibold text-slate-700 dark:text-slate-300 truncate max-w-[125px]">{user.name || "Default User"}</p>
                <p className="text-[10px] text-slate-400 truncate max-w-[125px]">{user.email || "user@invoice.ai"}</p>
              </div>
            </div>
            <button
              onClick={() => setDarkMode(!darkMode)}
              className="p-2 rounded-xl text-slate-500 dark:text-slate-400 hover:bg-slate-100 dark:hover:bg-slate-800 transition-colors"
              title="Toggle Light/Dark Theme"
            >
              {darkMode ? <Sun size={16} /> : <Moon size={16} />}
            </button>
          </div>
          
          <button
            onClick={handleLogout}
            className="flex items-center justify-center gap-2 w-full px-4 py-2 mt-1 rounded-xl text-sm font-medium text-rose-600 hover:bg-rose-50 dark:hover:bg-rose-950/20 border border-transparent hover:border-rose-200 dark:hover:border-rose-900/30 transition-all duration-200"
          >
            <LogOut size={16} />
            <span>Logout</span>
          </button>
        </div>
      </aside>

      {/* Main Content Area */}
      <div className="flex-1 flex flex-col min-w-0">
        {/* Top Header */}
        <header className="flex items-center justify-between px-6 py-4 md:px-8 bg-white/70 dark:bg-slate-950/60 backdrop-blur-md border-b border-slate-200/50 dark:border-slate-800/40 z-30 sticky top-0 m-0">
          <div className="flex items-center gap-4">
            {/* Mobile Menu Button */}
            <button
              onClick={() => setMobileMenuOpen(true)}
              className="p-2 -ml-2 rounded-xl text-slate-500 dark:text-slate-400 hover:bg-slate-100 dark:hover:bg-slate-800 md:hidden"
            >
              <Menu size={20} />
            </button>

            {/* Header Global Search Box */}
            {!isAdmin && (
              <form onSubmit={handleSearchSubmit} className="hidden sm:flex items-center relative w-64 md:w-80">
                <span className="absolute left-3 text-slate-400 dark:text-slate-500">
                  <Search size={16} />
                </span>
                <input
                  type="text"
                  placeholder="Search across Company, Invoice #, Buyer..."
                  value={searchVal}
                  onChange={(e) => setSearchVal(e.target.value)}
                  className="w-full pl-10 pr-4 py-2 text-xs rounded-xl glass-input placeholder-slate-400 border border-slate-200 dark:border-slate-800 focus:outline-none focus:ring-1 focus:ring-brand-500 dark:focus:ring-brand-500 focus:border-transparent transition-all"
                />
              </form>
            )}
          </div>

          <div className="flex items-center gap-4">
            {/* Mobile Search Icon (opens filter on history) */}
            {!isAdmin && (
              <form onSubmit={handleSearchSubmit} className="sm:hidden flex items-center relative w-36">
                <span className="absolute left-2.5 text-slate-400 dark:text-slate-500">
                  <Search size={14} />
                </span>
                <input
                  type="text"
                  placeholder="Search..."
                  value={searchVal}
                  onChange={(e) => setSearchVal(e.target.value)}
                  className="w-full pl-8 pr-2 py-1.5 text-[11px] rounded-lg glass-input border border-slate-200 dark:border-slate-800 placeholder-slate-400 focus:outline-none"
                />
              </form>
            )}

            {/* Health status indicator */}
            <div className="hidden lg:flex items-center gap-2 px-3 py-1.5 rounded-full bg-emerald-50 dark:bg-emerald-950/30 border border-emerald-200 dark:border-emerald-900/40 text-emerald-600 dark:text-emerald-400 text-xs font-medium">
              <HeartPulse size={12} className="animate-pulse" />
              <span>System Online</span>
            </div>

            {/* Dark Mode toggle for mobile */}
            <button
              onClick={() => setDarkMode(!darkMode)}
              className="md:hidden p-2 rounded-xl text-slate-500 dark:text-slate-400 hover:bg-slate-100 dark:hover:bg-slate-800 transition-colors"
            >
              {darkMode ? <Sun size={18} /> : <Moon size={18} />}
            </button>
          </div>
        </header>

        {/* Mobile Sidebar overlay */}
        {mobileMenuOpen && (
          <div className="fixed inset-0 bg-slate-900/40 dark:bg-slate-950/60 backdrop-blur-sm z-50 md:hidden">
            <aside className="fixed top-0 left-0 bottom-0 w-64 bg-white dark:bg-slate-900 p-6 flex flex-col justify-between border-r border-slate-200 dark:border-slate-800 animate-slide-in">
              <div>
                <div className="flex items-center justify-between pb-6 border-b border-slate-200 dark:border-slate-800">
                  <div className="flex items-center gap-3">
                    <div className="relative w-11 h-11 flex items-center justify-center bg-white dark:bg-[#1E293B] rounded-xl border border-slate-200 dark:border-slate-800 shadow-md p-2 shrink-0 select-none">
                      <svg 
                        viewBox="0 0 24 24" 
                        fill="none" 
                        className="w-6 h-6 text-[#10B981] dark:text-[#34D399] transition-colors duration-300"
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
                      <div className="absolute left-1.5 right-1.5 h-[1px] bg-[#10B981] dark:bg-[#34D399] shadow-[0_0_8px_#34D399] rounded-full top-[52%] -translate-y-1/2 animate-pulse" />
                    </div>
                    <div>
                      <h2 className="font-bold text-slate-800 dark:text-white text-md">InvoiceAI</h2>
                      <span className="text-[10px] text-brand-500 font-semibold tracking-wider">OCR SaaS</span>
                    </div>
                  </div>
                  <button
                    onClick={() => setMobileMenuOpen(false)}
                    className="p-2 rounded-xl text-slate-500 hover:bg-slate-100 dark:hover:bg-slate-800"
                  >
                    <X size={18} />
                  </button>
                </div>

                <nav className="py-6 space-y-1">
                  {!isAdmin && menuItems.map((item) => {
                    const Icon = item.icon;
                    const isActive = location.pathname === item.path;
                    return (
                      <Link
                        key={item.name}
                        to={item.path}
                        onClick={() => setMobileMenuOpen(false)}
                        className={`flex items-center gap-3 px-4 py-3 rounded-xl font-medium text-sm transition-all duration-200 ${
                          isActive
                            ? "bg-brand-500 text-white"
                            : "text-slate-600 dark:text-slate-400 hover:bg-slate-100 dark:hover:bg-slate-800"
                        }`}
                      >
                        <Icon size={18} />
                        {item.name}
                      </Link>
                    );
                  })}

                  {/* Admin Navigation Section Mobile */}
                  {isAdmin && adminMenuItems.map((item) => {
                    const Icon = item.icon;
                    const isActive = location.pathname === item.path;
                    return (
                      <Link
                        key={item.name}
                        to={item.path}
                        onClick={() => setMobileMenuOpen(false)}
                        className={`flex items-center gap-3 px-4 py-3 rounded-xl font-medium text-sm transition-all duration-200 ${
                          isActive
                            ? "bg-emerald-600 text-white"
                            : "text-slate-600 dark:text-slate-400 hover:bg-slate-100 dark:hover:bg-slate-800"
                        }`}
                      >
                        <Icon size={18} />
                        {item.name}
                      </Link>
                    );
                  })}
                </nav>
              </div>

              <div className="pt-4 border-t border-slate-200 dark:border-slate-800 flex flex-col gap-3">
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    {user.picture ? (
                      <img src={user.picture} alt={user.name} className="w-8 h-8 rounded-full object-cover" />
                    ) : (
                      <div className="w-8 h-8 rounded-full bg-slate-200 dark:bg-slate-800 flex items-center justify-center text-slate-600 font-bold text-sm">
                        {user.name ? user.name.charAt(0).toUpperCase() : "U"}
                      </div>
                    )}
                    <div>
                      <p className="text-xs font-semibold text-slate-700 dark:text-slate-300">{user.name || "Default User"}</p>
                      <p className="text-[9px] text-slate-400">{user.email || "user@invoice.ai"}</p>
                    </div>
                  </div>
                </div>
                <button
                  onClick={handleLogout}
                  className="flex items-center justify-center gap-2 w-full px-4 py-2 mt-1 rounded-xl text-xs font-medium text-rose-600 hover:bg-rose-50 dark:hover:bg-rose-950/20 transition-all duration-200"
                >
                  <LogOut size={14} />
                  <span>Logout</span>
                </button>
              </div>
            </aside>
          </div>
        )}

        {/* Page Content Container */}
        <main className="flex-1 p-6 md:p-8 overflow-y-auto max-w-7xl w-full mx-auto">
          {children}
        </main>
        <ChatAssistant />
      </div>
    </div>
  );
};

export default Layout;
