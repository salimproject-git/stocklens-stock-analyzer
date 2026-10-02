from __future__ import annotations

import json
import sys
import unittest
from datetime import date
from decimal import Decimal, localcontext
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'supabase'))

from backtest_engine import (  # noqa: E402
    CASE_MIN_AGE_MONTHS,
    CONSENSUS_MIN_VALID_METHODS,
    CONSENSUS_UNDERVALUED_CLASSES,
    DECIMAL_PRECISION,
    FLAG_ANALYSIS_PRICE_UNAVAILABLE,
    FLAG_CONSENSUS_BELOW_THREE_METHODS,
    FLAG_HIGH_ZERO_SUBSTITUTED,
    FLAG_LOW_ZERO_SUBSTITUTED,
    FLAG_METHOD_UNAVAILABLE,
    FLAG_MOS_DENOMINATOR_ZERO,
    FLAG_NEGATIVE_INTRINSIC_VALUE_VALID,
    FLAG_NO_PRICE_HISTORY,
    FLAG_POINT_IN_TIME_UNAVAILABLE_DATE,
    FLAG_VALUATION_UNAVAILABLE,
    FLAG_VERDICT_MOS_UNDEFINED,
    FLAG_VERDICT_NO_CONSENSUS,
    FLAG_VERDICT_NO_PRICE_WINDOW,
    FLAG_WINDOW_EMPTY,
    FLAG_WINDOW_PARTIAL,
    FLAG_YEARS_AVAILABLE_TRUNCATED,
    MAIN_METHOD_PETER_LYNCH,
    MAIN_METHOD_TYPE_SECTOR,
    MAGNITUDE_THRESHOLD,
    METHOD_CODE,
    METHOD_VERDICT_NOT_APPLICABLE,
    METHOD_VERDICT_OVERVALUED,
    METHOD_VERDICT_UNDERVALUED,
    MOS_VERDICT_THRESHOLD,
    VERDICTS,
    VERDICTS_CURRENT,
    VERDICT_DOWNSIDE,
    VERDICT_DOWNSIDE_OTHER,
    VERDICT_DOWNSIDE_UNDERVALUED,
    VERDICT_UPSIDE,
    VERDICT_UPSIDE_OTHER,
    VERDICT_UPSIDE_UNDERVALUED,
    BacktestCase,
    BacktestError,
    Bar,
    analysis_date_for,
    as_of_price,
    backtest_methodology_seed,
    case_provenance_flags,
    classify_consensus,
    datedif_months,
    decimal_or_none,
    edate,
    is_case_mature,
    magnitude_for,
    method_verdict,
    mos_for,
    normalize_bars,
    price_metrics,
    price_windows,
    resolve_case_years_available,
    resolve_consensus,
    resolve_main_method,
    select_backtest_cases,
    select_mature_cases,
    unavailable_valuation_case_metrics,
    valuation_case_metrics,
    verdict_case_metrics,
    verdict_for,
    verdict_mos_for,
    valid_base_years,
)
from calculation_registry import sha256_json, sha256_text  # noqa: E402

FIXTURE_DIR = ROOT / 'tests' / 'fixtures'

#: Jumlah kasus per ticker, dari `docs/BACKTEST_ARCHITECTURE.md` bagian 6.
#: Angka-angka ini sudah dicocokkan ke database dan ke workbook.
EXPECTED_CASE_COUNTS = {
    'AUTO': 18,
    'GEMA': 18,
    'DSSA': 17,
    'GOLD': 22,
    'WIFI': 22,
}

#: Fixture harga lengkap (butuh high/low untuk rumus window).
PRICE_FIXTURES = ('auto', 'gema')
#: Fixture periode saja (cukup untuk menguji daftar kasus).
PERIOD_FIXTURES = ('dssa', 'gold', 'wifi')


def load_fixture(name: str) -> dict:
    path = FIXTURE_DIR / f'{name}_backtest.json'
    if not path.exists():
        path = FIXTURE_DIR / f'{name}_backtest_periods.json'
    return json.loads(path.read_text(encoding='utf-8'))


def fixture_cases(fixture: dict) -> list:
    return select_backtest_cases(
        [row for row in fixture['periods'] if row['period_type'] == 'ANNUAL'],
        [row for row in fixture['periods'] if row['period_type'] == 'QUARTER'],
    )


def case_for(fixture: dict, quarter: str):
    return next(case for case in fixture_cases(fixture) if case.case_quarter == quarter)


class CaseSelectionTests(unittest.TestCase):
    """Tahap A: daftar kasus dari aturan `Helper!C2#`."""

    def test_two_smallest_annual_years_are_dropped(self) -> None:
        annual = [
            {'period_end': f'{year}-12-31', 'instrument_id': 'i'}
            for year in range(2019, 2026)
        ]
        self.assertEqual(valid_base_years(annual), [2021, 2022, 2023, 2024, 2025])

    def test_two_or_fewer_years_produce_no_base_year(self) -> None:
        """`IF(ROWS(Years)<=2, "", ...)` - bukan error, hanya kosong."""
        for years in ([2024], [2024, 2025]):
            annual = [
                {'period_end': f'{year}-12-31', 'instrument_id': 'i'} for year in years
            ]
            self.assertEqual(valid_base_years(annual), [])

    def test_case_counts_match_the_documented_table(self) -> None:
        """18 untuk sebagian besar ticker, DSSA 17, GOLD/WIFI 22."""
        for name, expected in EXPECTED_CASE_COUNTS.items():
            with self.subTest(ticker=name):
                fixture = load_fixture(name)
                self.assertEqual(len(fixture_cases(fixture)), expected)

    def test_auto_cases_are_2022_q1_through_2026_q2(self) -> None:
        cases = fixture_cases(load_fixture('auto'))
        self.assertEqual(cases[0].case_quarter, '2022-Q1')
        self.assertEqual(cases[-1].case_quarter, '2026-Q2')
        self.assertEqual(
            sorted({case.base_year for case in cases}),
            [2021, 2022, 2023, 2024, 2025],
        )

    def test_quarter_maps_to_the_previous_year_as_base_year(self) -> None:
        """`baseYear = dbYear - 1`: kuartal 2022 memakai base year 2021."""
        for case in fixture_cases(load_fixture('auto')):
            self.assertEqual(case.base_year, case.period_end.year - 1)

    def test_dssa_has_no_2026_q2_case(self) -> None:
        """Kuartal 2026 Q2 memang tidak ada di `financial_periods` DSSA."""
        quarters = {case.case_quarter for case in fixture_cases(load_fixture('dssa'))}
        self.assertNotIn('2026-Q2', quarters)
        self.assertIn('2026-Q1', quarters)

    def test_gold_and_wifi_keep_the_2020_base_year(self) -> None:
        """Delapan tahun annual -> base year mulai 2020 -> kasus dari 2021 Q1."""
        for name in ('gold', 'wifi'):
            with self.subTest(ticker=name):
                cases = fixture_cases(load_fixture(name))
                self.assertEqual(cases[0].case_quarter, '2021-Q1')
                self.assertIn(2020, {case.base_year for case in cases})

    def test_quarters_without_a_valid_base_year_are_skipped_silently(self) -> None:
        annual = [
            {'period_end': f'{year}-12-31', 'instrument_id': 'i'} for year in (2019, 2020, 2021)
        ]
        quarters = [
            {'id': 'q1', 'period_end': '2021-03-31', 'instrument_id': 'i'},
            {'id': 'q2', 'period_end': '2022-03-31', 'instrument_id': 'i'},
        ]
        cases = select_backtest_cases(annual, quarters)
        # 2021 memakai base year 2020 yang tidak valid; 2022 memakai 2021 yang valid.
        self.assertEqual([case.case_quarter for case in cases], ['2022-Q1'])

    def test_mixed_instruments_are_rejected(self) -> None:
        """Duplikat/bercampur berarti pemanggil mengirim data yang salah."""
        annual = [{'period_end': '2021-12-31', 'instrument_id': 'a'}]
        quarters = [{'id': 'q', 'period_end': '2022-03-31', 'instrument_id': 'b'}]
        with self.assertRaisesRegex(BacktestError, 'CASE_SELECTION_REQUIRES_ONE_INSTRUMENT'):
            select_backtest_cases(annual, quarters)


class CaseMaturityTests(unittest.TestCase):
    """Kasus yang belum berumur `CASE_MIN_AGE_MONTHS` dibuang dari hasil.

    Laporan kuartalan IDX baru terbit sekitar 3-4 bulan setelah akhir periode, jadi
    kuartal terbaru belum punya riwayat harga yang layak dinilai.
    """

    def case(self, period_end: str):
        return BacktestCase(
            instrument_id='i',
            as_of_financial_period_id='p',
            case_quarter='2026-Q2',
            base_year=2025,
            period_end=date.fromisoformat(period_end),
        )

    def test_min_age_is_four_months(self) -> None:
        self.assertEqual(CASE_MIN_AGE_MONTHS, 4)

    def test_quarter_ending_june_is_too_young_in_september(self) -> None:
        """Q2 berakhir 30 Juni; pada 30 September umurnya baru 3 bulan."""
        case = self.case('2026-06-30')
        self.assertFalse(is_case_mature(case, '2026-09-30'))
        # Batasnya 30 Oktober: sehari sebelum belum, tepat pada hari sudah.
        self.assertFalse(is_case_mature(case, '2026-10-29'))
        self.assertTrue(is_case_mature(case, '2026-10-30'))

    def test_quarter_ending_march_is_old_enough_in_september(self) -> None:
        """Q1 berakhir 31 Maret; pada 30 September sudah 6 bulan.

        Ini yang membuat DSSA tetap tampil walau ticker lain kehilangan kuartal
        terakhirnya.
        """
        case = self.case('2026-03-31')
        self.assertTrue(is_case_mature(case, '2026-09-30'))
        self.assertTrue(is_case_mature(case, '2026-07-31'))
        self.assertFalse(is_case_mature(case, '2026-07-30'))

    def test_available_date_shifts_the_boundary(self) -> None:
        """`available_date` menggantikan `period_end` sebagai anchor."""
        case = BacktestCase(
            instrument_id='i',
            as_of_financial_period_id='p',
            case_quarter='2026-Q2',
            base_year=2025,
            period_end=date(2026, 6, 30),
            available_date=date(2026, 8, 15),
        )
        # Anchor 15 Agustus -> matang 15 Desember, bukan 30 Oktober.
        self.assertFalse(is_case_mature(case, '2026-12-14'))
        self.assertTrue(is_case_mature(case, '2026-12-15'))

    def test_end_of_month_anchor_does_not_overflow(self) -> None:
        """`EDATE` menjepit tanggal, jadi 31 Desember + 4 bulan = 30 April."""
        case = self.case('2025-12-31')
        self.assertFalse(is_case_mature(case, '2026-04-29'))
        self.assertTrue(is_case_mature(case, '2026-04-30'))

    def test_select_mature_cases_filters_the_list(self) -> None:
        cases = [
            self.case('2026-03-31'),
            self.case('2026-06-30'),
        ]
        kept = select_mature_cases(cases, '2026-09-30')
        self.assertEqual([c.period_end.isoformat() for c in kept], ['2026-03-31'])


