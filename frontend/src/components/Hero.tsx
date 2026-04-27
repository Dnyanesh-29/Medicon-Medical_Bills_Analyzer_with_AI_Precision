"use client";

import Link from "next/link";
import { UploadCloud, FileText, Search, Activity, ShieldCheck, Zap } from "lucide-react";
import { motion } from "framer-motion";

const features = [
    {
        title: "AI Analysis",
        description: "Advanced semantic engine detects anomalies in billing line items instantly.",
        icon: <Zap className="w-6 h-6 text-cyan-400" />,
    },
    {
        title: "CGHS Compliance",
        description: "Auto-verify rates against the latest CGHS rate list for your city.",
        icon: <ShieldCheck className="w-6 h-6 text-indigo-400" />,
    },
    {
        title: "Fraud Detection",
        description: "Identify duplicate charges, unbundled procedures, and hidden costs.",
        icon: <Search className="w-6 h-6 text-pink-400" />,
    },
];

const container = {
    hidden: { opacity: 0 },
    show: {
        opacity: 1,
        transition: {
            staggerChildren: 0.1
        }
    }
};

const item = {
    hidden: { opacity: 0, y: 20 },
    show: { opacity: 1, y: 0 }
};

export default function Hero() {
    return (
        <div className="relative min-h-[85vh] flex items-center justify-center overflow-hidden bg-slate-50">
            {/* Background Pattern */}
            <div className="absolute inset-0 z-0 opacity-[0.03] bg-[url('/grid.svg')] bg-center pointer-events-none" />

            <div className="container mx-auto px-6 relative z-10">
                <div className="grid lg:grid-cols-2 gap-16 items-center">

                    {/* Left Column: Text Content */}
                    <motion.div
                        variants={container}
                        initial="hidden"
                        animate="show"
                        className="space-y-8 text-center lg:text-left"
                    >
                        <motion.div variants={item} className="inline-flex items-center space-x-2 bg-teal-50 border border-teal-100 rounded-full px-4 py-1.5">
                            <span className="flex h-2 w-2 relative">
                                <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-teal-400 opacity-75"></span>
                                <span className="relative inline-flex rounded-full h-2 w-2 bg-teal-600"></span>
                            </span>
                            <span className="text-sm font-semibold text-teal-700">System v3.1 Online</span>
                        </motion.div>

                        <motion.h1 variants={item} className="text-5xl lg:text-6xl font-bold tracking-tight text-slate-900 leading-[1.1]">
                            Analyze Medical Bills with <span className="text-teal-600">AI Precision</span>
                        </motion.h1>

                        <motion.p variants={item} className="text-xl text-slate-600 max-w-2xl mx-auto lg:mx-0 leading-relaxed">
                            Ensure fair pricing and compliance with CGHS standards. Detect billing anomalies instantly with our advanced semantic analysis engine.
                        </motion.p>

                        <motion.div variants={item} className="flex flex-col sm:flex-row gap-4 justify-center lg:justify-start">
                            <Link href="/upload" className="group relative px-8 py-4 bg-teal-600 hover:bg-teal-700 text-white font-bold rounded-xl transition-all shadow-lg hover:shadow-teal-200">
                                <span className="relative z-10 flex items-center gap-2">
                                    <UploadCloud className="w-5 h-5" />
                                    Analyze Now
                                </span>
                            </Link>
                            <Link href="/hospitals" className="px-8 py-4 bg-white hover:bg-slate-50 text-slate-700 font-semibold rounded-xl border border-slate-200 hover:border-slate-300 transition-all shadow-sm">
                                Find Hospitals
                            </Link>
                        </motion.div>

                        
                    </motion.div>

                    {/* Right Column: Visual Features */}
                    <motion.div
                        initial={{ opacity: 0, x: 50 }}
                        animate={{ opacity: 1, x: 0 }}
                        transition={{ delay: 0.5, duration: 0.8 }}
                        className="relative hidden lg:block"
                    >

                        <div className="grid gap-6 relative z-10">
                            {features.map((feature, idx) => (
                                <motion.div
                                    key={feature.title}
                                    initial={{ opacity: 0, x: 20 }}
                                    animate={{ opacity: 1, x: 0 }}
                                    transition={{ delay: 0.8 + (idx * 0.1) }}
                                    whileHover={{ scale: 1.02 }}
                                    className="p-6 rounded-2xl bg-white border border-slate-200 shadow-sm hover:shadow-md transition-all group"
                                >
                                    <div className="flex items-start gap-4">
                                        <div className="p-3 rounded-lg bg-slate-100 text-teal-600 group-hover:bg-teal-600 group-hover:text-white transition-colors">
                                            {feature.icon}
                                        </div>
                                        <div>
                                            <h3 className="font-bold text-lg text-slate-900">{feature.title}</h3>
                                            <p className="text-slate-500 text-sm mt-1 leading-relaxed">{feature.description}</p>
                                        </div>
                                    </div>
                                </motion.div>
                            ))}

                            {/* Live Scanner Card - Clean Version */}
                            {/* <motion.div
                                animate={{ y: [0, -10, 0] }}
                                transition={{ duration: 4, repeat: Infinity, ease: "easeInOut" }}
                                className="absolute -right-8 top-1/2 -translate-y-1/2 p-5 rounded-xl bg-white border border-slate-200 shadow-xl w-72 z-20"
                            >
                                <div className="flex items-center gap-3 mb-4 border-b border-slate-100 pb-3">
                                    <Activity className="w-5 h-5 text-emerald-500" />
                                    <span className="font-semibold text-sm text-slate-700">System Status</span>
                                    <span className="ml-auto flex h-2 w-2 rounded-full bg-emerald-500"></span>
                                </div>
                                <div className="space-y-3">
                                    <div className="h-2 bg-slate-100 rounded-full overflow-hidden">
                                        <motion.div
                                            className="h-full bg-emerald-500"
                                            animate={{ width: ["0%", "100%"] }}
                                            transition={{ duration: 2, repeat: Infinity }}
                                        />
                                    </div>
                                    <div className="flex justify-between text-xs font-medium text-slate-500 uppercase tracking-wide">
                                        <span>Engine Active</span>
                                        <span className="text-emerald-600">Ready</span>
                                    </div>
                                </div>
                            </motion.div> */}
                        </div>
                    </motion.div>
                </div>
            </div>
        </div>
    );
}
