"use client";

import { useState, useEffect } from "react";
import { getStats } from "@/lib/api";
import { StatsResponse } from "@/types";
import { Loader2, Database, ShieldCheck, Activity, Server, FileCode2, Cpu } from "lucide-react";
import { PieChart, Pie, Cell, Tooltip, ResponsiveContainer } from "recharts";
import { motion } from "framer-motion";

export default function AnalyticsPage() {
    const [stats, setStats] = useState<StatsResponse | null>(null);
    const [loading, setLoading] = useState(true);

    useEffect(() => {
        async function loadStats() {
            try {
                const data = await getStats();
                setStats(data);
            } catch (error) {
                console.error("Failed to load stats:", error);
            } finally {
                setLoading(false);
            }
        }
        loadStats();
    }, []);

    if (loading) {
        return (
            <div className="flex h-[50vh] items-center justify-center">
                <Loader2 className="w-8 h-8 animate-spin text-teal-600" />
            </div>
        );
    }

    if (!stats) {
        return (
            <div className="text-center py-20">
                <div className="inline-flex p-4 rounded-full bg-red-50 text-red-500 mb-4">
                    <Server className="w-8 h-8" />
                </div>
                <h3 className="text-lg font-semibold text-slate-800">Connection Failed</h3>
                <p className="text-slate-500 mt-2">Failed to load statistics. Is the backend running?</p>
            </div>
        );
    }

    const pieData = [
        { name: "NABH Accredited", value: stats.hospitals.nabh, color: "#10b981" },
        { name: "Non-NABH", value: stats.hospitals.non_nabh, color: "#94a3b8" },
    ];

    const container = {
        hidden: { opacity: 0 },
        show: { opacity: 1, transition: { staggerChildren: 0.1 } }
    };

    const item = {
        hidden: { opacity: 0, y: 20 },
        show: { opacity: 1, y: 0 }
    };

    return (
        <div className="container mx-auto px-4 py-8 space-y-12 max-w-6xl">
            <div className="text-center space-y-4">
                <motion.h1
                    initial={{ opacity: 0, y: -20 }}
                    animate={{ opacity: 1, y: 0 }}
                    className="text-4xl font-bold text-slate-900 inline-block"
                >
                    System Analytics
                </motion.h1>
                <motion.p
                    initial={{ opacity: 0 }}
                    animate={{ opacity: 1 }}
                    transition={{ delay: 0.2 }}
                    className="text-slate-600 max-w-2xl mx-auto"
                >
                    Real-time overview of the CGHS database and system performance.
                </motion.p>
            </div>

            {/* KPI Cards */}
            <motion.div
                variants={container}
                initial="hidden"
                animate="show"
                className="grid grid-cols-1 md:grid-cols-3 gap-6"
            >
                <motion.div variants={item} className="bg-white p-6 rounded-xl border border-slate-200 shadow-sm hover:shadow-md transition-shadow flex items-center justify-between">
                    <div>
                        <p className="text-sm font-medium text-slate-500 uppercase tracking-wider">Total Hospitals</p>
                        <h3 className="text-4xl font-bold text-slate-900 mt-2">{stats.hospitals.total}</h3>
                    </div>
                    <div className="p-4 bg-teal-50 rounded-lg">
                        <Database className="w-8 h-8 text-teal-600" />
                    </div>
                </motion.div>

                <motion.div variants={item} className="bg-white p-6 rounded-xl border border-slate-200 shadow-sm hover:shadow-md transition-shadow flex items-center justify-between">
                    <div>
                        <p className="text-sm font-medium text-slate-500 uppercase tracking-wider">NABH Accredited</p>
                        <h3 className="text-4xl font-bold text-emerald-600 mt-2">{stats.hospitals.nabh}</h3>
                    </div>
                    <div className="p-4 bg-emerald-50 rounded-lg">
                        <ShieldCheck className="w-8 h-8 text-emerald-600" />
                    </div>
                </motion.div>

                <motion.div variants={item} className="bg-white p-6 rounded-xl border border-slate-200 shadow-sm hover:shadow-md transition-shadow flex items-center justify-between">
                    <div>
                        <p className="text-sm font-medium text-slate-500 uppercase tracking-wider">Total Procedures</p>
                        <h3 className="text-4xl font-bold text-indigo-600 mt-2">{stats.procedures.total.toLocaleString()}</h3>
                    </div>
                    <div className="p-4 bg-indigo-50 rounded-lg">
                        <Activity className="w-8 h-8 text-indigo-600" />
                    </div>
                </motion.div>
            </motion.div>

            {/* Charts Section */}
            <motion.div
                initial={{ opacity: 0, y: 20 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ delay: 0.4 }}
                className="grid grid-cols-1 md:grid-cols-2 gap-8"
            >
                {/* Chart Card */}
                <div className="bg-white p-8 rounded-xl border border-slate-200 shadow-sm flex flex-col items-center">
                    <h3 className="text-lg font-semibold text-slate-800 mb-6 w-full text-left">Accreditation Distribution</h3>
                    <div className="h-[300px] w-full relative">
                        <ResponsiveContainer width="100%" height="100%">
                            <PieChart>
                                <Pie
                                    data={pieData}
                                    cx="50%"
                                    cy="50%"
                                    innerRadius={80}
                                    outerRadius={110}
                                    paddingAngle={5}
                                    dataKey="value"
                                >
                                    {pieData.map((entry, index) => (
                                        <Cell key={`cell-${index}`} fill={entry.color} stroke="none" />
                                    ))}
                                </Pie>
                                <Tooltip
                                    contentStyle={{ backgroundColor: '#ffffff', border: '1px solid #e2e8f0', borderRadius: '8px', boxShadow: '0 4px 6px -1px rgb(0 0 0 / 0.1)' }}
                                    itemStyle={{ color: '#1e293b' }}
                                />
                            </PieChart>
                        </ResponsiveContainer>
                        {/* Legend Overlay */}
                        <div className="absolute top-1/2 left-1/2 transform -translate-x-1/2 -translate-y-1/2 text-center pointer-events-none">
                            <span className="text-3xl font-bold text-slate-800">
                                {Math.round((stats.hospitals.nabh / stats.hospitals.total) * 100)}%
                            </span>
                            <p className="text-xs text-slate-500 uppercase font-semibold mt-1">NABH Rate</p>
                        </div>
                    </div>
                    <div className="flex gap-8 mt-6">
                        {pieData.map((entry, i) => (
                            <div key={i} className="flex items-center gap-2">
                                <div className="w-3 h-3 rounded-full" style={{ backgroundColor: entry.color }} />
                                <span className="text-sm font-medium text-slate-600">{entry.name}</span>
                            </div>
                        ))}
                    </div>
                </div>

                {/* System Health Card */}
                <div className="bg-white p-8 rounded-xl border border-slate-200 shadow-sm">
                    <h3 className="text-lg font-semibold text-slate-800 mb-8">System Health</h3>

                    <div className="space-y-8">
                        <div className="space-y-3">
                            <div className="flex justify-between text-sm">
                                <span className="text-slate-600 font-medium">Database Integrity</span>
                                <span className="text-emerald-600 font-bold bg-emerald-50 px-2 py-0.5 rounded text-xs uppercase">Healthy</span>
                            </div>
                            <div className="h-2 bg-slate-100 rounded-full overflow-hidden">
                                <div className="h-full bg-emerald-500 w-full animate-pulse"></div>
                            </div>
                        </div>

                        <div className="space-y-3">
                            <div className="flex justify-between text-sm">
                                <span className="text-slate-600 font-medium">Matching Algorithm</span>
                                <span className="text-teal-600 font-bold bg-teal-50 px-2 py-0.5 rounded text-xs uppercase">{stats.matching_method}</span>
                            </div>
                            <div className="h-2 bg-slate-100 rounded-full overflow-hidden">
                                <div className="h-full bg-teal-500 w-3/4"></div>
                            </div>
                        </div>

                        <div className="p-6 bg-slate-50 rounded-xl border border-slate-200 mt-6">
                            <div className="flex items-center gap-2 mb-4">
                                <Cpu className="w-5 h-5 text-slate-500" />
                                <h4 className="font-semibold text-slate-700">Technical Details</h4>
                            </div>
                            <ul className="grid grid-cols-2 gap-y-4 gap-x-2">
                                <li className="flex items-center gap-2 text-sm text-slate-600">
                                    <Server className="w-4 h-4 text-slate-400" />
                                    FastAPI Backend
                                </li>
                                <li className="flex items-center gap-2 text-sm text-slate-600">
                                    <FileCode2 className="w-4 h-4 text-slate-400" />
                                    Next.js 14 Frontend
                                </li>
                                <li className="flex items-center gap-2 text-sm text-slate-600">
                                    <div className="w-4 h-4 rounded bg-slate-200 flex items-center justify-center text-[10px] font-bold text-slate-500">AI</div>
                                    Google Gemini
                                </li>
                                <li className="flex items-center gap-2 text-sm text-slate-600">
                                    <div className="w-4 h-4 rounded bg-slate-200 flex items-center justify-center text-[10px] font-bold text-slate-500">ML</div>
                                    Semantic Search
                                </li>
                            </ul>
                        </div>
                    </div>
                </div>
            </motion.div>
        </div>
    );
}
