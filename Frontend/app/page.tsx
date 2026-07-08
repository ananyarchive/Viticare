"use client";

import { useEffect, useState } from "react";
import Link from "next/link";

const QUOTES = [
  "Progress isn't always visible to the eye — but it's always worth tracking.",
  "Your skin's story is still being written.",
  "Small changes, noticed consistently, become the whole picture.",
  "You are not your patch. You are the person tracking its journey.",
  "Healing isn't linear, but it is measurable.",
];

export default function Landing() {
  const [quoteIndex, setQuoteIndex] = useState(0);

  useEffect(() => {
    const interval = setInterval(() => {
      setQuoteIndex((i) => (i + 1) % QUOTES.length);
    }, 5000);
    return () => clearInterval(interval);
  }, []);

  return (
    <div className="min-h-screen relative overflow-hidden bg-[#F3F1E7]">
      <div className="pointer-events-none absolute inset-0 overflow-hidden">
        <div className="watercolor-blob blob-1" />
        <div className="watercolor-blob blob-2" />
        <div className="watercolor-blob blob-3" />
      </div>

      <header className="relative z-10 flex items-center justify-between px-10 py-6">
        <div className="font-[family-name:var(--font-display)] text-xl text-[#4B5A3E]">
          VitiCare
        </div>
        <nav className="flex items-center gap-3">
          <Link
            href="/portal?mode=existing"
            className="text-sm text-[#5C5245] hover:text-[#4B5A3E] px-4 py-2 transition-colors"
          >
            Existing Patient
          </Link>
          <Link
            href="/portal?mode=new"
            className="text-sm text-[#5C5245] hover:text-[#4B5A3E] px-4 py-2 transition-colors"
          >
            New Patient
          </Link>
          <Link
            href="/dashboard"
            className="text-sm bg-[#4B5A3E] text-[#F3F1E7] rounded-full px-5 py-2 hover:bg-[#3D4A32] transition-colors"
          >
            Personal Dashboard
          </Link>
        </nav>
      </header>

      <main className="relative z-10 flex flex-col items-center justify-center text-center px-6 pt-24 pb-32">
        <h1 className="font-[family-name:var(--font-display)] text-[64px] leading-none text-[#332C24]">
          <span className="font-[family-name:var(--font-script)] text-[96px] text-[#4B5A3E] mr-1">
            V
          </span>
          itiCare
        </h1>

        <p className="mt-8 text-2xl italic font-[family-name:var(--font-display)] text-[#5B6B4F] max-w-xl transition-opacity duration-700">
          {'\u201C'}{QUOTES[quoteIndex]}{'\u201D'}
        </p>

        <p className="mt-6 text-sm uppercase tracking-[0.15em] text-[#8C8172]">
          Longitudinal vitiligo tracking, backed by evidence
        </p>

        <Link
          href="/portal"
          className="mt-12 inline-flex items-center gap-2 bg-[#332C24] text-[#F3F1E7] rounded-full px-8 py-4 text-sm hover:bg-[#4B5A3E] transition-colors"
        >
          Try it now <span>{'\u2192'}</span>
        </Link>
      </main>

      <style jsx>{`
        .watercolor-blob {
          position: absolute;
          border-radius: 50%;
          filter: blur(60px);
          opacity: 0.35;
          animation: drift 22s ease-in-out infinite;
        }
        .blob-1 {
          width: 500px;
          height: 500px;
          background: #a8b78e;
          top: -150px;
          left: -100px;
          animation-delay: 0s;
        }
        .blob-2 {
          width: 400px;
          height: 400px;
          background: #d8c4a8;
          bottom: -120px;
          right: -80px;
          animation-delay: 7s;
        }
        .blob-3 {
          width: 350px;
          height: 350px;
          background: #c9a8a0;
          top: 40%;
          right: 10%;
          animation-delay: 14s;
        }
        @keyframes drift {
          0%, 100% { transform: translate(0, 0) scale(1); }
          33% { transform: translate(40px, -30px) scale(1.08); }
          66% { transform: translate(-30px, 20px) scale(0.95); }
        }
      `}</style>
    </div>
  );
}
