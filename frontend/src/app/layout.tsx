import type { Metadata } from "next";
import { Plus_Jakarta_Sans } from "next/font/google";
import "./globals.css";
import Navbar from "@/components/Navbar";
import { Toaster } from "sonner";

const plusJakarta = Plus_Jakarta_Sans({
  subsets: ["latin"],
  variable: "--font-sans",
  display: "swap",
});

export const metadata: Metadata = {
  title: "Medicon Analyzer",
  description: "AI-powered medical bill analysis for CGHS compliance",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en" className={plusJakarta.variable}>
      <body className="antialiased">
        <Navbar />
        <main className="min-h-screen bg-[#fafaf9] text-stone-900 antialiased flex flex-col items-center pt-24 pb-12 transition-colors duration-300">
          {children}
        </main>
        <footer className="w-full py-6 text-center text-stone-400 text-sm bg-[#fafaf9] border-t border-stone-200">
          <div className="container mx-auto">
            <p>© {new Date().getFullYear()} Medicon. AI-Powered Medical Audit System.</p>
          </div>
        </footer>
        <Toaster richColors theme="light" position="top-center" />
      </body>
    </html>
  );
}
