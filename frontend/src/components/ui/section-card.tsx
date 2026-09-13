import React from "react";

export function SectionCard({
  icon,
  title,
  subtitle,
  actionSlot,
  children,
  className = "",
}: {
  icon?: React.ReactNode;
  title?: React.ReactNode;
  subtitle?: React.ReactNode;
  actionSlot?: React.ReactNode;
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <article
      className={[
        "flex flex-col justify-between rounded-[20px] border border-white/10 bg-[linear-gradient(180deg,_rgba(11,23,37,0.92),_rgba(7,16,28,0.94))] p-6 shadow-[0_24px_48px_rgba(0,0,0,0.28)]",
        className,
      ].join(" ")}
    >
      <div>
        {(title || icon || actionSlot) && (
          <div className="mb-5 flex items-start justify-between gap-4">
            <div className="flex items-center gap-3">
              {icon && (
                <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg border border-[#d6a24d]/40 bg-[#f2bb5c]/10 text-[#f2bb5c]">
                  {icon}
                </span>
              )}
              <div>
                {title && (
                  <h3 className="text-[17px] font-semibold tracking-[-0.01em] text-white">
                    {title}
                  </h3>
                )}
                {subtitle && (
                  <p className="mt-0.5 text-xs text-[#9aa9bf]">{subtitle}</p>
                )}
              </div>
            </div>
            {actionSlot && <div>{actionSlot}</div>}
          </div>
        )}
        {children}
      </div>
    </article>
  );
}