class AutoParityTests(unittest.TestCase):
    """Parity AUTO 2022 Q1 terhadap tabel di dokumen arsitektur bagian 1.

    Dua belas angka di sini sudah dicocokkan manual ke workbook. Kalau salah satu
    bergeser, aturan window sudah berubah dan fase 2 tidak akan pernah persis.
    """

    @classmethod
    def setUpClass(cls) -> None:
        cls.fixture = load_fixture('auto')
        cls.case = case_for(cls.fixture, '2022-Q1')
        cls.windows = price_windows(cls.fixture['prices'], analysis_date_for(cls.case))

    def test_analysis_date_is_the_case_period_end(self) -> None:
        """D1 opsi (a): `available_date` NULL -> pakai `period_end`."""
        self.assertEqual(analysis_date_for(self.case), date(2022, 3, 31))
        self.assertIn(FLAG_POINT_IN_TIME_UNAVAILABLE_DATE, case_provenance_flags(self.case))

    def test_analysis_price_matches_the_workbook(self) -> None:
        self.assertEqual(self.windows.analysis_price, Decimal('1125'))

    def test_three_month_window_matches_the_workbook(self) -> None:
        self.assertEqual(self.windows.high_3m, Decimal('1285'))
        self.assertEqual(self.windows.low_3m, Decimal('1080'))

    def test_six_month_window_matches_the_workbook(self) -> None:
        self.assertEqual(self.windows.high_6m, Decimal('1375'))
        self.assertEqual(self.windows.low_6m, Decimal('1085'))

    def test_nine_month_window_matches_the_workbook(self) -> None:
        self.assertEqual(self.windows.high_9m, Decimal('1590'))
        self.assertEqual(self.windows.low_9m, Decimal('1155'))

    def test_twelve_month_window_matches_the_workbook(self) -> None:
        self.assertEqual(self.windows.high_12m, Decimal('1855'))
        self.assertEqual(self.windows.low_12m, Decimal('1335'))

    def test_peak_and_trough_match_the_workbook(self) -> None:
        self.assertEqual(self.windows.peak_price, Decimal('1855'))
        self.assertEqual(self.windows.trough_price, Decimal('1080'))

    def test_peak_month_is_m_plus_11(self) -> None:
        """`MIN(Date) saat High = Harga Peak` adalah 2023-03-03, bukan 2023-03-31."""
        self.assertEqual(self.windows.peak_date, date(2023, 3, 3))
        self.assertEqual(self.windows.peak_month, 11)

    def test_trough_month_is_the_counterpart_of_peak_month(self) -> None:
        """`Bln Trough` = bulan dari tanggal **pertama** yang menyentuh trough.

        Dipakai UI untuk kolom "Bln Trough", jadi harus disimpan: menghitungnya
        ulang di browser dengan `monthsBetween` akan memberi angka berbeda pada
        kasus yang tanggal analisisnya akhir bulan (lihat AUTO 2023-Q3).

        Kolom ini tidak ada di workbook; aturannya sengaja disamakan dengan
        `Bln Peak` (`DATEDIF`), sehingga 2022-03-31 -> 2022-04-25 adalah 0 bulan.
        """
        self.assertEqual(self.windows.trough_date, date(2022, 4, 25))
        self.assertEqual(self.windows.trough_month, 0)

    def test_month_offsets_are_datedif_months_not_month_boundaries(self) -> None:
        """DATEDIF menghitung bulan **penuh**; kasus 0 bulan harus benar.

        AUTO 2023-Q3: analisis 2023-09-30, peak 2023-10-02. Itu 0 bulan penuh
        (DATEDIF) tetapi 1 batas bulan (`monthsBetween`). Yang benar adalah 0.
        """
        bars = [
            {'trading_date': '2023-09-30', 'close_price': '3000',
             'high_price': '3000', 'low_price': '2990'},
            {'trading_date': '2023-10-02', 'close_price': '3210',
             'high_price': '3210', 'low_price': '3200'},
        ]
        windows = price_windows(bars, '2023-09-30')
        self.assertEqual(windows.peak_date, date(2023, 10, 2))
        self.assertEqual(windows.peak_month, 0)

    def test_return_peak_and_return_down_use_the_analysis_price(self) -> None:
        """`Ret Peak`/`Ret Down` = harga / harga analisis - 1 (bukan kebalikannya).

        Dihitung pada presisi `DECIMAL_PRECISION`, sama seperti engine. Presisi
        default `decimal` (28 digit) menghasilkan angka yang sedikit berbeda,
        jadi membandingkannya tanpa konteks yang sama akan gagal karena alasan
        yang salah.
        """
        with localcontext() as context:
            context.prec = DECIMAL_PRECISION
            expected_peak = Decimal('1855') / Decimal('1125') - Decimal(1)
            expected_down = Decimal('1080') / Decimal('1125') - Decimal(1)
        self.assertEqual(self.windows.return_peak, expected_peak)
        self.assertEqual(self.windows.return_down, expected_down)

    def test_return_peak_is_positive_and_return_down_is_negative(self) -> None:
        """Sanity arah: peak di atas harga analisis, trough di bawahnya."""
        self.assertGreater(self.windows.return_peak, Decimal(0))
        self.assertLess(self.windows.return_down, Decimal(0))

    def test_full_window_case_is_valid_with_only_provenance_flags(self) -> None:
        """Window lengkap dan tidak ada High/Low nol -> VALID, bukan APPROXIMATED.

        Sejak D7 ditutup, satu-satunya flag provenance yang tersisa adalah
        `POINT_IN_TIME_UNAVAILABLE_DATE`; tipe saham dihitung pada tanggal kasus,
        jadi tidak ada lagi flag snapshot tipe.
        """
        row = price_metrics(
            self.fixture['prices'],
            analysis_date_for(self.case),
            case_flags=case_provenance_flags(self.case),
        )
        self.assertEqual(row['calculation_status'], 'VALID')
        self.assertEqual(
            row['flags'],
            [FLAG_POINT_IN_TIME_UNAVAILABLE_DATE],
        )

    def test_auto_has_no_zero_high_rows_so_this_fixture_cannot_catch_that_bug(self) -> None:
        """Bukti mengapa GEMA wajib: AUTO 0 baris `high_price = 0`."""
        self.assertEqual(self.fixture['zero_high_rows'], 0)


class ZeroHighLowTests(unittest.TestCase):
    """Aturan `High = 0 ? Close : High` dengan data nol yang nyata (GEMA).

    AUTO tidak punya satu pun baris `high_price = 0`, jadi kelas ini satu-satunya
    yang bisa menangkap bug tersebut. GEMA punya 195 baris, dan di beberapa window
    `MIN(Low)` mentahnya benar-benar 0.
    """

    @classmethod
    def setUpClass(cls) -> None:
        cls.fixture = load_fixture('gema')
        cls.cases = fixture_cases(cls.fixture)

    def case(self, quarter: str):
        return next(case for case in self.cases if case.case_quarter == quarter)

    def test_fixture_really_contains_zero_high_rows(self) -> None:
        """Kalau angka ini jadi 0, uji di kelas ini berhenti menguji apa pun."""
        self.assertEqual(self.fixture['zero_high_rows'], 195)
        self.assertEqual(
            sum(1 for row in self.fixture['prices'] if row['high_price'] == 0),
            195,
        )

    def test_zero_high_and_low_fall_back_to_close(self) -> None:
        bars = normalize_bars([
            {'trading_date': '2022-04-01', 'close_price': '150', 'high_price': '0', 'low_price': '0'},
        ])
        self.assertEqual(bars[0].high, Decimal('150'))
        self.assertEqual(bars[0].low, Decimal('150'))
        self.assertTrue(bars[0].high_substituted)
        self.assertTrue(bars[0].low_substituted)

    def test_non_zero_high_and_low_are_kept_unchanged(self) -> None:
        bars = normalize_bars([
            {'trading_date': '2022-04-01', 'close_price': '150', 'high_price': '170', 'low_price': '140'},
        ])
        self.assertEqual(bars[0].high, Decimal('170'))
        self.assertEqual(bars[0].low, Decimal('140'))
        self.assertFalse(bars[0].high_substituted)
        self.assertFalse(bars[0].low_substituted)

    def test_null_high_is_not_turned_into_zero(self) -> None:
        """NULL berarti tidak ada nilai; nol berarti ada tapi tidak masuk akal."""
        bars = normalize_bars([
            {'trading_date': '2022-04-01', 'close_price': '150', 'high_price': None, 'low_price': None},
        ])
        self.assertIsNone(bars[0].high)
        self.assertIsNone(bars[0].low)
        self.assertFalse(bars[0].high_substituted)

    def test_raw_aggregation_would_have_returned_zero_for_gema(self) -> None:
        """Tanpa substitusi, `MIN(Low)` window 3M GEMA 2022 Q1 = 0, bukan 312.

        Ini pembuktian bahwa aturan itu material, bukan kosmetik: angkanya
        dihitung langsung dari fixture tanpa melewati engine.
        """
        analysis_date = analysis_date_for(self.case('2022-Q1'))
        window_end = edate(analysis_date, 3)
        raw_lows = [
            row['low_price'] for row in self.fixture['prices']
            if analysis_date.isoformat() <= row['trading_date'] <= window_end.isoformat()
        ]
        self.assertTrue(raw_lows)
        self.assertEqual(min(raw_lows), 0)

    def test_gema_windows_use_the_close_fallback(self) -> None:
        """Angka yang benar setelah substitusi, dicocokkan ke agregasi SQL."""
        windows = price_windows(self.fixture['prices'], analysis_date_for(self.case('2022-Q1')))
        self.assertEqual(windows.analysis_price, Decimal('352'))
        self.assertEqual(windows.high_3m, Decimal('356'))
        self.assertEqual(windows.low_3m, Decimal('312'))
        self.assertEqual(windows.high_6m, Decimal('356'))
        self.assertEqual(windows.low_6m, Decimal('302'))
        self.assertEqual(windows.high_9m, Decimal('358'))
        self.assertEqual(windows.low_9m, Decimal('238'))
        self.assertEqual(windows.high_12m, Decimal('316'))
        self.assertEqual(windows.low_12m, Decimal('165'))
        self.assertEqual(windows.peak_price, Decimal('358'))
        self.assertEqual(windows.trough_price, Decimal('165'))
        self.assertEqual(windows.peak_month, 6)

    def test_gema_flags_both_substitutions_and_approximates_the_row(self) -> None:
        row = price_metrics(
            self.fixture['prices'],
            analysis_date_for(self.case('2022-Q1')),
            case_flags=case_provenance_flags(self.case('2022-Q1')),
        )
        self.assertIn(FLAG_HIGH_ZERO_SUBSTITUTED, row['flags'])
        self.assertIn(FLAG_LOW_ZERO_SUBSTITUTED, row['flags'])
        # Substitusi adalah caveat perhitungan, jadi barisnya APPROXIMATED.
        self.assertEqual(row['calculation_status'], 'APPROXIMATED')

    def test_second_gema_case_also_needs_the_fallback(self) -> None:
        """Lebih dari satu kasus GEMA terpengaruh, jadi bug ini tidak sempit."""
        windows = price_windows(self.fixture['prices'], analysis_date_for(self.case('2022-Q4')))
        self.assertEqual(windows.analysis_price, Decimal('300'))
        self.assertEqual(windows.low_3m, Decimal('165'))
        self.assertEqual(windows.high_12m, Decimal('460'))
        self.assertEqual(windows.peak_month, 9)


class MethodVerdictTests(unittest.TestCase):
    """Verdict per metode (Fase 2) - dan mengapa ia berbeda dari engine valuasi.

    Keputusan D5: IV negatif tetap valid. `valuation_engine.verdict()` memakai
    `value <= 0` sebagai `NOT_APPLICABLE`, yang akan membuat DDM AUTO 2022 Q1
    (-100228) keluar dari denominator dan konsensusnya jadi `2|4`, bukan `2|5`.
    Uji di kelas ini mengunci perbedaan itu supaya tidak ada yang "merapikan"nya
    kembali ke perilaku engine valuasi.
    """

    def test_positive_value_above_price_is_undervalued(self) -> None:
        self.assertEqual(
            method_verdict(Decimal('2000'), Decimal('1125')),
            METHOD_VERDICT_UNDERVALUED,
        )

    def test_positive_value_below_price_is_overvalued(self) -> None:
        self.assertEqual(
            method_verdict(Decimal('900'), Decimal('1125')),
            METHOD_VERDICT_OVERVALUED,
        )

    def test_negative_intrinsic_value_is_overvalued_not_not_applicable(self) -> None:
        """Ini inti D5: IV negatif tetap dibandingkan, bukan dibuang."""
        self.assertEqual(
            method_verdict(Decimal('-100228.7124'), Decimal('1125')),
            METHOD_VERDICT_OVERVALUED,
        )

    def test_zero_intrinsic_value_is_not_applicable(self) -> None:
        """IV nol = "N/A (Skip)" di workbook, jadi keluar dari penyebut.

        Bukan `OVERVALUED`: model yang tidak menghasilkan nilai (DDM tanpa
        dividen, Discounted Earnings yang runtuh) tidak sedang menyatakan
        apa pun tentang harga.
        """
        self.assertEqual(method_verdict(Decimal('0'), Decimal('1125')), METHOD_VERDICT_NOT_APPLICABLE)

    def test_negative_intrinsic_value_is_still_compared(self) -> None:
        """IV negatif tetap valid (D5) - hanya nol yang di-skip."""
        self.assertEqual(method_verdict(Decimal('-100'), Decimal('1125')), METHOD_VERDICT_OVERVALUED)

    def test_missing_value_or_price_is_not_applicable(self) -> None:
        self.assertEqual(method_verdict(None, Decimal('1125')), METHOD_VERDICT_NOT_APPLICABLE)
        self.assertEqual(method_verdict(Decimal('1000'), None), METHOD_VERDICT_NOT_APPLICABLE)

    def test_equal_value_and_price_is_overvalued(self) -> None:
        """Perbandingannya ketat `>`: harga yang sama bukan undervalued."""
        self.assertEqual(
            method_verdict(Decimal('1125'), Decimal('1125')),
            METHOD_VERDICT_OVERVALUED,
        )


