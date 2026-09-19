'use client';

import React, { useLayoutEffect, useRef } from 'react';
import { StockDetail } from '@/data/mock-stock-details';
import { SectionCard } from '@/components/ui/section-card';
import { formatRupiah, parseNumericValue } from '@/utils/currency';

type Tone = 'positive' | 'neutral' | 'negative';
type HealthGrowth = StockDetail['healthGrowth'];
type Metric = HealthGrowth['profitability']['metrics'][number];
type GrowthVisuals = HealthGrowth['growthVisuals'];

const valueTone: Record<Tone, string> = { positive: 'text-[#2ee6ae]', neutral: 'text-white', negative: 'text-[#ff8b82]' };
const dotTone: Record<Tone, string> = { positive: 'bg-[#25d49d]', neutral: 'bg-[#9aa9bf]', negative: 'bg-[#ff7168]' };
const validatorToneClass: Record<StockDetail['thesisValidator']['rows'][number]['trendTone'], string> = {
  green: 'text-[#3ef0a9]',
  yellow: 'text-[#f59e0b]',
  red: 'text-[#ef4444]',
  slate: 'text-[#b6c2d4]',
};

function SectionIcon({ icon }: { icon: string }) {
  const props = { viewBox: '0 0 24 24', fill: 'none', stroke: 'currentColor', strokeWidth: 1.8, className: 'h-4 w-4', 'aria-hidden': true } as const;
  if (icon === 'forensic') return <svg {...props}><circle cx='12' cy='12' r='8.5' /><path d='m8 13 2.5 2.5L16.5 9' /><path d='M12 3.5v2M20.5 12h-2M12 18.5v2M5.5 12h-2' /></svg>;
  if (icon === 'dividend') return <svg {...props}><circle cx='12' cy='12' r='8.5' /><path d='M15 8.5c-.7-.7-1.5-1-2.7-1-1.4 0-2.4.8-2.4 1.9 0 3 5.2 1.1 5.2 4.3 0 1.2-1.1 2-2.7 2-1.2 0-2.3-.4-3.1-1.2M12 5.5v13' /></svg>;
  if (icon === 'quarterly') return <svg {...props}><rect x='3.5' y='4' width='17' height='16' rx='2' /><path d='M7.5 15v-3M12 15V9M16.5 15v-5' /></svg>;
  return <svg {...props}><path d='M4 17 9 12l3 3 7-8' /><path d='M15 7h4v4' /><path d='M4 20h16' /></svg>;
}

function Arrow() {
  return <svg viewBox='0 0 22 16' fill='none' className='h-4 w-5 text-[#2ee6ae]' aria-hidden='true'><path d='M1 14 8 7l4 4 8-9M14 2h6v6' stroke='currentColor' strokeWidth='2' strokeLinecap='round' strokeLinejoin='round' /></svg>;
}

function GrowthMetric({ label, value, period, arrow = false, className = '', valueClass = '' }: { label: string; value: string; period?: string; arrow?: boolean; className?: string; valueClass?: string }) {
  return <div className={'min-w-0 border-r border-white/[0.08] px-4 py-3 last:border-r-0 ' + className}><div className='text-[11px] leading-[1.35] text-[#aebbd0]'>{label}</div><div className='mt-2 flex items-center gap-3'><span className={'font-semibold tracking-[-0.02em] text-[#2ee6ae] ' + (valueClass || 'text-[23px]')}>{value}</span>{arrow && <Arrow />}</div>{period && <div className='mt-1 text-[11px] text-[#8090a7]'>{period}</div>}</div>;
}

function Momentum({ value, tone }: { value: string; tone: Tone }) {
  const className = tone === 'positive' ? 'bg-[#073c35] text-[#2ee6ae]' : tone === 'negative' ? 'bg-[#47211f] text-[#ff8b82]' : 'bg-[#1d2a3b] text-[#c5d1e1]';
  return <span className={'inline-flex items-center gap-2 rounded-md px-3 py-2 text-xs font-semibold ' + className}>{value}{tone === 'positive' && <svg viewBox='0 0 20 16' fill='none' className='h-3.5 w-4' aria-hidden='true'><path d='M1 14 7 8l4 3 7-8M12 3h6v6' stroke='currentColor' strokeWidth='2' strokeLinecap='round' strokeLinejoin='round' /></svg>}</span>;
}

