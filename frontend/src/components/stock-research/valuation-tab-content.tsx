import React from 'react'
import { StockDetail } from '@/data/mock-stock-details'
import { SectionCard } from '@/components/ui/section-card'
import { StatusBadge } from '@/components/ui/status-badge'
import { formatRupiah } from '@/utils/currency'
import { getMainValuationMethod } from '@/lib/analysis'

const toneClass: Record<string, string> = { 'EPS (TTM)': 'text-white', BVPS: 'text-white', 'P/E Ratio': 'text-[#3ef0a9]', 'P/BV Ratio': 'text-[#3ef0a9]', 'PEG Ratio': 'text-[#3ef0a9]', 'Dividend Yield': 'text-[#d8f4e7]' }

function formatChangePercent(value: number) {
  const sign = value > 0 ? '+' : '';
  return `${sign}${new Intl.NumberFormat('id-ID', { minimumFractionDigits: 2, maximumFractionDigits: 2 }).format(value)}% today`;
}

export function ValuationTabContent({ stock }: { stock: StockDetail }) {
  const mainMethod = getMainValuationMethod(stock.stockType);
  const valuation = stock.currentValuation;
  const methods = valuation.methods;
  const points = methods.map((method) => ({
    method: method.method,
    value: method.intrinsicValue,
    color: method.method === 'Peter Lynch / Adaptive' ? 'bg-[#3ecf9d]' : method.method === 'Type & Sector Weighted' ? 'bg-[#42bfd0]' : method.method === 'Mean Reversion PBV' ? 'bg-[#c79d51]' : method.method === 'Dividend Discount Model' ? 'bg-[#d66f65]' : 'bg-[#78a8c8]',
  }));

  return <div className='space-y-6'>
    <header className='flex flex-col justify-between gap-4 md:flex-row md:items-center'>
      <div>
        <h2 className='text-3xl font-bold tracking-tight text-white'>Valuation</h2>
        <p className='mt-1 text-sm text-[#aeb9ca]'>Compare current price with intrinsic value estimates across multiple valuation methods.</p>
      </div>
    </header>
    <SectionCard icon={<SectionIcon kind='current' />} title='Current Valuation' subtitle='Key valuation metrics based on the latest available data.' className='p-5 md:p-6'>
      <div className='grid grid-cols-1 gap-px overflow-hidden rounded-xl border border-white/[0.08] bg-white/[0.08] sm:grid-cols-2 lg:grid-cols-4 xl:grid-cols-7'>
        <div className='min-w-0 bg-[#081523] px-4 py-4'><div className='text-[11px] font-medium text-[#aebbd0]'>Current Price</div><div className='mt-5 whitespace-nowrap text-[22px] font-semibold text-[#3ef0a9]'>{formatRupiah(valuation.currentPrice)}</div><div className='mt-1.5 text-[11px] text-[#8090a7]'>{formatChangePercent(stock.changePercent)}</div></div>
        {valuation.metrics.map(card => <div key={card.label} className='min-w-0 bg-[#081523] px-4 py-4'><div className='text-[11px] font-medium text-[#aebbd0]'>{card.label}</div><div className={`mt-5 whitespace-nowrap text-[22px] font-semibold ${toneClass[card.label] ?? 'text-white'}`}>{typeof card.value === 'number' ? formatRupiah(card.value) : card.value}</div><div className='mt-1.5 text-[11px] text-[#8090a7]'>{card.note}</div></div>)}
      </div>
    </SectionCard>
    <SectionCard icon={<SectionIcon kind='spectrum' />} title='Price vs Estimated Value' subtitle='Current price compared to intrinsic value estimates from different valuation methods.' className='p-5 md:p-6'>
       <div className='grid items-stretch gap-4 xl:grid-cols-[minmax(0,7fr)_minmax(280px,3fr)]'><EqualSpacedSpectrum currentPrice={valuation.currentPrice} points={points} /><div className='h-full rounded-2xl border border-[#d6a24d]/25 bg-[#1d1b15] p-4'><div className='flex items-center gap-2 text-sm font-semibold text-[#f2d18f]'><InsightIcon />Key Takeaway</div><p className='mt-3 text-xs leading-6 text-[#d2dbea]'>{valuation.comparison.takeaway}</p><ul className='mt-4 space-y-2 text-xs text-[#b9c6d8]'>{valuation.comparison.readouts.map((readout) => <li key={readout}>- {readout}</li>)}</ul></div></div>
    </SectionCard>
    <SectionCard icon={<SectionIcon kind='methods' />} title='Valuation Methods' subtitle='Intrinsic value estimates using different valuation approaches.' className='p-5 md:p-6'>
      <div className='overflow-x-auto rounded-xl border border-white/[0.08]'><table className='w-full min-w-[900px] border-collapse text-left text-xs'><thead className='bg-[#081523] text-[10px] uppercase tracking-[0.1em] text-[#7f8fa6]'><tr>{['Method', 'Intrinsic Value', 'Potential', 'Margin of Safety', 'Status', 'How it works'].map(heading => <th key={heading} className='px-4 py-3'>{heading}</th>)}</tr></thead><tbody>{methods.map(({ method, intrinsicValue, potential, marginOfSafety, status, description }) => <tr key={method} className='border-t border-white/[0.07]'><td className='whitespace-nowrap px-4 py-4 font-medium text-white'><span className='inline-flex items-center gap-2'>{method}{method === mainMethod && <span className='rounded-md border border-[#d6a24d]/45 bg-[#f2bb5c]/10 px-2 py-0.5 text-[10px] font-semibold uppercase tracking-[0.08em] text-[#f2d18f]'>Main</span>}</span></td><td className='px-4 py-4 font-semibold text-[#f2d18f]'>{formatRupiah(intrinsicValue)}</td><td className={`px-4 py-4 font-semibold ${potential.startsWith('+') ? 'text-[#3ef0a9]' : 'text-[#ff8b82]'}`}>{potential}</td><td className={`px-4 py-4 font-semibold ${marginOfSafety.startsWith('-') ? 'text-[#ff8b82]' : 'text-[#3ef0a9]'}`}>{marginOfSafety}</td><td className='px-4 py-4'><StatusBadge tone={status === 'UNDERVALUED' ? 'undervalued' : 'overvalued'}>{status}</StatusBadge></td><td className='whitespace-nowrap px-4 py-4 text-[#9aa9bf]'>{description}</td></tr>)}</tbody></table></div>
    </SectionCard>
    <SectionCard icon={<SectionIcon kind='compare' />} title='Why the Methods Differ?' subtitle='Each valuation method looks at the company from a different perspective, which leads to different intrinsic value estimates.' className='p-5 md:p-6'><div className='grid gap-3 md:grid-cols-3'>{valuation.explanations.map((explanation) => <Explain key={explanation.title} title={explanation.title} text={explanation.text} tags={explanation.methods} />)}</div></SectionCard>
  </div>
}

