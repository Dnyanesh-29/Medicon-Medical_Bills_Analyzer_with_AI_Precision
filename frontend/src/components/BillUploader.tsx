// ... imports kept same ...
import { useState } from "react";
import { useDropzone } from "react-dropzone";
import { UploadCloud, File, AlertCircle, CheckCircle, Loader2 } from "lucide-react";
import { cn } from "@/lib/utils";
import { motion, AnimatePresence } from "framer-motion";

interface BillUploaderProps {
    onUpload: (file: File) => Promise<void>;
    isUploading: boolean;
}

export default function BillUploader({ onUpload, isUploading }: BillUploaderProps) {
    const [error, setError] = useState<string | null>(null);
    const [file, setFile] = useState<File | null>(null);
    const [preview, setPreview] = useState<string | null>(null);

    const onDrop = async (acceptedFiles: File[]) => {
        setError(null);
        if (acceptedFiles.length === 0) return;

        const selectedFile = acceptedFiles[0];
        if (selectedFile.size > 10 * 1024 * 1024) { // 10MB limit
            setError("File size exceeds 10MB limit.");
            return;
        }

        setFile(selectedFile);

        // Create preview
        if (selectedFile.type.startsWith("image/")) {
            const url = URL.createObjectURL(selectedFile);
            setPreview(url);
        } else {
            setPreview(null);
        }

        await onUpload(selectedFile);
    };

    const removeFile = (e: React.MouseEvent) => {
        e.stopPropagation();
        setFile(null);
        if (preview) URL.revokeObjectURL(preview);
        setPreview(null);
    };

    const { getRootProps, getInputProps, isDragActive } = useDropzone({
        onDrop,
        accept: {
            "image/*": [".png", ".jpg", ".jpeg", ".webp"],
            "application/pdf": [".pdf"],
        },
        maxFiles: 1,
        disabled: isUploading || !!file,
    });

    return (
        <div className="w-full max-w-xl mx-auto">
            <div
                {...getRootProps()}
                className={cn(
                    "relative group border-2 border-dashed rounded-xl transition-all flex flex-col items-center justify-center gap-4 overflow-hidden",
                    isDragActive ? "border-teal-500 bg-teal-50" : "border-slate-300 bg-white hover:border-teal-400 hover:bg-slate-50",
                    (isUploading || file) ? "cursor-default" : "cursor-pointer",
                    file ? "p-0 border-solid border-slate-200" : "p-10 shadow-sm"
                )}
            >
                <input {...getInputProps()} />

                {file ? (
                    <div className="relative w-full h-full min-h-[300px] flex items-center justify-center bg-slate-50">
                        {preview ? (
                            <img src={preview} alt="Preview" className="w-full h-full object-contain max-h-[400px]" />
                        ) : (
                            <div className="flex flex-col items-center p-8">
                                <div className="p-4 bg-white rounded-full shadow-sm mb-4">
                                    <File className="w-12 h-12 text-teal-600" />
                                </div>
                                <p className="text-lg font-medium text-slate-900">{file.name}</p>
                                <p className="text-sm text-slate-500">{(file.size / 1024 / 1024).toFixed(2)} MB</p>
                            </div>
                        )}

                        {/* Overlay Loading or Actions */}
                        <div className="absolute inset-0 bg-white/90 backdrop-blur-[2px] flex items-center justify-center transition-opacity opacity-0 hover:opacity-100 data-[uploading=true]:opacity-100" data-uploading={isUploading}>
                            {isUploading ? (
                                <div className="flex flex-col items-center">
                                    <Loader2 className="w-10 h-10 text-teal-600 animate-spin mb-2" />
                                    <span className="text-teal-700 font-medium animate-pulse">Analyzing Bill...</span>
                                </div>
                            ) : (
                                <button
                                    onClick={removeFile}
                                    className="bg-red-500 hover:bg-red-600 text-white px-6 py-2 rounded-full font-medium flex items-center gap-2 transform hover:scale-105 transition-all shadow-md"
                                >
                                    Change File
                                </button>
                            )}
                        </div>
                    </div>
                ) : (
                    <>
                        <div className="p-4 bg-teal-50 rounded-full group-hover:scale-110 transition-all duration-300">
                            <UploadCloud className="w-10 h-10 text-teal-600" />
                        </div>

                        <div className="text-center space-y-1">
                            <p className="text-lg font-medium text-slate-700">
                                {isDragActive ? "Drop the bill here" : "Click to upload or drag & drop"}
                            </p>
                            <p className="text-sm text-slate-500 px-4">
                                Supports PDF, PNG, JPG (Max 10MB)
                            </p>
                        </div>
                    </>
                )}
            </div>

            <AnimatePresence>
                {error && (
                    <motion.div
                        initial={{ opacity: 0, y: 10 }}
                        animate={{ opacity: 1, y: 0 }}
                        exit={{ opacity: 0, y: -10 }}
                        className="mt-4 p-3 bg-red-50 border border-red-200 rounded-lg flex items-center gap-2 text-red-600 text-sm"
                    >
                        <AlertCircle className="w-4 h-4" />
                        {error}
                    </motion.div>
                )}
            </AnimatePresence>
        </div>
    );
}