function MetricCard({ metric }: { metric: Metric }) {
  return <div className='rounded-lg border border-white/[0.09] bg-[#081523]/75 p-4'><div className='text-[11px] text-[#aebbd0]'>{metric.label}</div><div className={'mt-2 text-[22px] font-semibold tracking-[-0.02em] ' + valueTone[metric.tone as Tone]}>{metric.value}</div><div className='mt-1.5 flex items-start gap-2 text-[11px] leading-relaxed text-[#8090a7]'><span className={'mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full ' + dotTone[metric.tone as Tone]} aria-hidden='true' />{metric.context}</div></div>;
}

function HealthSection({ icon, title, subtitle, children }: { icon: string; title: string; subtitle: string; children: React.ReactNode }) {
  return <SectionCard icon={<SectionIcon icon={icon} />} title={title} subtitle={subtitle} className='p-5 md:p-6'>{children}</SectionCard>;
}

function MetricGrid({ metrics }: { metrics: Metric[] }) {
  return <div className='grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-5'>{metrics.map((metric) => <MetricCard key={metric.label} metric={metric} />)}</div>;
}


function QuarterlyGrowthCheck({ stock }: { stock: StockDetail }) {
  const tableScrollRef = useRef<HTMLDivElement>(null);
  const validator = stock.thesisValidator;

  useLayoutEffect(() => {
    const tableScroll = tableScrollRef.current;
    if (tableScroll) tableScroll.scrollLeft = tableScroll.scrollWidth - tableScroll.clientWidth;
  }, []);
  const rows = validator.rows.filter((row) => ['Revenue YoY (%)', 'Gross Margin (Actual %)', 'Net Income YoY (%)', 'OCF / NI Ratio (x)', 'Interest Expense (M Rp)'].includes(row.item));
  const quarterFields = ['q3', 'q4', 'q1', 'q2'] as const;
  const comparisonPeriods = validator.quarters.map((quarter) => {
    const match = quarter.match(/^(Q[1-4]) (\d{4})$/);
    return match ? `${match[1]} ${match[2]} vs ${match[1]} ${Number(match[2]) - 1}` : quarter;
  });
  const titles: Record<string, string> = {
    'Revenue YoY (%)': 'Revenue YoY',
    'Gross Margin (Actual %)': 'Gross Margin',
    'Net Income YoY (%)': 'Net Income YoY',
    'OCF / NI Ratio (x)': 'OCF / NI',
    'Interest Expense (M Rp)': 'Interest Expense',
  };

  return <HealthSection icon='quarterly' title='Quarterly Growth Check' subtitle='Recent operating performance compared with the same quarter of the previous year.'><div ref={tableScrollRef} className='overflow-x-auto rounded-xl border border-white/8 bg-[#07111c]/60'><table className='w-full min-w-[1080px] text-left text-xs'><thead className='border-b border-white/8 bg-white/4 text-[11px] font-semibold text-[#8e9bb0]'><tr><th className='sticky left-0 z-20 min-w-[190px] border-r border-white/8 bg-[#0b1928] px-4 py-3'>METRIC</th>{comparisonPeriods.map((period) => <th key={period} className='min-w-[175px] whitespace-nowrap px-3 py-3 text-center'>{period}</th>)}<th className='min-w-[220px] px-4 py-3 text-left'>STATUS</th></tr></thead><tbody className='divide-y divide-white/6 text-white'>{rows.map((row) => <tr key={row.item} className='transition hover:bg-white/3'><td className='sticky left-0 z-10 min-w-[190px] border-r border-white/6 bg-[#0b1928] px-4 py-3 font-medium text-[#d4dcec]'>{titles[row.item] ?? row.item}</td>{quarterFields.map((field, index) => <td key={field} className={index === quarterFields.length - 1 ? 'whitespace-nowrap px-3 py-3 text-center font-semibold text-white' : 'whitespace-nowrap px-3 py-3 text-center text-[#9aa9bf]'}>{row[field] ?? '-'}</td>)}<td className={'whitespace-nowrap px-4 py-3 text-left font-semibold ' + validatorToneClass[row.trendTone]}>{row.trend}</td></tr>)}</tbody></table></div></HealthSection>;
}
type DividendData = StockDetail['dividendConsistency'];
type DividendRow = DividendData['rows'][number];

