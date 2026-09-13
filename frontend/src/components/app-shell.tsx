"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import React from "react";

const SIDEBAR_WIDTH = 240;

export function AppShell({ children }: { children: React.ReactNode }) {
  return (
    <div className="h-screen overflow-hidden bg-[radial-gradient(circle_at_top_right,_rgba(245,192,91,0.14),_transparent_24%),linear-gradient(180deg,_#06111d_0%,_#030914_100%)] text-[#f5f7fb]">
      <Sidebar />
      <div
        className="fixed inset-x-0 inset-y-0 overflow-hidden"
        style={{
          left: SIDEBAR_WIDTH,
        }}
      >
        <main className="h-full overflow-y-auto overflow-x-hidden gold-scroll">
          <div className="min-h-full w-full max-w-[1800px] px-8 pb-12 pt-5">
            {children}
          </div>
        </main>
      </div>
    </div>
  );
}

function Sidebar() {
  const pathname = usePathname();
  const isMarketActive = pathname === "/" || pathname.startsWith("/market");
  const isProfileActive = pathname.startsWith("/profile");

  return (
    <aside
      className="fixed inset-y-0 left-0 z-20 flex flex-col border-r border-white/10 bg-[linear-gradient(180deg,_rgba(6,17,29,0.99),_rgba(4,12,22,0.98))] px-4 pb-5 pt-4"
      style={{
        width: SIDEBAR_WIDTH,
      }}
    >
      <div className="mb-5 px-2">
        <StockLensLogo />
      </div>
      <nav className="space-y-2.5">
        <NavItem
          href="/market"
          label="Market Overview"
          active={isMarketActive}
          icon={<BarChartIcon className="h-4 w-4" />}
        />
        <NavItem
          href="/profile"
          label="Profile"
          active={isProfileActive}
          icon={<UserIcon className="h-4 w-4" />}
        />
      </nav>

      <div className="mt-auto rounded-2xl border border-[#d6a24d]/65 bg-[linear-gradient(180deg,_rgba(255,197,92,0.05),_rgba(7,17,29,0.82))] p-4 shadow-[0_20px_60px_rgba(0,0,0,0.35)]">
        <div className="mb-4 flex items-start gap-3">
          <span className="mt-0.5 flex h-9 w-9 items-center justify-center rounded-full border border-[#d6a24d]/50 bg-[#f2bb5c]/10 text-[#f2bb5c]">
            <CapIcon className="h-4 w-4" />
          </span>
          <div>
            <p className="text-[15px] font-semibold text-white">Learn our data</p>
            <p className="mt-1 text-xs leading-5 text-[#9aa9bf]">
              Understand the data behind our stock analysis.
            </p>
          </div>
        </div>
        <button
          type="button"
          className="w-full rounded-xl border border-[#d6a24d]/80 px-3 py-2 text-sm font-semibold text-[#f2bb5c] transition hover:bg-[#f2bb5c]/8"
        >
          Visit Learning Center
        </button>
      </div>
    </aside>
  );
}

function NavItem({
  active = false,
  href,
  icon,
  label,
}: {
  active?: boolean;
  href: string;
  icon: React.ReactNode;
  label: string;
}) {
  return (
    <Link
      href={href}
      className={[
        "flex min-h-[52px] w-full items-center gap-3 rounded-[14px] px-5 py-3 text-[15px] font-medium transition",
        active
          ? "border border-[#d1a14f]/55 bg-[linear-gradient(90deg,_rgba(242,187,92,0.24),_rgba(177,123,34,0.12))] text-[#f4d18b] shadow-[inset_0_1px_0_rgba(255,255,255,0.04)]"
          : "text-[#d4dcec] hover:bg-white/5 hover:text-white",
      ].join(" ")}
    >
      <span className={active ? "text-[#f4c46a]" : "text-[#b9c7d8]"}>{icon}</span>
      <span>{label}</span>
    </Link>
  );
}

function StockLensLogo() {
  return (
    <Link href="/market" className="flex items-center gap-3">
      <span className="text-[#f2bb5c]">
        <LogoMark className="h-10 w-8" />
      </span>
      <div>
        <div className="text-[18px] font-semibold tracking-[-0.02em] text-white">StockLens</div>
        <div className="text-[11px] leading-4 text-[#b1bdd0]">Understand Indonesian Stocks</div>
      </div>
    </Link>
  );
}

function Icon({
  className,
  children,
  viewBox = "0 0 24 24",
}: {
  className?: string;
  children: React.ReactNode;
  viewBox?: string;
}) {
  return (
    <svg
      viewBox={viewBox}
      fill="none"
      stroke="currentColor"
      strokeWidth="1.8"
      strokeLinecap="round"
      strokeLinejoin="round"
      className={className}
      aria-hidden="true"
    >
      {children}
    </svg>
  );
}

function LogoMark({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 36 44" className={className} aria-hidden="true">
      <rect x="2" y="24" width="6" height="16" rx="2" fill="currentColor" />
      <rect x="12" y="16" width="6" height="24" rx="2" fill="currentColor" opacity="0.9" />
      <rect x="22" y="9" width="6" height="31" rx="2" fill="currentColor" opacity="0.8" />
      <rect x="32" y="2" width="6" height="38" rx="2" fill="currentColor" opacity="0.7" />
    </svg>
  );
}

function BarChartIcon({ className }: { className?: string }) {
  return (
    <Icon className={className}>
      <path d="M4 20V10" />
      <path d="M10 20V4" />
      <path d="M16 20v-7" />
      <path d="M22 20V7" />
    </Icon>
  );
}

function UserIcon({ className }: { className?: string }) {
  return (
    <Icon className={className}>
      <path d="M12 12a4 4 0 1 0 0-8 4 4 0 0 0 0 8Z" />
      <path d="M4 20c1.7-3.2 4.3-4.8 8-4.8S18.3 16.8 20 20" />
    </Icon>
  );
}

function CapIcon({ className }: { className?: string }) {
  return (
    <Icon className={className}>
      <path d="m2 10 10-5 10 5-10 5-10-5Z" />
      <path d="M6 12v4c0 1.7 2.7 3 6 3s6-1.3 6-3v-4" />
    </Icon>
  );
}