class MosTests(unittest.TestCase):
    """`MoS = (IV - price) / IV` - denominator IV (D6)."""

    def test_denominator_is_the_intrinsic_value(self) -> None:
        value, flags = mos_for(Decimal('2000'), Decimal('1125'))
        self.assertEqual(flags, [])
        self.assertEqual(value, (Decimal('2000') - Decimal('1125')) / Decimal('2000'))

    def test_denominator_is_not_the_price(self) -> None:
        """Kalau denominator harga, hasilnya akan 0.777..., bukan 0.4375."""
        value, _ = mos_for(Decimal('2000'), Decimal('1125'))
        self.assertNotEqual(value, (Decimal('2000') - Decimal('1125')) / Decimal('1125'))

    def test_negative_intrinsic_value_still_yields_a_mos(self) -> None:
        """DDM AUTO 2022 Q1: -100228.71 dengan harga 1125 -> MoS ~ 1.0112."""
        value, flags = mos_for(Decimal('-100228.7124'), Decimal('1125'))
        self.assertEqual(flags, [])
        self.assertAlmostEqual(float(value), 1.0112243, places=6)

    def test_zero_intrinsic_value_is_flagged_not_divided(self) -> None:
        value, flags = mos_for(Decimal('0'), Decimal('1125'))
        self.assertIsNone(value)
        self.assertEqual(flags, [FLAG_MOS_DENOMINATOR_ZERO])

    def test_missing_inputs_return_nothing(self) -> None:
        self.assertEqual(mos_for(None, Decimal('1125')), (None, []))
        self.assertEqual(mos_for(Decimal('1000'), None), (None, []))


class MainMethodTests(unittest.TestCase):
    """`SUMMARY!B69`: stalwart / fast grower -> weighted, selain itu Peter Lynch."""

    def test_stalwart_and_fast_grower_use_the_weighted_iv(self) -> None:
        for stock_type in ('STALWART', 'FAST GROWER'):
            with self.subTest(stock_type=stock_type):
                self.assertEqual(resolve_main_method(stock_type), MAIN_METHOD_TYPE_SECTOR)

    def test_other_types_use_peter_lynch(self) -> None:
        for stock_type in ('CYCLICAL', 'SLOW GROWER', 'TURN AROUND', 'ASSET PLAY'):
            with self.subTest(stock_type=stock_type):
                self.assertEqual(resolve_main_method(stock_type), MAIN_METHOD_PETER_LYNCH)

    def test_unknown_or_missing_type_falls_back_to_peter_lynch(self) -> None:
        """Cabang ELSE rumus Excel dipilih untuk apa pun selain dua tipe itu."""
        for stock_type in (None, '', 'UNCLASSIFIED', 'SOMETHING ELSE'):
            with self.subTest(stock_type=stock_type):
                self.assertEqual(resolve_main_method(stock_type), MAIN_METHOD_PETER_LYNCH)

    def test_underscored_variants_are_normalised(self) -> None:
        self.assertEqual(resolve_main_method('FAST_GROWER'), MAIN_METHOD_TYPE_SECTOR)


class ConsensusTests(unittest.TestCase):
    """`Konsensus` = `Under_Count & "|" & Valid_Count` (aturan workbook).

    Fixture di sini adalah lima IV AUTO 2022 Q1 dari data sampel frontend, yang
    sudah dicocokkan ke workbook: konsensusnya `2|5` karena hanya dua IV di atas
    harga 1125, sedangkan DDM yang negatif tetap dihitung valid (D5).
    """

    PRICE = Decimal('1125')
    METHODS = [
        {'method_code': 'PETER_LYNCH', 'intrinsic_value': Decimal('2505.247668')},
        {'method_code': 'TYPE_SECTOR_WEIGHTED', 'intrinsic_value': Decimal('1297.503507')},
        {'method_code': 'MEAN_REVERSION_PBV', 'intrinsic_value': Decimal('988.3189914')},
        {'method_code': 'DDM', 'intrinsic_value': Decimal('-100228.7124')},
        {'method_code': 'DISCOUNTED_EARNINGS', 'intrinsic_value': Decimal('1041.622105')},
    ]

    def test_workbook_consensus_is_two_of_five(self) -> None:
        result = resolve_consensus(self.METHODS, self.PRICE)
        self.assertEqual(result['consensus'], '2|5')
        self.assertEqual(result['consensus_undervalued'], 2)
        self.assertEqual(result['consensus_valid'], 5)

    def test_negative_intrinsic_value_is_flagged_but_still_valid(self) -> None:
        result = resolve_consensus(self.METHODS, self.PRICE)
        self.assertIn(FLAG_NEGATIVE_INTRINSIC_VALUE_VALID, result['flags'])
        self.assertNotIn(FLAG_CONSENSUS_BELOW_THREE_METHODS, result['flags'])

    def test_counting_negative_value_as_invalid_would_give_two_of_four(self) -> None:
        """Kontrol negatif: aturan `<= 0` menghasilkan `2|4` dan salah."""
        without_negative = [row for row in self.METHODS if row['intrinsic_value'] > 0]
        result = resolve_consensus(without_negative, self.PRICE)
        self.assertEqual(result['consensus'], '2|4')
        self.assertNotEqual(result['consensus'], '2|5')

    def test_zero_intrinsic_value_leaves_the_denominator(self) -> None:
        """IV nol = "N/A (Skip)", jadi penyebutnya mengecil.

        Ini inti dari "jangan diratakan semua 5": saham tanpa dividen tidak punya
        DDM, sehingga konsensusnya `/4`, bukan `/5`. Bukti ke workbook: ARII
        2026-Q2 punya DDM = 0 dan workbook menulis `3|4`, bukan `3|5`.
        """
        methods = [
            {'method_code': 'PETER_LYNCH', 'intrinsic_value': Decimal('477')},
            {'method_code': 'TYPE_SECTOR_WEIGHTED', 'intrinsic_value': Decimal('753')},
            {'method_code': 'MEAN_REVERSION_PBV', 'intrinsic_value': Decimal('266')},
            {'method_code': 'DDM', 'intrinsic_value': Decimal('0')},
            {'method_code': 'DISCOUNTED_EARNINGS', 'intrinsic_value': Decimal('2164')},
        ]
        # Harga 280: PL, Weighted, dan DE di atas harga -> 3; MR-PBV dan DDM tidak.
        result = resolve_consensus(methods, Decimal('280'))
        self.assertEqual(result['consensus'], '3|4')
        self.assertEqual(result['consensus_valid'], 4)
        self.assertEqual(result['consensus_undervalued'], 3)

    def test_zero_valued_method_is_not_counted_as_undervalued(self) -> None:
        """IV nol tidak boleh ikut dihitung sebagai undervalued."""
        methods = [
            {'method_code': 'PETER_LYNCH', 'intrinsic_value': Decimal('0')},
            {'method_code': 'TYPE_SECTOR_WEIGHTED', 'intrinsic_value': Decimal('200')},
            {'method_code': 'MEAN_REVERSION_PBV', 'intrinsic_value': Decimal('200')},
            {'method_code': 'DDM', 'intrinsic_value': Decimal('200')},
        ]
        result = resolve_consensus(methods, Decimal('100'))
        self.assertEqual(result['consensus'], '3|3')

    def test_all_zero_methods_yield_na(self) -> None:
        """Semua nol berarti tidak ada metode valid sama sekali."""
        methods = [
            {'method_code': code, 'intrinsic_value': Decimal('0')}
            for code in ('PETER_LYNCH', 'TYPE_SECTOR_WEIGHTED',
                         'MEAN_REVERSION_PBV', 'DDM', 'DISCOUNTED_EARNINGS')
        ]
        result = resolve_consensus(methods, Decimal('100'))
        self.assertEqual(result['consensus'], 'N/A')
        self.assertEqual(result['consensus_valid'], 0)

    def test_fewer_than_three_valid_methods_yields_na(self) -> None:
        result = resolve_consensus(self.METHODS[:2], self.PRICE)
        self.assertEqual(result['consensus'], 'N/A')
        self.assertIsNone(result['consensus_undervalued'])
        self.assertEqual(result['consensus_valid'], 2)
        self.assertIn(FLAG_CONSENSUS_BELOW_THREE_METHODS, result['flags'])

    def test_exactly_three_valid_methods_is_not_na(self) -> None:
        """Ambangnya `>= 3`, jadi tepat tiga masih menghasilkan konsensus."""
        result = resolve_consensus(self.METHODS[:3], self.PRICE)
        # Tiga IV pertama: 2505 dan 1297 di atas 1125, 988 di bawahnya.
        self.assertEqual(result['consensus'], '2|3')
        self.assertNotIn(FLAG_CONSENSUS_BELOW_THREE_METHODS, result['flags'])

    def test_missing_intrinsic_values_reduce_the_valid_count(self) -> None:
        methods = [
            {'method_code': 'PETER_LYNCH', 'intrinsic_value': Decimal('2505.247668')},
            {'method_code': 'TYPE_SECTOR_WEIGHTED', 'intrinsic_value': None},
            {'method_code': 'MEAN_REVERSION_PBV', 'intrinsic_value': Decimal('988.3189914')},
            {'method_code': 'DDM', 'intrinsic_value': None},
            {'method_code': 'DISCOUNTED_EARNINGS', 'intrinsic_value': Decimal('1041.622105')},
        ]
        result = resolve_consensus(methods, self.PRICE)
        self.assertEqual(result['consensus'], '1|3')
        self.assertEqual(result['consensus_valid'], 3)

    def test_all_five_undervalued(self) -> None:
        methods = [
            {'method_code': code, 'intrinsic_value': Decimal('5000')}
            for code in ('A', 'B', 'C', 'D', 'E')
        ]
        self.assertEqual(resolve_consensus(methods, self.PRICE)['consensus'], '5|5')

    def test_no_methods_at_all_is_na_with_zero_valid(self) -> None:
        result = resolve_consensus([], self.PRICE)
        self.assertEqual(result['consensus'], 'N/A')
        self.assertEqual(result['consensus_valid'], 0)

    def test_missing_price_makes_nothing_undervalued(self) -> None:
        result = resolve_consensus(self.METHODS, None)
        self.assertEqual(result['consensus'], '0|5')


