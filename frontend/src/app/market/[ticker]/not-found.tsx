import Link from "next/link";
import { Breadcrumb } from "@/components/stock-research/breadcrumb";

export default function NotFound() {
  return (
    <div className="min-h-screen bg-[linear-gradient(180deg,_#0b1723,_#050d16)] px-6 py-8 text-white">
      <div className="mx-auto max-w-7xl">
        <Breadcrumb ticker="[ticker]" />
        
        <div className="mt-12 flex flex-col items-center justify-center rounded-2xl border border-white/10 bg-[linear-gradient(180deg,_rgba(11,23,37,0.92),_rgba(7,16,28,0.94))] p-12 text-center">
          <div className="flex h-20 w-20 items-center justify-center rounded-full border-2 border-[#ff5967]/40 bg-[#ff5967]/10">
            <svg
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="2"
              strokeLinecap="round"
              strokeLinejoin="round"
              className="h-10 w-10 text-[#ff5967]"
            >
              <circle cx="12" cy="12" r="10" />
              <line x1="15" y1="9" x2="9" y2="15" />
              <line x1="9" y1="9" x2="15" y2="15" />
            </svg>
          </div>
          
          <h1 className="mt-6 text-3xl font-bold tracking-tight">
            Ticker Not Found
          </h1>
          
          <p className="mt-3 max-w-md text-[15px] leading-relaxed text-[#b6c2d4]">
            The ticker you are looking for is not available in our database. Make sure the ticker is correct and belongs to a company listed on the IDX.
          </p>
          
          <Link
            href="/market"
            className="mt-8 rounded-xl bg-[linear-gradient(180deg,_#f5c15d,_#e0a843)] px-6 py-3 text-sm font-semibold text-[#1d170f] shadow-[0_8px_20px_rgba(224,168,67,0.24)] transition hover:brightness-105"
          >
            ← Back to Market Overview
          </Link>
        </div>
      </div>
    </div>
  );
}
