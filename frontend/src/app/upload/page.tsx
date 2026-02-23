"use client";

import { useState } from "react";
import BillUploader from "@/components/BillUploader";
import AnalysisResult from "@/components/AnalysisResult";
import { uploadAndAnalyzeBill } from "@/lib/api";
import { BillData, BillAnalysisResult } from "@/types";

export default function UploadPage() {
    const [isUploading, setIsUploading] = useState(false);
    const [result, setResult] = useState<{
        billData: BillData;
        analysis: BillAnalysisResult;
    } | null>(null);

    const handleUpload = async (file: File) => {
        setIsUploading(true);
        setResult(null);
        try {
            const response = await uploadAndAnalyzeBill(file);
            if (response.success) {
                setResult({
                    billData: response.extracted_bill_data,
                    analysis: response.analysis,
                });
            } else {
                console.error("Analysis failed:", response);
            }
        } catch (error) {
            console.error("Upload error:", error);
        } finally {
            setIsUploading(false);
        }
    };

    return (
        <div className="container mx-auto px-4 py-12 sm:py-16 space-y-12 max-w-7xl">
            <div className="max-w-2xl mx-auto space-y-12">
                <div className="text-center space-y-3">
                    <h1 className="text-2xl sm:text-3xl font-semibold text-stone-800 tracking-tight">
                        Check your medical bill
                    </h1>
                    <p className="text-stone-600 text-base max-w-md mx-auto leading-relaxed">
                        Upload a PDF or photo of your bill. We’ll compare it with CGHS rates and point out anything that looks off.
                    </p>
                </div>

                <div className="flex justify-center">
                    <BillUploader onUpload={handleUpload} isUploading={isUploading} />
                </div>
            </div>

            {result && (
                <div className="mt-16 pt-12 border-t border-stone-200">
                    <AnalysisResult billData={result.billData} analysis={result.analysis} />
                </div>
            )}
        </div>
    );
}
