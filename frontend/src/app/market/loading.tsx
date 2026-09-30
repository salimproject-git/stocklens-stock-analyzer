export default function MarketLoading() {
  return <LoadingMessage message="Loading market data from the database…" />;
}

function LoadingMessage({ message }: { message: string }) {
  return (
    <section className="mt-6 animate-pulse rounded-[20px] border border-white/10 bg-[linear-gradient(180deg,_rgba(11,23,37,0.92),_rgba(7,16,28,0.94))] p-8 text-center" role="status" aria-live="polite">
      <p className="text-sm text-[#9aa9bf]">{message}</p>
    </section>
  );
}