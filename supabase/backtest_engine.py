#!/usr/bin/env python3
"""
backtest_engine.py
==================

Fase 1 backtest historis - daftar kasus dan metrik harga murni.

Ruang lingkup
-------------
Modul ini **hanya** berisi rumus murni (tanpa I/O) untuk Tahap A dan Tahap B
bagian harga dari `docs/BACKTEST_ARCHITECTURE.md`:

* :func:`select_backtest_cases` - daftar kasus dari aturan `Helper!C2#` (Tahap A)
* :func:`analysis_date_for`     - satu-satunya tempat keputusan D1
* :func:`as_of_price`           - close point-in-time, didelegasikan ke
  :mod:`pit_primitives`
* :func:`price_windows`         - `high_nm` / `low_nm` / peak / trough / peak month
* :func:`price_metrics`         - komposisi satu baris hasil (harga + status + flag)

Valuasi per kasus (fase 2), verdict (fase 3), dan RPC/UI (fase 4) **tidak** ada
di sini. Lihat `docs/BACKTEST_ARCHITECTURE.md` bagian 4.3.

Kenapa tanpa transport
----------------------
Modul ini sengaja **tidak** mengimpor `requests`, `calculation_v1_common`, atau
`SupabaseRest`. Dua alasan:

1. Rumusnya bisa diuji penuh secara offline (`tests/test_backtest_engine.py`).
2. Tidak ada jalan bagi rumus kasus untuk membaca data di luar cutoff kasus itu.
   Semua yang dibaca harus sudah dipotong oleh pemanggil.

Konstanta :data:`DECIMAL_PRECISION` didefinisikan di sini, bukan diimpor dari
`calculation_v1_common`, justru supaya alasan (1) tetap benar: modul itu menarik
`requests` secara transitif. Nilainya sama dan dijaga oleh uji.

Aturan yang direproduksi (terverifikasi ke workbook)
----------------------------------------------------
* `Helper!C2#` = semua tahun annual **kecuali dua tahun terkecil**.
* Kasus = semua kuartal pada tahun `base_year + 1` untuk setiap `base_year` valid.
* `Ret 3M`  = `[T0, EDATE(T0,+3)]`   - ujung awal **inklusif**
* `Ret 6M`  = `(EDATE(T0,+3), EDATE(T0,+6)]`
* `Ret 9M`  = `(EDATE(T0,+6), EDATE(T0,+9)]`
* `Ret 12M` = `(EDATE(T0,+9), EDATE(T0,+12)]`
* `Harga Peak` / `Harga trough` = `[T0, EDATE(T0,+12)]` - kedua ujung inklusif
* `High = 0 ? Close : High` dan `Low = 0 ? Close : Low`

Aturan High/Low nol itu **material**: ada 865 baris `high_price = 0` di
`prices_daily` (DSSA 539, GEMA 195, ARII 52, INDS 38, GOLD 34, IPOL 4, WIFI 3)
dan AUTO punya nol. Tanpa substitusi, `MAX(High)` mengembalikan 0 dan seluruh
`Ret nM` / `Harga Peak` untuk ticker-ticker itu salah.

Catatan bahasa
--------------
Sesuai aturan gaya repo untuk modul baru ini: komentar dan docstring berbahasa
Indonesia, sedangkan identifier kode berbahasa Inggris. Teks yang disimpan ke
database (`description`, `formula_text`) tetap berbahasa Inggris supaya sebaris
dengan baris registry yang sudah ada (`VALUATION_CURRENT` di migration 0014).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal, InvalidOperation, localcontext
from typing import Any, Iterable, Mapping, Sequence

from calculation_registry import sha256_json, sha256_text
from pit_primitives import PricePoint
from pit_primitives import as_of_price as _pit_as_of_price
from pit_primitives import edate as _pit_edate

__all__ = [
    'BACKTEST_METHODOLOGY',
    'BACKTEST_METHOD_CODES',
    'BacktestCase',
    'BacktestError',
    'Bar',
    'CASE_PROVENANCE_FLAGS_PHASE_2',
    'CODE_VERSION',
    'CONSENSUS_MIN_VALID_METHODS',
    'CONSENSUS_NOT_AVAILABLE',
    'CONSENSUS_UNDERVALUED_CLASSES',
    'DECIMAL_PRECISION',
    'FLAG_ANALYSIS_PRICE_UNAVAILABLE',
    'FLAG_BASE_PRICE_ZERO',
    'FLAG_CONSENSUS_BELOW_THREE_METHODS',
    'FLAG_CONSENSUS_DENOMINATOR_UNRESOLVED',
    'FLAG_HIGH_ZERO_SUBSTITUTED',
    'FLAG_LOW_ZERO_SUBSTITUTED',
    'FLAG_METHOD_UNAVAILABLE',
    'FLAG_VALUATION_UNAVAILABLE',
    'FLAG_MOS_DENOMINATOR_ZERO',
    'FLAG_MOS_MAIN_UNAVAILABLE',
    'FLAG_NEGATIVE_INTRINSIC_VALUE_VALID',
    'FLAG_NO_PRICE_HISTORY',
    'FLAG_POINT_IN_TIME_UNAVAILABLE_DATE',
    'FLAG_STOCK_TYPE_LATEST_SNAPSHOT',
    'FLAG_WINDOW_EMPTY',
    'FLAG_WINDOW_PARTIAL',
    'FLAG_VERDICT_MOS_UNDEFINED',
    'FLAG_VERDICT_NO_CONSENSUS',
    'FLAG_VERDICT_NO_PRICE_WINDOW',
    'FLAG_YEARS_AVAILABLE_TRUNCATED',
    'MAIN_METHOD_PETER_LYNCH',
    'MAIN_METHOD_TYPE_SECTOR',
    'MAIN_METHOD_WEIGHTED_TYPES',
    'MAGNITUDE_THRESHOLD',
    'CASE_MIN_AGE_MONTHS',
    'METHOD_CODE',
    'METHOD_VERDICT_NOT_APPLICABLE',
    'METHOD_VERDICT_OVERVALUED',
    'METHOD_VERDICT_UNDERVALUED',
    'METHOD_VERSION',
    'MOS_VERDICT_THRESHOLD',
    'PRICE_WINDOW_METRIC_FLAGS',
    'PriceWindows',
    'STATUS_APPROXIMATED',
    'STATUS_NOT_CALCULABLE',
    'STATUS_UNAVAILABLE',
    'STATUS_VALID',
    'VERDICTS',
    'VERDICTS_CURRENT',
    'VERDICT_DOWNSIDE',
    'VERDICT_DOWNSIDE_OTHER',
    'VERDICT_DOWNSIDE_UNDERVALUED',
    'VERDICT_UPSIDE',
    'VERDICT_UPSIDE_OTHER',
    'VERDICT_UPSIDE_UNDERVALUED',
    'WINDOW_HORIZONS_MONTHS',
    'analysis_date_for',
    'annual_years',
    'as_of_price',
    'backtest_methodology_seed',
    'case_provenance_flags',
    'classify_consensus',
    'datedif_months',
    'decimal_or_none',
    'edate',
    'is_case_mature',
    'magnitude_for',
    'method_verdict',
    'mos_for',
    'normalize_bars',
    'price_metrics',
    'price_windows',
    'resolve_case_years_available',
    'resolve_consensus',
    'resolve_main_method',
    'select_backtest_cases',
    'select_mature_cases',
    'unavailable_valuation_case_metrics',
    'valuation_case_metrics',
    'verdict_case_metrics',
    'verdict_for',
    'verdict_mos_for',
    'valid_base_years',
]

#: Presisi aritmetika desimal. Sama dengan `calculation_v1_common.DECIMAL_PRECISION`
#: (dijaga oleh uji), tapi didefinisikan lokal supaya modul ini bebas transport.
DECIMAL_PRECISION = 34

#: Versi kode yang menghasilkan baris backtest. Dipakai di `calculation_runs`.
CODE_VERSION = 'stocklens-backtest-v1'

METHOD_CODE = 'BACKTEST_HISTORICAL'

#: Versi definisi metodologi. Dinaikkan dari `1.0.0` ke `1.1.0` ketika Fase 2
#: menambahkan aturan valuasi/konsensus/MoS ke `formula_text` dan
#: `parameter_spec`: hash-nya berubah, dan baris 1.0.0 harus tetap ada supaya
#: hasil Fase 1 yang sudah tersimpan tetap bisa direproduksi. `run_backtest`
#: menolak memakai baris lama bila hash-nya berbeda
#: (`BACKTEST_METHODOLOGY_REGISTRY_DRIFT`), jadi versi baru adalah satu-satunya
#: cara yang tidak menimpa sejarah.
METHOD_VERSION = '1.3.0'

#: Batas window harga relatif terhadap tanggal analisis, dalam bulan.
WINDOW_HORIZONS_MONTHS = (3, 6, 9, 12)


class BacktestError(RuntimeError):
    """Dilempar bila input melanggar invariant data yang sudah didokumentasikan."""


# --------------------------------------------------------------------------
# Kosakata status dan flag
# --------------------------------------------------------------------------
# `calculation_status` memakai kosakata yang sudah dipakai `calc_valuation_*`
# (blueprint bagian 3.5) supaya satu arti di seluruh repo:
#
#   VALID          nilai dihitung apa adanya
#   APPROXIMATED   nilai ada, tapi ada caveat terdokumentasi
#   NOT_CALCULABLE input ada tapi penjaga terdokumentasi menolak nilainya
#   UNAVAILABLE    input hilang, jadi nilainya tidak mungkin ada

STATUS_VALID = 'VALID'
STATUS_APPROXIMATED = 'APPROXIMATED'
STATUS_NOT_CALCULABLE = 'NOT_CALCULABLE'
STATUS_UNAVAILABLE = 'UNAVAILABLE'

CALCULATION_STATUSES = (
    STATUS_VALID,
    STATUS_APPROXIMATED,
    STATUS_NOT_CALCULABLE,
    STATUS_UNAVAILABLE,
)

#: Flag kejujuran (D1/D7). Ini **bukan** caveat perhitungan: nilainya tetap
#: dihitung penuh, hanya provenance-nya belum point-in-time. Karena itu flag ini
#: tidak menurunkan status ke `APPROXIMATED` - pola yang sama dengan
#: `valuation_engine._status_for`, yang mengecualikan `POINT_IN_TIME_UNVERIFIED`.
FLAG_POINT_IN_TIME_UNAVAILABLE_DATE = 'POINT_IN_TIME_UNAVAILABLE_DATE'
FLAG_STOCK_TYPE_LATEST_SNAPSHOT = 'STOCK_TYPE_LATEST_SNAPSHOT'

#: Flag caveat harga. Salah satu saja sudah menurunkan status ke `APPROXIMATED`.
FLAG_WINDOW_PARTIAL = 'WINDOW_PARTIAL'
FLAG_WINDOW_EMPTY = 'WINDOW_EMPTY'
FLAG_HIGH_ZERO_SUBSTITUTED = 'HIGH_ZERO_SUBSTITUTED'
FLAG_LOW_ZERO_SUBSTITUTED = 'LOW_ZERO_SUBSTITUTED'

#: Flag kegagalan perhitungan.
FLAG_NO_PRICE_HISTORY = 'NO_PRICE_HISTORY'
FLAG_ANALYSIS_PRICE_UNAVAILABLE = 'ANALYSIS_PRICE_UNAVAILABLE'
FLAG_BASE_PRICE_ZERO = 'BASE_PRICE_ZERO'

#: Flag yang membuat sebuah baris menjadi `APPROXIMATED` (bukan `VALID`).
PRICE_WINDOW_METRIC_FLAGS = (
    FLAG_WINDOW_PARTIAL,
    FLAG_WINDOW_EMPTY,
    FLAG_HIGH_ZERO_SUBSTITUTED,
    FLAG_LOW_ZERO_SUBSTITUTED,
)

#: Nilai yang boleh muncul di `calc_backtest_cases.analysis_price_source`.
ANALYSIS_PRICE_SOURCES = ('CLOSE_PIT', 'MANUAL')

# --------------------------------------------------------------------------
# Kosakata Fase 2 - valuasi per kasus, konsensus, dan MoS
# --------------------------------------------------------------------------

#: Lima metode workbook, dalam urutan yang dipakai workbook.
#: Kode-kode ini adalah kontrak dengan `valuation_engine.calculate_valuation_snapshot`,
#: yang mengembalikannya di `methods[].method_code`. Disalin sebagai konstanta,
#: bukan diimpor, karena `valuation_engine` menarik `calculation_v1_common` dan
#: karenanya `requests` - modul ini harus tetap bisa diuji tanpa transport.
BACKTEST_METHOD_CODES = (
    'PETER_LYNCH',
    'TYPE_SECTOR_WEIGHTED',
    'MEAN_REVERSION_PBV',
    'DDM',
    'DISCOUNTED_EARNINGS',
)

#: `SUMMARY!B69`: stalwart / fast grower memakai weighted IV, selain itu Peter Lynch.
MAIN_METHOD_TYPE_SECTOR = 'TYPE_SECTOR_WEIGHTED'
MAIN_METHOD_PETER_LYNCH = 'PETER_LYNCH'
MAIN_METHOD_WEIGHTED_TYPES = ('STALWART', 'FAST GROWER')

#: Teks konsensus saat metode valid kurang dari ambang (aturan workbook).
CONSENSUS_NOT_AVAILABLE = 'N/A'

#: Ambang minimum metode valid sebelum konsensus dianggap ada.
CONSENSUS_MIN_VALID_METHODS = 3

#: Nilai `verdict` per metode di `calc_backtest_methods`.
METHOD_VERDICT_UNDERVALUED = 'UNDERVALUED'
METHOD_VERDICT_OVERVALUED = 'OVERVALUED'
METHOD_VERDICT_NOT_APPLICABLE = 'NOT_APPLICABLE'

#: Flag Fase 2.
FLAG_METHOD_UNAVAILABLE = 'METHOD_UNAVAILABLE'
FLAG_VALUATION_UNAVAILABLE = 'VALUATION_UNAVAILABLE'
FLAG_CONSENSUS_BELOW_THREE_METHODS = 'CONSENSUS_BELOW_THREE_METHODS'
FLAG_NEGATIVE_INTRINSIC_VALUE_VALID = 'NEGATIVE_INTRINSIC_VALUE_VALID'
FLAG_MOS_DENOMINATOR_ZERO = 'MOS_DENOMINATOR_ZERO'
FLAG_MOS_MAIN_UNAVAILABLE = 'MOS_MAIN_UNAVAILABLE'
FLAG_YEARS_AVAILABLE_TRUNCATED = 'YEARS_AVAILABLE_TRUNCATED'
FLAG_CONSENSUS_DENOMINATOR_UNRESOLVED = 'CONSENSUS_DENOMINATOR_UNRESOLVED'

#: Flag provenance Fase 2 (tidak menurunkan status, sama seperti Fase 1).
CASE_PROVENANCE_FLAGS_PHASE_2 = (
    FLAG_YEARS_AVAILABLE_TRUNCATED,
    FLAG_CONSENSUS_DENOMINATOR_UNRESOLVED,
)

# --------------------------------------------------------------------------
# Kosakata Fase 3 - verdict
# --------------------------------------------------------------------------
# Rumusnya disalin apa adanya dari `docs/BACKTEST_ARCHITECTURE.md` bagian 5.4.1,
# yang diverifikasi ulang ke workbook `Stock Analyzer [Dev] Quarter.xlsm` sheet
# `Backtest_Historical (New)` kolom `AY` (Verdict by Method) dan `AZ`
# (Verdict MoS). Keduanya formula hidup di sheet itu, bukan nilai tempelan.

#: Klasifikasi `Konsensus` yang dianggap UNDERVALUED.
#:
#: Sumber kebenarannya adalah rumus workbook kolom `J` (`Konsensus`) pada
#: `Backtest_Historical (New)`, disalin apa adanya:
#:
#: ```excel
#: =IF(OR(J2="3|3", J2="3|4", J2="4|4", J2="3|5", J2="4|5", J2="5|5"),
#:     "UNDERVALUED", "OVERVALUED")
#: ```
#:
#: Hanya dua kelas, **tanpa `MIXED`**. Rumus rasio (`Ratio >= 0.6` -> UNDERVALUED,
#: `>= 0.4` -> MIXED) yang dipakai sheet valuasi sengaja **tidak** diikuti di
#: sini: sheet backtest tidak punya cabang `MIXED`, dan rumus verdict kolom `AY`
#: hanya mengenal `UNDERVALUED`/`OVERVALUED` (sisanya `FLAT`).
CONSENSUS_UNDERVALUED_CLASSES = ('3|3', '3|4', '4|4', '3|5', '4|5', '5|5')

#: Tujuh nilai `verdict` yang sah (check constraint 0025).
#:
#: `OBSERVE` masih ada di sini karena baris lama (versi metodologi 1.2.0 ke
#: bawah) menyimpannya dan check constraint-nya belum dilonggarkan. Aturan
#: sekarang **tidak pernah** menghasilkannya lagi: cabang "tidak menyentuh apa
#: pun" pada sisi overvalued menjadi `FLAT`.
VERDICTS = (
    'WIN',
    'RISK',
    'RECOVERED',
    'FLAT',
    'CONFIRMED',
    'REPRICE',
    'OBSERVE',
)

#: Verdict yang bisa dihasilkan aturan sekarang. `OBSERVE` sengaja tidak ada.
VERDICTS_CURRENT = (
    'WIN',
    'RISK',
    'RECOVERED',
    'FLAT',
    'CONFIRMED',
    'REPRICE',
)

#: Threshold harga untuk verdict: `x1.20` naik, `x0.85` turun - **sama untuk
#: kedua klasifikasi**.
#:
#: Ini penyederhanaan dari rumus sebelumnya (UNDERVALUED `1.2`/`0.8`, selain itu
#: `1.15`/`0.9`). Sekarang `UNDERVALUED` dan `OVERVALUED` hanya berbeda di nama
#: verdict, bukan di ambang harga.
VERDICT_UPSIDE = Decimal('1.20')
VERDICT_DOWNSIDE = Decimal('0.85')

#: Alias lama, dipertahankan supaya importer yang belum pindah tetap terbaca.
#: Semuanya menunjuk ambang yang sama sekarang.
VERDICT_UPSIDE_UNDERVALUED = VERDICT_UPSIDE
VERDICT_DOWNSIDE_UNDERVALUED = VERDICT_DOWNSIDE
VERDICT_UPSIDE_OTHER = VERDICT_UPSIDE
VERDICT_DOWNSIDE_OTHER = VERDICT_DOWNSIDE

#: Umur minimum kasus sebelum dianggap layak ditampilkan, dalam bulan.
#:
#: Laporan kuartalan IDX baru terbit sekitar 3-4 bulan setelah akhir periode, jadi
#: kasus yang lebih muda dari ini belum punya cukup riwayat harga untuk dinilai
#: dan **dibuang** dari hasil. Contoh: kuartal Q2 (akhir Juni) baru terbit
#: Agustus, jadi pada September belum 4 bulan dan belum ditampilkan; DSSA yang
#: kuartal terakhirnya Q1 (akhir Maret) sudah lewat 4 bulan sehingga tetap ada.
CASE_MIN_AGE_MONTHS = 4

#: Threshold `Verdict MoS`: `MoS Main >= 30%` -> UNDERVALUED (D3).
MOS_VERDICT_THRESHOLD = Decimal('0.3')

#: Ambang |return| untuk menghitung `magnitude`: >= 10% atau <= -10%.
MAGNITUDE_THRESHOLD = Decimal('0.1')

#: Flag Fase 3.
FLAG_VERDICT_NO_CONSENSUS = 'VERDICT_NO_CONSENSUS'
FLAG_VERDICT_NO_PRICE_WINDOW = 'VERDICT_NO_PRICE_WINDOW'
FLAG_VERDICT_MOS_UNDEFINED = 'VERDICT_MOS_UNDEFINED'


# --------------------------------------------------------------------------
# Normalisasi nilai
# --------------------------------------------------------------------------

def _to_date(value: Any) -> date:
    """Ubah nilai tanggal dari DB/JSON menjadi :class:`datetime.date`."""
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        text = value.strip()
        if not text:
            raise BacktestError('DATE_EMPTY')
        try:
            return date.fromisoformat(text[:10])
        except ValueError as error:
            raise BacktestError(f'DATE_INVALID: {value!r}') from error
    raise BacktestError(f'DATE_UNSUPPORTED: {value!r}')


def _to_decimal(value: Any) -> Decimal | None:
    """Ubah nilai numerik menjadi :class:`~decimal.Decimal`, atau ``None``.

    ``None`` dan string kosong dipertahankan sebagai "tidak ada nilai", bukan
    dijadikan nol (prinsip P5: yang hilang bukan nol).
    """
    if value is None:
        return None
    if isinstance(value, Decimal):
        return value
    if isinstance(value, bool):
        raise BacktestError(f'NUMBER_UNSUPPORTED: {value!r}')
    if isinstance(value, int):
        return Decimal(value)
    if isinstance(value, float):
        # Lewat repr supaya nilai yang datang dari JSON mempertahankan bentuk
        # desimal terpendeknya, bukan ekspansi biner.
        return Decimal(repr(value))
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return None
        try:
            return Decimal(text)
        except InvalidOperation as error:
            raise BacktestError(f'NUMBER_INVALID: {value!r}') from error
    raise BacktestError(f'NUMBER_UNSUPPORTED: {value!r}')


@dataclass(frozen=True)
class Bar:
    """Satu baris harga harian yang sudah dinormalisasi.

    ``high`` dan ``low`` sudah menerapkan aturan workbook `High = 0 ? Close : High`.
    Substitusi dilakukan **sekali, di sini**, bukan di dalam setiap filter, supaya
    tidak ada dua implementasi aturan yang sama - penyebab drift yang persis
    dihindari dokumen arsitektur (D3/D4).
    """

    trading_date: date
    close_price: Decimal | None
    high: Decimal | None
    low: Decimal | None
    #: True bila baris ini punya `high_price = 0` di sumber dan high-nya
    #: digantikan close. Dipakai untuk mengangkat flag di tingkat kasus.
    high_substituted: bool = False
    #: Idem untuk `low_price = 0`.
    low_substituted: bool = False

    @property
    def has_high(self) -> bool:
        return self.high is not None

    @property
    def has_low(self) -> bool:
        return self.low is not None


def normalize_bars(
    rows: Sequence[PricePoint] | Sequence[Bar] | Iterable[Mapping[str, Any]],
) -> list[Bar]:
    """Normalisasi baris ``prices_daily`` menjadi daftar :class:`Bar` terurut.

    Menerima tiga bentuk input supaya pemanggil bisa memakai apa yang sudah
    dimilikinya:

    * :class:`Bar` (dipakai uji dan pemakaian ulang),
    * :class:`pit_primitives.PricePoint` (tidak membawa high/low, jadi high dan
      low jatuh ke close),
    * ``dict`` mentah dari ``prices_daily``.

    Baris diurutkan naik menurut ``trading_date``. Tanggal ganda ditolak: tabel
    kanonik menyimpan satu baris per instrumen per tanggal, jadi duplikat berarti
    pemanggil mengirim data beberapa instrumen sekaligus.
    """
    bars: list[Bar] = []
    seen: set[date] = set()

    for row in rows:
        if isinstance(row, Bar):
            bar = row
        elif isinstance(row, PricePoint):
            bar = Bar(
                trading_date=row.trading_date,
                close_price=row.close_price,
                high=row.close_price,
                low=row.close_price,
            )
        else:
            trading_date = _to_date(row.get('trading_date'))
            close = _to_decimal(row.get('close_price'))
            high = _to_decimal(row.get('high_price'))
            low = _to_decimal(row.get('low_price'))
            # Aturan workbook: nol berarti "tidak ada data high/low", bukan
            # harga nol. Close dipakai sebagai gantinya. Bila close sendiri
            # tidak ada, nilainya tetap None (tidak diciptakan).
            high_substituted = high == 0
            low_substituted = low == 0
            bar = Bar(
                trading_date=trading_date,
                close_price=close,
                high=close if high_substituted else high,
                low=close if low_substituted else low,
                high_substituted=high_substituted,
                low_substituted=low_substituted,
            )

        if bar.trading_date in seen:
            raise BacktestError(f'DUPLICATE_TRADING_DATE: {bar.trading_date.isoformat()}')
        seen.add(bar.trading_date)
        bars.append(bar)

    bars.sort(key=lambda item: item.trading_date)
    return bars


# --------------------------------------------------------------------------
# Tahap A - daftar kasus (makro `BuildHistoricalSnapshot`)
# --------------------------------------------------------------------------

@dataclass(frozen=True)
class BacktestCase:
    """Satu kasus backtest: (instrumen, kuartal kasus, base year).

    ``as_of_financial_period_id`` adalah id baris `financial_periods` kuartal
    kasus itu. Disimpan agar orkestrator bisa menulis foreign key tanpa mencari
    ulang, dan agar kunci unik tabel hasil bisa menolak duplikat.
    """

    instrument_id: str
    as_of_financial_period_id: str
    case_quarter: str
    base_year: int
    period_end: date
    #: `available_date` kuartal kasus bila ada. Dipakai D1 sebagai sumber
    #: tanggal analisis begitu backfill selesai; sekarang masih NULL.
    available_date: date | None = None

    @property
    def case_year(self) -> int:
        return self.period_end.year


def annual_years(annual_periods: Iterable[Mapping[str, Any]]) -> list[int]:
    """Kumpulkan tahun unik dari periode annual, terurut naik.

    Tahun diambil dari `period_end`, bukan dari `period_label`, karena
    `period_label` adalah teks tampilan yang bisa berubah bentuk.
    """
    years = {_to_date(period['period_end']).year for period in annual_periods}
    return sorted(years)


def valid_base_years(annual_periods: Iterable[Mapping[str, Any]]) -> list[int]:
    """Reproduksi `Helper!C2#`: semua tahun annual kecuali dua tahun terkecil.

    Dua tahun terkecil dibuang supaya setiap kasus punya riwayat tahun yang
    sebanding - meniru posisi analis saat itu, yang juga belum punya dua tahun
    pertama. Ticker dengan dua tahun atau kurang mengembalikan daftar kosong,
    sama seperti `IF(ROWS(Years)<=2, "", ...)` di workbook.
    """
    years = annual_years(annual_periods)
    if len(years) <= 2:
        return []
    return years[2:]


def select_backtest_cases(
    annual_periods: Iterable[Mapping[str, Any]],
    quarter_periods: Iterable[Mapping[str, Any]],
) -> list[BacktestCase]:
    """Bangun daftar kasus backtest dari periode annual dan kuartal.

    Aturan makro: untuk setiap baris kuartal, `base_year = dbYear - 1`, dan
    baris diproses hanya bila `base_year` ada di daftar `Helper!C2#`. Jadi
    kasusnya adalah **semua kuartal pada tahun setelah setiap base year valid**,
    bukan semua kuartal yang ada.

    Kuartal yang tidak punya pasangan base year valid dibuang tanpa error: itu
    memang perilaku workbook (loop melewatinya), bukan data rusak.

    Hasil terurut menurut `period_end` supaya urutan penulisan deterministik.
    """
    annual = list(annual_periods)
    quarters = list(quarter_periods)
    if not annual or not quarters:
        return []

    instrument_ids = {str(row['instrument_id']) for row in [*annual, *quarters]}
    if len(instrument_ids) != 1:
        raise BacktestError('CASE_SELECTION_REQUIRES_ONE_INSTRUMENT')
    instrument_id = instrument_ids.pop()

    valid_years = set(valid_base_years(annual))
    cases: list[BacktestCase] = []
    for quarter in quarters:
        period_end = _to_date(quarter['period_end'])
        base_year = period_end.year - 1
        if base_year not in valid_years:
            continue
        available = quarter.get('available_date')
        cases.append(
            BacktestCase(
                instrument_id=instrument_id,
                as_of_financial_period_id=str(quarter['id']),
                case_quarter=f'{period_end.year}-Q{((period_end.month - 1) // 3) + 1}',
                base_year=base_year,
                period_end=period_end,
                available_date=_to_date(available) if available else None,
            )
        )

    cases.sort(key=lambda case: (case.period_end, case.case_quarter))
    return cases


def analysis_date_for(case: BacktestCase) -> date:
    """Tanggal analisis kasus - **satu-satunya** tempat keputusan D1.

    Keputusan D1 (`docs/BACKTEST_ARCHITECTURE.md` bagian 2) opsi (a): pakai
    `period_end` kuartal kasus sekarang, dengan flag
    `POINT_IN_TIME_UNAVAILABLE_DATE` karena laporan IDX sebenarnya baru terbit
    sekitar dua bulan setelah akhir periode.

    `available_date` sudah diterima sebagai argumen dan sudah dipakai begitu
    terisi, sehingga pindah ke opsi (b) nanti tidak mengubah pemanggil: backfill
    tanggal rilis saja, dan fungsi ini otomatis jadi point-in-time penuh. Itu
    sebabnya fungsi ini ada walaupun badannya sekarang hanya satu ekspresi.
    """
    return case.available_date or case.period_end


def case_provenance_flags(case: BacktestCase) -> list[str]:
    """Flag kejujuran untuk satu kasus (D1 dan D7).

    Dua batas yang harus terlihat di UI, bukan disembunyikan:

    1. `available_date` NULL -> tanggal analisis memakai akhir periode.
    2. Tipe saham memakai snapshot terklasifikasi terbaru, bukan tipe pada
       tanggal kasus. Fase 1 tidak menghitung tipe sendiri, jadi flag ini selalu
       menyala selama fase 2 belum memotong classifier per kasus.
    """
    flags: list[str] = []
    if case.available_date is None:
        flags.append(FLAG_POINT_IN_TIME_UNAVAILABLE_DATE)
    flags.append(FLAG_STOCK_TYPE_LATEST_SNAPSHOT)
    return flags


def is_case_mature(
    case: BacktestCase,
    as_of_date: date | str,
    *,
    min_age_months: int = CASE_MIN_AGE_MONTHS,
) -> bool:
    """True bila kasus sudah cukup tua untuk ditampilkan.

    Laporan kuartalan IDX baru terbit sekitar 3-4 bulan setelah akhir periode,
    jadi kuartal terbaru belum punya riwayat harga yang layak dinilai. Kasus yang
    belum melewati `min_age_months` **dibuang** dari hasil, bukan disimpan dengan
    flag: baris yang belum bisa dinilai hanya akan tampil sebagai verdict kosong
    dan mengundang pertanyaan.

    Anchor-nya `analysis_date` (`available_date` bila sudah terisi), bukan
    `period_end`, supaya begitu backfill tanggal rilis selesai batasnya otomatis
    ikut bergeser tanpa mengubah fungsi ini.

    Contoh nyata: Q2 berakhir 30 Juni dan baru terbit Agustus, jadi pada 30
    September umurnya baru 3 bulan dan belum ditampilkan; DSSA yang kuartal
    terakhirnya Q1 (31 Maret) sudah 6 bulan sehingga tetap ada.
    """
    cutoff = _to_date(as_of_date)
    # `edate` mereproduksi aritmetika bulan Excel (tanggal akhir bulan tidak
    # meluber), jadi batasnya sama dengan cara workbook menghitung `EDATE`.
    mature_from = edate(analysis_date_for(case), min_age_months)
    return cutoff >= mature_from


def select_mature_cases(
    cases: Iterable[BacktestCase],
    as_of_date: date | str,
    *,
    min_age_months: int = CASE_MIN_AGE_MONTHS,
) -> list[BacktestCase]:
    """Saring daftar kasus ke yang sudah melewati `min_age_months`.

    Dipisah dari :func:`is_case_mature` supaya pemanggil bisa memakai keduanya:
    orkestrator menyaring sekali di depan, sedangkan uji bisa memeriksa satu
    kasus tanpa membangun daftar.
    """
    return [
        case for case in cases
        if is_case_mature(case, as_of_date, min_age_months=min_age_months)
    ]


# --------------------------------------------------------------------------
# Excel EDATE dan DATEDIF
# --------------------------------------------------------------------------

def edate(start: date, months: int) -> date:
    """Reproduksi Excel ``EDATE(start_date, months)``.

    Didelegasikan ke :func:`pit_primitives.edate` supaya hanya ada satu
    implementasi aritmetika bulan di repo - kalau tidak, window harga dan
    `Avg Vol (3M)` bisa berbeda di kasus tanggal akhir bulan (mis.
    ``EDATE(2026-05-31, -3) == 2026-02-28``).
    """
    return _pit_edate(_to_date(start), months)


def datedif_months(start: date, end: date) -> int:
    """Reproduksi Excel ``DATEDIF(start, end, "m")``: jumlah bulan **penuh**.

    Excel menghitung bulan kalender yang sudah selesai, jadi ``DATEDIF``
    mengembalikan 11 untuk (2022-03-31 -> 2023-03-03) walaupun selisih bulan
    kalendernya 12: tanggal 3 belum mencapai tanggal 31, jadi bulan ke-12 belum
    selesai. Ini yang menghasilkan `Bln Peak` = M+11 pada fixture AUTO 2022 Q1,
    sehingga perbandingan ``end.day < start.day`` tidak boleh dilewatkan.

    Hasil negatif dikembalikan apa adanya (bukan dijepit ke nol) supaya tanggal
    yang tidak masuk akal tetap terlihat, bukan disembunyikan.
    """
    start = _to_date(start)
    end = _to_date(end)
    months = (end.year - start.year) * 12 + (end.month - start.month)
    if end.day < start.day:
        months -= 1
    return months


def as_of_price(
    bars: Sequence[Bar] | Sequence[PricePoint] | Iterable[Mapping[str, Any]],
    as_of_date: date | str,
) -> Decimal | None:
    """Close terakhir dengan ``trading_date <= as_of_date``.

    Didelegasikan ke :func:`pit_primitives.as_of_price` (aturan PIT-1) supaya
    harga analisis backtest persis sama dengan harga point-in-time yang sudah
    dipakai mesin valuasi. Baris setelah ``as_of_date`` tidak pernah dilihat,
    jadi tidak ada harga masa depan yang bisa bocor ke harga analisis.

    Bar dinormalisasi lebih dulu lalu dikirim sebagai baris `dict`, karena
    :func:`pit_primitives.as_of_price` hanya mengenali ``dict`` dan
    :class:`pit_primitives.PricePoint`. Konversi ini murni bentuk, bukan
    perhitungan ulang.
    """
    rows = [
        {'trading_date': bar.trading_date, 'close_price': bar.close_price}
        for bar in normalize_bars(bars)
    ]
    return _pit_as_of_price(rows, _to_date(as_of_date))


# --------------------------------------------------------------------------
# Tahap B - window harga
# --------------------------------------------------------------------------

@dataclass(frozen=True)
class PriceWindows:
    """Semua metrik harga satu kasus.

    ``None`` berarti "tidak bisa dihitung", bukan nol. Setiap ``None`` selalu
    punya penjelasan di :attr:`flags`.
    """

    analysis_date: date
    analysis_price: Decimal | None
    #: Tanggal perdagangan terakhir yang tersedia untuk instrumen ini, apa pun
    #: window-nya. Dipakai untuk membedakan "window belum lengkap karena data
    #: berhenti" dari "window kosong".
    data_edge: date | None
    #: Batas akhir window 12 bulan, yaitu `EDATE(analysis_date, +12)`.
    window_end: date

    high_3m: Decimal | None = None
    low_3m: Decimal | None = None
    high_6m: Decimal | None = None
    low_6m: Decimal | None = None
    high_9m: Decimal | None = None
    low_9m: Decimal | None = None
    high_12m: Decimal | None = None
    low_12m: Decimal | None = None

    peak_price: Decimal | None = None
    trough_price: Decimal | None = None
    peak_date: date | None = None
    peak_month: int | None = None
    #: `Bln Trough` - pasangan `Bln Peak`. Tidak ada di kolom workbook, tetapi UI
    #: sudah menampilkannya, dan menyimpannya membuat UI berhenti menghitung ulang
    #: dari jalur harga (D4: frontend hanya menampilkan yang tersimpan).
    trough_date: date | None = None
    trough_month: int | None = None
    return_peak: Decimal | None = None
    return_down: Decimal | None = None

    flags: tuple[str, ...] = ()

    def high_low(self, horizon: int) -> tuple[Decimal | None, Decimal | None]:
        """Kembalikan ``(high, low)`` untuk horizon 3/6/9/12 bulan."""
        if horizon not in WINDOW_HORIZONS_MONTHS:
            raise BacktestError(f'HORIZON_UNSUPPORTED: {horizon!r}')
        return (
            getattr(self, f'high_{horizon}m'),
            getattr(self, f'low_{horizon}m'),
        )


def _window_bounds(analysis_date: date, horizon: int) -> tuple[date, bool]:
    """Batas window satu horizon, mengikuti rumus kolom `Backtest_Result`.

    Mengembalikan ``(start, start_inclusive)``. Rumusnya:

    * 3 bulan  -> ``[T0, EDATE(T0,+3)]``, jadi awal **inklusif**
    * 6/9/12   -> ``(EDATE(T0,+n-3), EDATE(T0,+n)]``, jadi awal **eksklusif**

    Batas akhir selalu inklusif di semua horizon. Perbedaan inklusivitas awal
    ini bukan detail kosmetik: bar tanggal `EDATE(T0,+3)` dihitung dua kali bila
    semuanya dibuat inklusif, dan angka `Ret 6M` akan berbeda dari workbook.
    """
    end = edate(analysis_date, horizon)
    if horizon == 3:
        return analysis_date, True
    return edate(analysis_date, horizon - 3), False


def _max_high(bars: Iterable[Bar]) -> Decimal | None:
    values = [bar.high for bar in bars if bar.high is not None]
    return max(values) if values else None


def _min_low(bars: Iterable[Bar]) -> Decimal | None:
    values = [bar.low for bar in bars if bar.low is not None]
    return min(values) if values else None


def _select(bars: Sequence[Bar], start: date, start_inclusive: bool, end: date) -> list[Bar]:
    """Potong bar ke window ``[start, end]`` atau ``(start, end]``."""
    if start_inclusive:
        return [bar for bar in bars if start <= bar.trading_date <= end]
    return [bar for bar in bars if start < bar.trading_date <= end]


def price_windows(
    prices: Sequence[Bar] | Sequence[PricePoint] | Iterable[Mapping[str, Any]],
    analysis_date: date | str,
) -> PriceWindows:
    """Hitung semua metrik harga Tahap B untuk satu kasus.

    Urutan langkahnya sengaja seperti ini:

    1. Normalisasi bar (termasuk substitusi `High/Low` nol -> close).
    2. Harga analisis = close PIT pada `analysis_date`.
    3. `high_nm` / `low_nm` per horizon dengan aturan inklusivitas masing-masing.
    4. Peak/trough pada `[T0, EDATE(T0,+12)]` inklusif, lalu `Bln Peak` dari
       tanggal perdagangan **pertama** yang menyentuh `peak_price`
       (`MIN(Date) saat High = Harga Peak`).
    5. `Ret Peak` / `Ret Down` = `peak/base - 1` dan `trough/base - 1`.

    Data setelah `EDATE(T0,+12)` dibuang lebih dulu. Tanpa pemotongan ini, peak
    dan trough akan memakai harga di luar horizon 12 bulan dan angkanya tidak
    akan pernah cocok dengan workbook.
    """
    cutoff = _to_date(analysis_date)
    all_bars = normalize_bars(prices)
    window_end = edate(cutoff, 12)
    # Window observasi adalah `[T0, EDATE(T0,+12)]`. Riwayat sebelum T0 tetap
    # dipakai untuk harga analisis (close PIT), tetapi **tidak** boleh masuk
    # peak/trough: kalau ikut, peak akan diambil dari harga sebelum analisis dan
    # angkanya tidak akan pernah cocok dengan workbook.
    bars = [bar for bar in all_bars if cutoff <= bar.trading_date <= window_end]

    data_edge = all_bars[-1].trading_date if all_bars else None
    analysis_price = as_of_price(all_bars, cutoff)

    flags: list[str] = []
    if not bars:
        flags.append(FLAG_NO_PRICE_HISTORY)
    elif data_edge is not None and data_edge < window_end:
        # Kasus 2026 Q2: window 12 bulan belum selesai karena data berhenti di
        # tengah window. Ini bukan error, hanya belum lengkap - jadi kasusnya
        # tetap tersimpan dengan flag, bukan dihilangkan.
        flags.append(FLAG_WINDOW_PARTIAL)
    if analysis_price is None:
        flags.append(FLAG_ANALYSIS_PRICE_UNAVAILABLE)
    if any(bar.high_substituted for bar in bars):
        flags.append(FLAG_HIGH_ZERO_SUBSTITUTED)
    if any(bar.low_substituted for bar in bars):
        flags.append(FLAG_LOW_ZERO_SUBSTITUTED)

    values: dict[str, Decimal | None] = {}
    for horizon in WINDOW_HORIZONS_MONTHS:
        start, start_inclusive = _window_bounds(cutoff, horizon)
        selected = _select(bars, start, start_inclusive, edate(cutoff, horizon))
        if not selected:
            flags.append(FLAG_WINDOW_EMPTY)
        values[f'high_{horizon}m'] = _max_high(selected)
        values[f'low_{horizon}m'] = _min_low(selected)

    peak_price = _max_high(bars)
    trough_price = _min_low(bars)

    # `MIN(Date)` di antara bar yang high-nya sama dengan peak. Bar yang high-nya
    # tidak diketahui tidak pernah bisa "menyentuh" peak, jadi dikecualikan.
    peak_dates = [
        bar.trading_date
        for bar in bars
        if bar.high is not None and peak_price is not None and bar.high == peak_price
    ]
    peak_date = min(peak_dates) if peak_dates else None

    # `MIN(Date)` di antara bar yang low-nya sama dengan trough, simetris dengan
    # peak. Ini yang membuat `Bln Trough` bisa disimpan alih-alih dihitung ulang
    # di frontend.
    trough_dates = [
        bar.trading_date
        for bar in bars
        if bar.low is not None and trough_price is not None and bar.low == trough_price
    ]
    trough_date = min(trough_dates) if trough_dates else None

    return_peak: Decimal | None = None
    return_down: Decimal | None = None
    if analysis_price == 0:
        # Denominator nol: pembagian tidak didefinisikan, jadi nilainya NULL
        # dengan alasan eksplisit, bukan nol.
        flags.append(FLAG_BASE_PRICE_ZERO)
    elif analysis_price is not None:
        with localcontext() as context:
            context.prec = DECIMAL_PRECISION
            if peak_price is not None:
                return_peak = peak_price / analysis_price - Decimal(1)
            if trough_price is not None:
                return_down = trough_price / analysis_price - Decimal(1)

    return PriceWindows(
        analysis_date=cutoff,
        analysis_price=analysis_price,
        data_edge=data_edge,
        window_end=window_end,
        peak_price=peak_price,
        trough_price=trough_price,
        peak_date=peak_date,
        peak_month=datedif_months(cutoff, peak_date) if peak_date else None,
        trough_date=trough_date,
        trough_month=datedif_months(cutoff, trough_date) if trough_date else None,
        return_peak=return_peak,
        return_down=return_down,
        flags=tuple(dict.fromkeys(flags)),
        **values,
    )


# --------------------------------------------------------------------------
# Komposisi baris hasil
# --------------------------------------------------------------------------

def _row_status(flags: Sequence[str]) -> str:
    """Tentukan `calculation_status` dari flag satu kasus.

    Aturannya, berurutan:

    * tidak ada window harga sama sekali -> `UNAVAILABLE` (inputnya hilang)
    * ada caveat harga -> `APPROXIMATED`
    * selain itu -> `VALID`

    Flag kejujuran (D1/D7) **tidak** menurunkan status: tanggal analisis dan tipe
    saham belum point-in-time, tetapi metrik harganya sendiri dihitung penuh dan
    benar. Menurunkannya ke `APPROXIMATED` akan menyamakan dua hal berbeda -
    ketidakpastian perhitungan dan keterbatasan provenance - sehingga UI tidak
    lagi bisa membedakannya.
    """
    if FLAG_NO_PRICE_HISTORY in flags:
        return STATUS_UNAVAILABLE
    if any(flag in PRICE_WINDOW_METRIC_FLAGS for flag in flags):
        return STATUS_APPROXIMATED
    return STATUS_VALID


def price_metrics(
    prices: Sequence[Bar] | Sequence[PricePoint] | Iterable[Mapping[str, Any]],
    analysis_date: date | str,
    *,
    case_flags: Sequence[str] = (),
) -> dict[str, Any]:
    """Susun satu baris hasil backtest: metrik harga + status + flag.

    Mengembalikan ``dict`` dengan kunci yang langsung cocok dengan kolom
    `calc_backtest_cases` (bagian harga saja; kolom valuasi/verdict diisi fase
    berikutnya). ``case_flags`` adalah flag provenance dari
    :func:`case_provenance_flags`.

    ``details`` menyimpan tanggal peak dan tanggal data terakhir. Keduanya tidak
    masuk kolom tersendiri karena bukan angka yang dipakai UI, tapi tanpanya
    `Bln Peak` dan `WINDOW_PARTIAL` tidak bisa diaudit ulang.
    """
    windows = price_windows(prices, analysis_date)
    flags = list(dict.fromkeys([*windows.flags, *case_flags]))

    return {
        'analysis_date': windows.analysis_date.isoformat(),
        'analysis_price': windows.analysis_price,
        'analysis_price_source': 'CLOSE_PIT',
        'high_3m': windows.high_3m,
        'low_3m': windows.low_3m,
        'high_6m': windows.high_6m,
        'low_6m': windows.low_6m,
        'high_9m': windows.high_9m,
        'low_9m': windows.low_9m,
        'high_12m': windows.high_12m,
        'low_12m': windows.low_12m,
        'peak_price': windows.peak_price,
        'trough_price': windows.trough_price,
        'peak_month': windows.peak_month,
        'trough_month': windows.trough_month,
        'return_peak': windows.return_peak,
        'return_down': windows.return_down,
        'calculation_status': _row_status(flags),
        'flags': flags,
        'details': {
            'peak_date': windows.peak_date.isoformat() if windows.peak_date else None,
            'trough_date': windows.trough_date.isoformat() if windows.trough_date else None,
            'data_edge': windows.data_edge.isoformat() if windows.data_edge else None,
            'window_end': windows.window_end.isoformat(),
        },
    }


# --------------------------------------------------------------------------
# Fase 2 - valuasi per kasus, konsensus, dan MoS
# --------------------------------------------------------------------------
# Semua fungsi di bawah ini murni: menerima hasil `calculate_valuation_snapshot`
# yang sudah dihitung, lalu menyusun angka tingkat kasus. Tidak ada I/O dan tidak
# ada perhitungan ulang lima metode - sesuai `docs/BACKTEST_ARCHITECTURE.md` 3.4,
# menyalin rumus valuasi ke sini adalah penyebab drift D3/D4.


def resolve_case_years_available(
    registry_years: int,
    annual_periods: Sequence[Mapping[str, Any]],
    analysis_date: date | str,
    *,
    cutoff_date: date | str | None = None,
) -> tuple[int, list[str]]:
    """Hitung `years_available` untuk satu kasus (keputusan D2).

    Workbook memakai konstanta `Years_Avail = 7` untuk semua kasus, sedangkan
    engine menolak `years_available > jumlah periode annual`
    (`YEARS_AVAILABLE_EXCEEDS_HISTORY`). Kasus 2022 Q1 hanya punya 3 tahun annual
    (2019-2021), jadi 7 mustahil.

    Karena itu nilainya dipotong ke riwayat yang benar-benar ada **pada tanggal
    kasus**, dan pemotongan itu diangkat sebagai flag. Ini perbaikan point-in-time
    yang disengaja: akibatnya IV kasus paling awal bisa sedikit berbeda dari
    workbook, dan perbedaan itu harus terlihat, bukan disembunyikan.

    ``cutoff_date`` adalah tanggal yang benar-benar dipakai engine valuasi untuk
    memotong periode annual, yaitu `period_end` kuartal dasar - yang bisa lebih
    awal daripada `analysis_date` bila kuartal terakhir belum lengkap (mis. AUTO
    2023-Q4: kuartal dasarnya 2023-Q3). Keduanya harus dipakai bergantian:
    menghitung dengan `analysis_date` saja akan meloloskan satu tahun yang
    kemudian dibuang engine, dan engine menolak dengan
    `YEARS_AVAILABLE_EXCEEDS_HISTORY`.

    Mengembalikan ``(years_available, flags)``. `years_available` minimal 1:
    nol akan ditolak engine dan tidak ada artinya bagi kasus yang sudah ada.
    """
    cutoff = _to_date(cutoff_date) if cutoff_date is not None else _to_date(analysis_date)
    available = [
        period for period in annual_periods
        if _to_date(period['period_end']) <= cutoff
    ]
    capped = max(1, min(int(registry_years), len(available)))
    flags = [FLAG_YEARS_AVAILABLE_TRUNCATED] if capped < int(registry_years) else []
    return capped, flags


def method_verdict(intrinsic_value: Decimal | None, price: Decimal | None) -> str:
    """Verdict satu metode untuk backtest.

    Mengembalikan `NOT_APPLICABLE` bila IV atau harga tidak ada, **atau bila IV
    nol**. IV nol berarti model tidak menghasilkan nilai (mis. DDM tanpa dividen
    atau Discounted Earnings yang runtuh), dan workbook menandainya
    `IF(B25=0, "⚪ N/A (Skip)", ...)` - bukan "sangat overvalued". Itu juga yang
    membuat metode ini keluar dari penyebut konsensus.

    IV yang **negatif** tetap dianggap valid dan tetap dibandingkan.

    Ini sengaja **berbeda** dari `valuation_engine.verdict()`, yang memakai
    `value <= 0` sebagai `NOT_APPLICABLE`. Keputusan D5
    (`docs/BACKTEST_ARCHITECTURE.md` bagian 2) menyatakan IV negatif tetap
    dihitung valid: DDM AUTO 2022 Q1 = -100228 adalah metode valid yang
    OVERVALUED, dan konsensus workbook untuk kasus itu adalah `2|5` - yang hanya
    mungkin bila DDM ikut masuk denominator. Memakai aturan `<= 0` akan
    menghasilkan `2|4` dan tidak cocok dengan workbook.

    Konsekuensinya `verdict` di `calc_valuation_methods` (dihitung engine valuasi
    untuk snapshot harian) tidak boleh dipakai ulang di sini; backtest menghitung
    verdict metodenya sendiri. Perbedaan itu disengaja dan diuji.
    """
    if intrinsic_value is None or price is None:
        return METHOD_VERDICT_NOT_APPLICABLE
    if intrinsic_value == 0:
        return METHOD_VERDICT_NOT_APPLICABLE
    return (
        METHOD_VERDICT_UNDERVALUED
        if intrinsic_value > price
        else METHOD_VERDICT_OVERVALUED
    )


def mos_for(intrinsic_value: Decimal | None, price: Decimal | None) -> tuple[Decimal | None, list[str]]:
    """`MoS = (IV - price) / IV` - denominator **IV**, bukan harga (D6).

    Denominator IV berarti MoS mendekati 1 saat IV jauh di atas harga, dan
    menjadi tak terdefinisi saat IV = 0. IV negatif tetap menghasilkan MoS yang
    sah (mis. DDM -100228 dengan harga 1125 memberi MoS ~ 1.011), jadi yang
    ditolak hanya denominator nol.

    Mengembalikan ``(value, flags)``.
    """
    if intrinsic_value is None or price is None:
        return None, []
    if intrinsic_value == 0:
        return None, [FLAG_MOS_DENOMINATOR_ZERO]
    with localcontext() as context:
        context.prec = DECIMAL_PRECISION
        return (intrinsic_value - price) / intrinsic_value, []


def resolve_main_method(stock_type: str | None) -> str:
    """Metode `main` untuk `MoS Main` (`SUMMARY!B69`).

    Stalwart dan fast grower memakai `Type & Sector Weighted`; tipe lain memakai
    Peter Lynch. Tipe yang tidak dikenal atau kosong jatuh ke Peter Lynch, sama
    seperti `IF(OR(Stock_Type="stalwart", ...), "Weighted IV (Proj)", "Peter Lynch (Current)")`
    yang memilih cabang ELSE untuk nilai apa pun selain dua tipe itu.
    """
    normalized = str(stock_type or '').upper().replace('_', ' ').strip()
    if normalized in MAIN_METHOD_WEIGHTED_TYPES:
        return MAIN_METHOD_TYPE_SECTOR
    return MAIN_METHOD_PETER_LYNCH


def decimal_or_none(value: Any) -> Decimal | None:
    """`_to_decimal` tanpa melempar: `None` bila nilainya tidak bisa dibaca.

    Dipakai di jalur Fase 2 karena angka di sana berasal dari `methods` engine
    yang sudah bertipe benar; nilai yang tidak terbaca berarti bug, dan lebih
    berguna ditandai sebagai tidak ada daripada menghentikan seluruh run.
    """
    try:
        return _to_decimal(value)
    except BacktestError:
        return None


def resolve_consensus(
    methods: Sequence[Mapping[str, Any]],
    price: Decimal | None,
    *,
    min_valid_methods: int = CONSENSUS_MIN_VALID_METHODS,
) -> dict[str, Any]:
    """Hitung `Konsensus` = `Under_Count & "|" & Valid_Count` (aturan workbook).

    Aturannya, disalin dari rumus sheet valuasi:

    ```excel
    Skip_Count,COUNTIF(E13:E17,"⚪ N/A (Skip)")
    Err_Count,SUMPRODUCT((ISERROR(E13:E17))*1)
    Valid_Count,5-Invalid_Count
    Under_Count,COUNTIF(E13:E17,"✅ UNDERVALUED")
    ```

    * `Under_Count` = jumlah metode valid yang IV-nya **di atas** harga.
    * `Valid_Count` = `5 - (N/A + error)`.
    * `"N/A"` bila `Valid_Count < min_valid_methods` (default 3).

    **`IV = 0` adalah "N/A (Skip)", bukan metode valid.** Ini yang membuat
    penyebutnya benar-benar bervariasi (`/3`, `/4`, `/5`) dan bukan selalu 5.
    Statusnya di workbook:

    ```excel
    =IF(B25=0, "⚪ N/A (Skip)", IF(price < B25, "UNDERVALUED", "OVERVALUED"))
    ```

    Jadi saham tanpa dividen (DDM = 0) atau yang model diskontoannya runtuh ke
    nol **keluar dari penyebut**. Bukti ke workbook: dari 72 baris dengan lima IV
    lengkap, aturan "IV=0 di-skip" cocok 72/72, sedangkan "IV=0 dihitung valid"
    gagal tepat di INDF 2024-Q4 dan 2025-Q2 (workbook `1|3`, bukan `1|5`).

    **IV negatif tetap valid** (D5): hanya nol yang di-skip. DDM AUTO 2022 Q1
    (-100228) masih masuk denominator sehingga konsensusnya `2|5`.

    Mengembalikan dict dengan `consensus`, `consensus_undervalued`,
    `consensus_valid`, dan `flags`.
    """
    valid = [
        row for row in methods
        if row.get('intrinsic_value') is not None
        and decimal_or_none(row.get('intrinsic_value')) != 0
    ]
    valid_count = len(valid)
    flags: list[str] = []

    if price is None:
        undervalued_count = 0
    else:
        undervalued_count = sum(
            1 for row in valid if decimal_or_none(row.get('intrinsic_value')) > price
        )

    # IV negatif yang ikut dihitung valid adalah pilihan sadar (D5), bukan
    # kebetulan. Diangkat sebagai flag supaya auditor bisa membedakan konsensus
    # yang lahir dari IV wajar dan yang lahir dari IV negatif.
    if any(decimal_or_none(row.get('intrinsic_value')) < 0 for row in valid):
        flags.append(FLAG_NEGATIVE_INTRINSIC_VALUE_VALID)

    if valid_count < min_valid_methods:
        flags.append(FLAG_CONSENSUS_BELOW_THREE_METHODS)
        return {
            'consensus': CONSENSUS_NOT_AVAILABLE,
            'consensus_undervalued': None,
            'consensus_valid': valid_count,
            'flags': flags,
        }

    return {
        'consensus': f'{undervalued_count}|{valid_count}',
        'consensus_undervalued': undervalued_count,
        'consensus_valid': valid_count,
        'flags': flags,
    }


def unavailable_valuation_case_metrics(
    *,
    price: Decimal | None,
    reason: str,
    case_flags: Sequence[str] = (),
) -> dict[str, Any]:
    """Baris kasus saat valuasinya tidak bisa dihitung sama sekali.

    Dipakai ketika pembentukan skenario point-in-time gagal (misalnya satu
    kuartal dasar belum lengkap pada tanggal kasus). Aturannya sama dengan
    Fase 1: kasusnya tetap tersimpan, `intrinsic_value` NULL, `consensus` `N/A`,
    dan alasannya di `flags` - bukan dihilangkan dan bukan diisi nol.

    Lima baris `methods` tetap dibuat dengan `NOT_APPLICABLE` supaya jumlah baris
    per kasus selalu lima dan `consensus_valid = 0` bisa dilacak asalnya.
    """
    method_rows = [
        {
            'method_code': code,
            'method_name': code,
            'intrinsic_value': None,
            'current_price': price,
            'gap_ratio': None,
            'mos': None,
            'verdict': METHOD_VERDICT_NOT_APPLICABLE,
            'calculation_status': STATUS_UNAVAILABLE,
            'flags': [FLAG_METHOD_UNAVAILABLE, FLAG_VALUATION_UNAVAILABLE],
            'details': {'reason': reason},
        }
        for code in BACKTEST_METHOD_CODES
    ]
    return {
        'mos_main': None,
        'mos_peter': None,
        'mos_weight': None,
        'mos_method_code': resolve_main_method(None),
        'consensus': CONSENSUS_NOT_AVAILABLE,
        'consensus_undervalued': None,
        'consensus_valid': 0,
        'methods': method_rows,
        'flags': list(dict.fromkeys([
            FLAG_VALUATION_UNAVAILABLE,
            FLAG_CONSENSUS_BELOW_THREE_METHODS,
            *case_flags,
        ])),
    }


def valuation_case_metrics(
    valuation: Mapping[str, Any],
    *,
    stock_type: str | None,
    price: Decimal | None,
    case_flags: Sequence[str] = (),
) -> dict[str, Any]:
    """Susun angka tingkat kasus dari satu snapshot valuasi.

    Mengembalikan kolom valuasi `calc_backtest_cases` (`mos_main`, `mos_peter`,
    `mos_weight`, `mos_method_code`, `consensus*`) plus `methods` siap tulis ke
    `calc_backtest_methods`.

    Harga yang dipakai adalah `analysis_price` kasus, **bukan**
    `valuation['current_price']`. Keduanya seharusnya sama karena engine
    menerima `valuation_date = analysis_date`; tetapi kalau berbeda, harga kasus
    yang menang, karena itu yang sudah tersimpan dan ditampilkan Fase 1.
    """
    methods = list(valuation.get('methods') or [])
    by_code = {str(row.get('method_code')): row for row in methods}
    main_code = resolve_main_method(stock_type)

    method_rows: list[dict[str, Any]] = []
    for code in BACKTEST_METHOD_CODES:
        row = by_code.get(code)
        if row is None:
            # Metode yang tidak dikembalikan engine. Ini tidak seharusnya terjadi,
            # jadi dicatat sebagai baris NOT_APPLICABLE dengan flag, bukan
            # dihilangkan: konsensus `5` harus bisa dilacak asalnya.
            method_rows.append({
                'method_code': code,
                'method_name': code,
                'intrinsic_value': None,
                'current_price': price,
                'gap_ratio': None,
                'mos': None,
                'verdict': METHOD_VERDICT_NOT_APPLICABLE,
                'calculation_status': STATUS_UNAVAILABLE,
                'flags': [FLAG_METHOD_UNAVAILABLE],
                'details': {'reason': 'method_not_returned_by_engine'},
            })
            continue

        intrinsic = decimal_or_none(row.get('intrinsic_value'))
        mos, mos_flags = mos_for(intrinsic, price)
        method_flags = list(dict.fromkeys([*(row.get('flags') or []), *mos_flags]))
        if intrinsic is None:
            method_flags = list(dict.fromkeys([*method_flags, FLAG_METHOD_UNAVAILABLE]))
        # Workbook: `=IF(B25=0, "-", (B25 - Price) / Price)`. IV nol berarti
        # "N/A (Skip)", jadi gap-nya juga kosong - bukan -100% yang terlihat
        # seperti sinyal kuat padahal cuma model yang tidak menghasilkan nilai.
        gap_ratio = None if intrinsic in (None, Decimal(0)) else decimal_or_none(row.get('gap_ratio'))
        method_rows.append({
            'method_code': code,
            'method_name': str(row.get('method_name') or code),
            'intrinsic_value': intrinsic,
            'current_price': price,
            'gap_ratio': gap_ratio,
            'mos': mos,
            'verdict': method_verdict(intrinsic, price),
            'calculation_status': str(row.get('calculation_status') or STATUS_UNAVAILABLE),
            'flags': method_flags,
            'details': dict(row.get('details') or {}),
        })

    consensus = resolve_consensus(methods, price)

    def method_mos(code: str) -> Decimal | None:
        selected = next((item for item in method_rows if item['method_code'] == code), None)
        return selected['mos'] if selected else None

    main_mos = method_mos(main_code)
    main_flags: list[str] = []
    if main_mos is None:
        main_flags.append(FLAG_MOS_MAIN_UNAVAILABLE)

    return {
        'mos_main': main_mos,
        'mos_peter': method_mos(MAIN_METHOD_PETER_LYNCH),
        'mos_weight': method_mos(MAIN_METHOD_TYPE_SECTOR),
        'mos_method_code': main_code,
        'consensus': consensus['consensus'],
        'consensus_undervalued': consensus['consensus_undervalued'],
        'consensus_valid': consensus['consensus_valid'],
        'methods': method_rows,
        'flags': list(dict.fromkeys([
            *consensus['flags'],
            *main_flags,
            *case_flags,
        ])),
    }

# Ini **bukan** `supplemental_methodology_seeds()` di
# `calculation_methodology_registry.py`. Fungsi itu dikunci oleh
# `tests/test_valuation_engine.py:105` (`len(rows) == 1`, hanya VALUATION_CURRENT),
# jadi menambahkan backtest di sana akan memecah kontrak yang sudah ada.
# Fase 1 tidak butuh baris registry baru untuk berjalan: yang dibutuhkan hanyalah
# definisinya tersedia dan bisa di-hash, sehingga fase 2 bisa mendaftarkannya
# lewat jalur additive tanpa menyentuh seed yang sudah beku.

#: Nama metodologi yang akan dipakai fase 2 saat mendaftarkan hasilnya.
BACKTEST_METHODOLOGY = METHOD_CODE


def classify_consensus(consensus: str | None) -> str | None:
    """Klasifikasi `Konsensus` menjadi `UNDERVALUED` / `OVERVALUED`.

    Ini yang menjadi `K` di rumus verdict. Sumbernya rumus workbook kolom
    `Konsensus`:

    ```excel
    =IF(OR(J2="3|3", J2="3|4", J2="4|4", J2="3|5", J2="4|5", J2="5|5"),
        "UNDERVALUED", "OVERVALUED")
    ```

    **Hanya dua kelas.** `MIXED` tidak pernah muncul di sini - sheet backtest
    tidak punya cabang itu, dan rumus verdictnya memperlakukan apa pun selain
    `UNDERVALUED`/`OVERVALUED` sebagai `FLAT`. Rumus rasio (`Ratio >= 0.6` /
    `>= 0.4`) milik sheet valuasi sengaja tidak diikuti.

    `None` dikembalikan bila konsensusnya belum ada (`N/A` atau kosong): verdict
    tidak bisa dihitung, dan itu harus terlihat, bukan ditebak.
    """
    if not consensus or consensus == CONSENSUS_NOT_AVAILABLE:
        return None
    return 'UNDERVALUED' if consensus in CONSENSUS_UNDERVALUED_CLASSES else 'OVERVALUED'


def magnitude_for(return_value: Decimal | None) -> str | None:
    """`magnitude` = `UP` bila return `>= +10%`, `DOWN` bila `<= -10%`, selain itu `FLAT`.

    Kolom ini **tidak** berasal dari workbook: ia disimpan karena frontend sudah
    menyaring pergerakan signifikan dengan ambang 10%
    (`frontend/src/lib/analysis/backtest.ts`), dan menyimpannya membuat
    penyaringan itu bisa dilakukan di SQL. Ambiguitas asalnya (tidak ada ambang
    10% di `Backtest_Historical (New)`) dicatat di `details.magnitude_rule`.
    """
    if return_value is None:
        return None
    if return_value >= MAGNITUDE_THRESHOLD:
        return 'UP'
    if return_value <= -MAGNITUDE_THRESHOLD:
        return 'DOWN'
    return 'FLAT'


def verdict_for(
    classification: str | None,
    analysis_price: Decimal | None,
    bars: Sequence[Bar] | Sequence[PricePoint] | Iterable[Mapping[str, Any]],
    analysis_date: date | str,
) -> tuple[str | None, dict[str, Any], list[str]]:
    """`Verdict by Method` - salinan `AY` dari `Backtest_Historical (New)`.

    Rumus yang dipakai sekarang, disalin apa adanya:

    ```excel
    UpTarget,   BasePrice*1.20,
    DownTarget, BasePrice*0.85,

    IF(K="UNDERVALUED",
        IF(AND(UpDate="",DownDate=""), "FLAT",
        IF(AND(UpDate<>"",DownDate=""), "WIN",
        IF(AND(UpDate="",DownDate<>""), "RISK",
        IF(DownDate<UpDate, "RECOVERED", "WIN")))),
        IF(K="OVERVALUED",
            IF(AND(UpDate="",DownDate=""), "FLAT",
            IF(AND(UpDate<>"",DownDate=""), "REPRICE",
            IF(AND(UpDate="",DownDate<>""), "CONFIRMED",
            IF(DownDate<UpDate, "CONFIRMED", "REPRICE")))),
            "FLAT"))
    ```

    Lima sifat yang harus dipatuhi, semuanya dikunci uji:

    1. **Satu ambang untuk kedua klasifikasi** (`x1.20` naik, `x0.85` turun).
       Sebelumnya overvalued memakai `x1.15`/`x0.9`; sekarang klasifikasi hanya
       memilih **nama** verdict, bukan ambangnya.
    2. **Hari yang sama persis bukan lagi kasus khusus.** Cabang terakhir
       dibandingkan dengan `<`, jadi `UpDate == DownDate` jatuh ke `WIN`
       (undervalued) atau `REPRICE` (overvalued). `RECOVERED` sekarang **hanya**
       untuk kasus yang benar-benar turun dulu lalu naik.
    3. **Tidak ada `OBSERVE`.** Cabang "tidak menyentuh apa pun" pada sisi
       overvalued menjadi `FLAT`, sama seperti sisi undervalued. "Naik dulu" pada
       sisi overvalued tetap `REPRICE` (pasar menolak tesis), "turun dulu" tetap
       `CONFIRMED`.
    4. **`K` di luar `UNDERVALUED`/`OVERVALUED` -> `FLAT`**, bukan error. Ini
       termasuk `MIXED`, yang memang tidak pernah dihasilkan
       :func:`classify_consensus`.
    5. **Window 12 bulan dengan awal eksklusif** (`> StartDate`), berbeda dari
       `Ret 3M` yang inklusif. `High`/`Low` nol -> `Close` sudah diterapkan di
       :class:`Bar`.

    Mengembalikan ``(verdict, details, flags)``. ``details`` memuat target dan
    tanggal tembusnya supaya verdict bisa diaudit ulang tanpa menjalankan ulang
    rumusnya. `verdict` bernilai `None` bila konsensus atau harganya belum ada.
    """
    cutoff = _to_date(analysis_date)
    if classification is None or analysis_price is None:
        return None, {}, [FLAG_VERDICT_NO_CONSENSUS]

    if classification not in ('UNDERVALUED', 'OVERVALUED'):
        # Termasuk `MIXED` dan `K` tak dikenal: rumus mengembalikan FLAT.
        return 'FLAT', {
            'classification': classification,
            'upside_target': None,
            'downside_target': None,
            'up_date': None,
            'down_date': None,
            'reason': 'CLASSIFICATION_NOT_RECOGNISED',
        }, []

    upside_target = analysis_price * VERDICT_UPSIDE
    downside_target = analysis_price * VERDICT_DOWNSIDE

    window_end = edate(cutoff, 12)
    # Batas awal EKSKLUSIF (`> StartDate`), batas akhir inklusif. Ini yang
    # membedakan window verdict dari window `Ret 3M`.
    window = [
        bar for bar in normalize_bars(bars)
        if cutoff < bar.trading_date <= window_end
    ]

    up_dates = [
        bar.trading_date for bar in window
        if bar.high is not None and bar.high >= upside_target
    ]
    down_dates = [
        bar.trading_date for bar in window
        if bar.low is not None and bar.low <= downside_target
    ]
    up_date = min(up_dates) if up_dates else None
    down_date = min(down_dates) if down_dates else None

    flags: list[str] = []
    if not window:
        flags.append(FLAG_VERDICT_NO_PRICE_WINDOW)

    if classification == 'UNDERVALUED':
        if up_date is None and down_date is None:
            verdict = 'FLAT'
        elif up_date is not None and down_date is None:
            verdict = 'WIN'
        elif up_date is None and down_date is not None:
            verdict = 'RISK'
        elif down_date < up_date:
            verdict = 'RECOVERED'
        else:
            # `up_date <= down_date`: naik dulu (atau hari yang sama) -> WIN.
            verdict = 'WIN'
    else:
        if up_date is None and down_date is None:
            verdict = 'FLAT'
        elif up_date is not None and down_date is None:
            verdict = 'REPRICE'
        elif up_date is None and down_date is not None:
            verdict = 'CONFIRMED'
        elif down_date < up_date:
            verdict = 'CONFIRMED'
        else:
            # `up_date <= down_date`: naik dulu (atau hari yang sama) -> REPRICE.
            verdict = 'REPRICE'

    return verdict, {
        'classification': classification,
        'upside_target': upside_target,
        'downside_target': downside_target,
        'up_date': up_date.isoformat() if up_date else None,
        'down_date': down_date.isoformat() if down_date else None,
    }, flags


def verdict_mos_for(
    mos_main: Decimal | None,
    analysis_price: Decimal | None,
    bars: Sequence[Bar] | Sequence[PricePoint] | Iterable[Mapping[str, Any]],
    analysis_date: date | str,
) -> tuple[str | None, dict[str, Any], list[str]]:
    """`Verdict MoS` - salinan `AZ`, hitungan terpisah dari `Verdict by Method`.

    Satu-satunya bedanya dari :func:`verdict_for` adalah sumber `K`:

    ```excel
    K, IF([@[MoS Main]]>=30%, "UNDERVALUED", "OVERVALUED")
    ```

    Jadi `MoS Main` hanya menentukan **nama** verdict; ambang harga (`x1.20` /
    `x0.85`) dan arah pergerakannya sama persis dengan `Verdict by Method`,
    karena keduanya memakai rumus `IF` yang identik. Karena `K` selalu bernilai
    salah satu dari dua nilai itu, cabang `MIXED` dan `K` tak dikenal tidak
    pernah terjadi di sini.
    """
    if mos_main is None:
        return None, {}, [FLAG_VERDICT_MOS_UNDEFINED]
    classification = 'UNDERVALUED' if mos_main >= MOS_VERDICT_THRESHOLD else 'OVERVALUED'
    verdict, details, flags = verdict_for(
        classification, analysis_price, bars, analysis_date
    )
    if details:
        details = {
            **details,
            'mos_main': str(mos_main),
            'mos_threshold': str(MOS_VERDICT_THRESHOLD),
        }
    return verdict, details, flags


def verdict_case_metrics(
    *,
    consensus: str | None,
    mos_main: Decimal | None,
    analysis_price: Decimal | None,
    analysis_date: date | str,
    bars: Sequence[Bar] | Sequence[PricePoint] | Iterable[Mapping[str, Any]],
    return_peak: Decimal | None = None,
    return_down: Decimal | None = None,
) -> dict[str, Any]:
    """Susun kolom verdict satu kasus: `verdict`, `verdict_mos`, dan magnitude.

    Ketiganya dihitung dari `consensus`/`mos_main` (Fase 2) plus harga Fase 1,
    jadi tidak ada perhitungan ulang dan tidak ada I/O. Bila verdict tidak bisa
    dihitung, nilainya `None` dengan flag - bukan default yang terlihat sah.
    """
    classification = classify_consensus(consensus)
    verdict, verdict_details, verdict_flags = verdict_for(
        classification, analysis_price, bars, analysis_date
    )
    verdict_mos, mos_details, mos_flags = verdict_mos_for(
        mos_main, analysis_price, bars, analysis_date
    )

    details: dict[str, Any] = {}
    if verdict_details:
        details['verdict'] = verdict_details
    if mos_details:
        details['verdict_mos'] = mos_details
    details['magnitude_rule'] = 'abs(return) >= 0.10, not from the workbook'

    return {
        'verdict': verdict,
        'verdict_mos': verdict_mos,
        'return_magnitude': magnitude_for(return_peak),
        'return_magnitude_down': magnitude_for(return_down),
        'verdict_details': details,
        'flags': list(dict.fromkeys([*verdict_flags, *mos_flags])),
    }


def backtest_methodology_seed() -> dict[str, Any]:
    """Definisi metodologi `BACKTEST_HISTORICAL` beserta hash-nya.

    `formula_text` sengaja memuat **aturan pemilihan kasus** dan **aturan window
    harga** karena keduanya adalah rumus yang menentukan angka, bukan sekadar
    konfigurasi. Kalau keduanya hanya hidup di kode, perubahan aturan tidak akan
    terlihat di registry dan hasil lama tidak bisa direproduksi.

    Hash dihitung dari teks kanonik yang sama dengan seeder lain
    (`sha256_text` untuk formula, `sha256_json` untuk parameter), sehingga baris
    ini bisa diverifikasi dengan cara yang sama seperti `VALUATION_CURRENT`.
    """
    formula_text = (
        'Case selection: annual years minus the two smallest, then every quarter '
        'whose year is base_year + 1. A case is dropped until it is at least four '
        'months old, because quarterly IDX reports are not published before then. '
        'Analysis date: case period end (D1, '
        'available_date when present). Analysis price: last close on or before '
        'the analysis date. Ret 3M over [T0, EDATE(T0,+3)] inclusive at both ends; '
        'Ret 6M/9M/12M over (EDATE(T0,+n-3), EDATE(T0,+n)] exclusive at the start. '
        'Peak and trough over [T0, EDATE(T0,+12)] inclusive, using High = 0 ? Close : High '
        'and Low = 0 ? Close : Low. Bln Peak = DATEDIF(T0, first date reaching the '
        'peak price, months). Ret Peak/Down = price / analysis price - 1. '
        'Phase 2: five method intrinsic values from the point-in-time scenario; '
        'Consensus = undervalued count over valid methods, where a negative intrinsic '
        'value stays valid but a zero intrinsic value is N/A (skip) and leaves the '
        'denominator, and fewer than three valid methods yields N/A; '
        'MoS = (intrinsic value - price) / intrinsic value; main method is the '
        'weighted IV for stalwart and fast grower, otherwise Peter Lynch. '
        'Phase 3: Verdict by Method and Verdict MoS from the workbook formula; '
        'upside target x1.20 and downside target x0.85 for BOTH classifications, '
        'over a 12 month window that starts strictly after the analysis date. '
        'Undervalued: neither touched -> FLAT, up only -> WIN, down only -> RISK, '
        'down first -> RECOVERED, otherwise (including the same day) -> WIN. '
        'Overvalued: neither touched -> FLAT, up only -> REPRICE, down only -> '
        'CONFIRMED, down first -> CONFIRMED, otherwise (including the same day) -> '
        'REPRICE. Any other classification yields FLAT, and Verdict MoS uses '
        'K = MoS Main >= 0.3.'
    )
    parameter_spec: dict[str, Any] = {
        'horizons_months': ['3', '6', '9', '12'],
        'observation_months': '12',
        # Kasus = kuartal pada tahun setelah base year, bukan semua kuartal.
        'case_year_offset': '1',
        # `Helper!C2#`: buang dua tahun annual terkecil.
        'base_year_drop_smallest': '2',
        'window_start_inclusive_months': ['3'],
        'window_start_exclusive_months': ['6', '9', '12'],
        'window_end_inclusive': 'true',
        'zero_high_low_falls_back_to_close': 'true',
        'peak_month_rule': 'datedif_months_to_first_peak_date',
        'return_peak_denominator': 'analysis_price',
        'return_down_denominator': 'analysis_price',
        # --- Fase 2: valuasi per kasus, konsensus, MoS ---
        # IV negatif tetap valid (D5). Ini yang membuat DDM AUTO 2022 Q1
        # (-100228) masuk denominator sehingga konsensusnya `2|5`, bukan `2|4`.
        'negative_intrinsic_value_is_valid': 'true',
        # IV nol BUKAN valid: status workbook `IF(B25=0, "N/A (Skip)", ...)`,
        # jadi ia keluar dari penyebut. Ini yang membuat denominator bervariasi.
        'zero_intrinsic_value_is_skip': 'true',
        'consensus_denominator': 'valid_methods_5_minus_na_minus_error',
        'consensus_min_valid_methods': '3',
        'consensus_not_available_text': 'N/A',
        # Hanya dua kelas, tanpa MIXED (rumus rasio sheet valuasi tidak diikuti).
        'consensus_classes': 'two_class_undervalued_or_overvalued',
        'mos_denominator': 'intrinsic_value',
        'mos_main_rule': 'weighted_iv_for_stalwart_and_fast_grower_else_peter_lynch',
        'years_available_rule': 'min(registry_years, annual_periods_on_or_before_analysis_date)',
        # Kasus yang belum berumur ini dibuang: laporan kuartalan belum terbit.
        'case_min_age_months': '4',
        # --- Fase 3: verdict ---
        # Rumus disalin apa adanya dari workbook `Stock Analyzer [Dev] Quarter.xlsm`,
        # sheet `Backtest_Historical (New)`, kolom AY/AZ.
        'verdict_rule': 'workbook_ay_az_verbatim',
        # Satu ambang untuk kedua klasifikasi; klasifikasi hanya memilih nama.
        'verdict_upside_target': '1.2',
        'verdict_downside_target': '0.85',
        'verdict_window_months': '12',
        'verdict_window_start': 'exclusive_after_analysis_date',
        'verdict_same_day_rule': 'up_date_lte_down_date_falls_to_win_or_reprice',
        'verdict_overvalued_no_touch': 'FLAT',
        'verdict_mos_threshold': '0.3',
        'consensus_undervalued_classes': ['3|3', '3|4', '4|4', '3|5', '4|5', '5|5'],
        'analysis_date_source': 'period_end_with_available_date_override',
    }
    formula_hash = sha256_text(formula_text)
    parameter_hash = sha256_json(parameter_spec)
    return {
        'method_code': METHOD_CODE,
        'method_version': METHOD_VERSION,
        'method_name': 'Historical Backtest',
        'description': (
            'Historical backtest cases: workbook case selection, point-in-time '
            'price windows, peak/trough observation. Valuation, consensus and '
            'verdict are added by later phases.'
        ),
        'formula_text': formula_text,
        'formula_hash': formula_hash,
        'parameter_spec': parameter_spec,
        'parameter_hash': parameter_hash,
        'code_version': CODE_VERSION,
        'status': 'DRAFT',
    }
