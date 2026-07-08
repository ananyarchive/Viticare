"use client";

import { useState } from "react";
import Link from "next/link";

export default function Portal() {
  const [patientId, setPatientId] = useState("");
  const [submitted, setSubmitted] = useState(false);

  if (!submitted) {
    return (
      <div className="min-h-screen bg-[#F3F1E7] flex items-center justify-center px-6">
        <div className="bg-[#FBF9F4] border border-[#E4D9C3] rounded-2xl p-10 max-w-md w-full text-center">
          <h1 className="font-[family-name:var(--font-display)] text-2xl text-[#4B5A3E] mb-2">
            Welcome back
          </h1>
          <p className="text-sm text-[#8C8172] mb-6">
            Enter your patient ID to continue
          </p>
          <input
            value={patientId}
            onChange={(e) => setPatientId(e.target.value)}
            placeholder="Patient ID"
            className="w-full border border-[#E4D9C3] rounded-lg px-4 py-3 text-sm text-[#332C24] bg-white mb-4 focus:outline-none focus:border-[#4B5A3E]"
          />
          <button
            onClick={() => setSubmitted(true)}
            disabled={!patientId}
            className="w-full bg-[#332C24] text-[#F3F1E7] rounded-lg py-3 text-sm hover:bg-[#4B5A3E] transition-colors disabled:opacity-40"
          >
            Continue
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-[#F3F1E7] px-10 py-12">
      <p className="text-xs uppercase tracking-wide text-[#8C8172] mb-1">
        Patient {patientId}
      </p>
      <h1 className="font-[family-name:var(--font-display)] text-3xl text-[#332C24] mb-10">
        What would you like to do?
      </h1>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-6 max-w-4xl">
        <Link
          href={`/dashboard?patient=${patientId}`}
          className="bg-[#FBF9F4] border border-[#E4D9C3] rounded-2xl p-7 hover:shadow-md hover:border-[#4B5A3E] transition-all group"
        >
          <div className="w-10 h-10 rounded-full bg-[#DCE3D0] flex items-center justify-center mb-4 text-[#4B5A3E]">
            {'\u2197'}
          </div>
          <h2 className="font-[family-name:var(--font-display)] text-lg text-[#4B5A3E] mb-1">
            Progress Report
          </h2>
          <p className="text-sm text-[#8C8172]">
            See your timeline, repigmentation comparisons, and progress heatmaps
          </p>
        </Link>

        <Link
          href={`/updates?patient=${patientId}`}
          className="bg-[#FBF9F4] border border-[#E4D9C3] rounded-2xl p-7 hover:shadow-md hover:border-[#8A6E4E] transition-all group"
        >
          <div className="w-10 h-10 rounded-full bg-[#F5EDE3] flex items-center justify-center mb-4 text-[#8A6E4E]">
            {'\u270E'}
          </div>
          <h2 className="font-[family-name:var(--font-display)] text-lg text-[#8A6E4E] mb-1">
            Check Out Updates
          </h2>
          <p className="text-sm text-[#8C8172]">
            Log a new photo or check in on your treatment consistency
          </p>
        </Link>

        <Link
          href={`/chat?patient=${patientId}`}
          className="bg-[#FBF9F4] border border-[#E4D9C3] rounded-2xl p-7 hover:shadow-md hover:border-[#6B6355] transition-all group"
        >
          <div className="w-10 h-10 rounded-full bg-[#EDEAE3] flex items-center justify-center mb-4 text-[#6B6355]">
            {'\u{1F4AC}'}
          </div>
          <h2 className="font-[family-name:var(--font-display)] text-lg text-[#6B6355] mb-1">
            Ask a Question
          </h2>
          <p className="text-sm text-[#8C8172]">
            Chat about treatments, evidence, or questions to bring to your doctor
          </p>
        </Link>
      </div>
    </div>
  );
}
