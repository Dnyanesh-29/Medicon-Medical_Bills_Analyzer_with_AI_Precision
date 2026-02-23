# Medical Bill Analyzer - Frontend

A modern, high-performance web interface for the Medical Bill Analyzer, built with Next.js 14, Tailwind CSS, and Framer Motion.

## 🚀 Features

- **AI-Powered Analysis**: Upload bills (PDF/Image) for instant CGHS compliance checks.
- **Interactive Dashboard**: Visualize price deviations and violations with charts.
- **Hospital Search**: Find CGHS & NABH accredited hospitals with live search.
- **System Analytics**: Real-time stats on the CGHS database.
- **Responsive Design**: Works on desktop, tablet, and mobile with a sleek dark theme.

## 🛠️ Tech Stack

- **Framework**: [Next.js 14](https://nextjs.org/) (App Router)
- **Styling**: [Tailwind CSS](https://tailwindcss.com/) + Glassmorphism
- **Animations**: [Framer Motion](https://www.framer.com/motion/)
- **Charts**: [Recharts](https://recharts.org/)
- **Icons**: [Lucide React](https://lucide.dev/)
- **API Client**: [Axios](https://axios-http.com/)

## 🏁 Getting Started

### Prerequisites

- Node.js 18+ installed
- Backend server running on `http://localhost:8000`

### Installation

1. Navigate to the frontend directory:
   ```bash
   cd frontend
   ```

2. Install dependencies:
   ```bash
   npm install
   ```

3. Run the development server:
   ```bash
   npm run dev
   ```

4. Open [http://localhost:3000](http://localhost:3000) in your browser.

## 📂 Project Structure

- `src/app`: Page routes (Home, Upload, Hospitals, Analytics)
- `src/components`: Reusable UI components (Navbar, Hero, BillUploader, AnalysisResult)
- `src/lib`: API client and utilities
- `src/types`: TypeScript interfaces mirroring backend schemas

## 🎨 Design System

- **Primary**: Teal (`text-teal-500`)
- **Accent**: Emerald (`text-emerald-500`) for compliance/NABH
- **Danger**: Red (`text-red-500`) for high severity violations
- **Background**: Deep Slate (`bg-slate-950`) with gradients