class ValuationCaseMetricsTests(unittest.TestCase):
    """Komposisi kolom valuasi satu kasus dari snapshot engine."""

    PRICE = Decimal('1125')

    def valuation(self) -> dict:
        return {
            'methods': [
                {
                    'method_code': 'PETER_LYNCH', 'method_name': 'Peter Lynch',
                    'intrinsic_value': Decimal('2505.247668'), 'gap_ratio': Decimal('1.2'),
                    'verdict': 'UNDERVALUED', 'calculation_status': 'VALID',
                    'flags': [], 'details': {'selected_branch': 'PER'},
                },
                {
                    'method_code': 'TYPE_SECTOR_WEIGHTED', 'method_name': 'Weighted',
                    'intrinsic_value': Decimal('1297.503507'), 'gap_ratio': Decimal('0.15'),
                    'verdict': 'UNDERVALUED', 'calculation_status': 'VALID',
                    'flags': [], 'details': {},
                },
                {
                    'method_code': 'MEAN_REVERSION_PBV', 'method_name': 'Mean Reversion',
                    'intrinsic_value': Decimal('988.3189914'), 'gap_ratio': Decimal('-0.12'),
                    'verdict': 'OVERVALUED', 'calculation_status': 'APPROXIMATED',
                    'flags': ['QUARTERLY_SHARES_ANNUAL_PROXY'], 'details': {},
                },
                {
                    'method_code': 'DDM', 'method_name': 'DDM',
                    'intrinsic_value': Decimal('-100228.7124'), 'gap_ratio': None,
                    'verdict': 'NOT_APPLICABLE', 'calculation_status': 'VALID',
                    'flags': [], 'details': {},
                },
                {
                    'method_code': 'DISCOUNTED_EARNINGS', 'method_name': 'Discounted Earnings',
                    'intrinsic_value': Decimal('1041.622105'), 'gap_ratio': None,
                    'verdict': 'OVERVALUED', 'calculation_status': 'VALID',
                    'flags': [], 'details': {},
                },
            ],
        }

    def test_all_five_methods_are_written_in_workbook_order(self) -> None:
        metrics = valuation_case_metrics(
            self.valuation(), stock_type='CYCLICAL', price=self.PRICE
        )
        self.assertEqual(
            [row['method_code'] for row in metrics['methods']],
            ['PETER_LYNCH', 'TYPE_SECTOR_WEIGHTED', 'MEAN_REVERSION_PBV', 'DDM', 'DISCOUNTED_EARNINGS'],
        )

    def test_consensus_and_mos_match_the_workbook_case(self) -> None:
        metrics = valuation_case_metrics(
            self.valuation(), stock_type='CYCLICAL', price=self.PRICE
        )
        self.assertEqual(metrics['consensus'], '2|5')
        self.assertEqual(metrics['mos_method_code'], MAIN_METHOD_PETER_LYNCH)
        self.assertAlmostEqual(float(metrics['mos_main']), 0.5509426, places=6)
        self.assertAlmostEqual(float(metrics['mos_weight']), 0.1329503, places=6)
        self.assertEqual(metrics['mos_peter'], metrics['mos_main'])

    def test_stalwart_makes_the_weighted_iv_the_main_method(self) -> None:
        metrics = valuation_case_metrics(
            self.valuation(), stock_type='STALWART', price=self.PRICE
        )
        self.assertEqual(metrics['mos_method_code'], MAIN_METHOD_TYPE_SECTOR)
        self.assertEqual(metrics['mos_main'], metrics['mos_weight'])
        self.assertNotEqual(metrics['mos_main'], metrics['mos_peter'])

    def test_ddm_verdict_is_overvalued_not_not_applicable(self) -> None:
        metrics = valuation_case_metrics(
            self.valuation(), stock_type='CYCLICAL', price=self.PRICE
        )
        ddm = next(row for row in metrics['methods'] if row['method_code'] == 'DDM')
        self.assertEqual(ddm['verdict'], METHOD_VERDICT_OVERVALUED)
        self.assertIsNotNone(ddm['mos'])

    def test_method_status_is_preserved_from_the_engine(self) -> None:
        metrics = valuation_case_metrics(
            self.valuation(), stock_type='CYCLICAL', price=self.PRICE
        )
        mean_reversion = next(
            row for row in metrics['methods'] if row['method_code'] == 'MEAN_REVERSION_PBV'
        )
        self.assertEqual(mean_reversion['calculation_status'], 'APPROXIMATED')
        self.assertIn('QUARTERLY_SHARES_ANNUAL_PROXY', mean_reversion['flags'])

    def test_unavailable_method_gets_a_flag_and_not_applicable(self) -> None:
        valuation = self.valuation()
        valuation['methods'][0]['intrinsic_value'] = None
        metrics = valuation_case_metrics(valuation, stock_type='CYCLICAL', price=self.PRICE)
        peter = next(row for row in metrics['methods'] if row['method_code'] == 'PETER_LYNCH')
        self.assertIsNone(peter['intrinsic_value'])
        self.assertIsNone(peter['mos'])
        self.assertEqual(peter['verdict'], METHOD_VERDICT_NOT_APPLICABLE)
        self.assertIn(FLAG_METHOD_UNAVAILABLE, peter['flags'])

    def test_method_missing_from_engine_output_still_yields_five_rows(self) -> None:
        valuation = self.valuation()
        valuation['methods'] = valuation['methods'][:4]
        metrics = valuation_case_metrics(valuation, stock_type='CYCLICAL', price=self.PRICE)
        self.assertEqual(len(metrics['methods']), 5)
        missing = next(
            row for row in metrics['methods'] if row['method_code'] == 'DISCOUNTED_EARNINGS'
        )
        self.assertEqual(missing['verdict'], METHOD_VERDICT_NOT_APPLICABLE)
        self.assertIn(FLAG_METHOD_UNAVAILABLE, missing['flags'])

    def test_missing_price_leaves_mos_none_and_zero_undervalued(self) -> None:
        metrics = valuation_case_metrics(self.valuation(), stock_type='CYCLICAL', price=None)
        self.assertIsNone(metrics['mos_main'])
        self.assertIsNone(metrics['mos_weight'])
        self.assertEqual(metrics['consensus'], '0|5')

    def test_case_flags_are_merged(self) -> None:
        metrics = valuation_case_metrics(
            self.valuation(), stock_type='CYCLICAL', price=self.PRICE,
            case_flags=[FLAG_POINT_IN_TIME_UNAVAILABLE_DATE],
        )
        self.assertIn(FLAG_POINT_IN_TIME_UNAVAILABLE_DATE, metrics['flags'])
        self.assertIn(FLAG_NEGATIVE_INTRINSIC_VALUE_VALID, metrics['flags'])

    def test_unavailable_valuation_keeps_five_traceable_rows(self) -> None:
        metrics = unavailable_valuation_case_metrics(
            price=self.PRICE, reason='BASE_QUARTER_FACT_MISSING: COST_OF_REVENUE'
        )
        self.assertEqual(len(metrics['methods']), 5)
        self.assertEqual(metrics['consensus'], 'N/A')
        self.assertEqual(metrics['consensus_valid'], 0)
        self.assertIsNone(metrics['mos_main'])
        self.assertIn(FLAG_VALUATION_UNAVAILABLE, metrics['flags'])
        self.assertIn(FLAG_CONSENSUS_BELOW_THREE_METHODS, metrics['flags'])
        for row in metrics['methods']:
            self.assertEqual(row['verdict'], METHOD_VERDICT_NOT_APPLICABLE)
            self.assertIn(FLAG_VALUATION_UNAVAILABLE, row['flags'])
            self.assertEqual(
                row['details']['reason'], 'BASE_QUARTER_FACT_MISSING: COST_OF_REVENUE'
            )


class YearsAvailableTests(unittest.TestCase):
    """Keputusan D2: `years_available` dipotong ke riwayat yang tersedia.

    Workbook memakai konstanta 7 untuk semua kasus; engine menolak
    `years_available > jumlah periode annual`. Pemotongan itu harus terlihat
    sebagai flag, karena ia membuat IV kasus awal berbeda dari workbook.
    """

    ANNUAL = [
        {'period_end': f'{year}-12-31'} for year in range(2019, 2026)
    ]

    def test_full_history_keeps_the_registry_constant(self) -> None:
        years, flags = resolve_case_years_available(7, self.ANNUAL, '2026-06-30')
        self.assertEqual(years, 7)
        self.assertEqual(flags, [])

    def test_early_case_is_truncated_and_flagged(self) -> None:
        """Kasus 2022 Q1 hanya punya 3 tahun annual (2019-2021)."""
        years, flags = resolve_case_years_available(7, self.ANNUAL, '2022-03-31')
        self.assertEqual(years, 3)
        self.assertEqual(flags, [FLAG_YEARS_AVAILABLE_TRUNCATED])

    def test_cutoff_date_can_be_earlier_than_the_analysis_date(self) -> None:
        """Regresi bug nyata: AUTO 2023-Q4 memakai kuartal dasar 2023-Q3.

        Engine valuasi memotong periode annual pada `period_end` kuartal dasar,
        bukan pada `analysis_date`. Bila `years_available` dihitung dari
        `analysis_date`, satu tahun yang kemudian dibuang engine tetap terhitung
        dan engine menolak dengan `YEARS_AVAILABLE_EXCEEDS_HISTORY`.

        Pada 2023-12-31 ada 5 tahun annual (2019-2023); pada 2023-09-30 hanya 4
        (2019-2022, karena 2023 baru lengkap setelah Q4).
        """
        with_analysis_date, _ = resolve_case_years_available(
            7, self.ANNUAL, '2023-12-31'
        )
        with_cutoff, _ = resolve_case_years_available(
            7, self.ANNUAL, '2023-12-31', cutoff_date='2023-09-30'
        )
        self.assertEqual(with_analysis_date, 5)
        self.assertEqual(with_cutoff, 4)
        self.assertLess(with_cutoff, with_analysis_date)

    def test_at_least_one_year_is_always_returned(self) -> None:
        """Nol akan ditolak engine dan tidak berarti apa pun."""
        years, _ = resolve_case_years_available(7, [], '2022-03-31')
        self.assertEqual(years, 1)

    def test_registry_lower_than_history_is_not_flagged(self) -> None:
        years, flags = resolve_case_years_available(3, self.ANNUAL, '2026-06-30')
        self.assertEqual(years, 3)
        self.assertEqual(flags, [])


class WindowBoundaryTests(unittest.TestCase):
    """Inklusivitas batas window - sumber bug paling mudah di fase ini.

    `Ret 3M` memakai `[T0, EDATE(+3)]` (awal inklusif), sedangkan `Ret 6M`/`9M`/
    `12M` memakai `(EDATE(+n-3), EDATE(+n)]` (awal eksklusif). Bar tanggal
    `EDATE(+3)` karena itu masuk ke `Ret 3M` **dan** `Ret 6M`; bar tanggal
    `EDATE(+6)` masuk `Ret 6M` **dan** `Ret 9M`.
    """

    #: Bar di batas-batas window: T0, +3, +6, +9, +12, dan satu di luar.
    BARS = [
        {'trading_date': '2024-01-31', 'close_price': '100', 'high_price': '110', 'low_price': '90'},
        {'trading_date': '2024-04-30', 'close_price': '100', 'high_price': '200', 'low_price': '80'},
        {'trading_date': '2024-07-31', 'close_price': '100', 'high_price': '300', 'low_price': '70'},
        {'trading_date': '2024-10-31', 'close_price': '100', 'high_price': '400', 'low_price': '60'},
        {'trading_date': '2025-01-31', 'close_price': '100', 'high_price': '500', 'low_price': '50'},
        {'trading_date': '2025-02-28', 'close_price': '100', 'high_price': '900', 'low_price': '10'},
    ]

    def test_boundary_day_is_shared_between_adjacent_windows(self) -> None:
        windows = price_windows(self.BARS, '2024-01-31')
        # EDATE(2024-01-31, +3) = 2024-04-30 -> high 200 ada di 3M dan 6M.
        self.assertEqual(windows.high_3m, Decimal('200'))
        self.assertEqual(windows.high_6m, Decimal('300'))
        self.assertEqual(windows.high_9m, Decimal('400'))
        self.assertEqual(windows.high_12m, Decimal('500'))

    def test_lows_use_the_same_boundaries(self) -> None:
        windows = price_windows(self.BARS, '2024-01-31')
        self.assertEqual(windows.low_3m, Decimal('80'))
        self.assertEqual(windows.low_6m, Decimal('70'))
        self.assertEqual(windows.low_9m, Decimal('60'))
        self.assertEqual(windows.low_12m, Decimal('50'))

    def test_the_start_of_the_3m_window_is_inclusive(self) -> None:
        """Bar T0 sendiri ikut dihitung di `Ret 3M`."""
        windows = price_windows(self.BARS, '2024-01-31')
        self.assertEqual(windows.high_3m, Decimal('200'))
        self.assertGreaterEqual(windows.high_3m, Decimal('110'))

    def test_data_after_the_twelve_month_window_is_excluded(self) -> None:
        """Bar 2025-02-28 (di luar EDATE(+12) = 2025-01-31) tidak boleh muncul."""
        windows = price_windows(self.BARS, '2024-01-31')
        self.assertEqual(windows.peak_price, Decimal('500'))
        self.assertEqual(windows.trough_price, Decimal('50'))
        self.assertEqual(windows.window_end, date(2025, 1, 31))

    def test_peak_and_trough_never_look_before_the_analysis_date(self) -> None:
        """Riwayat sebelum T0 dipakai untuk harga analisis, bukan untuk peak.

        Kalau peak ikut mengambil riwayat lama, `Harga Peak` bisa lebih kecil dari
        harga analisis dan `Ret Peak` jadi negatif - sesuatu yang tidak pernah
        terjadi di workbook.
        """
        bars = [
            {'trading_date': '2023-06-30', 'close_price': '100', 'high_price': '9999', 'low_price': '1'},
            *self.BARS,
        ]
        windows = price_windows(bars, '2024-01-31')
        self.assertEqual(windows.analysis_price, Decimal('100'))
        self.assertEqual(windows.peak_price, Decimal('500'))
        self.assertEqual(windows.trough_price, Decimal('50'))

    def test_empty_window_yields_none_not_zero(self) -> None:
        """Window kosong -> NULL + `WINDOW_EMPTY`, bukan 0."""
        bars = [{'trading_date': '2024-01-31', 'close_price': '100', 'high_price': '110', 'low_price': '90'}]
        windows = price_windows(bars, '2024-01-31')
        self.assertIsNone(windows.high_6m)
        self.assertIsNone(windows.low_12m)
        self.assertIn(FLAG_WINDOW_EMPTY, windows.flags)

    def test_no_price_history_at_all_is_flagged(self) -> None:
        windows = price_windows([], '2024-01-31')
        self.assertIsNone(windows.analysis_price)
        self.assertIsNone(windows.peak_price)
        self.assertIn(FLAG_NO_PRICE_HISTORY, windows.flags)
        row = price_metrics([], '2024-01-31')
        self.assertEqual(row['calculation_status'], 'UNAVAILABLE')
        self.assertIn(FLAG_ANALYSIS_PRICE_UNAVAILABLE, row['flags'])


class PartialWindowTests(unittest.TestCase):
    """Kasus 2026 Q2: window 12 bulan belum selesai.

    Data berhenti jauh sebelum `EDATE(2026-06-30, +12)`, jadi `Ret 9M` dan
    `Ret 12M` belum bisa dihitung. Ini **bukan** error: barisnya tetap disimpan
    dengan `WINDOW_PARTIAL` supaya UI bisa menampilkan "belum lengkap" alih-alih
    kehilangan kasusnya sama sekali.
    """

    @classmethod
    def setUpClass(cls) -> None:
        cls.fixture = load_fixture('auto')
        cls.case = case_for(cls.fixture, '2026-Q2')

    def test_case_is_selected_not_skipped(self) -> None:
        self.assertEqual(self.case.case_quarter, '2026-Q2')
        self.assertEqual(analysis_date_for(self.case), date(2026, 6, 30))

    def test_analysis_price_is_available(self) -> None:
        windows = price_windows(self.fixture['prices'], analysis_date_for(self.case))
        self.assertEqual(windows.analysis_price, Decimal('2350'))

    def test_incomplete_horizons_are_null_not_error(self) -> None:
        windows = price_windows(self.fixture['prices'], analysis_date_for(self.case))
        self.assertEqual(windows.high_3m, Decimal('3520'))
        self.assertEqual(windows.low_3m, Decimal('2320'))
        self.assertIsNone(windows.high_6m)
        self.assertIsNone(windows.low_6m)
        self.assertIsNone(windows.high_9m)
        self.assertIsNone(windows.low_9m)
        self.assertIsNone(windows.high_12m)
        self.assertIsNone(windows.low_12m)

    def test_window_partial_flag_is_raised(self) -> None:
        windows = price_windows(self.fixture['prices'], analysis_date_for(self.case))
        self.assertIn(FLAG_WINDOW_PARTIAL, windows.flags)
        self.assertLess(windows.data_edge, windows.window_end)

    def test_row_is_approximated_not_unavailable(self) -> None:
        row = price_metrics(
            self.fixture['prices'],
            analysis_date_for(self.case),
            case_flags=case_provenance_flags(self.case),
        )
        self.assertEqual(row['calculation_status'], 'APPROXIMATED')
        self.assertIsNotNone(row['peak_price'])
        self.assertEqual(row['details']['window_end'], '2027-06-30')

    def test_peak_and_trough_still_use_the_available_part(self) -> None:
        """Peak/trough dari data yang ada tetap berguna dan tetap dilaporkan."""
        windows = price_windows(self.fixture['prices'], analysis_date_for(self.case))
        self.assertEqual(windows.peak_price, Decimal('3520'))
        self.assertEqual(windows.trough_price, Decimal('2320'))