const dividendPeriodKeys: Record<string, keyof DividendRow> = {
  '2026 (Proyeksi)': 'p2026',
  '2025': 'y2025',
  '2024': 'y2024',
  '2023': 'y2023',
  '2022': 'y2022',
  'Avg (4Y)': 'avg4Y',
};

function parseDividendValue(value: string) {
  return parseNumericValue(value.replace(/[^0-9.,-]/g, '')) || 0;
}

function getDividendMetricLabel(row: DividendRow) {
  return row.item === 'DPS [Rp]' ? 'DPS (Rp)' : row.item;
}

function formatDividendMetricValue(row: DividendRow, period: string) {
  const value = row[dividendPeriodKeys[period]] ?? '-';
  return row.item === 'DPS [Rp]' ? formatRupiah(parseDividendValue(value)).replace(/^Rp/, '') : value;
}

function DividendTrendChart({ periods, dpsValues, yieldValues }: { periods: string[]; dpsValues: number[]; yieldValues: number[] }) {
  const width = 680;
  const height = 250;
  const padding = { top: 24, right: 70, bottom: 36, left: 70 };
  const plotHeight = height - padding.top - padding.bottom;
  const maxDps = Math.max(...dpsValues, 1);
  const maxYield = Math.max(...yieldValues, 1);
  const x = (index: number) => padding.left + (index / Math.max(periods.length - 1, 1)) * (width - padding.left - padding.right);
  const yDps = (value: number) => padding.top + ((maxDps - value) / maxDps) * plotHeight;
  const yYield = (value: number) => padding.top + ((maxYield - value) / maxYield) * plotHeight;
  const dpsLine = dpsValues.map((value, index) => `${x(index)},${yDps(value)}`).join(' ');
  const yieldLine = yieldValues.map((value, index) => `${x(index)},${yYield(value)}`).join(' ');

  return <div className='flex h-full flex-col rounded-xl border border-white/[0.09] bg-[#081523]/75 p-4'><div className='text-sm font-semibold text-white'>Dividend Trend</div><div className='mt-1 text-[11px] text-[#8e9db3]'>DPS and yield, each on its own scale</div><div className='mt-3 flex flex-wrap gap-x-4 gap-y-2 text-[10px] text-[#b6c5d8]'><span className='flex items-center gap-2'><svg viewBox='0 0 28 8' className='h-2 w-7' aria-hidden='true'><path d='M1 4h26' stroke='#f2bb5c' strokeWidth='2' /><circle cx='14' cy='4' r='2.5' fill='#f2bb5c' /></svg>DPS (Rp) · left axis</span><span className='flex items-center gap-2'><svg viewBox='0 0 28 8' className='h-2 w-7' aria-hidden='true'><path d='M1 4h26' stroke='#2ee6ae' strokeWidth='2' strokeDasharray='3 2' /><rect x='11.5' y='1.5' width='5' height='5' fill='#2ee6ae' /></svg>Yield (%) · right axis</span></div><svg viewBox={`0 0 ${width} ${height}`} className='mt-2 h-[190px] w-full' role='img' aria-label='Dividend per share and dividend yield trend'>
    {[0, 1, 2, 3].map((level) => { const dpsValue = maxDps * (1 - level / 3); const yieldValue = maxYield * (1 - level / 3); const y = padding.top + (plotHeight * level) / 3; return <g key={level}><line x1={padding.left} x2={width - padding.right} y1={y} y2={y} stroke='rgba(255,255,255,0.08)' /><text x={padding.left - 8} y={y + 4} textAnchor='end' fill='#8e9db3' fontSize='10'>{formatRupiah(dpsValue).replace(/^Rp/, '')}</text><text x={width - padding.right + 8} y={y + 4} textAnchor='start' fill='#8e9db3' fontSize='10'>{yieldValue.toFixed(0)}%</text></g>; })}
    <polyline points={dpsLine} fill='none' stroke='#f2bb5c' strokeWidth='2.5' strokeLinejoin='round' />
    <polyline points={yieldLine} fill='none' stroke='#2ee6ae' strokeWidth='2.5' strokeDasharray='6 4' strokeLinejoin='round' />
    {periods.map((period, index) => <g key={period}><circle cx={x(index)} cy={yDps(dpsValues[index])} r='4' fill='#f2bb5c' stroke='#081523' strokeWidth='2' /><rect x={x(index) - 3.5} y={yYield(yieldValues[index]) - 3.5} width='7' height='7' fill='#2ee6ae' stroke='#081523' strokeWidth='1.5' /><text x={x(index)} y={height - 10} textAnchor='middle' fill='#8e9db3' fontSize='10'>{period}</text></g>)}
    <text x='14' y='125' transform='rotate(-90 14 125)' textAnchor='middle' fill='#f2bb5c' fontSize='13' fontWeight='700'>DPS (Rp)</text>
    <text x='666' y='125' transform='rotate(90 666 125)' textAnchor='middle' fill='#2ee6ae' fontSize='13' fontWeight='700'>Yield (%)</text>
  </svg></div>;
}

