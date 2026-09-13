import React from "react";
import { StockDetail } from "@/data/mock-stock-details";
import { SectionCard } from "@/components/ui/section-card";

export function CompanyProfileCard({
  profile,
}: {
  profile: StockDetail["companyProfile"];
}) {
  return (
    <SectionCard
      icon={<BuildingIcon className="h-4 w-4" />}
      title="Company Profile"
    >
      <p className="text-xs leading-relaxed text-[#b6c2d4]">
        {profile.description}
      </p>

      <div className="mt-6 grid grid-cols-2 gap-y-4 pt-4 border-t border-white/8 text-xs">
        {/* Sector */}
        <div className="flex items-center gap-2.5">
          <span className="flex h-7 w-7 shrink-0 items-center justify-center rounded-lg border border-white/10 bg-white/5 text-[#8f9db1]">
            <GridIcon className="h-3.5 w-3.5" />
          </span>
          <div>
            <div className="text-[11px] text-[#7f8c9f]">Sector</div>
            <div className="font-semibold text-white">{profile.sector}</div>
          </div>
        </div>

        {/* Stock Type */}
        <div className="flex items-center gap-2.5">
          <span className="flex h-7 w-7 shrink-0 items-center justify-center rounded-lg border border-white/10 bg-white/5 text-[#8f9db1]">
            <ActivityIcon className="h-3.5 w-3.5" />
          </span>
          <div>
            <div className="text-[11px] text-[#7f8c9f]">Stock Type</div>
            <div className="font-semibold text-white">{profile.stockType}</div>
          </div>
        </div>

        {/* Listed */}
        <div className="flex items-center gap-2.5">
          <span className="flex h-7 w-7 shrink-0 items-center justify-center rounded-lg border border-white/10 bg-white/5 text-[#8f9db1]">
            <LinkIcon className="h-3.5 w-3.5" />
          </span>
          <div>
            <div className="text-[11px] text-[#7f8c9f]">Listed</div>
            <div className="font-semibold text-white">{profile.listedDate}</div>
          </div>
        </div>

        {/* Headquarters */}
        <div className="flex items-center gap-2.5">
          <span className="flex h-7 w-7 shrink-0 items-center justify-center rounded-lg border border-white/10 bg-white/5 text-[#8f9db1]">
            <MapPinIcon className="h-3.5 w-3.5" />
          </span>
          <div>
            <div className="text-[11px] text-[#7f8c9f]">Headquarters</div>
            <div className="font-semibold text-white">{profile.headquarters}</div>
          </div>
        </div>

        {/* Website */}
        <div className="col-span-2 flex items-center gap-2.5 pt-1">
          <span className="flex h-7 w-7 shrink-0 items-center justify-center rounded-lg border border-white/10 bg-white/5 text-[#8f9db1]">
            <GlobeIcon className="h-3.5 w-3.5" />
          </span>
          <div>
            <div className="text-[11px] text-[#7f8c9f]">Website</div>
            <a
              href={`https://${profile.website}`}
              target="_blank"
              rel="noopener noreferrer"
              className="font-semibold text-[#59b3f4] transition hover:underline"
            >
              {profile.website}
            </a>
          </div>
        </div>
      </div>
    </SectionCard>
  );
}

function BuildingIcon({ className }: { className?: string }) {
  return (
    <svg
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
      className={className}
      aria-hidden="true"
    >
      <rect x="4" y="2" width="16" height="20" rx="2" ry="2" />
      <path d="M9 22v-4h6v4" />
      <path d="M8 6h.01" />
      <path d="M16 6h.01" />
      <path d="M8 10h.01" />
      <path d="M16 10h.01" />
      <path d="M8 14h.01" />
      <path d="M16 14h.01" />
    </svg>
  );
}

function GridIcon({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" className={className} aria-hidden="true">
      <rect x="3" y="3" width="7" height="7" rx="1" />
      <rect x="14" y="3" width="7" height="7" rx="1" />
      <rect x="3" y="14" width="7" height="7" rx="1" />
      <rect x="14" y="14" width="7" height="7" rx="1" />
    </svg>
  );
}

function ActivityIcon({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" className={className} aria-hidden="true">
      <polyline points="22 12 18 12 15 21 9 3 6 12 2 12" />
    </svg>
  );
}

function LinkIcon({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" className={className} aria-hidden="true">
      <path d="M10 13a5 5 0 0 0 7.54.54l3-3a5 5 0 0 0-7.07-7.07l-1.72 1.71" />
      <path d="M14 11a5 5 0 0 0-7.54-.54l-3 3a5 5 0 0 0 7.07 7.07l1.71-1.71" />
    </svg>
  );
}

function MapPinIcon({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" className={className} aria-hidden="true">
      <path d="M21 10c0 7-9 13-9 13s-9-6-9-13a9 9 0 0 1 18 0z" />
      <circle cx="12" cy="10" r="3" />
    </svg>
  );
}

function GlobeIcon({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" className={className} aria-hidden="true">
      <circle cx="12" cy="12" r="10" />
      <line x1="2" y1="12" x2="22" y2="12" />
      <path d="M12 2a15.3 15.3 0 0 1 4 10 15.3 15.3 0 0 1-4 10 15.3 15.3 0 0 1-4-10 15.3 15.3 0 0 1 4-10z" />
    </svg>
  );
}

