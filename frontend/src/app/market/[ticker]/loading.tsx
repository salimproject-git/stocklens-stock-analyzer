import { Breadcrumb } from "@/components/stock-research/breadcrumb";

export default function StockLoading() {
  return (
    <>
      <Breadcrumb ticker="…" />
      <section className="my-8 animate-pulse rounded-[20px] border border-white/10 bg-[linear-gradient(180deg,_rgba(11,23,37,0.92),_rgba(7,16,28,0.94))] p-8 text-center" role="status" aria-live="polite">
        <p className="text-sm text-[#9aa9bf]">Loading stock data from the database…</p>
      </section>
    </>
  );
}