function DividendGrowthSection({ dividend }: { dividend: DividendData }) {
  const tableScrollRef = useRef<HTMLDivElement>(null);
  const dps = dividend.rows.find((row) => row.item === 'DPS [Rp]');
  const yieldRow = dividend.rows.find((row) => row.item === 'Yield [%]');
  const chartSourcePeriods = ['2022', '2023', '2024', '2025', '2026 (Proyeksi)'];
  const chartPeriods = chartSourcePeriods.map((period) => period.replace(' (Proyeksi)', 'P'));
  const getValues = (row: DividendRow | undefined) => chartSourcePeriods.map((period) => parseDividendValue(row?.[dividendPeriodKeys[period]] ?? '0'));
  const tablePeriods = ['2022', '2023', '2024', '2025'];
  const dividendMetrics = [
    { label: 'DPS', row: dps },
    { label: 'DPR', row: dividend.rows.find((row) => row.item === 'DPR [%]') },
    { label: 'Yield', row: yieldRow },
  ];
  const dividendProfileSections = [
    { title: 'Historical Performance', period: 'Avg (4Y)' },
    { title: '2026 Projection', period: '2026 (Proyeksi)' },
  ];
  React.useLayoutEffect(() => {
    const tableScroll = tableScrollRef.current;
    if (tableScroll) tableScroll.scrollLeft = tableScroll.scrollWidth - tableScroll.clientWidth;
  }, []);

  return (
    <HealthSection icon='dividend' title='Dividends' subtitle='Dividend per share, yield, and payout trends across recent fiscal years.'>
      <div className='grid grid-cols-1 items-stretch gap-4 xl:grid-cols-[1fr_1.15fr]'>
        <DividendTrendChart periods={chartPeriods} dpsValues={getValues(dps)} yieldValues={getValues(yieldRow)} />
        <div className='flex min-w-0 flex-col gap-3'>
          <div className='grid grid-cols-1 gap-3 sm:grid-cols-2'>
            {dividendProfileSections.map((section) => <div key={section.period} className='overflow-hidden rounded-lg border border-white/[0.09] bg-[#081523]/70'>
              <div className='border-b border-white/[0.08] px-4 py-2 text-[11px] font-semibold uppercase tracking-[0.08em] text-[#8fa0b8]'>{section.period === 'Avg (4Y)' ? <>Historical Performance · Avg (4Y)</> : '2026 Projection'}</div>
              <div className='grid grid-cols-1 sm:grid-cols-3'>
                {dividendMetrics.map((metric) => <GrowthMetric key={metric.label} label={metric.label} value={metric.row ? (metric.row.item === 'DPS [Rp]' ? formatRupiah(parseDividendValue(metric.row[dividendPeriodKeys[section.period]] ?? '0')) : formatDividendMetricValue(metric.row, section.period)) : '-'} className='px-2' valueClass='whitespace-nowrap text-[14px]' />)}
              </div>
            </div>)}
          </div>
          <div className='min-w-0 overflow-x-auto rounded-lg border border-white/[0.09] bg-[#081523]/70'>
            <table className='w-full min-w-[540px] text-left text-xs'>
              <caption className='border-b border-white/[0.08] px-4 py-2 text-left text-[11px] font-semibold uppercase tracking-[0.08em] text-[#8fa0b8]'>Dividend History</caption>
              <thead className='border-b border-white/8 bg-white/4 text-[11px] font-semibold text-[#8e9bb0]'>
                <tr>
                  <th className='sticky left-0 z-20 min-w-[60px] border-r border-white/8 bg-[#0b1928] px-2 py-3'>METRIC</th>
                  {tablePeriods.map((period) => <th key={period} className='whitespace-nowrap px-3 py-3 text-center'>{period}</th>)}
                </tr>
              </thead>
              <tbody className='divide-y divide-white/6 text-white'>
                {dividend.rows.map((row) => <tr key={row.item} className='transition hover:bg-white/3'>
                  <td className='sticky left-0 z-10 min-w-[60px] border-r border-white/6 bg-[#0b1928] px-2 py-3 font-medium text-[#d4dcec]'>{getDividendMetricLabel(row)}</td>
                  {tablePeriods.map((period, index) => <td key={period} className={index === tablePeriods.length - 1 ? 'whitespace-nowrap px-3 py-3 text-center font-semibold text-white' : 'whitespace-nowrap px-3 py-3 text-center text-[#9aa9bf]'}>{formatDividendMetricValue(row, period)}</td>)}
                </tr>)}
              </tbody>
            </table>
          </div>
        </div>
      </div>
    </HealthSection>
  );
}
function GroupedBarChart({ title, subtitle, revenue, netIncome, periods }: { title: string; subtitle: string; revenue: number[]; netIncome: number[]; periods: string[] }) {
  const width = 720;
  const height = 220;
  const padding = { top: 24, right: 18, bottom: 34, left: 48 };
  const plotWidth = width - padding.left - padding.right;
  const plotHeight = height - padding.top - padding.bottom;
  const max = Math.max(...revenue, ...netIncome, 1);
  const y = (value: number) => padding.top + ((max - value) / max) * plotHeight;
  const groupWidth = plotWidth / Math.max(periods.length, 1);
  const barWidth = Math.min(22, groupWidth * 0.28);
  const baseline = y(0);

  return <div className='rounded-lg border border-white/[0.09] bg-[#081523]/75 p-4'><div className='text-sm font-semibold text-white'>{title}</div><div className='mt-1 text-[11px] text-[#8e9db3]'>{subtitle}</div><div className='mt-3 flex items-center gap-4 text-[10px] text-[#9aa9bf]'><span className='flex items-center gap-1.5'><span className='h-2 w-2 rounded-full bg-[#2388ff]' />Revenue</span><span className='flex items-center gap-1.5'><span className='h-2 w-2 rounded-full bg-[#2ee6ae]' />Net Income</span></div><svg viewBox={`0 0 ${width} ${height}`} className='mt-2 h-[220px] w-full' role='img' aria-label={title}>{[0, 1, 2, 3].map((level) => { const value = max - (max * level) / 3; return <g key={level}><line x1={padding.left} x2={width - padding.right} y1={y(value)} y2={y(value)} stroke='rgba(255,255,255,0.08)' /><text x={padding.left - 8} y={y(value) + 4} textAnchor='end' fill='#7f8fa6' fontSize='10'>{Math.round(value)}</text></g>; })}{periods.map((period, index) => { const center = padding.left + groupWidth * index + groupWidth / 2; const revenueHeight = Math.max(0, baseline - y(revenue[index] ?? 0)); const incomeHeight = Math.max(0, baseline - y(netIncome[index] ?? 0)); return <g key={period}><rect x={center - barWidth - 2} y={baseline - revenueHeight} width={barWidth} height={revenueHeight} rx='2' fill='#2388ff' /><rect x={center + 2} y={baseline - incomeHeight} width={barWidth} height={incomeHeight} rx='2' fill='#2ee6ae' /><text x={center} y={height - 10} textAnchor='middle' fill='#7f8fa6' fontSize='10'>{period}</text></g>; })}</svg></div>;
}

