"use client";

import { useState, useRef, useEffect } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { MessageCircle, X, Send, Bot, User, Sparkles } from "lucide-react";
import { cn } from "@/lib/utils";
import { BillData, BillAnalysisResult } from "@/types";

interface ChatMessage {
  role: "user" | "assistant";
  content: string;
}

interface ChatbotProps {
  billData: BillData;
  analysis: BillAnalysisResult;
}

export default function Chatbot({ billData, analysis }: ChatbotProps) {
  const [isOpen, setIsOpen] = useState(false);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const [reasoning, setReasoning] = useState<string>("");
  const messagesEndRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, reasoning, isOpen]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!input.trim() || isLoading) return;

    const userMessage = input;
    setInput("");
    setMessages(prev => [...prev, { role: "user", content: userMessage }]);
    setIsLoading(true);
    setReasoning("");

    try {
      const response = await fetch("http://localhost:8000/api/v1/chat", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          messages: [...messages, { role: "user", content: userMessage }].map(m => ({ role: m.role, content: m.content })),
          context: { bill: billData, analysis: analysis }
        })
      });

      if (!response.ok) throw new Error("Network error");
      if (!response.body) throw new Error("No body in response");

      setMessages(prev => [...prev, { role: "assistant", content: "" }]);
      
      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let assistantContent = "";
      let currentReasoning = "";

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        const chunk = decoder.decode(value, { stream: true });
        const lines = chunk.split("\n\n");
        
        for (const line of lines) {
          if (line.startsWith("data: ")) {
            const dataStr = line.slice(6);
            if (dataStr.trim() === "[DONE]") continue;

            try {
              const data = JSON.parse(dataStr);
              if (data.type === "reasoning") {
                currentReasoning += data.content;
                setReasoning(currentReasoning);
              } else if (data.type === "content") {
                setReasoning(""); // Once we get content, reasoning is done typically
                assistantContent += data.content;
                setMessages(prev => {
                  const newMsgs = [...prev];
                  newMsgs[newMsgs.length - 1].content = assistantContent;
                  return newMsgs;
                });
              } else if (data.error) {
                console.error("Chat error:", data.error);
              }
            } catch (err) {
              // ignore parse errors for partial chunks if any
            }
          }
        }
      }
    } catch (error) {
      console.error(error);
      setMessages(prev => [...prev, { role: "assistant", content: "Sorry, I encountered an error while processing your request." }]);
    } finally {
      setIsLoading(false);
      setReasoning("");
    }
  };

  return (
    <>
      <motion.button
        initial={{ scale: 0 }}
        animate={{ scale: isOpen ? 0 : 1 }}
        whileHover={{ scale: 1.05 }}
        whileTap={{ scale: 0.95 }}
        onClick={() => setIsOpen(true)}
        className="fixed bottom-6 right-6 w-14 h-14 bg-teal-600 text-white rounded-full shadow-2xl flex items-center justify-center z-50 hover:bg-teal-700 transition-colors border-2 border-white/20"
      >
        <MessageCircle className="w-6 h-6" />
        <span className="absolute -top-1 -right-1 w-4 h-4 bg-rose-500 rounded-full border-2 border-white" />
      </motion.button>

      <AnimatePresence>
        {isOpen && (
          <motion.div
            initial={{ opacity: 0, y: 20, scale: 0.95 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, y: 20, scale: 0.95 }}
            transition={{ type: "spring", stiffness: 300, damping: 25 }}
            className="fixed bottom-6 right-6 w-[380px] max-h-[600px] h-[80vh] bg-white rounded-2xl shadow-2xl border border-stone-200/50 flex flex-col z-50 overflow-hidden"
          >
            <div className="bg-gradient-to-r from-teal-600 to-teal-500 p-4 text-white flex items-center justify-between shadow-sm relative overflow-hidden">
              <div className="absolute top-0 right-0 p-4 opacity-10 pointer-events-none">
                <Sparkles className="w-16 h-16" />
              </div>
              <div className="flex items-center gap-3 relative z-10">
                <div className="w-8 h-8 bg-white/20 rounded-full flex items-center justify-center backdrop-blur-sm">
                  <Bot className="w-5 h-5 text-white" />
                </div>
                <div>
                  <h3 className="font-bold text-[15px]">Bill Assistant AI</h3>
                  <p className="text-teal-100 text-[11px] font-medium tracking-wide uppercase">Ask questions about your bill</p>
                </div>
              </div>
              <button 
                onClick={() => setIsOpen(false)}
                className="w-8 h-8 bg-white/10 hover:bg-white/20 rounded-full flex items-center justify-center transition-colors relative z-10"
              >
                <X className="w-5 h-5" />
              </button>
            </div>

            <div className="flex-1 overflow-y-auto p-4 bg-stone-50/50 space-y-4">
              {messages.length === 0 && (
                <div className="text-center text-stone-500 mt-10 space-y-3">
                  <div className="w-16 h-16 bg-teal-100 rounded-full flex items-center justify-center mx-auto">
                    <Bot className="w-8 h-8 text-teal-600" />
                  </div>
                  <p className="text-sm font-medium">Hi! I am analyzing your hospital bill.<br/>What would you like to know?</p>
                </div>
              )}
              {messages.map((msg, idx) => (
                <div key={idx} className={cn("flex gap-3", msg.role === "user" ? "justify-end" : "justify-start")}>
                  {msg.role === "assistant" && (
                     <div className="w-8 h-8 rounded-full bg-teal-100 flex items-center justify-center shrink-0">
                       <Bot className="w-4 h-4 text-teal-700" />
                     </div>
                  )}
                  <div className={cn(
                    "max-w-[75%] rounded-2xl px-4 py-2.5 text-sm whitespace-pre-wrap leading-relaxed",
                    msg.role === "user" 
                      ? "bg-teal-600 text-white rounded-tr-sm" 
                      : "bg-white border border-stone-200/50 text-stone-800 rounded-tl-sm shadow-sm"
                  )}>
                    {msg.content}
                  </div>
                  {msg.role === "user" && (
                    <div className="w-8 h-8 rounded-full bg-stone-200 flex items-center justify-center shrink-0">
                      <User className="w-4 h-4 text-stone-600" />
                    </div>
                  )}
                </div>
              ))}
              
              {reasoning && (
                <div className="flex gap-3">
                  <div className="w-8 h-8 rounded-full bg-teal-100 flex items-center justify-center shrink-0">
                    <Bot className="w-4 h-4 text-teal-700" />
                  </div>
                  <div className="max-w-[75%] rounded-2xl px-4 py-2.5 text-xs bg-stone-100 border border-stone-200 text-stone-500 italic rounded-tl-sm shadow-sm whitespace-pre-wrap">
                    <span className="font-semibold text-stone-600 block mb-1">Thinking...</span>
                    {reasoning}
                  </div>
                </div>
              )}

              {isLoading && !reasoning && (
                <div className="flex gap-3">
                  <div className="w-8 h-8 rounded-full bg-teal-100 flex items-center justify-center shrink-0">
                    <Bot className="w-4 h-4 text-teal-700" />
                  </div>
                  <div className="bg-white border border-stone-200/50 text-stone-800 rounded-2xl rounded-tl-sm px-4 py-3 flex items-center gap-1 shadow-sm">
                    <motion.div animate={{ y: [0, -5, 0] }} transition={{ repeat: Infinity, duration: 0.6, delay: 0 }} className="w-1.5 h-1.5 bg-stone-400 rounded-full" />
                    <motion.div animate={{ y: [0, -5, 0] }} transition={{ repeat: Infinity, duration: 0.6, delay: 0.2 }} className="w-1.5 h-1.5 bg-stone-400 rounded-full" />
                    <motion.div animate={{ y: [0, -5, 0] }} transition={{ repeat: Infinity, duration: 0.6, delay: 0.4 }} className="w-1.5 h-1.5 bg-stone-400 rounded-full" />
                  </div>
                </div>
              )}
              <div ref={messagesEndRef} />
            </div>

            <form onSubmit={handleSubmit} className="p-3 bg-white border-t border-stone-200/50 flex gap-2">
              <input
                type="text"
                value={input}
                onChange={(e) => setInput(e.target.value)}
                placeholder="Ask about overcharges..."
                className="flex-1 bg-stone-50 border border-stone-200 rounded-xl px-4 py-2.5 focus:outline-none focus:ring-2 focus:ring-teal-500/50 text-sm font-medium"
              />
              <button
                type="submit"
                disabled={isLoading || !input.trim()}
                className="bg-teal-600 hover:bg-teal-700 disabled:opacity-50 text-white p-2.5 rounded-xl transition-colors flex items-center justify-center shrink-0"
              >
                <Send className="w-5 h-5" />
              </button>
            </form>
          </motion.div>
        )}
      </AnimatePresence>
    </>
  );
}