class ExcelHelperTests(unittest.TestCase):
    """`EDATE` dan `DATEDIF` harus sama dengan Excel, termasuk di akhir bulan."""

    def test_edate_clamps_the_day_of_month(self) -> None:
        self.assertEqual(edate(date(2026, 5, 31), -3), date(2026, 2, 28))
        self.assertEqual(edate(date(2026, 6, 30), -3), date(2026, 3, 30))
        self.assertEqual(edate(date(2024, 1, 31), 3), date(2024, 4, 30))

    def test_edate_shifts_across_years(self) -> None:
        self.assertEqual(edate(date(2022, 3, 31), 12), date(2023, 3, 31))

    def test_datedif_counts_only_completed_months(self) -> None:
        """2022-03-31 -> 2023-03-03: 11 bulan, bukan 12 (tanggal 3 < 31)."""
        self.assertEqual(datedif_months(date(2022, 3, 31), date(2023, 3, 3)), 11)
        self.assertEqual(datedif_months(date(2022, 3, 31), date(2023, 3, 31)), 12)

    def test_datedif_is_zero_on_the_same_day(self) -> None:
        self.assertEqual(datedif_months(date(2022, 3, 31), date(2022, 3, 31)), 0)

    def test_datedif_same_day_of_month_is_exact(self) -> None:
        self.assertEqual(datedif_months(date(2022, 1, 15), date(2022, 4, 15)), 3)
        self.assertEqual(datedif_months(date(2022, 1, 15), date(2022, 4, 14)), 2)


class AsOfPriceTests(unittest.TestCase):
    """Harga analisis harus point-in-time: tidak ada harga masa depan."""

    PRICES = [
        {'trading_date': '2024-01-05', 'close_price': '100'},
        {'trading_date': '2024-01-20', 'close_price': '200'},
        {'trading_date': '2024-02-10', 'close_price': '300'},
    ]

    def test_last_close_on_or_before_the_date_wins(self) -> None:
        self.assertEqual(as_of_price(self.PRICES, '2024-01-20'), Decimal('200'))
        self.assertEqual(as_of_price(self.PRICES, '2024-01-31'), Decimal('200'))
        self.assertEqual(as_of_price(self.PRICES, '2024-02-28'), Decimal('300'))

    def test_no_price_before_the_date_returns_none(self) -> None:
        self.assertIsNone(as_of_price(self.PRICES, '2024-01-01'))

    def test_future_prices_are_never_substituted(self) -> None:
        self.assertNotEqual(as_of_price(self.PRICES, '2024-01-01'), Decimal('100'))

    def test_null_close_is_skipped_in_favour_of_the_last_real_close(self) -> None:
        prices = [
            {'trading_date': '2024-01-05', 'close_price': '100'},
            {'trading_date': '2024-01-20', 'close_price': None},
        ]
        self.assertEqual(as_of_price(prices, '2024-01-31'), Decimal('100'))

    def test_duplicate_trading_dates_are_rejected(self) -> None:
        prices = [
            {'trading_date': '2024-01-05', 'close_price': '100'},
            {'trading_date': '2024-01-05', 'close_price': '110'},
        ]
        with self.assertRaisesRegex(BacktestError, 'DUPLICATE_TRADING_DATE'):
            normalize_bars(prices)