function DotLineChart({ title, subtitle, primary, secondary, primaryColor, secondaryColor, primaryLabel, secondaryLabel, periods }: { title: string; subtitle: string; primary: number[]; secondary?: number[]; primaryColor: string; secondaryColor?: string; primaryLabel: string; secondaryLabel?: string; periods: string[] }) {
  const width = 720;
  const height = 220;
  const padding = { top: 24, right: 18, bottom: 34, left: 48 };
  const values = [...primary, ...(secondary ?? [])];
  const min = Math.min(...values, 0);
  const max = Math.max(...values, 1);
  const range = max - min || 1;
  const x = (index: number) => padding.left + (index / Math.max(periods.length - 1, 1)) * (width - padding.left - padding.right);
  const y = (value: number) => padding.top + ((max - value) / range) * (height - padding.top - padding.bottom);
  const line = (series: number[]) => series.map((value, index) => `${x(index)},${y(value)}`).join(' ');
  const renderSeries = (series: number[], color: string) => <>{series.map((value, index) => <circle key={`${index}-${value}`} cx={x(index)} cy={y(value)} r='3.5' fill={color} stroke='#081523' strokeWidth='1.5' />)}</>;

  return <div className='rounded-lg border border-white/[0.09] bg-[#081523]/75 p-4'><div className='text-sm font-semibold text-white'>{title}</div><div className='mt-1 text-[11px] text-[#8e9db3]'>{subtitle}</div><div className='mt-3 flex items-center gap-4 text-[10px] text-[#9aa9bf]'><span className='flex items-center gap-1.5'><span className='h-2 w-2 rounded-full' style={{ backgroundColor: primaryColor }} />{primaryLabel}</span>{secondary && secondaryLabel && <span className='flex items-center gap-1.5'><span className='h-2 w-2 rounded-full' style={{ backgroundColor: secondaryColor }} />{secondaryLabel}</span>}</div><svg viewBox={`0 0 ${width} ${height}`} className='mt-2 h-[220px] w-full' role='img' aria-label={title}>{[0, 1, 2, 3].map((level) => { const value = max - (range * level) / 3; return <g key={level}><line x1={padding.left} x2={width - padding.right} y1={y(value)} y2={y(value)} stroke='rgba(255,255,255,0.08)' /><text x={padding.left - 8} y={y(value) + 4} textAnchor='end' fill='#7f8fa6' fontSize='10'>{Math.round(value)}</text></g>; })}<polyline points={line(primary)} fill='none' stroke={primaryColor} strokeWidth='2.5' />{renderSeries(primary, primaryColor)}{secondary && <><polyline points={line(secondary)} fill='none' stroke={secondaryColor} strokeWidth='2.5' />{renderSeries(secondary, secondaryColor ?? '#2ee6ae')}</>}{periods.map((period, index) => <text key={period} x={x(index)} y={height - 10} textAnchor='middle' fill='#7f8fa6' fontSize='10'>{period}</text>)}</svg></div>;
}


