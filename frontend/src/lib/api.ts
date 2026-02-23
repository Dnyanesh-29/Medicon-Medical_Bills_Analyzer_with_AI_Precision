import axios from "axios";

// Access environment variable for API URL or default to localhost
const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

const api = axios.create({
    baseURL: API_BASE_URL,
    headers: {
        "Content-Type": "application/json",
    },
});

export const checkHealth = async () => {
    try {
        const res = await api.get("/api/v1/health");
        return res.data;
    } catch (error) {
        console.error("Health check failed:", error);
        return null;
    }
};

export const getStats = async () => {
    try {
        const res = await api.get("/api/v1/stats");
        return res.data;
    } catch (error) {
        console.error("Failed to fetch stats:", error);
        return null;
    }
};

export const searchHospitals = async (params: { nabh_only?: boolean; name_query?: string } = {}) => {
    try {
        const res = await api.get("/api/v1/hospitals/list", { params });
        return res.data;
    } catch (error) {
        console.error("Failed to search hospitals:", error);
        return null;
    }
};

export const uploadAndAnalyzeBill = async (file: File) => {
    const formData = new FormData();
    formData.append("file", file);

    try {
        // Increase timeout for analysis
        const res = await api.post("/api/v1/bills/upload-and-analyze", formData, {
            headers: {
                "Content-Type": "multipart/form-data",
            },
            timeout: 120000,
        });
        return res.data;
    } catch (error) {
        if (axios.isAxiosError(error)) {
            throw new Error(error.response?.data?.detail || "Upload failed");
        }
        throw error;
    }
};

export default api;
