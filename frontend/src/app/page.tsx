"use client";

import Hero from "@/components/Hero";
import { motion } from "framer-motion";
import { CheckCircle, XCircle, Upload, ScanLine, FileBarChart, ArrowRight, Shield, Zap, Lock } from "lucide-react";
import Link from "next/link";

const fadeIn = {
  hidden: { opacity: 0, y: 40 },
  visible: { opacity: 1, y: 0, transition: { duration: 0.8, ease: "easeOut" } }
};

const features = [
  {
    title: "100+ Procedures",
    description: "Comprehensive CGHS rate database covering all major medical procedures and specialties.",
    icon: <Shield className="w-6 h-6 text-emerald-600" />
  },
  {
    title: "Instant Analysis",
    description: "Process complex 50-page bills in under 5 seconds with our optimized pipeline.",
    icon: <Zap className="w-6 h-6 text-teal-600" />
  },
  {
    title: "Bank-Grade Security",
    description: "Your data is encrypted at rest and in transit. We prioritize patient privacy.",
    icon: <Lock className="w-6 h-6 text-teal-600" />
  }
];

export default function Home() {
  return (
    <div className="flex flex-col min-h-screen bg-white w-full">
      <Hero />

      {/* Trust Strip */}
      <div className="w-full bg-slate-50 border-y border-slate-200 py-12">
        <div className="container mx-auto px-6">
          <p className="text-center text-sm font-semibold text-slate-400 uppercase tracking-widest mb-8">Trusted Standards & Compliance</p>
          <div className="flex flex-wrap justify-center gap-12 md:gap-24 opacity-60 hover:opacity-100 transition-opacity duration-500">
            {["CGHS Empanelled", "NABH Accredited"].map((standard, i) => (
              <span key={i} className="text-xl md:text-2xl font-bold text-slate-800 flex items-center gap-2">
                <Shield className="w-6 h-6" /> {standard}
              </span>
            ))}
          </div>
        </div>
      </div>

      {/* Problem vs Solution Section */}
      <section className="py-24 bg-white relative overflow-hidden">
        <div className="container mx-auto px-6 relative z-10">
          <motion.div
            initial="hidden"
            whileInView="visible"
            viewport={{ once: true, margin: "-100px" }}
            variants={fadeIn}
            className="text-center max-w-3xl mx-auto mb-16"
          >
            <h2 className="text-3xl md:text-5xl font-bold text-slate-900 mb-6">Why Automate Medical Audits?</h2>
            <p className="text-lg text-slate-600 leading-relaxed">
              Manual verification is prone to errors and takes hours. Medicon revolutionizes the process with effortless precision.
            </p>
          </motion.div>

          <div className="grid md:grid-cols-2 gap-12">
            {/* The Old Way */}
            <motion.div
              initial={{ opacity: 0, x: -50 }}
              whileInView={{ opacity: 1, x: 0 }}
              viewport={{ once: true }}
              transition={{ duration: 0.6 }}
              className="p-8 rounded-3xl bg-slate-50 border border-slate-100"
            >
              <h3 className="text-xl font-bold text-slate-500 mb-6 flex items-center gap-2">
                <span className="p-2 rounded-full bg-slate-200"><XCircle className="w-5 h-5 text-slate-600" /></span>
                Manual Processing
              </h3>
              <ul className="space-y-4">
                {["Hours spent on a single bill", "Missed rate discrepancies", "Human calculation errors", "Inconsistent policy application"].map((item, i) => (
                  <li key={i} className="flex items-center gap-3 text-slate-500">
                    <XCircle className="w-5 h-5 text-red-300 flex-shrink-0" />
                    {item}
                  </li>
                ))}
              </ul>
            </motion.div>

            {/* The Medicon Way */}
            <motion.div
              initial={{ opacity: 0, x: 50 }}
              whileInView={{ opacity: 1, x: 0 }}
              viewport={{ once: true }}
              transition={{ duration: 0.6 }}
              className="p-8 rounded-3xl bg-teal-50 border border-teal-100 shadow-xl shadow-teal-500/10 relative overflow-hidden"
            >
              <div className="absolute top-0 right-0 w-32 h-32 bg-teal-400/10 rounded-full blur-3xl -mr-10 -mt-10"></div>
              <h3 className="text-xl font-bold text-teal-900 mb-6 flex items-center gap-2">
                <span className="p-2 rounded-full bg-teal-200"><CheckCircle className="w-5 h-5 text-teal-700" /></span>
                Medicon AI
              </h3>
              <ul className="space-y-4 relative z-10">
                {["Results in < 5 seconds", "Exact CGHS rate matching", "100% Calculation accuracy", "Automated violation flagging"].map((item, i) => (
                  <li key={i} className="flex items-center gap-3 text-teal-800 font-medium">
                    <CheckCircle className="w-5 h-5 text-teal-500 flex-shrink-0" />
                    {item}
                  </li>
                ))}
              </ul>
            </motion.div>
          </div>
        </div>
      </section>

      {/* Workflow Section */}
      <section className="py-24 bg-slate-900 text-white relative overflow-hidden">
        <div className="absolute inset-0 bg-[url('/grid.svg')] opacity-10"></div>
        <div className="container mx-auto px-6 relative z-10">
          <motion.div
            initial="hidden"
            whileInView="visible"
            viewport={{ once: true }}
            variants={fadeIn}
            className="text-center mb-20"
          >
            <h2 className="text-3xl md:text-5xl font-bold mb-6">How It Works</h2>
            <p className="text-slate-400 max-w-2xl mx-auto">Three simple steps to complete audit compliance.</p>
          </motion.div>

          <div className="grid md:grid-cols-3 gap-12 relative">
            <div className="hidden md:block absolute top-12 left-[16%] right-[16%] h-0.5 bg-gradient-to-r from-slate-700 via-teal-500 to-slate-700 z-0"></div>

            {[
              { title: "Upload Bill", icon: <Upload className="w-8 h-8" />, desc: "Upload PDF or Image of the medical bill." },
              { title: "AI Extraction", icon: <ScanLine className="w-8 h-8" />, desc: "Our engine extracts line items and dates." },
              { title: "Get Report", icon: <FileBarChart className="w-8 h-8" />, desc: "Receive a detailed compliance report." }
            ].map((step, i) => (
              <motion.div
                key={i}
                initial={{ opacity: 0, y: 30 }}
                whileInView={{ opacity: 1, y: 0 }}
                viewport={{ once: true }}
                transition={{ delay: i * 0.2 }}
                className="relative z-10 flex flex-col items-center text-center group"
              >
                <div className="w-24 h-24 rounded-2xl bg-slate-800 border border-slate-700 flex items-center justify-center mb-8 group-hover:scale-110 group-hover:bg-teal-600 group-hover:border-teal-500 transition-all duration-300 shadow-2xl">
                  {step.icon}
                </div>
                <h3 className="text-xl font-bold mb-3">{step.title}</h3>
                <p className="text-slate-400 px-8">{step.desc}</p>
              </motion.div>
            ))}
          </div>
        </div>
      </section>

      {/* Final CTA */}
      <section className="py-24 bg-white">
        <div className="container mx-auto px-6">
          <div className="rounded-[2.5rem] bg-gradient-to-br from-teal-600 to-teal-800 p-12 md:p-24 text-center relative overflow-hidden shadow-2xl shadow-teal-900/20">
            <motion.div
              initial={{ scale: 0.9, opacity: 0 }}
              whileInView={{ scale: 1, opacity: 1 }}
              viewport={{ once: true }}
              transition={{ duration: 0.5 }}
              className="relative z-10"
            >
              <h2 className="text-3xl md:text-5xl font-bold text-white mb-8 tracking-tight">Ready to streamline your audits?</h2>
              <p className="text-teal-100 text-lg md:text-xl max-w-2xl mx-auto mb-10">Start saving costs and ensuring compliance today with our advanced AI analysis tool.</p>
              <div className="flex flex-col sm:flex-row gap-4 justify-center">
                <Link href="/upload" className="px-8 py-4 bg-white text-teal-700 font-bold rounded-xl hover:bg-slate-100 transition-all flex items-center justify-center gap-2">
                  <Upload className="w-5 h-5" /> Start Analysis
                </Link>
                <Link href="/analytics" className="px-8 py-4 bg-white/20 border border-white/20 text-white font-bold rounded-xl hover:bg-white/30 transition-all flex items-center justify-center gap-2 backdrop-blur-sm">
                  View Analytics <ArrowRight className="w-5 h-5" />
                </Link>
              </div>
            </motion.div>
          </div>
        </div>
      </section>
    </div>
  );
}