function GrowthSection({ data, visuals }: { data: HealthGrowth['growth']; visuals: GrowthVisuals }) {
  const chartPeriods = visuals.periods;
  const chartRevenue = visuals.revenueNetIncome.revenue;
  const chartNetIncome = visuals.revenueNetIncome.netIncome;
  const chartEps = visuals.eps;
  const chartRevenueGrowth = visuals.growthRate.revenue;
  const chartEpsGrowth = visuals.growthRate.eps;

  return <HealthSection icon='growth' title='Growth' subtitle='Historical performance, current momentum, growth quality, and quarterly confirmation.'><div className='grid grid-cols-1 gap-4 xl:grid-cols-[1.4fr_1fr]'><div className='overflow-hidden rounded-lg border border-white/[0.09] bg-[#081523]/70'><div className='border-b border-white/[0.08] px-4 py-2 text-[11px] font-semibold uppercase tracking-[0.08em] text-[#8fa0b8]'>Revenue Performance</div><div className='grid grid-cols-1 sm:grid-cols-4'><GrowthMetric label='Revenue CAGR (Historical)' value={data.revenueHistorical.value} period={data.revenueHistorical.period} arrow /><GrowthMetric label='Revenue CAGR (5Y)' value={data.revenueFiveYear.value} period={data.revenueFiveYear.period} arrow /><GrowthMetric label='Revenue Growth (YoY)' value={data.revenueYoY.value} period={data.revenueYoY.period} arrow /><div className='px-4 py-3'><div className='text-[11px] text-[#aebbd0]'>Revenue Momentum</div><div className='mt-2'><Momentum value={data.revenueMomentum.value} tone={data.revenueMomentum.tone} /></div><div className='mt-1 text-[11px] text-[#8090a7]'>{data.revenueMomentum.period}</div></div></div></div><div className='overflow-hidden rounded-lg border border-white/[0.09] bg-[#081523]/70'><div className='border-b border-white/[0.08] px-4 py-2 text-[11px] font-semibold uppercase tracking-[0.08em] text-[#8fa0b8]'>Earnings Power</div><div className='grid grid-cols-1 sm:grid-cols-3'><GrowthMetric label='EPS Growth (Historical)' value={data.epsHistorical.value} period={data.epsHistorical.period} arrow /><GrowthMetric label='EPS Growth (5Y)' value={data.epsFiveYear.value} period={data.epsFiveYear.period} arrow /><div className='px-4 py-3'><div className='text-[11px] text-[#aebbd0]'>EPS Momentum</div><div className='mt-2'><Momentum value={data.epsMomentum.value} tone={data.epsMomentum.tone} /></div><div className='mt-1 text-[11px] text-[#8090a7]'>{data.epsMomentum.period}</div></div></div></div></div><div className='mt-4 grid grid-cols-1 gap-4 xl:grid-cols-2'><GroupedBarChart title='Revenue & Net Income' subtitle='Rp Million' revenue={chartRevenue} netIncome={chartNetIncome} periods={chartPeriods} /><DotLineChart title='EPS (Earning Per Share)' subtitle='Rp per share' primary={chartEps} primaryColor='#f0b85b' primaryLabel='EPS' periods={chartPeriods} /><DotLineChart title='Historical Growth Rate' subtitle='Year-over-year growth' primary={chartRevenueGrowth} secondary={chartEpsGrowth} primaryColor='#42a5ff' secondaryColor='#2ee6ae' primaryLabel='Revenue Growth (YoY)' secondaryLabel='EPS Growth (YoY)' periods={chartPeriods} /><DotLineChart title='Operating Cash Flow & Net Income' subtitle='Rp Million' primary={visuals.operatingCashFlow} secondary={chartNetIncome} primaryColor='#b17cff' secondaryColor='#2ee6ae' primaryLabel='Operating Cash Flow' secondaryLabel='Net Income' periods={chartPeriods} /></div></HealthSection>;
}

export function GrowthTabContent({ stock }: { stock: StockDetail }) {
  const data = stock.healthGrowth;
  const visuals = data.growthVisuals;
  return <div className='space-y-6'><header className='flex flex-col justify-between gap-4 md:flex-row md:items-center'><div><h2 className='text-3xl font-bold tracking-tight text-white'>Growth</h2><p className='mt-1 text-sm text-[#aeb9ca]'>Understand the company&apos;s growth trajectory, momentum, growth quality, and recent operating performance.</p></div></header><GrowthSection data={data.growth} visuals={visuals} /><HealthSection icon='forensic' title='Growth Quality / Forensic Growth' subtitle='Supporting evidence for the quality and sustainability of reported growth.'><MetricGrid metrics={data.forensic.metrics} /></HealthSection><QuarterlyGrowthCheck stock={stock} /><DividendGrowthSection dividend={stock.dividendConsistency} /></div>;
}