class EngineBoundaryTests(unittest.TestCase):
    """Batas arsitektur yang mudah dilanggar tanpa disadari.

    Dua hal yang dijaga di sini:

    1. `backtest_engine` tidak boleh menarik transport. Kalau ia bisa membaca DB,
       maka ada jalan membaca data di luar cutoff kasus.
    2. Definisi metodologi backtest tidak boleh masuk ke
       `supplemental_methodology_seeds()`, karena
       `tests/test_valuation_engine.py:105` mengunci fungsi itu ke tepat satu
       baris `VALUATION_CURRENT`.
    """

    def test_engine_does_not_import_transport(self) -> None:
        """Diperiksa dari baris `import`, bukan dari seluruh teks file.

        Docstring modul ini sengaja menyebut `requests`/`SupabaseRest` untuk
        menjelaskan mengapa keduanya **tidak** dipakai, jadi pencocokan teks
        mentah akan menuduh dirinya sendiri. Yang benar-benar menjaga batasnya
        adalah daftar import.
        """
        import ast

        source = (ROOT / 'supabase' / 'backtest_engine.py').read_text(encoding='utf-8')
        tree = ast.parse(source)
        imported: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.update(alias.name.split('.')[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported.add(node.module.split('.')[0])

        for forbidden in ('requests', 'calculation_v1_common', 'supabase'):
            self.assertNotIn(forbidden, imported, f'backtest_engine must not import {forbidden}')
        # `calculation_registry` hanya untuk hashing, bukan transport.
        self.assertEqual(imported, {'__future__', 'dataclasses', 'datetime', 'decimal', 'typing', 'calculation_registry', 'pit_primitives'})

    def test_decimal_precision_matches_the_calculation_layer(self) -> None:
        """Konstanta lokal harus sama nilainya, bukan sekadar ada."""
        source = (ROOT / 'supabase' / 'calculation_v1_common.py').read_text(encoding='utf-8')
        expected = next(
            line for line in source.splitlines() if line.startswith('DECIMAL_PRECISION')
        )
        self.assertEqual(DECIMAL_PRECISION, int(expected.split('=')[1].strip()))

    def test_backtest_methodology_is_not_in_the_frozen_supplemental_seed(self) -> None:
        from calculation_methodology_registry import supplemental_methodology_seeds

        codes = {seed['method_code'] for seed in supplemental_methodology_seeds()}
        self.assertEqual(codes, {'VALUATION_CURRENT'})
        self.assertNotIn(METHOD_CODE, codes)

    def test_backtest_methodology_hashes_are_reproducible(self) -> None:
        seed = backtest_methodology_seed()
        self.assertEqual(seed['method_code'], METHOD_CODE)
        self.assertEqual(seed['formula_hash'], sha256_text(seed['formula_text']))
        self.assertEqual(seed['parameter_hash'], sha256_json(seed['parameter_spec']))

    def test_backtest_methodology_declares_the_window_rules(self) -> None:
        """Aturan window harus terbaca dari registry, bukan hanya dari kode."""
        spec = backtest_methodology_seed()['parameter_spec']
        self.assertEqual(spec['window_start_inclusive_months'], ['3'])
        self.assertEqual(spec['window_start_exclusive_months'], ['6', '9', '12'])
        self.assertEqual(spec['zero_high_low_falls_back_to_close'], 'true')
        self.assertEqual(spec['peak_month_rule'], 'datedif_months_to_first_peak_date')

    def test_backtest_methodology_declares_the_verdict_rules(self) -> None:
        """Aturan verdict harus terbaca dari registry, bukan hanya dari kode."""
        spec = backtest_methodology_seed()['parameter_spec']
        self.assertEqual(spec['verdict_rule'], 'workbook_ay_az_verbatim')
        # Satu ambang untuk kedua klasifikasi.
        self.assertEqual(spec['verdict_upside_target'], '1.2')
        self.assertEqual(spec['verdict_downside_target'], '0.85')
        self.assertEqual(spec['verdict_window_months'], '12')
        self.assertEqual(spec['verdict_window_start'], 'exclusive_after_analysis_date')
        self.assertEqual(spec['verdict_mos_threshold'], '0.3')
        self.assertEqual(spec['verdict_overvalued_no_touch'], 'FLAT')
        self.assertEqual(spec['zero_intrinsic_value_is_skip'], 'true')
        self.assertEqual(spec['case_min_age_months'], '4')
        self.assertEqual(
            list(spec['consensus_undervalued_classes']), list(CONSENSUS_UNDERVALUED_CLASSES)
        )

    def test_backtest_methodology_declares_the_stock_type_rule(self) -> None:
        """Aturan tipe per kasus (D7) harus terbaca dari registry, bukan hanya kode."""
        spec = backtest_methodology_seed()['parameter_spec']
        self.assertEqual(
            spec['stock_type_rule'], 'metrics_classification_recomputed_per_case'
        )
        self.assertEqual(spec['stock_type_cutoff'], 'period_end_lte_analysis_date')
        self.assertEqual(
            spec['stock_type_price_cutoff'], 'trading_date_lte_analysis_date'
        )
        self.assertEqual(
            spec['stock_type_growth_window'],
            'annual_growth_recomputed_for_the_case_window',
        )
        self.assertEqual(
            spec['stock_type_reference_selection'],
            'type_weights_and_thresholds_of_the_case_type',
        )
        self.assertIn('Stock type per case (D7)', backtest_methodology_seed()['formula_text'])

    def test_phase_1_rows_carry_no_valuation_columns(self) -> None:
        """Fase 1 hanya harga: tidak ada MoS, konsensus, atau verdict."""
        row = price_metrics(
            [{'trading_date': '2024-01-31', 'close_price': '100', 'high_price': '110', 'low_price': '90'}],
            '2024-01-31',
        )
        for absent in ('mos_main', 'mos_weight', 'consensus', 'verdict', 'verdict_mos'):
            self.assertNotIn(absent, row)

    def test_price_metrics_keys_are_the_storable_column_names(self) -> None:
        row = price_metrics([], '2024-01-31')
        self.assertEqual(
            set(row),
            {
                'analysis_date', 'analysis_price', 'analysis_price_source',
                'high_3m', 'low_3m', 'high_6m', 'low_6m',
                'high_9m', 'low_9m', 'high_12m', 'low_12m',
                'peak_price', 'trough_price', 'peak_month', 'trough_month',
                'return_peak', 'return_down',
                'calculation_status', 'flags', 'details',
            },
        )

    def test_bar_high_low_accessors(self) -> None:
        bar = Bar(
            trading_date=date(2024, 1, 31),
            close_price=Decimal('100'),
            high=Decimal('110'),
            low=Decimal('90'),
        )
        self.assertTrue(bar.has_high)
        self.assertTrue(bar.has_low)
        self.assertFalse(
            Bar(trading_date=date(2024, 1, 31), close_price=None, high=None, low=None).has_high
        )


class OrchestratorCaseTests(unittest.TestCase):
    """Regresi pada pemotongan harga di `run_backtest.calculate_cases`.

    Bug yang dijaga di sini pernah benar-benar terjadi: orkestrator memotong
    harga pada `analysis_date` **dan** `EDATE(+12)`. Karena akhir kuartal sering
    jatuh pada akhir pekan atau hari libur bursa, bar yang menjadi harga analisis
    justru ada **sebelum** `analysis_date`, sehingga pemotongan itu mengosongkan
    harga analisis untuk 182 dari 367 kasus. Engine-nya benar; pemanggilnya yang
    salah, jadi ujinya ada di tingkat pemanggil.
    """

    #: `2024-03-31` adalah hari Minggu, jadi tidak ada bar pada tanggal itu.
    PERIODS = [
        {'id': 'a-2020', 'instrument_id': 'i', 'period_type': 'ANNUAL', 'period_end': '2020-12-31'},
        {'id': 'a-2021', 'instrument_id': 'i', 'period_type': 'ANNUAL', 'period_end': '2021-12-31'},
        {'id': 'a-2022', 'instrument_id': 'i', 'period_type': 'ANNUAL', 'period_end': '2022-12-31'},
        {'id': 'a-2023', 'instrument_id': 'i', 'period_type': 'ANNUAL', 'period_end': '2023-12-31'},
        {'id': 'q-2024-1', 'instrument_id': 'i', 'period_type': 'QUARTER', 'period_end': '2024-03-31'},
    ]

    PRICES = [
        {'trading_date': '2024-03-28', 'close_price': '100', 'high_price': '105', 'low_price': '95'},
        {'trading_date': '2024-06-28', 'close_price': '120', 'high_price': '130', 'low_price': '110'},
        {'trading_date': '2025-03-28', 'close_price': '150', 'high_price': '160', 'low_price': '140'},
    ]

    def test_analysis_price_survives_a_non_trading_period_end(self) -> None:
        import run_backtest

        results = run_backtest.calculate_cases(self.PERIODS, self.PRICES)
        self.assertEqual(len(results), 1)
        metrics = results[0]['metrics']
        self.assertEqual(metrics['analysis_date'], '2024-03-31')
        # Close terakhir sebelum 2024-03-31 adalah 2024-03-28 -> 100.
        self.assertEqual(metrics['analysis_price'], Decimal('100'))
        self.assertNotIn(FLAG_ANALYSIS_PRICE_UNAVAILABLE, metrics['flags'])

    def test_prices_after_the_twelve_month_window_are_dropped_by_the_caller(self) -> None:
        """Bar 2025-03-28 ada tepat di `EDATE(+12)` dan tetap dipakai."""
        import run_backtest

        results = run_backtest.calculate_cases(self.PERIODS, self.PRICES)
        metrics = results[0]['metrics']
        self.assertEqual(metrics['high_12m'], Decimal('160'))
        self.assertEqual(metrics['peak_price'], Decimal('160'))

    def test_row_keys_match_the_table_columns(self) -> None:
        import run_backtest

        results = run_backtest.calculate_cases(self.PERIODS, self.PRICES)
        rows = run_backtest._case_rows(
            results,
            methodology_id='m',
            instrument_id='i',
            sector_name='Sector',
        )
        self.assertEqual(len(rows), 1)
        row = rows[0]
        for column in (
            'case_quarter', 'base_year', 'analysis_date', 'analysis_price',
            'analysis_price_source', 'high_3m', 'low_3m', 'high_6m', 'low_6m',
            'high_9m', 'low_9m', 'high_12m', 'low_12m', 'peak_price',
            'trough_price', 'peak_month', 'return_peak', 'return_down',
            'calculation_status', 'flags', 'details',
        ):
            self.assertIn(column, row)
        self.assertEqual(row['case_quarter'], '2024-Q1')
        self.assertEqual(row['base_year'], 2023)
        # `calculation_run_id` distempel `_store` setelah run dibuat.
        self.assertNotIn('calculation_run_id', row)
        # Kolom valuasi Fase 2 ada, tetapi kosong karena tidak ada
        # `valuation_inputs` di kasus ini.
        self.assertIsNone(row['stock_type'])
        self.assertIsNone(row['mos_main'])
        self.assertIsNone(row['consensus'])
        # Verdict tetap NULL: itu Fase 3, dan verdict palsu tidak bisa
        # dibedakan dari verdict asli.
        self.assertIsNone(row['verdict'])
        self.assertIsNone(row['verdict_mos'])

    def test_unresolved_stock_type_keeps_price_metrics(self) -> None:
        """Regresi bug nyata: INDF/JSMR `UNCLASSIFIED` menggagalkan seluruh ticker.

        Tipe saham yang tidak bisa dipertanggungjawabkan harus menggagalkan
        **valuasi**, bukan kasusnya. Sebelum diperbaiki, `_resolve_stock_type`
        melempar sebelum satu pun metrik harga dihitung, sehingga 18 kasus INDF
        hilang seluruhnya.
        """
        import run_backtest

        results = run_backtest.calculate_cases(
            self.PERIODS,
            self.PRICES,
            valuation_inputs={
                'ticker': 'TEST',
                'instrument': {'ticker': 'TEST', 'sector_name': 'Sector'},
                'stock_type': None,
                'stock_type_error': 'CLASSIFICATION_UNCLASSIFIED_NO_RULE_MATCHED',
                'periods': self.PERIODS,
                'facts': [],
                'prices': self.PRICES,
                'dividend_rows': [],
                'reference': {},
                'risk_free_rate': None,
                'risk_free_source': None,
                'valuation_parameters': {},
            },
        )
        self.assertEqual(len(results), 1)
        metrics = results[0]['metrics']
        # Metrik harga tetap lengkap dan benar.
        self.assertEqual(metrics['analysis_price'], Decimal('100'))
        self.assertEqual(metrics['high_12m'], Decimal('160'))
        # Valuasinya ditandai tidak tersedia, dengan alasan yang bisa dilacak.
        valuation = results[0]['valuation']
        self.assertIn(FLAG_VALUATION_UNAVAILABLE, valuation['flags'])
        self.assertEqual(valuation['consensus'], 'N/A')
        self.assertIsNone(valuation['stock_type'])
        self.assertIsNone(valuation['years_available'])
        self.assertIn(
            'STOCK_TYPE_UNRESOLVED',
            valuation['methods'][0]['details']['reason'],
        )

    def test_case_rows_include_phase_2_columns_as_null_without_valuation(self) -> None:
        """Tanpa input valuasi, kolom Fase 2 tetap ada tetapi NULL."""
        import run_backtest

        results = run_backtest.calculate_cases(self.PERIODS, self.PRICES)
        row = run_backtest._case_rows(
            results,
            methodology_id='m',
            instrument_id='i',
            sector_name='Sector',
        )[0]
        for column in (
            'years_available', 'years_compare', 'mos_main', 'mos_peter', 'mos_weight',
            'mos_method_code', 'consensus', 'consensus_undervalued', 'consensus_valid',
        ):
            self.assertIn(column, row)
            self.assertIsNone(row[column])


class PerCaseStockTypeTests(unittest.TestCase):
    """D7: tipe saham dihitung pada tanggal kasus, bukan snapshot terbaru.

    Yang dikunci di sini adalah **bentuk** mekanismenya (sidik input, pemilihan
    bobot tipe per kasus, cache), bukan angka IV - angka itu bergantung pada
    registry dan data hidup dan diperiksa lewat `Testing/stock_type_pit_check.py`.
    """

    PERIODS = [
        {'id': 'a-2019', 'instrument_id': 'i', 'period_type': 'ANNUAL', 'period_end': '2019-12-31'},
        {'id': 'a-2020', 'instrument_id': 'i', 'period_type': 'ANNUAL', 'period_end': '2020-12-31'},
        {'id': 'a-2021', 'instrument_id': 'i', 'period_type': 'ANNUAL', 'period_end': '2021-12-31'},
        {'id': 'a-2022', 'instrument_id': 'i', 'period_type': 'ANNUAL', 'period_end': '2022-12-31'},
        {'id': 'a-2023', 'instrument_id': 'i', 'period_type': 'ANNUAL', 'period_end': '2023-12-31'},
        {'id': 'q-2024-1', 'instrument_id': 'i', 'period_type': 'QUARTER',
         'period_label': '2024-Q1', 'period_end': '2024-03-31'},
    ]

    PRICES = [
        {'trading_date': '2024-03-28', 'close_price': '100', 'high_price': '105', 'low_price': '95'},
    ]

    FACTS = [
        {'financial_period_id': 'q-2024-1', 'metric_code': 'REVENUE',
         'value_numeric': '1000', 'revision_key': 'CURRENT'},
    ]

    def fingerprint(self, **overrides):
        import run_backtest

        arguments = {
            'instrument_id': 'i',
            'case_quarter': '2024-Q1',
            'analysis_date': '2024-03-31',
            'years_available': 4,
            'base_quarter': '2024-Q1',
            'classifier_parameters': {'classifier_thresholds': {'x': '1'}},
            'annual_periods': self.PERIODS[:5],
            'quarter_periods': self.PERIODS[5:],
            'facts': self.FACTS,
            'prices': self.PRICES,
            'dividend_rows': [],
        }
        arguments.update(overrides)
        return run_backtest._stock_type_fingerprint(**arguments)

    def test_fingerprint_is_stable_for_the_same_input(self) -> None:
        """Input yang sama selalu menghasilkan sidik yang sama."""
        self.assertEqual(self.fingerprint(), self.fingerprint())

    def test_fingerprint_changes_when_a_fact_is_revised(self) -> None:
        """Revisi laporan menggugurkan cache walau daftar periodenya tetap.

        Ini inti janji cache: `revision_key` dan nilai fakta ikut di-hash, jadi
        laporan yang direvisi pada periode yang sama tidak akan memakai tipe lama.
        """
        revised = [{**self.FACTS[0], 'value_numeric': '1200'}]
        self.assertNotEqual(self.fingerprint(), self.fingerprint(facts=revised))

        rekeyed = [{**self.FACTS[0], 'revision_key': 'RESTATED'}]
        self.assertNotEqual(self.fingerprint(), self.fingerprint(facts=rekeyed))

    def test_fingerprint_changes_when_classifier_thresholds_change(self) -> None:
        """Perubahan ambang classifier harus memaksa tipe dihitung ulang."""
        changed = {'classifier_thresholds': {'x': '2'}}
        self.assertNotEqual(
            self.fingerprint(), self.fingerprint(classifier_parameters=changed)
        )

    def test_fingerprint_changes_when_a_price_lands_on_the_case(self) -> None:
        """Harga baru pada atau sebelum tanggal kasus mengubah sidik."""
        extra = [
            *self.PRICES,
            {'trading_date': '2024-03-29', 'close_price': '101',
             'high_price': '106', 'low_price': '96'},
        ]
        self.assertNotEqual(self.fingerprint(), self.fingerprint(prices=extra))

    def test_fingerprint_ignores_row_order(self) -> None:
        """Urutan baris dari PostgREST tidak boleh mengubah sidik."""
        self.assertEqual(
            self.fingerprint(),
            self.fingerprint(
                annual_periods=list(reversed(self.PERIODS[:5])),
                facts=list(reversed(self.FACTS)),
            ),
        )

    def test_reference_selection_uses_the_case_type(self) -> None:
        """Bobot/ambang dipilih per tipe kasus, bukan per tipe snapshot."""
        import run_backtest

        reference = {
            'sector_weights': {'sector_name': 'S'},
            'type_weights_by_type': {
                'Cyclical': {'stock_type': 'Cyclical', 'w_pe': '0'},
                'Fast Grower': {'stock_type': 'Fast Grower', 'w_pe': '3'},
            },
            'type_thresholds_by_type': {
                'Cyclical': {'stock_type': 'Cyclical', 'max_der': '1'},
            },
        }
        cyclical = run_backtest._reference_for_type(reference, 'CYCLICAL')
        self.assertEqual(cyclical['type_weights']['stock_type'], 'Cyclical')
        self.assertEqual(cyclical['type_thresholds']['stock_type'], 'Cyclical')
        fast = run_backtest._reference_for_type(reference, 'FAST GROWER')
        self.assertEqual(fast['type_weights']['stock_type'], 'Fast Grower')
        # Ambang tipe yang tidak ada tetap `None`, bukan ditebak dari tipe lain.
        self.assertIsNone(fast['type_thresholds'])

    def test_reference_selection_returns_none_without_a_type(self) -> None:
        """Tipe yang tidak bisa dipertanggungjawabkan tidak memakai bobot tipe."""
        import run_backtest

        reference = {'type_weights_by_type': {'Cyclical': {'stock_type': 'Cyclical'}}}
        selected = run_backtest._reference_for_type(reference, None)
        self.assertIsNone(selected['type_weights'])
        self.assertIsNone(selected['type_thresholds'])

    def test_case_rows_record_the_stock_type_provenance(self) -> None:
        """Tanpa valuasi, `details` hanya memuat provenance harga kasus."""
        import run_backtest

        results = run_backtest.calculate_cases(self.PERIODS, self.PRICES)
        row = run_backtest._case_rows(
            results,
            methodology_id='m',
            instrument_id='i',
            sector_name='Sector',
        )[0]
        self.assertIsNone(row['stock_type'])
        self.assertNotIn('stock_type_fingerprint', row['details'])
        self.assertIn('window_end', row['details'])

    def test_cache_skips_unresolved_cases_instead_of_storing_empty_text(self) -> None:
        """Regresi: cache tidak boleh mengubah `stock_type` NULL menjadi `''`.

        Bug nyata: baris yang tipenya tidak bisa dipertanggungjawabkan
        (`stock_type` NULL) ikut di-cache sebagai string kosong, sehingga run
        berikutnya melewati jalur `STOCK_TYPE_UNRESOLVED` dan menulis `''` ke
        kolom `stock_type`. Itu tampak seperti tipe yang sah padahal bukan.
        """
        import run_backtest

        class StubDb:
            def get_all(self, table, params):
                if table == 'calculation_runs':
                    return [{'id': 'run-1', 'completed_at': 'x', 'created_at': 'x'}]
                return [
                    {
                        'case_quarter': '2021-Q1',
                        'stock_type': None,
                        'details': {'stock_type_fingerprint': 'fp-a'},
                    },
                    {
                        'case_quarter': '2021-Q2',
                        'stock_type': '',
                        'details': {'stock_type_fingerprint': 'fp-b'},
                    },
                    {
                        'case_quarter': '2021-Q3',
                        'stock_type': 'CYCLICAL',
                        'details': {'stock_type_fingerprint': 'fp-c', 'stock_type_raw': 'CYCLICAL'},
                    },
                    {
                        'case_quarter': '2021-Q4',
                        'stock_type': 'CYCLICAL',
                        'details': {},
                    },
                ]

        cache = run_backtest._stock_type_cache(StubDb(), 'instrument-1')
        self.assertEqual(set(cache), {'2021-Q3'})
        self.assertEqual(cache['2021-Q3']['fingerprint'], 'fp-c')
        self.assertEqual(cache['2021-Q3']['stock_type'], 'CYCLICAL')

    def test_cache_is_empty_without_a_succeeded_run(self) -> None:
        """Belum ada run -> tidak ada yang bisa dipakai ulang."""
        import run_backtest

        class StubDb:
            def get_all(self, table, params):
                return []

        self.assertEqual(run_backtest._stock_type_cache(StubDb(), 'instrument-1'), {})


class VerdictTests(unittest.TestCase):
    """Fase 3: `Verdict by Method` dan `Verdict MoS` dari rumus workbook 5.4.1.

    Nilai acuan diambil dari sheet `Backtest_Historical (New)` di
    `Template/Stock Analyzer [Dev] Quarter.xlsm`, kolom AY/AZ - bukan dari
    frontend, yang tiga cabangnya berbeda.
    """

    #: Ground truth AUTO 2022Q1..2026Q2 (18 baris).
    #:
    #: Kolom AY/AZ workbook di disk masih memakai rumus **lama** (`1.15`/`0.9`,
    #: `OBSERVE`, cabang hari-sama), jadi 16 dari 18 baris masih sama dan dua
    #: baris sengaja **berbeda** di sini karena aturan barunya berbeda:
    #:
    #:   * `2024-Q3` - lama `REPRICE`, baru `CONFIRMED`. Ambang naik 1.15 -> 1.20
    #:     membuat peak 2620 tidak lagi menembus 2712 dari harga 2260.
    #:   * `2026-Q1` - lama `CONFIRMED`, baru `REPRICE`. Ambang turun 0.90 -> 0.85
    #:     membuat trough 2230 tidak lagi menembus 2218.5 dari harga 2610.
    #:
    #: Nilai baru dihitung ulang dari `tests/fixtures/auto_backtest.json` dengan
    #: implementasi kedua (tidak memanggil `backtest_engine`) supaya hasilnya
    #: bukan sekadar salinan keluaran engine.
    AUTO_TRUTH = (
        ('2022-Q1', '2|5', '0.55094260162338926', 'REPRICE', 'WIN'),
        ('2022-Q2', '2|5', '0.54482564268219025', 'REPRICE', 'WIN'),
        ('2022-Q3', '3|5', '0.521076267913687', 'WIN', 'WIN'),
        ('2022-Q4', '3|5', '0.46037833218774904', 'WIN', 'WIN'),
        ('2023-Q1', '2|5', '0.39756011049805484', 'REPRICE', 'WIN'),
        ('2023-Q2', '1|5', '0.11033656590063758', 'REPRICE', 'REPRICE'),
        ('2023-Q3', '0|5', '-9.6730131166103586E-2', 'CONFIRMED', 'CONFIRMED'),
        ('2023-Q4', '1|5', '0.21769011021117038', 'CONFIRMED', 'CONFIRMED'),
        ('2024-Q1', '1|5', '0.28568749160111601', 'CONFIRMED', 'CONFIRMED'),
        ('2024-Q2', '3|5', '0.38458759040353824', 'WIN', 'WIN'),
        ('2024-Q3', '1|5', '0.29245343533952156', 'CONFIRMED', 'CONFIRMED'),
        ('2024-Q4', '1|5', '0.28885695931081889', 'CONFIRMED', 'CONFIRMED'),
        ('2025-Q1', '3|5', '0.40993585118315051', 'WIN', 'WIN'),
        ('2025-Q2', '2|5', '0.37354402656736402', 'REPRICE', 'WIN'),
        ('2025-Q3', '2|5', '0.32644284320243816', 'REPRICE', 'WIN'),
        ('2025-Q4', '1|5', '0.23574688603451641', 'CONFIRMED', 'CONFIRMED'),
        ('2026-Q1', '1|5', '0.28074882322314787', 'REPRICE', 'REPRICE'),
        ('2026-Q2', '2|5', '0.34131319486671524', 'REPRICE', 'WIN'),
    )

    #: Harga analisis workbook per kasus (kolom `Harga Manual`/`Harga Analisis`).
    AUTO_PRICES = {
        '2022-Q1': '1125', '2022-Q2': '1140', '2022-Q3': '1245', '2022-Q4': '1460',
        '2023-Q1': '1690', '2023-Q2': '2480', '2023-Q3': '3180', '2023-Q4': '2360',
        '2024-Q1': '2230', '2024-Q2': '1895', '2024-Q3': '2260', '2024-Q4': '2300',
        '2025-Q1': '1975', '2025-Q2': '2060', '2025-Q3': '2310', '2025-Q4': '2690',
        '2026-Q1': '2610', '2026-Q2': '2350',
    }

    @classmethod
    def setUpClass(cls) -> None:
        cls.fixture = load_fixture('auto')

    def test_every_auto_case_matches_the_workbook_verdict(self) -> None:
        """Fase 3 kriteria selesai: 18/18 sama dengan kolom AY dan AZ."""
        cases = {case.case_quarter: case for case in fixture_cases(self.fixture)}
        checked = 0
        for quarter, consensus, mos_main, expected_verdict, expected_mos in self.AUTO_TRUTH:
            case = cases[quarter]
            metrics = verdict_case_metrics(
                consensus=consensus,
                mos_main=Decimal(mos_main),
                analysis_price=Decimal(self.AUTO_PRICES[quarter]),
                analysis_date=analysis_date_for(case),
                bars=self.fixture['prices'],
            )
            with self.subTest(quarter=quarter, column='Verdict by Method'):
                self.assertEqual(metrics['verdict'], expected_verdict)
            with self.subTest(quarter=quarter, column='Verdict MoS'):
                self.assertEqual(metrics['verdict_mos'], expected_mos)
            checked += 1
        self.assertEqual(checked, 18)

    def test_consensus_classification_matches_the_workbook(self) -> None:
        """`K` = `[@Konsensus]`, dan hanya enam kelas yang UNDERVALUED."""
        for consensus, expected in (
            ('3|3', 'UNDERVALUED'), ('3|4', 'UNDERVALUED'), ('4|4', 'UNDERVALUED'),
            ('3|5', 'UNDERVALUED'), ('4|5', 'UNDERVALUED'), ('5|5', 'UNDERVALUED'),
            ('0|5', 'OVERVALUED'), ('1|5', 'OVERVALUED'), ('2|5', 'OVERVALUED'),
            ('2|4', 'OVERVALUED'), ('1|3', 'OVERVALUED'),
        ):
            with self.subTest(consensus=consensus):
                self.assertEqual(classify_consensus(consensus), expected)

    def test_missing_consensus_yields_no_verdict_not_flat(self) -> None:
        """`N/A` berarti verdict tidak ada - `FLAT` adalah klaim, bukan ketiadaan."""
        for consensus in ('N/A', None, ''):
            with self.subTest(consensus=consensus):
                verdict, details, flags = verdict_for(
                    classify_consensus(consensus), Decimal('100'), [], '2024-01-31'
                )
                self.assertIsNone(verdict)
                self.assertEqual(details, {})
                self.assertEqual(flags, [FLAG_VERDICT_NO_CONSENSUS])

    def test_unrecognised_classification_is_flat_not_an_error(self) -> None:
        """Sifat 2: `K` di luar tiga nilai yang dikenal -> `FLAT`."""
        verdict, details, flags = verdict_for(
            'SOMETHING_ELSE', Decimal('100'), [], '2024-01-31'
        )
        self.assertEqual(verdict, 'FLAT')
        self.assertEqual(details['reason'], 'CLASSIFICATION_NOT_RECOGNISED')
        self.assertEqual(flags, [])

    def test_same_day_touch_falls_to_win_or_reprice(self) -> None:
        """Hari yang sama -> `WIN` (undervalued) / `REPRICE` (overvalued).

        Cabang terakhir rumus membandingkan dengan `<`, jadi `UpDate == DownDate`
        tidak lagi jadi kasus khusus. Sebelumnya hari-sama jatuh ke `RECOVERED` /
        `OBSERVE`; sekarang naik-dulu yang menang, dan `RECOVERED` hanya untuk
        yang benar-benar turun dulu.
        """
        bar = [{'trading_date': '2024-03-15', 'close_price': '100',
                'high_price': '125', 'low_price': '84'}]
        undervalued, _, _ = verdict_for('UNDERVALUED', Decimal('100'), bar, '2024-01-31')
        self.assertEqual(undervalued, 'WIN')
        overvalued, _, _ = verdict_for('OVERVALUED', Decimal('100'), bar, '2024-01-31')
        self.assertEqual(overvalued, 'REPRICE')

    def test_recovered_needs_a_genuine_down_then_up(self) -> None:
        """`RECOVERED` = turun dulu, **baru** naik - bukan hari yang sama."""
        bars = [
            {'trading_date': '2024-02-10', 'close_price': '100',
             'high_price': '101', 'low_price': '84'},
            {'trading_date': '2024-03-15', 'close_price': '100',
             'high_price': '121', 'low_price': '110'},
        ]
        verdict, details, _ = verdict_for('UNDERVALUED', Decimal('100'), bars, '2024-01-31')
        self.assertEqual(verdict, 'RECOVERED')
        self.assertEqual(details['down_date'], '2024-02-10')
        self.assertEqual(details['up_date'], '2024-03-15')

    def test_earlier_touch_wins(self) -> None:
        """Urutan tanggal menentukan, bukan urutan baris."""
        bars = [
            {'trading_date': '2024-03-15', 'close_price': '100',
             'high_price': '125', 'low_price': '99'},
            {'trading_date': '2024-02-10', 'close_price': '100',
             'high_price': '101', 'low_price': '79'},
        ]
        # Down lebih dulu (10 Feb) daripada up (15 Mar).
        verdict, details, _ = verdict_for('UNDERVALUED', Decimal('100'), bars, '2024-01-31')
        self.assertEqual(verdict, 'RECOVERED')
        self.assertEqual(details['down_date'], '2024-02-10')
        self.assertEqual(details['up_date'], '2024-03-15')

    def test_verdict_window_starts_strictly_after_the_analysis_date(self) -> None:
        """Sifat 3: window verdict `> StartDate`, berbeda dari `Ret 3M` `>=`."""
        # Hanya ada satu bar, tepat pada tanggal analisis, dan sudah menembus
        # target. Kalau batas awalnya inklusif, verdict-nya jadi WIN.
        on_date = [{'trading_date': '2024-01-31', 'close_price': '100',
                    'high_price': '125', 'low_price': '120'}]
        verdict, details, _ = verdict_for(
            'UNDERVALUED', Decimal('100'), on_date, '2024-01-31'
        )
        self.assertEqual(verdict, 'FLAT')
        self.assertIsNone(details['up_date'])

        # Satu hari setelahnya: sekarang terhitung.
        after = [{'trading_date': '2024-02-01', 'close_price': '100',
                  'high_price': '125', 'low_price': '120'}]
        verdict, details, _ = verdict_for('UNDERVALUED', Decimal('100'), after, '2024-01-31')
        self.assertEqual(verdict, 'WIN')
        self.assertEqual(details['up_date'], '2024-02-01')

    def test_verdict_window_ends_at_twelve_months_inclusive(self) -> None:
        """Batas akhir 12 bulan inklusif, sama seperti `Ret 12M`."""
        last_day = [{'trading_date': '2025-01-31', 'close_price': '100',
                     'high_price': '125', 'low_price': '120'}]
        verdict, _, _ = verdict_for('UNDERVALUED', Decimal('100'), last_day, '2024-01-31')
        self.assertEqual(verdict, 'WIN')

        too_late = [{'trading_date': '2025-02-03', 'close_price': '100',
                     'high_price': '125', 'low_price': '120'}]
        verdict, _, flags = verdict_for('UNDERVALUED', Decimal('100'), too_late, '2024-01-31')
        self.assertEqual(verdict, 'FLAT')
        self.assertEqual(flags, [FLAG_VERDICT_NO_PRICE_WINDOW])

    def test_one_threshold_pair_for_both_classifications(self) -> None:
        """x1.20 naik / x0.85 turun, **sama** untuk kedua klasifikasi.

        Klasifikasi sekarang hanya memilih nama verdict, bukan ambang harga.
        `117` tidak lagi menembus apa pun (dulu overvalued memakai 1.15).
        """
        self.assertEqual(VERDICT_UPSIDE, Decimal('1.20'))
        self.assertEqual(VERDICT_DOWNSIDE, Decimal('0.85'))
        # Alias lama harus menunjuk nilai yang sama, bukan nilai lamanya.
        self.assertEqual(VERDICT_UPSIDE_UNDERVALUED, VERDICT_UPSIDE)
        self.assertEqual(VERDICT_DOWNSIDE_UNDERVALUED, VERDICT_DOWNSIDE)
        self.assertEqual(VERDICT_UPSIDE_OTHER, VERDICT_UPSIDE)
        self.assertEqual(VERDICT_DOWNSIDE_OTHER, VERDICT_DOWNSIDE)

        bars = [{'trading_date': '2024-02-01', 'close_price': '100',
                 'high_price': '117', 'low_price': '100'}]
        undervalued, _, _ = verdict_for('UNDERVALUED', Decimal('100'), bars, '2024-01-31')
        self.assertEqual(undervalued, 'FLAT')
        overvalued, _, _ = verdict_for('OVERVALUED', Decimal('100'), bars, '2024-01-31')
        self.assertEqual(overvalued, 'FLAT')

    def test_mixed_classification_yields_flat(self) -> None:
        """`MIXED` -> `FLAT`, bukan cabang overvalued.

        Rumus kolom `AY` hanya mengenal `UNDERVALUED` dan `OVERVALUED`; apa pun
        selain itu jatuh ke `FLAT`. `classify_consensus` juga tidak pernah
        menghasilkan `MIXED`, jadi cabang ini hanya bisa dicapai lewat pemanggilan
        langsung.
        """
        bars = [{'trading_date': '2024-02-01', 'close_price': '100',
                 'high_price': '116', 'low_price': '89'}]
        verdict, details, _ = verdict_for('MIXED', Decimal('100'), bars, '2024-01-31')
        self.assertEqual(verdict, 'FLAT')
        self.assertEqual(details['reason'], 'CLASSIFICATION_NOT_RECOGNISED')
        self.assertIsNone(details['upside_target'])

    def test_overvalued_that_touches_nothing_is_flat_not_observe(self) -> None:
        """`OBSERVE` tidak dipakai lagi; cabang itu jadi `FLAT`."""
        bars = [{'trading_date': '2024-02-01', 'close_price': '100',
                 'high_price': '110', 'low_price': '95'}]
        verdict, _, _ = verdict_for('OVERVALUED', Decimal('100'), bars, '2024-01-31')
        self.assertEqual(verdict, 'FLAT')
        self.assertNotIn('OBSERVE', VERDICTS_CURRENT)

    def test_zero_high_falls_back_to_close_inside_the_filter(self) -> None:
        """Sifat 4: `High`/`Low` nol -> `Close`, di dalam filter."""
        bars = [
            {'trading_date': '2024-02-01', 'close_price': '119',
             'high_price': '0', 'low_price': '0'},
            {'trading_date': '2024-03-01', 'close_price': '121',
             'high_price': '0', 'low_price': '0'},
        ]
        verdict, details, _ = verdict_for('UNDERVALUED', Decimal('100'), bars, '2024-01-31')
        # Bar pertama close 119 belum tembus 120; yang kedua close 121 tembus.
        self.assertEqual(verdict, 'WIN')
        self.assertEqual(details['up_date'], '2024-03-01')

    def test_verdict_mos_uses_mos_main_as_k(self) -> None:
        """`Verdict MoS` = `K = MoS Main >= 30%`, hitungan terpisah."""
        self.assertEqual(MOS_VERDICT_THRESHOLD, Decimal('0.3'))
        bars = [{'trading_date': '2024-02-01', 'close_price': '100',
                 'high_price': '120', 'low_price': '100'}]
        # MoS 0.31 -> K=UNDERVALUED -> threshold 1.2; 120 tembus -> WIN.
        verdict, details, _ = verdict_mos_for(Decimal('0.31'), Decimal('100'), bars, '2024-01-31')
        self.assertEqual(verdict, 'WIN')
        self.assertEqual(details['mos_main'], '0.31')
        # MoS 0.29 -> K=OVERVALUED -> threshold 1.15; 120 tembus -> REPRICE.
        verdict, _, _ = verdict_mos_for(Decimal('0.29'), Decimal('100'), bars, '2024-01-31')
        self.assertEqual(verdict, 'REPRICE')

    def test_verdict_mos_at_the_threshold_is_undervalued(self) -> None:
        """Batas `>= 30%` inklusif."""
        bars = [{'trading_date': '2024-02-01', 'close_price': '100',
                 'high_price': '120', 'low_price': '100'}]
        verdict, _, _ = verdict_mos_for(Decimal('0.3'), Decimal('100'), bars, '2024-01-31')
        self.assertEqual(verdict, 'WIN')

    def test_missing_mos_yields_no_verdict_mos(self) -> None:
        verdict, details, flags = verdict_mos_for(None, Decimal('100'), [], '2024-01-31')
        self.assertIsNone(verdict)
        self.assertEqual(details, {})
        self.assertEqual(flags, [FLAG_VERDICT_MOS_UNDEFINED])

    def test_verdict_and_verdict_mos_can_disagree(self) -> None:
        """AUTO 2025Q2: `Verdict by Method` REPRICE tapi `Verdict MoS` WIN.

        Kalau keduanya dihitung dari `K` yang sama, kasus ini akan sama. Ini
        bukti bahwa keduanya memang dua perhitungan terpisah.
        """
        case = case_for(self.fixture, '2025-Q2')
        metrics = verdict_case_metrics(
            consensus='2|5',
            mos_main=Decimal('0.37354402656736402'),
            analysis_price=Decimal('2060'),
            analysis_date=analysis_date_for(case),
            bars=self.fixture['prices'],
        )
        self.assertEqual(metrics['verdict'], 'REPRICE')
        self.assertEqual(metrics['verdict_mos'], 'WIN')

    def test_magnitude_uses_a_ten_percent_threshold(self) -> None:
        self.assertEqual(MAGNITUDE_THRESHOLD, Decimal('0.1'))
        self.assertEqual(magnitude_for(Decimal('0.1')), 'UP')
        self.assertEqual(magnitude_for(Decimal('0.0999')), 'FLAT')
        self.assertEqual(magnitude_for(Decimal('-0.1')), 'DOWN')
        self.assertEqual(magnitude_for(Decimal('-0.0999')), 'FLAT')
        self.assertEqual(magnitude_for(Decimal('0')), 'FLAT')
        self.assertIsNone(magnitude_for(None))

    def test_every_verdict_is_one_of_the_seven_allowed_values(self) -> None:
        """Tidak boleh ada verdict di luar check constraint 0025."""
        self.assertEqual(len(VERDICTS), 7)
        self.assertEqual(
            set(VERDICTS),
            {'WIN', 'RISK', 'RECOVERED', 'FLAT', 'CONFIRMED', 'REPRICE', 'OBSERVE'},
        )
        for quarter, consensus, mos_main, _, _ in self.AUTO_TRUTH:
            case = case_for(self.fixture, quarter)
            metrics = verdict_case_metrics(
                consensus=consensus,
                mos_main=Decimal(mos_main),
                analysis_price=Decimal(self.AUTO_PRICES[quarter]),
                analysis_date=analysis_date_for(case),
                bars=self.fixture['prices'],
            )
            with self.subTest(quarter=quarter):
                self.assertIn(metrics['verdict'], VERDICTS)
                self.assertIn(metrics['verdict_mos'], VERDICTS)

    def test_risk_branch_is_reachable(self) -> None:
        """`RISK` = up kosong, down ada. Harus bisa terjadi, bukan cabang mati."""
        bars = [{'trading_date': '2024-02-01', 'close_price': '100',
                 'high_price': '101', 'low_price': '79'}]
        verdict, _, _ = verdict_for('UNDERVALUED', Decimal('100'), bars, '2024-01-31')
        self.assertEqual(verdict, 'RISK')

    def test_flat_branch_is_reachable_for_both_classifications(self) -> None:
        """Tidak menyentuh apa pun -> `FLAT` di kedua sisi (bukan `OBSERVE`)."""
        bars = [{'trading_date': '2024-02-01', 'close_price': '100',
                 'high_price': '119', 'low_price': '86'}]
        verdict, _, _ = verdict_for('UNDERVALUED', Decimal('100'), bars, '2024-01-31')
        self.assertEqual(verdict, 'FLAT')
        verdict, _, _ = verdict_for('OVERVALUED', Decimal('100'), bars, '2024-01-31')
        self.assertEqual(verdict, 'FLAT')


class VerdictCaseMetricsTests(unittest.TestCase):
    """`verdict_case_metrics` menyatukan kolom verdict satu kasus."""

    def test_bundles_verdict_verdict_mos_and_magnitudes(self) -> None:
        result = verdict_case_metrics(
            consensus='3|5',
            mos_main=Decimal('0.4'),
            analysis_price=Decimal('100'),
            analysis_date='2024-01-31',
            bars=[{'trading_date': '2024-02-01', 'close_price': '100',
                   'high_price': '121', 'low_price': '85'}],
            return_peak=Decimal('0.21'),
            return_down=Decimal('-0.21'),
        )
        self.assertEqual(result['verdict'], 'WIN')
        self.assertEqual(result['verdict_mos'], 'WIN')
        self.assertEqual(result['return_magnitude'], 'UP')
        self.assertEqual(result['return_magnitude_down'], 'DOWN')
        self.assertIn('verdict', result['verdict_details'])
        self.assertIn('verdict_mos', result['verdict_details'])
        self.assertIn('magnitude_rule', result['verdict_details'])
        self.assertEqual(result['flags'], [])

    def test_flags_are_deduplicated_and_ordered(self) -> None:
        """Konsensus dan MoS dua-duanya hilang: dua flag berbeda, tanpa duplikat."""
        result = verdict_case_metrics(
            consensus='N/A',
            mos_main=None,
            analysis_price=Decimal('100'),
            analysis_date='2024-01-31',
            bars=[],
        )
        self.assertIsNone(result['verdict'])
        self.assertIsNone(result['verdict_mos'])
        self.assertEqual(result['flags'], [FLAG_VERDICT_NO_CONSENSUS, FLAG_VERDICT_MOS_UNDEFINED])

    def test_no_price_window_is_flagged(self) -> None:
        result = verdict_case_metrics(
            consensus='2|5',
            mos_main=Decimal('0.1'),
            analysis_price=Decimal('100'),
            analysis_date='2024-01-31',
            bars=[],
        )
        self.assertIn(FLAG_VERDICT_NO_PRICE_WINDOW, result['flags'])

    def test_missing_analysis_price_yields_no_verdict(self) -> None:
        result = verdict_case_metrics(
            consensus='2|5',
            mos_main=Decimal('0.1'),
            analysis_price=None,
            analysis_date='2024-01-31',
            bars=[],
        )
        self.assertIsNone(result['verdict'])
        self.assertIn(FLAG_VERDICT_NO_CONSENSUS, result['flags'])

    def test_consensus_min_valid_methods_still_three(self) -> None:
        """Ambang `N/A` tidak ikut berubah saat verdict ditambahkan."""
        self.assertEqual(CONSENSUS_MIN_VALID_METHODS, 3)


class VerdictOrchestratorTests(unittest.TestCase):
    """Verdict harus ikut dipersist oleh orkestrator, bukan hanya dihitung."""

    PERIODS = [
        {'id': 'a-2020', 'instrument_id': 'i', 'period_type': 'ANNUAL', 'period_end': '2020-12-31'},
        {'id': 'a-2021', 'instrument_id': 'i', 'period_type': 'ANNUAL', 'period_end': '2021-12-31'},
        {'id': 'a-2022', 'instrument_id': 'i', 'period_type': 'ANNUAL', 'period_end': '2022-12-31'},
        {'id': 'a-2023', 'instrument_id': 'i', 'period_type': 'ANNUAL', 'period_end': '2023-12-31'},
        {'id': 'q-2024-1', 'instrument_id': 'i', 'period_type': 'QUARTER', 'period_end': '2024-03-31'},
    ]
    PRICES = [
        {'trading_date': '2024-03-28', 'close_price': '100', 'high_price': '105', 'low_price': '95'},
        {'trading_date': '2024-06-28', 'close_price': '120', 'high_price': '130', 'low_price': '110'},
        {'trading_date': '2025-03-28', 'close_price': '150', 'high_price': '160', 'low_price': '140'},
    ]

    def case_rows(self) -> list:
        import run_backtest

        results = run_backtest.calculate_cases(self.PERIODS, self.PRICES)
        return run_backtest._case_rows(
            results,
            methodology_id='m',
            instrument_id='i',
            sector_name='Sector',
        )

    def test_case_rows_persist_the_verdict_columns(self) -> None:
        rows = self.case_rows()
        self.assertTrue(rows)
        for row in rows:
            for column in (
                'verdict', 'verdict_mos', 'return_magnitude', 'return_magnitude_down',
            ):
                self.assertIn(column, row)

    def test_case_without_valuation_gets_null_verdict_with_a_flag(self) -> None:
        """Tanpa valuasi, verdict NULL - bukan FLAT, karena itu klaim."""
        for row in self.case_rows():
            self.assertIsNone(row['verdict'])
            self.assertIsNone(row['verdict_mos'])
            self.assertIn(FLAG_VALUATION_UNAVAILABLE, row['flags'])

    def test_verdict_details_are_merged_into_case_details(self) -> None:
        self.assertIn('magnitude_rule', self.case_rows()[0]['details'])


if __name__ == '__main__':
    unittest.main()
