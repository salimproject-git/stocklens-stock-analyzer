import Link from "next/link";
import React from "react";

export function Breadcrumb({ ticker, currentPage }: { ticker: string; currentPage?: string }) {
  return (
    <nav className="mb-4 flex items-center gap-2 text-[13px] font-medium text-[#8f9db1]">
      <Link href="/market" className="transition hover:text-white">
        Market
      </Link>
      <span>&gt;</span>
      <span className="text-white">{ticker}</span>
      {currentPage && (
        <>
          <span>&gt;</span>
          <span className="text-white">{currentPage}</span>
        </>
      )}
    </nav>
  );
}