function InsightIcon() { return <svg viewBox='0 0 24 24' fill='none' stroke='currentColor' strokeWidth='1.8' strokeLinecap='round' strokeLinejoin='round' className='h-4 w-4' aria-hidden='true'><path d='M9 18h6M10 21h4M8.5 14.5a6 6 0 1 1 7 0c-.9.7-1.5 1.5-1.5 2.5h-5c0-1-.6-1.8-1.5-2.5Z' /><path d='M12 2v1M4.9 4.9l.7.7M19.1 4.9l-.7.7' /></svg> }

function SectionIcon({ kind }: { kind: 'current' | 'spectrum' | 'methods' | 'compare' | 'history' }) {
  const paths = {
    current: <><path d='M4 17 9 12l3 3 7-8' /><path d='M15 7h4v4' /><path d='M4 20h16' /></>,
    spectrum: <><path d='M4 18V6M4 18h16' /><path d='m7 14 3-4 3 2 4-6' /><circle cx='7' cy='14' r='1' /><circle cx='10' cy='10' r='1' /><circle cx='13' cy='12' r='1' /><circle cx='17' cy='6' r='1' /></>,
    methods: <><path d='M4 19V5M4 19h16' /><rect x='7' y='12' width='2.8' height='5' rx='.7' /><rect x='11' y='9' width='2.8' height='8' rx='.7' /><rect x='15' y='6' width='2.8' height='11' rx='.7' /></>,
    compare: <><path d='M12 4v16M7 7h10M5 7 2.5 12a3 3 0 0 0 5 0L5 7ZM19 7l-2.5 5a3 3 0 0 0 5 0L19 7Z' /><path d='M8 20h8' /></>,
    history: <><path d='M4 19V5M4 19h16' /><path d='M7 15v-3M11 15V8M15 15v-5M19 15V6' /></>,
  };
  return <svg viewBox='0 0 24 24' fill='none' stroke='currentColor' strokeWidth='1.8' strokeLinecap='round' strokeLinejoin='round' className='h-4 w-4' aria-hidden='true'>{paths[kind]}</svg>;
}

