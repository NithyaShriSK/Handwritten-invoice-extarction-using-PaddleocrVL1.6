import React, { useState, useEffect } from "react";
import { toast } from "react-toastify";
import { api } from "../services/api";
import {
  Users,
  Shield,
  ShieldAlert,
  UserCheck,
  UserMinus,
  Ban,
  CheckCircle,
  Search,
  FileText,
  Percent,
  RefreshCw
} from "lucide-react";

const UserManagement = () => {
  const [users, setUsers] = useState([]);
  const [loading, setLoading] = useState(true);
  const [searchQuery, setSearchQuery] = useState("");
  const [actionLoadingId, setActionLoadingId] = useState(null);

  const fetchUsers = async () => {
    setLoading(true);
    try {
      const res = await api.adminGetUsers();
      if (res.success) {
        setUsers(res.data || []);
      } else {
        toast.error(res.message || "Failed to load users");
      }
    } catch (error) {
      console.error("Error loading users:", error);
      toast.error(error.response?.data?.message || "Failed to load users list.");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchUsers();
  }, []);

  const handleRoleToggle = async (userId, currentRole) => {
    const nextRole = currentRole === "admin" ? "user" : "admin";
    
    // Safety check: Don't accidentally demote yourself if you are the logged in admin
    const currentUser = JSON.parse(localStorage.getItem("user") || "{}");
    if (userId === currentUser.id && currentRole === "admin") {
      if (!window.confirm("WARNING: You are about to demote yourself from admin. You will lose access to this admin dashboard. Are you sure?")) {
        return;
      }
    }

    setActionLoadingId(userId);
    try {
      const res = await api.adminUpdateUserRole(userId, nextRole);
      if (res.success) {
        toast.success(`User role updated to ${nextRole}`);
        // If current user demoted themselves, refresh page
        if (userId === currentUser.id && nextRole === "user") {
          currentUser.role = "user";
          localStorage.setItem("user", JSON.stringify(currentUser));
          window.location.href = "/";
          return;
        }
        // Update local state
        setUsers(users.map(u => u.id === userId ? { ...u, role: nextRole } : u));
      } else {
        toast.error(res.message || "Failed to update user role");
      }
    } catch (error) {
      console.error("Error updating user role:", error);
      toast.error(error.response?.data?.message || "Failed to change user role.");
    } finally {
      setActionLoadingId(null);
    }
  };

  const handleStatusToggle = async (userId, currentStatus) => {
    const nextStatus = !currentStatus;
    
    // Safety check: Don't disable yourself
    const currentUser = JSON.parse(localStorage.getItem("user") || "{}");
    if (userId === currentUser.id && currentStatus) {
      toast.error("You cannot disable your own active administrator account.");
      return;
    }

    setActionLoadingId(userId);
    try {
      const res = await api.adminUpdateUserStatus(userId, nextStatus);
      if (res.success) {
        toast.success(`User account ${nextStatus ? "enabled" : "disabled"}`);
        setUsers(users.map(u => u.id === userId ? { ...u, is_active: nextStatus } : u));
      } else {
        toast.error(res.message || "Failed to update status");
      }
    } catch (error) {
      console.error("Error updating user status:", error);
      toast.error(error.response?.data?.message || "Failed to update account status.");
    } finally {
      setActionLoadingId(null);
    }
  };

  // Filter users based on search
  const filteredUsers = users.filter(
    u =>
      u.name.toLowerCase().includes(searchQuery.toLowerCase()) ||
      u.email.toLowerCase().includes(searchQuery.toLowerCase())
  );

  return (
    <div className="space-y-6">
      {/* Header section */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <h1 className="text-2xl md:text-3xl font-extrabold text-slate-900 dark:text-white flex items-center gap-3">
            <Users className="text-brand-500" />
            User Management
          </h1>
          <p className="text-slate-500 dark:text-slate-400 mt-1">
            Manage users, assign roles, toggle account status, and view individual correction statistics.
          </p>
        </div>

        <button
          onClick={fetchUsers}
          disabled={loading}
          className="flex items-center justify-center gap-2 px-4 py-2.5 bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-xl hover:bg-slate-50 dark:hover:bg-slate-800/80 text-sm font-medium text-slate-700 dark:text-slate-300 transition-colors shadow-sm disabled:opacity-50"
        >
          <RefreshCw size={16} className={loading ? "animate-spin" : ""} />
          <span>Refresh</span>
        </button>
      </div>

      {/* Stats Cards */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <div className="glass-card p-6 border border-slate-200 dark:border-slate-800 rounded-2xl flex items-center justify-between">
          <div>
            <span className="text-xs font-semibold text-slate-400 uppercase tracking-wider">Total Users</span>
            <h3 className="text-3xl font-extrabold text-slate-800 dark:text-white mt-1">{users.length}</h3>
          </div>
          <div className="p-3 bg-emerald-500/10 text-emerald-600 rounded-xl">
            <Users size={24} />
          </div>
        </div>

        <div className="glass-card p-6 border border-slate-200 dark:border-slate-800 rounded-2xl flex items-center justify-between">
          <div>
            <span className="text-xs font-semibold text-slate-400 uppercase tracking-wider">Active Admins</span>
            <h3 className="text-3xl font-extrabold text-slate-800 dark:text-white mt-1">
              {users.filter(u => u.role === "admin" && u.is_active).length}
            </h3>
          </div>
          <div className="p-3 bg-emerald-500/10 text-emerald-600 rounded-xl">
            <Shield size={24} />
          </div>
        </div>

        <div className="glass-card p-6 border border-slate-200 dark:border-slate-800 rounded-2xl flex items-center justify-between">
          <div>
            <span className="text-xs font-semibold text-slate-400 uppercase tracking-wider">Disabled Accounts</span>
            <h3 className="text-3xl font-extrabold text-slate-800 dark:text-white mt-1">
              {users.filter(u => !u.is_active).length}
            </h3>
          </div>
          <div className="p-3 bg-rose-500/10 text-rose-600 rounded-xl">
            <Ban size={24} />
          </div>
        </div>
      </div>

      {/* Control panel and Table */}
      <div className="glass-card border border-slate-200 dark:border-slate-800 rounded-2xl overflow-hidden">
        {/* Search bar */}
        <div className="p-5 border-b border-slate-200 dark:border-slate-800 flex items-center relative">
          <Search className="absolute left-9 text-slate-400 dark:text-slate-500" size={18} />
          <input
            type="text"
            placeholder="Search by name or email address..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className="w-full pl-11 pr-4 py-2.5 rounded-xl border border-slate-200 dark:border-slate-800 bg-slate-50/50 dark:bg-slate-900/50 text-sm placeholder-slate-400 dark:placeholder-slate-500 focus:outline-none focus:ring-1 focus:ring-brand-500 dark:focus:ring-brand-500 transition-all"
          />
        </div>

        {/* Table Content */}
        {loading ? (
          <div className="flex flex-col items-center justify-center py-20 space-y-4">
            <div className="w-10 h-10 border-4 border-brand-500 border-t-transparent rounded-full animate-spin"></div>
            <span className="text-sm text-slate-500 dark:text-slate-400 font-medium">Fetching users database...</span>
          </div>
        ) : filteredUsers.length === 0 ? (
          <div className="text-center py-20 text-slate-500 dark:text-slate-400">
            No users match your current search criteria.
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full border-collapse text-left">
              <thead>
                <tr className="bg-slate-50 dark:bg-slate-900/30 text-xs font-semibold text-slate-500 dark:text-slate-400 border-b border-slate-200 dark:border-slate-800 uppercase tracking-wider">
                  <th className="py-4 px-6">User Info</th>
                  <th className="py-4 px-6">Role</th>
                  <th className="py-4 px-6">Status</th>
                  <th className="py-4 px-6 text-center">Total Invoices</th>
                  <th className="py-4 px-6 text-center">Correction Rate</th>
                  <th className="py-4 px-6 text-center">Last Login</th>
                  <th className="py-4 px-6 text-right">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-200 dark:divide-slate-800/80">
                {filteredUsers.map((u) => {
                  const isPending = actionLoadingId === u.id;
                  return (
                    <tr
                      key={u.id}
                      className="hover:bg-slate-50/50 dark:hover:bg-slate-900/10 transition-colors text-slate-700 dark:text-slate-300 text-sm"
                    >
                      {/* User Info */}
                      <td className="py-4 px-6">
                        <div className="flex items-center gap-3">
                          {u.picture ? (
                            <img src={u.picture} alt={u.name} className="w-10 h-10 rounded-full object-cover border border-slate-200 dark:border-slate-800" />
                          ) : (
                            <div className="w-10 h-10 rounded-full bg-brand-500/10 text-brand-600 font-extrabold text-sm flex items-center justify-center">
                              {u.name.charAt(0).toUpperCase()}
                            </div>
                          )}
                          <div>
                            <p className="font-semibold text-slate-900 dark:text-white leading-tight">{u.name}</p>
                            <p className="text-xs text-slate-400 dark:text-slate-500 mt-0.5">{u.email}</p>
                          </div>
                        </div>
                      </td>

                      {/* Role */}
                      <td className="py-4 px-6">
                        <span className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-semibold ${
                          u.role === "admin"
                            ? "bg-emerald-50 dark:bg-emerald-950/40 text-emerald-600 dark:text-emerald-400 border border-emerald-200 dark:border-emerald-900/40"
                            : "bg-slate-100 dark:bg-slate-800 text-slate-600 dark:text-slate-400 border border-transparent"
                        }`}>
                          {u.role === "admin" ? <Shield size={12} /> : null}
                          {u.role}
                        </span>
                      </td>

                      {/* Status */}
                      <td className="py-4 px-6">
                        <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-md text-xs font-medium ${
                          u.is_active
                            ? "bg-emerald-50 dark:bg-emerald-950/30 text-emerald-600 dark:text-emerald-400"
                            : "bg-rose-50 dark:bg-rose-950/30 text-rose-600 dark:text-rose-400"
                        }`}>
                          {u.is_active ? <CheckCircle size={12} /> : <Ban size={12} />}
                          {u.is_active ? "Active" : "Disabled"}
                        </span>
                      </td>

                      {/* Total Invoices */}
                      <td className="py-4 px-6 text-center font-semibold text-slate-900 dark:text-white">
                        {u.total_invoices}
                      </td>

                      {/* Correction Rate */}
                      <td className="py-4 px-6 text-center">
                        <div className="flex items-center justify-center gap-1">
                          <span className={`font-semibold ${
                            u.correction_rate > 50
                              ? "text-amber-600 dark:text-amber-400"
                              : u.correction_rate > 20
                              ? "text-emerald-600 dark:text-emerald-400"
                              : "text-slate-600 dark:text-slate-400"
                          }`}>
                            {u.correction_rate}%
                          </span>
                          <span className="text-[10px] text-slate-400">({u.total_corrections}/{u.total_invoices})</span>
                        </div>
                      </td>

                      {/* Last Login */}
                      <td className="py-4 px-6 text-center text-xs text-slate-400">
                        {u.last_login ? new Date(u.last_login).toLocaleString() : "Never"}
                      </td>

                      {/* Actions */}
                      <td className="py-4 px-6 text-right">
                        <div className="flex items-center justify-end gap-2">
                          {/* Toggle Role Button */}
                          <button
                            onClick={() => handleRoleToggle(u.id, u.role)}
                            disabled={isPending}
                            className={`p-1.5 rounded-lg border text-xs font-semibold transition-all ${
                              u.role === "admin"
                                ? "bg-rose-50 dark:bg-rose-950/20 text-rose-600 border-rose-200 dark:border-rose-900/30 hover:bg-rose-100"
                                : "bg-emerald-50 dark:bg-emerald-950/20 text-emerald-600 border border-emerald-200 dark:border-emerald-900/30 hover:bg-emerald-100"
                            }`}
                            title={u.role === "admin" ? "Demote to User" : "Promote to Admin"}
                          >
                            {u.role === "admin" ? "Demote" : "Make Admin"}
                          </button>

                          {/* Toggle Status Button */}
                          <button
                            onClick={() => handleStatusToggle(u.id, u.is_active)}
                            disabled={isPending}
                            className={`p-1.5 rounded-lg border text-xs font-semibold transition-all ${
                              u.is_active
                                ? "bg-amber-50 dark:bg-amber-950/20 text-amber-600 border-amber-200 dark:border-amber-900/30 hover:bg-amber-100"
                                : "bg-emerald-50 dark:bg-emerald-950/20 text-emerald-600 border-emerald-200 dark:border-emerald-900/30 hover:bg-emerald-100"
                            }`}
                          >
                            {u.is_active ? "Block" : "Activate"}
                          </button>
                        </div>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
};

export default UserManagement;
