"use client";

import { useState } from "react";

const API_BASE = "http://localhost:8000";

interface Message {
  role: "user" | "assistant";
  text: string;
}

export default function Chat() {
  const [messages, setMessages] = useState<Message[]>([
    {
      role: "assistant",
      text: "Hi — ask me anything about vitiligo treatments. I'll only answer using real research evidence, and I'll always tell you where it comes from.",
    },
  ]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);

  const sendMessage = async () => {
    if (!input.trim()) return;
    const question = input;
    setMessages((prev) => [...prev, { role: "user", text: question }]);
    setInput("");
    setLoading(true);

    try {
      const res = await fetch(`${API_BASE}/research/ask`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ question }),
      });
      const data = await res.json();
      setMessages((prev) => [...prev, { role: "assistant", text: data.answer }]);
    } catch {
      setMessages((prev) => [
        ...prev,
        { role: "assistant", text: "Sorry, I couldn't reach the research agent. Is the backend running?" },
      ]);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen bg-[#F3F1E7] flex flex-col items-center px-6 py-10">
      <h1 className="font-[family-name:var(--font-display)] text-2xl text-[#4B5A3E] mb-6">
        Ask VitiCare
      </h1>

      <div className="w-full max-w-2xl flex-1 space-y-4 mb-6">
        {messages.map((m, i) => (
          <div
            key={i}
            className={
              m.role === "user"
                ? "rounded-2xl px-5 py-4 text-sm whitespace-pre-wrap bg-[#DCE3D0] text-[#3A4530] ml-auto max-w-[80%]"
                : "rounded-2xl px-5 py-4 text-sm whitespace-pre-wrap bg-[#FBF9F4] border border-[#E4D9C3] text-[#332C24] max-w-[85%]"
            }
          >
            {m.text}
          </div>
        ))}
        {loading && (
          <div className="bg-[#FBF9F4] border border-[#E4D9C3] rounded-2xl px-5 py-4 text-sm text-[#8C8172] max-w-[85%]">
            Searching evidence…
          </div>
        )}
      </div>

      <div className="w-full max-w-2xl flex gap-3">
        <input
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && sendMessage()}
          placeholder="e.g. Does tacrolimus work for facial vitiligo?"
          className="flex-1 border border-[#E4D9C3] rounded-full px-5 py-3 text-sm bg-white focus:outline-none focus:border-[#4B5A3E]"
        />
        <button
          onClick={sendMessage}
          disabled={loading}
          className="bg-[#332C24] text-[#F3F1E7] rounded-full px-6 py-3 text-sm hover:bg-[#4B5A3E] transition-colors disabled:opacity-40"
        >
          Ask
        </button>
      </div>
    </div>
  );
}
