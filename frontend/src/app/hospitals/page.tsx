 "use client";

import { useState, useEffect } from "react";
import { Search, MapPin, Phone, Hospital, Loader2, CheckCircle, AlertTriangle, Building2, Compass } from "lucide-react";
import { searchHospitals } from "@/lib/api";
import { Hospital as HospitalType, HospitalSearchResponse } from "@/types";
import { cn } from "@/lib/utils";
import { motion, AnimatePresence } from "framer-motion";

export default function HospitalsPage() {
    const [query, setQuery] = useState("");
    const [nabhOnly, setNabhOnly] = useState(false);
    const [loading, setLoading] = useState(false);
    const [results, setResults] = useState<HospitalSearchResponse | null>(null);

    const handleSearch = async () => {
        setLoading(true);
        try {
            const data = await searchHospitals({
                name_query: query,
                nabh_only: nabhOnly
            });
            setResults(data);
        } catch (error) {
            console.error("Search failed:", error);
        } finally {
            setLoading(false);
        }
    };

    // Initial load
    useEffect(() => {
        handleSearch();
    }, []); // Run once on mount

    return (
        <div className="container mx-auto px-4 py-10 space-y-8 max-w-6xl">
            <div className="text-center space-y-4">
                <div className="inline-flex items-center space-x-2 bg-teal-50 border border-teal-100 rounded-full px-4 py-1.5">
                    <span className="flex h-2 w-2 relative">
                        <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-teal-400 opacity-75"></span>
                        <span className="relative inline-flex rounded-full h-2 w-2 bg-teal-600"></span>
                    </span>
                    <span className="text-sm font-semibold text-teal-700">CGHS Hospital Directory</span>
                </div>
                <h1 className="text-4xl md:text-5xl font-bold text-slate-900 tracking-tight">
                    Find the right <span className="text-teal-600">hospital</span> for you
                </h1>
                <p className="text-slate-600 text-lg max-w-2xl mx-auto">
                    Search CGHS-empanelled hospitals, filter by NABH accreditation, and quickly find contact details for your next visit.
                </p>
            </div>

            {/* Search & Filters */}
            <div className="max-w-4xl mx-auto">
                <div className="bg-white/80 backdrop-blur-sm border border-slate-200/80 shadow-lg rounded-2xl p-5 md:p-6 space-y-4">
                    <div className="flex flex-col md:flex-row gap-4 items-center">
                        <div className="relative flex-1 w-full group">
                            <Search className="absolute left-4 top-1/2 -translate-y-1/2 w-5 h-5 text-slate-400 group-focus-within:text-teal-500 transition-colors" />
                            <input
                                type="text"
                                placeholder="Search hospital name..."
                                className="w-full pl-12 pr-4 py-4 bg-white border border-slate-200 rounded-xl focus:ring-2 focus:ring-teal-500 focus:border-transparent outline-none text-slate-900 placeholder:text-slate-400 transition-all font-medium shadow-sm hover:border-teal-300"
                                value={query}
                                onChange={(e) => setQuery(e.target.value)}
                                onKeyDown={(e) => e.key === "Enter" && handleSearch()}
                            />
                        </div>
                        <div className="flex items-center gap-3 w-full md:w-auto">
                            <button
                                type="button"
                                onClick={() => setNabhOnly((prev) => !prev)}
                                className={cn(
                                    "relative inline-flex items-center gap-3 cursor-pointer select-none px-5 py-3 rounded-2xl border text-sm font-medium transition-all shadow-sm flex-1 md:flex-none justify-center",
                                    nabhOnly
                                        ? "bg-emerald-50 border-emerald-200 text-emerald-800"
                                        : "bg-white border-slate-200 text-slate-700 hover:bg-slate-50 hover:border-teal-300"
                                )}
                            >
                                <span
                                    className={cn(
                                        "inline-flex items-center justify-center w-8 h-8 rounded-full text-xs font-semibold border",
                                        nabhOnly
                                            ? "bg-emerald-600 text-white border-emerald-600"
                                            : "bg-slate-100 text-slate-600 border-slate-200"
                                    )}
                                >
                                    NABH
                                </span>
                                <span>NABH accredited only</span>
                            </button>
                            <button
                                onClick={handleSearch}
                                disabled={loading}
                                className="bg-teal-600 hover:bg-teal-700 text-white px-7 md:px-8 py-3.5 rounded-xl font-bold transition-all flex items-center gap-2 disabled:opacity-70 disabled:cursor-not-allowed shadow-md hover:shadow-lg active:scale-95 whitespace-nowrap"
                            >
                                {loading ? (
                                    <>
                                        <Loader2 className="w-5 h-5 animate-spin" />
                                        <span>Searching...</span>
                                    </>
                                ) : (
                                    <>
                                        <Search className="w-5 h-5" />
                                        <span>Search</span>
                                    </>
                                )}
                            </button>
                        </div>
                    </div>
                    <div className="flex flex-wrap items-center justify-between gap-3 text-xs text-slate-500">
                        <span>
                            Press <span className="font-semibold text-slate-700">Enter</span> to search, or refine using filters.
                        </span>
                        {results && (
                            <span className="inline-flex items-center gap-1 rounded-full bg-slate-50 px-3 py-1 border border-slate-200">
                                <span className="h-1.5 w-1.5 rounded-full bg-emerald-500" />
                                Showing{" "}
                                <span className="font-semibold text-slate-800">
                                    {results.hospitals.length}
                                </span>{" "}
                                of{" "}
                                <span className="font-semibold text-slate-800">
                                    {results.total_count}
                                </span>{" "}
                                hospitals
                            </span>
                        )}
                    </div>
                </div>
            </div>

            {/* Stats */}
            {results && (
                <motion.div
                    initial={{ opacity: 0, y: 10 }}
                    animate={{ opacity: 1, y: 0 }}
                    className="grid grid-cols-1 sm:grid-cols-3 gap-4 max-w-4xl mx-auto"
                >
                    <div className="bg-white p-4 rounded-xl border border-slate-200 shadow-sm flex items-center gap-3">
                        <div className="p-3 rounded-lg bg-slate-50 text-teal-600">
                            <Building2 className="w-5 h-5" />
                        </div>
                        <div>
                            <span className="text-xs uppercase text-slate-500 font-bold tracking-wider">Total Hospitals</span>
                            <p className="text-2xl font-bold text-slate-900 mt-1">{results.total_count}</p>
                        </div>
                    </div>
                    <div className="bg-emerald-50 p-4 rounded-xl border border-emerald-100 shadow-sm flex items-center gap-3">
                        <div className="p-3 rounded-lg bg-emerald-100 text-emerald-700">
                            <CheckCircle className="w-5 h-5" />
                        </div>
                        <div>
                            <span className="text-xs uppercase text-emerald-700 font-bold tracking-wider">NABH Accredited</span>
                            <p className="text-2xl font-bold text-emerald-800 mt-1">{results.nabh_count}</p>
                        </div>
                    </div>
                    <div className="bg-white p-4 rounded-xl border border-slate-200 shadow-sm flex items-center gap-3">
                        <div className="p-3 rounded-lg bg-slate-100 text-amber-600">
                            <AlertTriangle className="w-5 h-5" />
                        </div>
                        <div>
                            <span className="text-xs uppercase text-slate-500 font-bold tracking-wider">Non-NABH</span>
                            <p className="text-2xl font-bold text-slate-500 mt-1">{results.non_nabh_count}</p>
                        </div>
                    </div>
                </motion.div>
            )}

            {/* Loading skeleton for initial search */}
            {loading && !results && (
                <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
                    {[...Array(6)].map((_, idx) => (
                        <div
                            key={idx}
                            className="bg-white p-6 rounded-xl border border-slate-200 shadow-sm animate-pulse space-y-4"
                        >
                            <div className="h-4 w-32 bg-slate-100 rounded" />
                            <div className="h-3 w-full bg-slate-100 rounded" />
                            <div className="h-3 w-5/6 bg-slate-100 rounded" />
                            <div className="h-3 w-1/2 bg-slate-100 rounded" />
                        </div>
                    ))}
                </div>
            )}

            {/* Results List */}
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
                <AnimatePresence mode="popLayout">
                    {results?.hospitals.map((hospital, index) => (
                        <motion.div
                            key={hospital.sr_no || index}
                            initial={{ opacity: 0, scale: 0.95 }}
                            animate={{ opacity: 1, scale: 1 }}
                            exit={{ opacity: 0, scale: 0.95 }}
                            transition={{ delay: index * 0.05 }}
                            className="bg-white p-6 rounded-xl border border-slate-200 shadow-sm hover:shadow-md hover:border-teal-200 transition-all group flex flex-col h-full"
                        >
                            <div className="flex justify-between items-start mb-4">
                                <div className="p-3 bg-teal-50 text-teal-600 rounded-lg group-hover:bg-teal-600 group-hover:text-white transition-colors">
                                    <Hospital className="w-6 h-6" />
                                </div>
                                {hospital.nabh_status === "NABH/ NABL" ? (
                                    <span className="flex items-center gap-1.5 text-[10px] font-bold text-emerald-700 bg-emerald-50 px-2.5 py-1 rounded-full border border-emerald-100 uppercase tracking-wide">
                                        <CheckCircle className="w-3 h-3" /> NABH
                                    </span>
                                ) : (
                                    <span className="flex items-center gap-1.5 text-[10px] font-bold text-slate-500 bg-slate-100 px-2.5 py-1 rounded-full border border-slate-200 uppercase tracking-wide">
                                        <AlertTriangle className="w-3 h-3" /> Standard
                                    </span>
                                )}
                            </div>

                            <h3 className="font-bold text-lg text-slate-900 mb-3 line-clamp-2 min-h-[3.5rem] leading-tight">
                                {hospital.hospital_name}
                            </h3>

                            <div className="space-y-3 text-sm text-slate-600 mt-auto">
                                <div className="flex items-start gap-2.5">
                                    <MapPin className="w-4 h-4 text-slate-400 mt-0.5 flex-shrink-0" />
                                    <p className="line-clamp-2 leading-relaxed">{hospital.address}</p>
                                </div>
                                <div className="flex items-center gap-2.5 pt-2 border-t border-slate-100">
                                    <Phone className="w-4 h-4 text-slate-400 flex-shrink-0" />
                                    <p className="font-medium text-slate-700">
                                        {hospital.contact_no || "Contact number unavailable"}
                                    </p>
                                </div>
                                {typeof hospital.distance_km === "number" && (
                                    <div className="flex items-center gap-2 pt-1 text-xs text-slate-500">
                                        <Compass className="w-3.5 h-3.5 text-teal-500" />
                                        <span>{hospital.distance_km.toFixed(1)} km away (approx.)</span>
                                    </div>
                                )}
                            </div>
                        </motion.div>
                    ))}
                </AnimatePresence>
            </div>

            {results?.hospitals.length === 0 && !loading && (
                <div className="text-center py-20">
                    <div className="w-20 h-20 bg-slate-50 rounded-full flex items-center justify-center mx-auto mb-6">
                        <Search className="w-8 h-8 text-slate-300" />
                    </div>
                    <h3 className="text-xl font-semibold text-slate-900">No hospitals found</h3>
                    <p className="text-slate-500 mt-2">Try adjusting your search terms or filters.</p>
                </div>
            )}
        </div>
    );
}