function EqualSpacedSpectrum({ currentPrice, points }: { currentPrice: number; points: { method: string; value: number; color: string }[] }) {
  const sortedPoints = [...points].sort((left, right) => left.value - right.value);
  const anchors = sortedPoints.map((_, index) => 15 + index * 17.5);
  const currentPosition = currentPrice <= sortedPoints[0].value ? 10 + ((currentPrice - sortedPoints[0].value) / sortedPoints[0].value) * 10 : currentPrice >= sortedPoints[sortedPoints.length - 1].value ? 80 + ((currentPrice - sortedPoints[sortedPoints.length - 1].value) / sortedPoints[sortedPoints.length - 1].value) * 10 : (() => {
    const upperIndex = sortedPoints.findIndex(point => point.value >= currentPrice);
    const lower = sortedPoints[upperIndex - 1];
    const upper = sortedPoints[upperIndex];
    return anchors[upperIndex - 1] + ((currentPrice - lower.value) / (upper.value - lower.value)) * 15;
  })();
  return <div className='flex min-w-0 flex-col rounded-2xl border border-white/[0.08] bg-[#07111c]/65 p-3'><div className='relative mt-7 h-36'><div className='absolute left-[8%] right-[8%] top-[30px] h-px bg-white/[0.18]' />{sortedPoints.map((point, index) => <div key={point.method} className='absolute top-0 -translate-x-1/2 text-center' style={{ left: anchors[index] + '%' }}><div className='mb-2 text-xs font-bold leading-4 text-white'>{formatRupiah(point.value)}</div><div className={`mx-auto h-3 w-3 rounded-full ${point.color}`} /><div className='mx-auto mt-2 w-24 text-[10px] leading-4 text-[#8e9db3]'>{point.method === 'Dividend Discount Model' ? <>Dividend<br />Discount Model</> : point.method === 'Mean Reversion PBV' ? <>Mean Reversion<br />PBV</> : point.method === 'Discounted Earnings' ? <>Discounted<br />Earnings</> : point.method === 'Type & Sector Weighted' ? <>Type & Sector<br />Weighted</> : <>Peter Lynch<br />/ Adaptive</>}</div></div>)}<div className='absolute -top-5 bottom-12 w-0.5 border-l border-dashed border-[#f2bb5c]' style={{ left: currentPosition + '%' }}><div className='absolute top-[calc(100%+2px)] left-1/2 -translate-x-1/2 whitespace-nowrap text-center text-xs font-bold text-[#f2d18f]'>{formatRupiah(currentPrice)}</div><div className='absolute top-[calc(100%+19px)] left-1/2 -translate-x-1/2 whitespace-nowrap text-center text-[10px] text-[#c79d51]'>Current Price</div></div></div></div>;
}

function Explain({ title, text, tags }: { title: string; text: string; tags: string[] }) {
  return <div className='flex min-h-[190px] flex-col rounded-xl border border-white/[0.08] bg-[#081523]/75 p-4'><div className='flex h-9 w-9 items-center justify-center rounded-lg border border-[#3892d0]/25 bg-[#3892d0]/10 text-[#6faed8]'><svg viewBox='0 0 24 24' fill='none' stroke='currentColor' strokeWidth='1.7' className='h-5 w-5' aria-hidden='true'><path d='m12 4 8 4-8 4-8-4 8-4Z' /><path d='m4 12 8 4 8-4M4 16l8 4 8-4' /></svg></div><h4 className='mt-4 text-sm font-semibold text-white'>{title}</h4><p className='mt-2 text-xs leading-6 text-[#9aa9bf]'>{text}</p><div className='mt-auto flex flex-wrap gap-2 pt-4'>{tags.map(tag => <span key={tag} className='rounded-md border border-white/[0.1] bg-white/[0.03] px-2 py-1 text-[10px] text-[#c5d1e1]'>{tag}</span>)}</div></div>
}

function HistoryPanel({ title, metrics, max, markers }: { title: string; metrics: [string, string, string][]; max: number; markers: [number, string][] }) {
  return <div className='rounded-xl border border-white/[0.08] bg-[#081523]/75 p-4'><h4 className='text-sm font-semibold text-white'>{title}</h4><div className='mt-4 grid grid-cols-2 gap-4 sm:grid-cols-4'>{metrics.map(([label, value, tone]) => <div key={label}><div className='text-[10px] text-[#7f8fa6]'>{label}</div><div className={`mt-1 text-lg font-semibold ${tone}`}>{value}</div></div>)}</div><div className='mt-6'><div className='relative h-16'><div className='absolute left-0 right-0 top-4 h-px bg-white/20' />{markers.map(([value, label], index) => <div key={label} className='absolute top-0 -translate-x-1/2' style={{ left: `${(value / max) * 100}%` }}><div className={`h-3 w-3 rounded-full border-2 border-[#081523] ${index === 0 ? 'bg-[#3892d0]' : 'bg-[#c79d51]'}`} /><div className='mt-2 whitespace-nowrap text-[10px] text-[#aebbd0]'>{label}</div></div>)}</div><div className='flex justify-between text-[10px] text-[#718096]'><span>0x</span><span>{max === 15 ? '5x' : '0,5x'}</span><span>{max === 15 ? '10x' : '1x'}</span><span>{max === 15 ? '15x' : '1,5x'}</span></div></div></div>
}
