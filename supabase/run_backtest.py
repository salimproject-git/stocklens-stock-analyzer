#!/usr/bin/env python3
"""
run_backtest.py
===============

Fase 1-4 - Orkestrator backtest historis: baca DB -> engine -> tulis hasil.

Alur
----
1. Selesaikan instrumen dari ticker.
2. Baca `financial_periods` dan `prices_daily` untuk instrumen itu.
3. Bangun daftar kasus dengan :func:`backtest_engine.select_backtest_cases`, lalu
   buang yang belum berumur 4 bulan (`select_mature_cases`).
4. Untuk tiap kasus: potong harga pada `EDATE(analysis_date, +12)`, hitung metrik
   harga (termasuk `peak_month` dan `trough_month`).
5. Bila `valuation_inputs` diberikan: hitung valuasi point-in-time, konsensus,
   MoS (Fase 2) dan tulis `calc_backtest_methods`.
6. Hitung `verdict` dan `verdict_mos` (Fase 3) dari konsensus/MoS plus harga.
7. Tulis ke `calc_backtest_cases` dan verifikasi jumlah barisnya.

Kenapa harga dipotong sebelum masuk engine
------------------------------------------
`backtest_engine` sendiri sudah membuang baris setelah window, tetapi pemotongan
di sini membuat batasnya terlihat di satu tempat yang bisa diaudit: tidak ada
baris harga setelah `EDATE(T0,+12)` yang pernah dikirim ke rumus kasus itu.
Ini juga yang membuat waktu proses tetap wajar (18 kasus x 1.619 baris).

Batas yang tersisa
------------------
Hasil dibaca frontend lewat RPC `get_stock_backtest`
(`supabase/migrations/0026_stock_research_backtest_rpc.sql`). `context` (Revenue
YoY, Net Income YoY, EPS/Revenue momentum) diturunkan di RPC, bukan disimpan di
sini - lihat `docs/BACKTEST_ARCHITECTURE.md` bagian 4.3.

`verdict`/`verdict_mos` sengaja NULL bila konsensusnya `N/A` atau `MoS Main`-nya
NULL - rumusnya tidak punya `K` di keadaan itu, dan mengisinya dengan `FLAT`
akan menciptakan klaim yang tidak bisa dibedakan dari verdict asli.

Usage
-----
    python supabase/run_backtest.py --ticker AUTO --apply
    python supabase/run_backtest.py --ticker AUTO            # dry run
    python supabase/run_backtest.py --all --apply
"""

from __future__ import annotations

import argparse
import csv
import io
import json
import os
import sys
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any, Mapping, Sequence

SUPABASE_DIR = Path(__file__).resolve().parent
REPO_ROOT = SUPABASE_DIR.parent
if str(SUPABASE_DIR) not in sys.path:
    sys.path.insert(0, str(SUPABASE_DIR))

from backtest_engine import (  # noqa: E402
    CODE_VERSION,
    FLAG_VALUATION_UNAVAILABLE,
    METHOD_CODE,
    METHOD_VERSION,
    STATUS_APPROXIMATED,
    STATUS_NOT_CALCULABLE,
    STATUS_UNAVAILABLE,
    STATUS_VALID,
    BacktestError,
    analysis_date_for,
    backtest_methodology_seed,
    case_provenance_flags,
    edate,
    price_metrics,
    resolve_case_years_available,
    select_backtest_cases,
    select_mature_cases,
    unavailable_valuation_case_metrics,
    valuation_case_metrics,
    verdict_case_metrics,
)
from calculation_registry import INPUT_VOCABULARY_VERSION, sha256_json  # noqa: E402
from calculation_v1_common import (  # noqa: E402
    CalculationError,
    SupabaseRest,
    calculation_contract,
    resolved_parameter,
)
from calculate_quarterly_growth_quality import (  # noqa: E402
    calculate_annual_growth_outputs,
    classify_metrics_classification,
)
from derive_classifier_inputs import derive_classifier_inputs  # noqa: E402
from derive_projection_scenario import (  # noqa: E402
    build_scenario,
    index_facts,
    resolve_base_quarter,
)
from valuation_engine import (  # noqa: E402
    CODE_VERSION as VALUATION_CODE_VERSION,
    REFERENCE_VERSION,
    ValuationError,
    calculate_valuation_snapshot,
)

CASE_TABLE = 'calc_backtest_cases'
METHOD_TABLE = 'calc_backtest_methods'
PAGE_SIZE = 1000

#: `Years_Avail` registry constant yang dipakai workbook untuk setiap kasus.
#: Dipotong per kasus oleh `resolve_case_years_available` (keputusan D2).
REGISTRY_YEARS_AVAILABLE = 7

#: Kode metrik yang membawa jawaban akhir classifier.
CLASSIFICATION_FINAL_TYPE_CODE = 'CLASSIFICATION_FINAL_TYPE'
CLASSIFICATION_ASSET_PLAY_CODE = 'CLASSIFICATION_ASSET_PLAY'

#: Versi skema sidik input tipe saham. Dinaikkan bila isi sidik berubah, supaya
#: cache lama tidak dianggap cocok oleh sidik dengan arti yang berbeda.
STOCK_TYPE_FINGERPRINT_VERSION = 'stock-type-input-v3'

#: Parameter classifier yang dibaca dari registry dan ikut masuk sidik input.
#: Kalau salah satu ambang berubah, sidiknya berubah dan tipenya dihitung ulang.
CLASSIFIER_PARAMETER_CODES = (
    'classifier_thresholds',
    'classifier_score_ladder',
    'classifier_energy_override',
    'classifier_cyclical_sectors',
    'classifier_consumer_defensive_sectors',
    'classifier_infrastructure_sectors',
)


def load_env_file(path: Path) -> None:
    """Isi ``os.environ`` dari file ``.env`` tanpa menimpa nilai yang sudah ada."""
    if not path.is_file():
        return
    for raw_line in path.read_text(encoding='utf-8').splitlines():
        line = raw_line.strip()
        if not line or line.startswith('#') or '=' not in line:
            continue
        key, value = line.split('=', 1)
        key, value = key.strip(), value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in ('"', "'"):
            value = value[1:-1]
        if key:
            os.environ.setdefault(key, value)


def _pages(db: SupabaseRest, table: str, params: Mapping[str, str]) -> list[dict[str, Any]]:
    """Baca seluruh halaman ``table``."""
    rows: list[dict[str, Any]] = []
    offset = 0
    while True:
        page = db.get_all(table, {**dict(params), 'limit': str(PAGE_SIZE), 'offset': str(offset)})
        rows.extend(page)
        if len(page) < PAGE_SIZE:
            return rows
        offset += PAGE_SIZE


def _postgrest_in(values: list[str]) -> str:
    """Rangkai filter PostgREST ``in.(...)`` dengan kutip yang benar."""
    stream = io.StringIO()
    writer = csv.writer(stream, lineterminator='')
    writer.writerow(values)
    return 'in.(' + stream.getvalue() + ')'


def _json_value(value: Any) -> Any:
    """Ubah :class:`~decimal.Decimal` menjadi teks agar aman di JSON."""
    if isinstance(value, Decimal):
        return format(value.normalize(), 'f') if value != 0 else '0'
    if isinstance(value, dict):
        return {str(key): _json_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_value(item) for item in value]
    return value


def _required_methodology_id(db: SupabaseRest) -> str:
    """Cari (atau daftarkan) versi metodologi `BACKTEST_HISTORICAL`.

    Baris registry dibuat dari :func:`backtest_engine.backtest_methodology_seed`
    sehingga hash-nya selalu bisa direproduksi dari kode. Kalau barisnya sudah
    ada, hash yang tersimpan dibandingkan dulu: hash yang berbeda berarti
    definisi lokal sudah berubah tanpa versi baru, dan hasil lama jadi tidak
    bisa direproduksi. Itu diperlakukan sebagai error, bukan ditimpa diam-diam -
    naikkan `METHOD_VERSION` sebagai gantinya, seperti yang dilakukan Fase 2
    (1.0.0 -> 1.1.0).

    Run yang sudah ada tetap menunjuk versi lamanya, jadi menambah versi baru
    tidak mengubah arti hasil yang sudah tersimpan.
    """
    seed = backtest_methodology_seed()
    rows = db.get_all('methodology_versions', {
        'method_code': 'eq.' + METHOD_CODE,
        'method_version': 'eq.' + METHOD_VERSION,
        'select': 'id,status,formula_hash,parameter_hash',
    })
    if len(rows) > 1:
        raise CalculationError('BACKTEST_METHODOLOGY_NOT_UNIQUE')

    if not rows:
        created = db.request(
            'POST', 'methodology_versions',
            payload={
                'method_code': seed['method_code'],
                'method_version': seed['method_version'],
                'method_name': seed['method_name'],
                'description': seed['description'],
                'formula_text': seed['formula_text'],
                'formula_hash': seed['formula_hash'],
                'parameter_spec': _json_value(seed['parameter_spec']),
                'parameter_hash': seed['parameter_hash'],
                'code_version': seed['code_version'],
                'input_vocabulary_version': INPUT_VOCABULARY_VERSION,
                'status': seed['status'],
            },
            headers={'Prefer': 'return=representation'},
        )
        if not isinstance(created, list) or len(created) != 1:
            raise CalculationError('BACKTEST_METHODOLOGY_CREATE_FAILED')
        return str(created[0]['id'])

    row = rows[0]
    if (
        row.get('formula_hash') != seed['formula_hash']
        or row.get('parameter_hash') != seed['parameter_hash']
    ):
        raise CalculationError('BACKTEST_METHODOLOGY_REGISTRY_DRIFT')
    if row.get('status') not in ('DRAFT', 'PUBLISHED'):
        raise CalculationError('BACKTEST_METHODOLOGY_NOT_EXECUTABLE')
    return str(rows[0]['id'])


def _write_run_status(db: SupabaseRest, run_id: str, status: str, error: str | None = None) -> None:
    """Perbarui status satu `calculation_runs`."""
    payload: dict[str, Any] = {'status': status, 'error_message': error}
    if status in ('SUCCEEDED', 'FAILED', 'PARTIAL'):
        payload['completed_at'] = datetime.now(timezone.utc).isoformat()
    db.request('PATCH', 'calculation_runs', params={'id': 'eq.' + run_id}, payload=payload)


def _persist_cases(db: SupabaseRest, rows: list[dict[str, Any]]) -> None:
    """Tulis baris kasus dengan upsert pada kunci uniknya."""
    conflict = 'calculation_run_id,instrument_id,as_of_financial_period_id'
    for offset in range(0, len(rows), 250):
        db.request(
            'POST', CASE_TABLE,
            params={'on_conflict': conflict},
            payload=rows[offset:offset + 250],
            headers={'Prefer': 'resolution=merge-duplicates,return=minimal'},
        )


def _persist_methods(db: SupabaseRest, rows: list[dict[str, Any]]) -> None:
    """Tulis baris metode dengan upsert pada `(case_id, method_code)`."""
    for offset in range(0, len(rows), 250):
        db.request(
            'POST', METHOD_TABLE,
            params={'on_conflict': 'case_id,method_code'},
            payload=rows[offset:offset + 250],
            headers={'Prefer': 'resolution=merge-duplicates,return=minimal'},
        )


def fetch_reference_inputs(db: SupabaseRest, sector_name: str | None) -> dict[str, Any]:
    """Ambil tabel referensi yang dibutuhkan lima metode valuasi.

    Sama seperti `calculate_valuation.calculate_live`: bobot sektor/tipe dan
    ambang tipe adalah data referensi berversi, bukan konstanta di kode. Baris
    yang tidak ada tetap `None` supaya engine mengangkat flag
    `SECTOR_WEIGHT_UNCLASSIFIED` / `TYPE_WEIGHT_UNCLASSIFIED`, bukan menebak.

    Sejak D7 tipe saham **berbeda per kasus**, jadi bobot/ambang tipe tidak bisa
    lagi diambil untuk satu tipe saja. Seluruh baris tipe dibaca sekali (enam
    baris) lalu :func:`_reference_for_type` memilih yang cocok untuk tiap kasus.
    Satu query untuk semua tipe lebih murah daripada satu query per kasus, dan
    hasilnya identik.
    """
    type_weights = db.get_all('valuation_type_weights', {
        'reference_version': 'eq.' + REFERENCE_VERSION,
        'select': 'stock_type,w_pe,w_pbv,w_ddm,w_graham,w_peg',
    })
    type_thresholds = db.get_all('valuation_type_thresholds', {
        'reference_version': 'eq.' + REFERENCE_VERSION,
        'select': 'stock_type,max_der,min_cr,min_icr',
    })

    sector_weights = db.get_all('valuation_sector_weights', {
        'reference_version': 'eq.' + REFERENCE_VERSION,
        'sector_name': 'eq.' + str(sector_name or ''),
        'select': 'sector_name,w_pe,w_pbv,w_ddm,w_graham,w_peg',
    })
    return {
        'sector_weights': sector_weights[0] if sector_weights else None,
        'type_weights_by_type': {
            str(row.get('stock_type') or '').strip(): row for row in type_weights
        },
        'type_thresholds_by_type': {
            str(row.get('stock_type') or '').strip(): row for row in type_thresholds
        },
    }


def _reference_for_type(reference: Mapping[str, Any], stock_type: str | None) -> dict[str, Any]:
    """Pilih baris referensi tipe untuk satu kasus (D7).

    ``stock_type=None`` (tipe belum bisa dipertanggungjawabkan) menghasilkan
    `None` tanpa menebak, sehingga engine mengangkat
    `TYPE_WEIGHT_UNCLASSIFIED` alih-alih memakai bobot tipe lain.
    """
    if not stock_type:
        return {'type_weights': None, 'type_thresholds': None}
    from calculate_valuation import _reference_type_name

    reference_type = _reference_type_name(stock_type)
    by_weight = reference.get('type_weights_by_type') or {}
    by_threshold = reference.get('type_thresholds_by_type') or {}
    return {
        'type_weights': by_weight.get(reference_type),
        'type_thresholds': by_threshold.get(reference_type),
    }


def _scenario_for_case(
    *,
    ticker: str,
    instrument: Mapping[str, Any],
    annual_periods: Sequence[Mapping[str, Any]],
    quarter_periods: Sequence[Mapping[str, Any]],
    facts: Sequence[Mapping[str, Any]],
    dividend_rows: Sequence[Mapping[str, Any]],
    years_available: int,
) -> dict[str, Any]:
    """Bentuk skenario point-in-time untuk satu kasus.

    `derive_projection_scenario.build_scenario` sudah menerima seluruh input
    sebagai argumen, jadi pemotongan PIT cukup dilakukan sebelum memanggilnya:
    hanya periode dengan `period_end <= analysis_date` yang dikirim. Dengan
    begitu `resolve_base_quarter` otomatis memilih kuartal lengkap terakhir yang
    **sudah ada pada tanggal kasus**, bukan kuartal terbaru hari ini.

    Dua hal yang harus ditambahkan setelah `build_scenario`, karena fungsi itu
    tidak mengetahuinya:

    * `as_of_financial_period_id` - dibutuhkan engine valuasi untuk menemukan
      periode dasar di dalam daftar periode yang diberikan.
    * `values` - bentuk yang dibaca engine (`scenario['values']`), dipetakan dari
      `projections` yang baru dihitung. Ini pengganti pembacaan
      `projection_values` dari database, yang justru akan memberi angka hari ini
      untuk kasus masa lalu.
    """
    index = index_facts(facts)
    base_period = resolve_base_quarter(quarter_periods, index)
    base_end = str(base_period.get('period_end') or '')

    # Potong kuartal pada kuartal dasar. Ini penting dan bukan sekadar
    # kerapian: `resolve_base_quarter` memilih kuartal lengkap TERBARU, jadi
    # setiap kuartal yang lebih baru pasti kehilangan minimal satu metrik wajib
    # (kalau tidak, ia sendiri yang akan jadi kuartal dasar). `build_scenario`
    # menjumlahkan SELURUH kuartal pada tahun kuartal dasar, sehingga membiarkan
    # kuartal yang tidak lengkap itu masuk akan menggagalkan run-rate dengan
    # `BASE_QUARTER_FACT_MISSING`.
    #
    # Contoh nyata: AUTO 2023-Q4 tidak punya `cost_of_revenue` (NULL di sumber
    # raw), jadi kuartal dasar per 2023-12-31 adalah 2023-Q3. Tanpa pemotongan
    # ini, Q4 ikut dijumlahkan dan seluruh kasus 2023-Q4 gagal divaluasi.
    #
    # Pemotongan ini juga membuat rumusnya persis sama dengan workbook:
    # `sum(Q1..Q_asof) * 4 / as_of_quarter`. Karena `quarter_count` menjadi sama
    # dengan nomor kuartal dasar, pembaginya pun sama.
    #
    # `index` **tidak** dihitung ulang dari `truncated`: ia harus tetap mencakup
    # periode annual juga, karena `annual_share_count` dan `annual_dpr_series`
    # membaca `OUTSTANDING_SHARES`, `EARNINGS` dan `TOTAL_EQUITY` dari sana.
    truncated = [
        row for row in quarter_periods
        if str(row.get('period_end') or '') <= base_end
    ]

    scenario = build_scenario(
        ticker=ticker,
        instrument=instrument,
        annual_periods=annual_periods,
        quarter_periods=truncated,
        index=index,
        dividend_rows=dividend_rows,
        years_available=years_available,
    )
    scenario['as_of_financial_period_id'] = str(base_period['id'])
    scenario['id'] = None
    scenario['input_hash'] = None
    scenario['values'] = {
        str(row['metric_code']): row['value_numeric'] for row in scenario['projections']
    }
    return scenario


def classifier_parameter_snapshot() -> dict[str, Any]:
    """Parameter classifier yang menentukan tipe, dibaca dari registry.

    Dipakai dua kali: sebagai bagian sidik input cache (kalau ambangnya berubah,
    sidiknya berubah dan tipe dihitung ulang) dan untuk membuktikan bahwa
    perhitungan per kasus memakai definisi yang sama dengan run klasifikasi
    harian. Nilainya dibaca lewat :func:`resolved_parameter`, jadi parameter yang
    belum `RESOLVED` menggagalkan run alih-alih dipakai diam-diam.
    """
    return {code: resolved_parameter(code) for code in CLASSIFIER_PARAMETER_CODES}


def _stock_type_fingerprint(
    *,
    instrument_id: str,
    case_quarter: str,
    analysis_date: str,
    years_available: int,
    base_quarter: str,
    classifier_parameters: Mapping[str, Any],
    annual_periods: Sequence[Mapping[str, Any]],
    quarter_periods: Sequence[Mapping[str, Any]],
    facts: Sequence[Mapping[str, Any]],
    prices: Sequence[Mapping[str, Any]],
    dividend_rows: Sequence[Mapping[str, Any]],
) -> str:
    """Sidik SHA-256 dari seluruh input yang menentukan tipe satu kasus.

    Ini **bukan** sidik hasil, melainkan sidik **input**. Cache dipakai ulang
    hanya bila sidiknya sama persis, sehingga setiap perubahan yang bisa
    menggeser tipe ikut terdeteksi:

    * **parameter classifier** (ambang, tangga skor, override Energy, daftar
      sektor Layer 1 dan Layer 2) - perubahan satu ambang saja sudah mengubah tipe;
    * **periode** yang dipotong pada tanggal kasus (`id`, `period_end`);
    * **fakta** yang dipotong, **termasuk `revision_key` dan nilainya** - inilah
      yang membuat revisi laporan (mis. restatement laba) menggugurkan cache,
      karena laporan yang direvisi mengubah fakta pada periode yang sama tanpa
      mengubah daftar periode;
    * **harga** yang dipotong (`trading_date`, `close_price`) - dipakai untuk
      PBV percentile dan year-end price;
    * **dividen** (`period_year`, `amount_per_share`) - dipakai payout ratio dan
      dividend yield;
    * **`years_available`** dan **kuartal dasar** - keduanya memotong jendela
      annual yang dibaca classifier.

    Urutan barisnya dinormalkan (di-sort) supaya urutan pembacaan dari PostgREST
    tidak mengubah sidik tanpa perubahan data. Versi skema sidik ikut disertakan
    supaya mengubah definisi sidik tidak membuat cache lama tampak cocok.
    """
    payload = {
        'fingerprint_version': STOCK_TYPE_FINGERPRINT_VERSION,
        'instrument_id': instrument_id,
        'case_quarter': case_quarter,
        'analysis_date': analysis_date,
        'years_available': int(years_available),
        'base_quarter': base_quarter,
        'classifier_parameters': _json_value(dict(classifier_parameters)),
        'periods': sorted(
            [
                str(row.get('id') or ''),
                str(row.get('period_type') or ''),
                str(row.get('period_end') or ''),
            ]
            for row in [*annual_periods, *quarter_periods]
        ),
        'facts': sorted(
            [
                str(row.get('financial_period_id') or ''),
                str(row.get('metric_code') or ''),
                str(row.get('revision_key') or ''),
                None if row.get('value_numeric') is None else str(row.get('value_numeric')),
            ]
            for row in facts
        ),
        'prices': sorted(
            [
                str(row.get('trading_date') or ''),
                None if row.get('close_price') is None else str(row.get('close_price')),
            ]
            for row in prices
        ),
        'dividends': sorted(
            [
                str(row.get('fact_type') or ''),
                None if row.get('period_year') is None else str(row.get('period_year')),
                None if row.get('amount_per_share') is None
                else str(row.get('amount_per_share')),
            ]
            for row in dividend_rows
        ),
    }
    return sha256_json(payload)


def _case_cut(
    *,
    ticker: str,
    instrument: Mapping[str, Any],
    analysis_date: date,
    periods: Sequence[Mapping[str, Any]],
    facts: Sequence[Mapping[str, Any]],
    prices: Sequence[Mapping[str, Any]],
    dividend_rows: Sequence[Mapping[str, Any]],
    registry_years_available: int,
) -> dict[str, Any]:
    """Potong seluruh input pada tanggal satu kasus, sekali, untuk kedua jalur.

    Fungsi ini adalah **satu-satunya** tempat potongan point-in-time dibentuk,
    dan itu disengaja: tipe saham per kasus (D7) dan valuasi kasus harus melihat
    input yang identik. Kalau masing-masing memotong sendiri, tipe dan valuasi
    bisa memakai kuartal dasar atau `years_available` yang berbeda, dan
    perbedaannya tidak akan terlihat di angka mana pun.

    Mengembalikan periode terpotong, fakta, harga, indeks fakta, kuartal dasar,
    `years_available` beserta flag pemotongannya, dan skenario proyeksi kasus.
    """
    cutoff = analysis_date.isoformat()
    annual = [
        row for row in periods
        if row.get('period_type') == 'ANNUAL' and str(row.get('period_end') or '') <= cutoff
    ]
    quarterly = [
        row for row in periods
        if row.get('period_type') == 'QUARTER' and str(row.get('period_end') or '') <= cutoff
    ]
    period_ids = {str(row['id']) for row in [*annual, *quarterly]}
    cut_facts = [row for row in facts if str(row.get('financial_period_id')) in period_ids]
    cut_prices = [
        row for row in prices if str(row.get('trading_date') or '') <= cutoff
    ]

    # Kuartal dasar ditentukan sebelum `years_available`, karena engine valuasi
    # memotong periode annual pada `period_end` kuartal dasar - bukan pada
    # `analysis_date`. Keduanya bisa berbeda: AUTO 2023-Q4 tidak punya
    # `cost_of_revenue`, sehingga kuartal dasarnya jatuh ke 2023-Q3 dan satu
    # tahun annual (2023) dibuang engine. Menghitung `years_available` dari
    # `analysis_date` saja akan meloloskan tahun itu dan engine menolak dengan
    # `YEARS_AVAILABLE_EXCEEDS_HISTORY`.
    index = index_facts(cut_facts)
    base_period = resolve_base_quarter(quarterly, index)
    years_available, year_flags = resolve_case_years_available(
        int(registry_years_available),
        annual,
        analysis_date,
        cutoff_date=str(base_period.get('period_end') or cutoff),
    )

    scenario = _scenario_for_case(
        ticker=ticker,
        instrument=instrument,
        annual_periods=annual,
        quarter_periods=quarterly,
        facts=cut_facts,
        dividend_rows=dividend_rows,
        years_available=years_available,
    )
    return {
        'analysis_date': cutoff,
        'annual': annual,
        'quarterly': quarterly,
        'facts': cut_facts,
        'prices': cut_prices,
        'years_available': years_available,
        'years_available_flags': year_flags,
        'base_quarter': str(base_period.get('period_label') or ''),
        'scenario': scenario,
    }


def stock_type_for_case(
    *,
    instrument: Mapping[str, Any],
    instrument_id: str,
    stock_type: str | None,
    stock_type_error: str | None,
    cut: Mapping[str, Any],
    dividend_rows: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    """Tipe saham yang classifier hasilkan **pada tanggal kasus** (D7).

    Workbook menghitung ulang `MetricsClassification` tiap kasus, jadi tipe
    sebuah kasus bisa berbeda dari tipe hari ini. Fungsi ini menjalankan ulang
    classifier itu di atas potongan point-in-time yang **sama** dengan yang
    dipakai :func:`valuation_for_case` (`cut`, dari :func:`_case_cut`):

    * periode dan harga sudah dipotong pada `analysis_date`;
    * `years_available` sudah dipotong ke riwayat yang ada pada kasus itu (D2);
    * baris Class-B (pertumbuhan/kualitas) **dihitung ulang** untuk jendela
      kasus, bukan dibaca dari run tersimpan - run tersimpan hanya satu per
      instrumen dan dipatok ke snapshot hari ini;
    * skenario proyeksi memakai skenario kasus sendiri, dan
      `projected_shares_outstanding`-nya diteruskan. Bila dibiarkan `None`,
      `projected_pbv` menjadi `None` dan ASSET PLAY salah menyala.

    Mengembalikan `stock_type` (sudah dinormalkan ke kosakata engine) atau
    `stock_type_error` bila tipenya tidak bisa dipertanggungjawabkan. Kegagalan
    di sini **tidak** menggagalkan kasusnya: pemanggil tetap menulis metrik
    harga dengan valuasi `VALUATION_UNAVAILABLE`, sama seperti perilaku lama.

    ``stock_type``/``stock_type_error`` yang diberikan adalah tipe snapshot
    terbaru; keduanya hanya dipakai sebagai fallback bila classifier per kasus
    tidak bisa dijalankan, supaya satu kasus bermasalah tidak menghapus tipe
    yang sudah terbukti benar untuk kasus itu.
    """
    annual = cut['annual']
    cut_facts = cut['facts']
    cut_prices = cut['prices']
    years_available = int(cut['years_available'])
    scenario = cut['scenario']

    window = annual[-years_available:] if years_available > 0 else annual
    growth_rows = calculate_annual_growth_outputs(
        window,
        cut_facts,
        instrument_id,
        'backtest-per-case',
        years_available=None,
        # The classifier only reads the four growth codes, but the dividend
        # ratios are passed too so this call produces the same row set as the
        # stored run. A missing dividend or price input must not change what the
        # classifier sees, and it does not: it only adds two rows.
        dividend_rows=dividend_rows,
        prices=cut_prices,
    )

    inputs = derive_classifier_inputs(
        annual_periods=annual,
        facts=cut_facts,
        prices=cut_prices,
        dividend_rows=dividend_rows,
        scenario_values=scenario['values'],
        projected_shares_outstanding=scenario.get('projected_shares_outstanding'),
        growth_rows=growth_rows,
        years_available=years_available,
    )

    rows = classify_metrics_classification(
        growth_rows=growth_rows,
        instrument_id=instrument_id,
        run_id='backtest-per-case',
        sector=instrument.get('sector_name'),
        projected_net_income=inputs['projected_net_income'],
        payout_ratio=inputs['payout_ratio'],
        historical_roe_average=inputs['historical_roe_average'],
        projected_pbv=inputs['projected_pbv'],
        pbv_percentile=inputs['pbv_percentile'],
        projected_pe=inputs['projected_pe'],
        projected_peg=inputs['projected_peg'],
        historical_dividend_yield=inputs['historical_dividend_yield'],
        gpm_stability=inputs['gpm_stability'],
    )
    by_code = {row['metric_code']: row for row in rows}
    raw = str(by_code[CLASSIFICATION_FINAL_TYPE_CODE].get('classification_code') or '')
    asset_play = (
        str(by_code[CLASSIFICATION_ASSET_PLAY_CODE].get('value_numeric') or '') == '1'
    )

    from calculate_valuation import normalise_classifier_type

    try:
        resolved_type = normalise_classifier_type(raw, asset_play)
    except CalculationError as error:
        # `UNCLASSIFIED` tanpa aturan yang cocok (INDF) tidak punya tipe yang
        # bisa dipertanggungjawabkan. Fallback ke tipe snapshot terbaru hanya
        # bila tipe itu memang ada; kalau tidak, alasannya diteruskan apa adanya.
        return {
            'stock_type': stock_type,
            'stock_type_error': stock_type_error or str(error),
            'raw_type': raw or None,
            'years_available': years_available,
            'base_quarter': str(cut.get('base_quarter') or ''),
        }

    return {
        'stock_type': resolved_type,
        'stock_type_error': None,
        'raw_type': raw or None,
        'years_available': years_available,
        'base_quarter': str(cut.get('base_quarter') or ''),
    }


def valuation_for_case(
    *,
    ticker: str,
    instrument: Mapping[str, Any],
    stock_type: str,
    analysis_date: date,
    periods: Sequence[Mapping[str, Any]],
    facts: Sequence[Mapping[str, Any]],
    prices: Sequence[Mapping[str, Any]],
    dividend_rows: Sequence[Mapping[str, Any]],
    reference: Mapping[str, Any],
    risk_free_rate: str | None,
    risk_free_source: str | None,
    valuation_parameters: Mapping[str, Any],
    cut: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Hitung snapshot valuasi untuk satu kasus, seluruhnya point-in-time.

    Yang dipotong dan mengapa:

    * **periode** `period_end <= analysis_date` - tanpa ini, kasus 2022 Q1 akan
      melihat laporan 2026 dan valuasinya tidak lagi historis.
    * **harga** `trading_date <= analysis_date` - engine memilih close terakhir
      pada atau sebelum `valuation_date`, jadi pemotongan ini hanya memperjelas
      batas; tanpa itu pun tidak ada harga masa depan yang terpakai.

    `years_available` (keputusan D2) dan kuartal dasar ikut dihitung di
    :func:`_case_cut`, karena keduanya bergantung satu sama lain. Kegagalan
    pembentukan skenario **tidak** ditelan: pemanggil yang memutuskan cara
    mencatatnya, karena hanya pemanggil yang tahu cara menulis baris gagal.

    ``cut`` boleh diberikan pemanggil yang sudah membentuknya. Itu yang terjadi
    pada jalur D7: classifier per kasus memakai potongan yang **sama** persis,
    jadi tipe dan valuasi tidak mungkin memakai kuartal dasar atau
    `years_available` yang berbeda.

    Bobot/ambang tipe dipilih **per tipe kasus ini** lewat
    :func:`_reference_for_type`, bukan per tipe snapshot terbaru.
    """
    if cut is None:
        cut = _case_cut(
            ticker=ticker,
            instrument=instrument,
            analysis_date=analysis_date,
            periods=periods,
            facts=facts,
            prices=prices,
            dividend_rows=dividend_rows,
            registry_years_available=REGISTRY_YEARS_AVAILABLE,
        )
    cutoff = str(cut['analysis_date'])
    annual = cut['annual']
    quarterly = cut['quarterly']
    cut_facts = cut['facts']
    cut_prices = cut['prices']
    years_available = int(cut['years_available'])
    scenario = cut['scenario']
    type_reference = _reference_for_type(reference, stock_type)
    result = calculate_valuation_snapshot(
        ticker=ticker,
        sector=instrument.get('sector_name'),
        stock_type=stock_type,
        annual_periods=annual,
        quarterly_periods=quarterly,
        facts=cut_facts,
        prices=cut_prices,
        scenario=scenario,
        valuation_date=cutoff,
        years_available=years_available,
        years_compare=None,
        risk_free_rate=risk_free_rate,
        risk_free_source=risk_free_source,
        sector_weights=reference.get('sector_weights'),
        type_weights=type_reference.get('type_weights'),
        type_thresholds=type_reference.get('type_thresholds'),
        valuation_parameters=valuation_parameters,
    )
    # `years_available` dan flag pemotongannya dilaporkan dari sini supaya
    # pemanggil tidak menghitungnya ulang dengan cara yang bisa berbeda.
    result['years_available'] = years_available
    result['years_available_flags'] = list(cut['years_available_flags'])
    result['base_quarter'] = str(cut['base_quarter'])
    return result


def _fetch_facts(db: SupabaseRest, period_ids: Sequence[str]) -> list[dict[str, Any]]:
    """Baca fakta kanonik untuk sekumpulan periode, dipotong 100 id per query.

    Batas 100 mengikuti `calculate_valuation` dan `derive_classifier_inputs`:
    URL PostgREST punya panjang maksimum, dan `in.(...)` dengan ratusan UUID akan
    melewatinya.
    """
    facts: list[dict[str, Any]] = []
    for offset in range(0, len(period_ids), 100):
        facts.extend(_pages(db, 'financial_facts', {
            'financial_period_id': _postgrest_in(list(period_ids[offset:offset + 100])),
            'select': (
                'financial_period_id,metric_code,value_numeric,unit_code,'
                'quality_status,revision_key'
            ),
        }))
    return facts


def _methodology_parameters(db: SupabaseRest) -> dict[str, Any]:
    """Parameter metodologi `VALUATION_CURRENT` (ambang, batas, kebijakan).

    Diambil dari baris registry, bukan konstanta di kode, supaya backtest dan
    valuasi harian tidak bisa memakai ambang yang berbeda.
    """
    rows = db.get_all('methodology_versions', {
        'method_code': 'eq.VALUATION_CURRENT',
        'method_version': 'eq.1.0.0',
        'select': 'parameter_spec',
    })
    if len(rows) != 1:
        raise CalculationError('VALUATION_METHODOLOGY_PARAMETERS_NOT_FOUND')
    return dict(rows[0].get('parameter_spec') or {})


def fetch_risk_free_rate(db: SupabaseRest) -> tuple[str | None, str | None]:
    """Ambil risk-free rate dari tabel referensi, atau `(None, None)`.

    Tabel referensi sekarang berisi satu baris `WORKBOOK_CONSTANT` (`0.0633`,
    `DataInput!B11`). Itu berarti memakai konstanta yang sama untuk setiap kasus
    historis **adalah** perilaku workbook, bukan kompromi point-in-time: workbook
    pun tidak punya seri yield per tanggal.

    Bila nanti tabelnya diisi seri observasi bertanggal, pemanggil sudah menerima
    `observation_date` lewat `source`, sehingga pemotongan per kasus bisa
    ditambahkan tanpa mengubah bentuk pemanggilan. Tidak adanya baris **tidak**
    dianggap error di sini: DDM dan Discounted Earnings akan melaporkan
    `RISK_FREE_RATE_*` lewat flag engine, dan metrik harga tetap tersimpan.
    """
    from calculate_valuation import REFERENCE_RATE_CODE

    rows = db.get_all('risk_free_rate_reference', {
        'reference_version': 'eq.' + REFERENCE_VERSION,
        'rate_code': 'eq.' + REFERENCE_RATE_CODE,
        'select': 'rate,observation_date,source_kind,source_name,source_reference,is_default',
        'order': 'observation_date.desc.nullslast',
    })
    if not rows:
        return None, None
    dated = [row for row in rows if row.get('observation_date')]
    if dated:
        chosen = dated[0]
    else:
        defaults = [row for row in rows if row.get('is_default')]
        if len(defaults) != 1:
            return None, None
        chosen = defaults[0]
    rate = _json_value(chosen.get('rate'))
    if rate is None:
        return None, None
    observation_date = chosen.get('observation_date') or 'no observation date recorded'
    source = (
        f"{chosen.get('source_kind')} via {chosen.get('source_name')} "
        f"({chosen.get('source_reference')}); observation_date={observation_date}"
    )
    return str(rate), source


def calculate_cases(
    periods: Sequence[Mapping[str, Any]],
    prices: Sequence[Mapping[str, Any]],
    *,
    valuation_inputs: Mapping[str, Any] | None = None,
    as_of_date: date | str | None = None,
) -> list[dict[str, Any]]:
    """Hitung semua baris hasil untuk satu instrumen.

    Murni terhadap inputnya: tidak menyentuh database, tidak membaca file. Ini
    yang membuatnya bisa diuji dengan fixture tanpa jaringan.

    ``valuation_inputs`` bersifat opsional supaya Fase 1 tetap bisa dijalankan
    sendirian (dan ujinya tidak perlu menyiapkan tabel referensi). Bila diberikan,
    setiap kasus juga mendapat snapshot valuasi point-in-time; lihat
    :func:`valuation_for_case`.

    Bila ``valuation_inputs`` memuat ``per_case_stock_type=True``, tipe saham
    dihitung ulang **pada tanggal setiap kasus** (D7) lewat
    :func:`stock_type_for_case`, menggantikan ``stock_type`` yang diberikan.
    Flag itu opsional supaya jalur Fase 2 lama (satu tipe untuk seluruh kasus)
    tetap bisa diuji tanpa menyiapkan classifier, dan supaya pengujian pemotongan
    harga tidak ikut bergantung pada classifier.

    ``as_of_date`` membuang kasus yang belum berumur
    :data:`backtest_engine.CASE_MIN_AGE_MONTHS` bulan. Kuartal terbaru belum
    terbit sebagai laporan saat snapshot diambil, jadi verdictnya hanya akan
    kosong. Defaultnya hari ini; uji mengisinya eksplisit supaya hasilnya tidak
    berubah seiring waktu.

    Kegagalan valuasi **tidak** menggagalkan kasusnya: metrik harga tetap
    tersimpan dan valuasinya ditandai `VALUATION_UNAVAILABLE`. Alasannya sama
    dengan `WINDOW_PARTIAL` - kasus yang tidak bisa divaluasi tetap punya nilai
    sebagai bukti historis, dan menghilangkannya akan menyembunyikan justru
    kasus yang paling perlu dilihat.
    """
    annual = [row for row in periods if row.get('period_type') == 'ANNUAL']
    quarters = [row for row in periods if row.get('period_type') == 'QUARTER']
    cases = select_mature_cases(
        select_backtest_cases(annual, quarters),
        as_of_date or date.today(),
    )

    results: list[dict[str, Any]] = []
    for case in cases:
        analysis_date = analysis_date_for(case)
        # Potong hanya batas ATAS. Batas bawah sengaja tidak dipotong: harga
        # analisis adalah close terakhir **pada atau sebelum** `analysis_date`,
        # dan akhir kuartal sering jatuh di akhir pekan, sehingga bar yang
        # dibutuhkan justru ada sebelum tanggal itu. Kalau batas bawah dipotong,
        # semua kasus yang akhir periodenya bukan hari bursa akan kehilangan
        # harga analisisnya. Batas bawah window 12 bulan ditangani engine, yang
        # memang membatasi peak/trough ke `[T0, EDATE(T0,+12)]`.
        window_end = edate(analysis_date, 12)
        window_prices = [
            row for row in prices
            if row.get('trading_date') and str(row['trading_date'])[:10] <= window_end.isoformat()
        ]
        metrics = price_metrics(
            window_prices,
            analysis_date,
            case_flags=case_provenance_flags(case),
        )
        result: dict[str, Any] = {
            'case': case,
            'metrics': metrics,
            'analysis_date': metrics['analysis_date'],
        }
        if valuation_inputs is not None:
            result['valuation'] = _valuation_metrics_for_case(
                case, analysis_date, metrics, valuation_inputs
            )
        # Fase 3: verdict. Butuh `consensus` dan `mos_main` dari Fase 2, jadi ia
        # dihitung setelah valuasi. Tanpa valuasi, verdict-nya NULL dengan flag -
        # bukan FLAT, karena FLAT berarti "tidak menyentuh target" dan itu klaim
        # yang tidak bisa dibuat tanpa data.
        valuation = result.get('valuation') or {}
        verdict = verdict_case_metrics(
            consensus=valuation.get('consensus'),
            mos_main=valuation.get('mos_main'),
            analysis_price=metrics.get('analysis_price'),
            analysis_date=analysis_date,
            bars=window_prices,
            return_peak=metrics.get('return_peak'),
            return_down=metrics.get('return_down'),
        )
        if not valuation:
            verdict['flags'] = list(dict.fromkeys([
                *verdict['flags'],
                FLAG_VALUATION_UNAVAILABLE,
            ]))
        result['verdict'] = verdict
        results.append(result)
    return results


def _valuation_metrics_for_case(
    case: Any,
    analysis_date: date,
    metrics: Mapping[str, Any],
    inputs: Mapping[str, Any],
) -> dict[str, Any]:
    """Valuasi satu kasus, dengan jalur gagal yang tetap menulis baris.

    Dua jalur tipe saham:

    * ``per_case_stock_type=True`` (D7): tipe dihitung ulang pada tanggal kasus,
      lalu potongan point-in-time yang **sama** dipakai untuk valuasinya;
    * selain itu: tipe yang diberikan dipakai apa adanya, seperti sebelum D7.

    Tipe yang tidak bisa dipertanggungjawabkan menggagalkan **valuasi**, bukan
    kasusnya: metrik harga tetap tersimpan.
    """
    price = metrics.get('analysis_price')
    case_flags = case_provenance_flags(case)
    stock_type = str(inputs.get('stock_type') or '')
    stock_type_error = inputs.get('stock_type_error')
    cut: dict[str, Any] | None = None
    raw_type: str | None = None

    if inputs.get('per_case_stock_type'):
        try:
            cut = _case_cut(
                ticker=str(inputs.get('ticker') or ''),
                instrument=inputs.get('instrument') or {},
                analysis_date=analysis_date,
                periods=inputs.get('periods') or [],
                facts=inputs.get('facts') or [],
                prices=inputs.get('prices') or [],
                dividend_rows=inputs.get('dividend_rows') or [],
                registry_years_available=REGISTRY_YEARS_AVAILABLE,
            )
        except (CalculationError, ValuationError) as error:
            # Skenario kasus tidak bisa dibentuk (mis. kuartal dasar belum
            # lengkap: `BASE_QUARTER_FACT_MISSING`). Tipe pun tidak bisa
            # dihitung, jadi alasannya dilaporkan apa adanya dan metrik harga
            # tetap tersimpan. Tipe snapshot terbaru tetap dipakai bila ada,
            # supaya satu kasus bermasalah tidak menghapus tipe yang sudah
            # terbukti benar untuk kasus itu.
            unavailable = unavailable_valuation_case_metrics(
                price=price,
                reason=str(error),
                case_flags=case_flags,
            )
            unavailable['years_available'] = None
            unavailable['years_compare'] = None
            unavailable['stock_type'] = stock_type or None
            unavailable['stock_type_source'] = 'GIVEN'
            return unavailable

        # Sidik input dibandingkan dengan cache: cache dipakai ulang hanya bila
        # inputnya terbukti identik. Sidiknya selalu dihitung, jadi cache tidak
        # pernah menyembunyikan perubahan input.
        fingerprint = _stock_type_fingerprint(
            instrument_id=str(inputs.get('instrument_id') or ''),
            case_quarter=str(case.case_quarter),
            analysis_date=str(cut['analysis_date']),
            years_available=int(cut['years_available']),
            base_quarter=str(cut['base_quarter']),
            classifier_parameters=inputs.get('classifier_parameters') or {},
            annual_periods=cut['annual'],
            quarter_periods=cut['quarterly'],
            facts=cut['facts'],
            prices=cut['prices'],
            dividend_rows=inputs.get('dividend_rows') or [],
        )
        cached = (inputs.get('stock_type_cache') or {}).get(str(case.case_quarter))
        if cached and str(cached.get('fingerprint')) == fingerprint:
            stock_type = str(cached.get('stock_type') or '')
            stock_type_error = None
            raw_type = cached.get('stock_type_raw')
            stock_type_source = 'CACHE'
        else:
            try:
                resolved = stock_type_for_case(
                    instrument=inputs.get('instrument') or {},
                    instrument_id=str(inputs.get('instrument_id') or ''),
                    stock_type=stock_type or None,
                    stock_type_error=stock_type_error,
                    cut=cut,
                    dividend_rows=inputs.get('dividend_rows') or [],
                )
            except (CalculationError, ValuationError) as error:
                unavailable = unavailable_valuation_case_metrics(
                    price=price,
                    reason=str(error),
                    case_flags=case_flags,
                )
                unavailable['years_available'] = None
                unavailable['years_compare'] = None
                unavailable['stock_type'] = stock_type or None
                return unavailable
            stock_type = str(resolved.get('stock_type') or '')
            stock_type_error = resolved.get('stock_type_error')
            raw_type = resolved.get('raw_type')
            stock_type_source = 'RECOMPUTED'
    else:
        fingerprint = None
        stock_type_source = 'GIVEN'

    if stock_type_error:
        unavailable = unavailable_valuation_case_metrics(
            price=price,
            reason=f'STOCK_TYPE_UNRESOLVED: {stock_type_error}',
            case_flags=case_flags,
        )
        unavailable['years_available'] = None
        unavailable['years_compare'] = None
        unavailable['stock_type'] = None
        if cut is not None and cut.get('base_quarter'):
            unavailable['base_quarter'] = cut['base_quarter']
        if raw_type is not None:
            unavailable['stock_type_raw'] = raw_type
        if fingerprint is not None:
            unavailable['stock_type_fingerprint'] = fingerprint
            unavailable['stock_type_source'] = stock_type_source
        return unavailable

    try:
        valuation = valuation_for_case(
            ticker=str(inputs.get('ticker') or ''),
            instrument=inputs.get('instrument') or {},
            stock_type=stock_type,
            analysis_date=analysis_date,
            periods=inputs.get('periods') or [],
            facts=inputs.get('facts') or [],
            prices=inputs.get('prices') or [],
            dividend_rows=inputs.get('dividend_rows') or [],
            reference=dict(inputs.get('reference') or {}),
            risk_free_rate=inputs.get('risk_free_rate'),
            risk_free_source=inputs.get('risk_free_source'),
            valuation_parameters=inputs.get('valuation_parameters') or {},
            cut=cut,
        )
    except (CalculationError, ValuationError) as error:
        unavailable = unavailable_valuation_case_metrics(
            price=price,
            reason=str(error),
            case_flags=case_flags,
        )
        unavailable['years_available'] = None
        unavailable['years_compare'] = None
        unavailable['stock_type'] = stock_type
        return unavailable

    case_flags = list(dict.fromkeys([
        *case_provenance_flags(case),
        *(valuation.get('years_available_flags') or []),
    ]))
    case_metrics = valuation_case_metrics(
        valuation,
        stock_type=stock_type,
        price=price,
        case_flags=case_flags,
    )
    case_metrics['years_available'] = valuation.get('years_available')
    case_metrics['years_compare'] = valuation.get('years_compare')
    case_metrics['stock_type'] = stock_type
    if raw_type is not None:
        case_metrics['stock_type_raw'] = raw_type
    # Kuartal dasar yang memotong jendela annual kasus ini. Diambil dari `cut`
    # (bukan dari hasil valuasi) supaya tetap terisi pada jalur cache, dan
    # supaya `details.base_quarter` bisa mengungkap mengapa `years_available`
    # sebuah kasus lebih kecil dari jumlah tahun annualnya.
    base_quarter = str(cut.get('base_quarter') or '') if cut is not None else ''
    if not base_quarter:
        base_quarter = str(valuation.get('base_quarter') or '')
    if base_quarter:
        case_metrics['base_quarter'] = base_quarter
    if fingerprint is not None:
        case_metrics['stock_type_fingerprint'] = fingerprint
        case_metrics['stock_type_source'] = stock_type_source
    return case_metrics


def _case_rows(
    results: Sequence[Mapping[str, Any]],
    *,
    methodology_id: str,
    instrument_id: str,
    sector_name: str | None,
) -> list[dict[str, Any]]:
    """Ubah hasil engine menjadi baris `calc_backtest_cases`.

    ``calculation_run_id`` **tidak** diisi di sini. Run-nya baru bisa dibuat
    setelah snapshot input diketahui, dan snapshot itu justru dibangun dari baris
    ini - jadi id-nya distempel belakangan oleh :func:`_store`.
    """
    rows: list[dict[str, Any]] = []
    for result in results:
        case = result['case']
        metrics = result['metrics']
        valuation = result.get('valuation') or {}
        verdict = result.get('verdict') or {}
        # Flag tingkat kasus adalah gabungan flag harga (Fase 1), valuasi (Fase 2),
        # dan verdict (Fase 3). Tiga sumber berbeda dengan arti berbeda, tapi satu
        # baris hanya punya satu kolom `flags`, jadi keduanya digabung tanpa
        # duplikat.
        flags = list(dict.fromkeys([
            *metrics['flags'],
            *(valuation.get('flags') or []),
            *(verdict.get('flags') or []),
        ]))
        rows.append({
            'methodology_version_id': methodology_id,
            'instrument_id': instrument_id,
            'as_of_financial_period_id': case.as_of_financial_period_id,
            'case_quarter': case.case_quarter,
            'base_year': case.base_year,
            'analysis_date': metrics['analysis_date'],
            'analysis_price': _json_value(metrics['analysis_price']),
            'analysis_price_source': metrics['analysis_price_source'],
            # Tipe saham pada tanggal kasus (keputusan D7): dihitung ulang oleh
            # classifier atas potongan PIT kasus itu, bukan disalin dari snapshot
            # hari ini. `details.stock_type_raw` menyimpan label mentah
            # classifier sebelum dinormalkan, supaya bisa dibandingkan dengan
            # kolom `Jenis Saham` workbook apa adanya.
            'stock_type': valuation.get('stock_type') if valuation else None,
            'sector_name': sector_name,
            'years_available': valuation.get('years_available'),
            'years_compare': valuation.get('years_compare'),
            'mos_main': _json_value(valuation.get('mos_main')),
            'mos_peter': _json_value(valuation.get('mos_peter')),
            'mos_weight': _json_value(valuation.get('mos_weight')),
            'mos_method_code': valuation.get('mos_method_code'),
            'consensus': valuation.get('consensus'),
            'consensus_undervalued': valuation.get('consensus_undervalued'),
            'consensus_valid': valuation.get('consensus_valid'),
            # Verdict dan Verdict MoS: rumus workbook bagian 5.4.1. NULL bila
            # konsensus atau MoS belum ada - bukan FLAT, karena FLAT adalah klaim.
            'verdict': verdict.get('verdict'),
            'verdict_mos': verdict.get('verdict_mos'),
            'return_magnitude': verdict.get('return_magnitude'),
            'return_magnitude_down': verdict.get('return_magnitude_down'),
            'high_3m': _json_value(metrics['high_3m']),
            'low_3m': _json_value(metrics['low_3m']),
            'high_6m': _json_value(metrics['high_6m']),
            'low_6m': _json_value(metrics['low_6m']),
            'high_9m': _json_value(metrics['high_9m']),
            'low_9m': _json_value(metrics['low_9m']),
            'high_12m': _json_value(metrics['high_12m']),
            'low_12m': _json_value(metrics['low_12m']),
            'peak_price': _json_value(metrics['peak_price']),
            'trough_price': _json_value(metrics['trough_price']),
            'peak_month': metrics['peak_month'],
            'trough_month': metrics['trough_month'],
            'return_peak': _json_value(metrics['return_peak']),
            'return_down': _json_value(metrics['return_down']),
            'calculation_status': _combined_status(metrics, valuation),
            'flags': flags,
            'details': {
                **_json_value(metrics['details']),
                **(_json_value(verdict.get('verdict_details')) or {}),
                # Provenance tipe per kasus: label mentah classifier (sebelum
                # dinormalkan), kuartal dasar yang memotong jendela annual, sidik
                # input (dipakai cache pada run berikutnya), dan asal tipe
                # (`RECOMPUTED` / `CACHE` / `GIVEN`). Kolom `stock_type` sendiri
                # memuat tipe yang sudah dinormalkan ke kosakata engine, sehingga
                # label workbook bisa berbeda ejaan (`TURN AROUND` vs
                # `Turn around`) tanpa kehilangan jejak.
                **(
                    {'stock_type_raw': valuation['stock_type_raw']}
                    if valuation.get('stock_type_raw') else {}
                ),
                **(
                    {'base_quarter': valuation['base_quarter']}
                    if valuation.get('base_quarter') else {}
                ),
                **(
                    {'stock_type_fingerprint': valuation['stock_type_fingerprint']}
                    if valuation.get('stock_type_fingerprint') else {}
                ),
                **(
                    {'stock_type_source': valuation['stock_type_source']}
                    if valuation.get('stock_type_source') else {}
                ),
            },
        })
    return rows


def _combined_status(metrics: Mapping[str, Any], valuation: Mapping[str, Any]) -> str:
    """Gabungkan status harga dan status valuasi menjadi satu status kasus.

    Aturannya sederhana dan sengaja konservatif: yang terburuk menang, dengan
    urutan `UNAVAILABLE` > `NOT_CALCULABLE` > `APPROXIMATED` > `VALID`. Satu
    kolom `calculation_status` tidak bisa menyatakan dua keadaan, jadi memilih
    yang paling tidak pasti adalah satu-satunya pilihan yang tidak menyembunyikan
    masalah.
    """
    rank = {STATUS_VALID: 0, STATUS_APPROXIMATED: 1, STATUS_NOT_CALCULABLE: 2, STATUS_UNAVAILABLE: 3}
    price_status = str(metrics.get('calculation_status') or STATUS_UNAVAILABLE)
    if not valuation:
        return price_status

    method_statuses = [
        str(row.get('calculation_status') or STATUS_UNAVAILABLE)
        for row in (valuation.get('methods') or [])
    ]
    if not method_statuses:
        return price_status
    worst = max(method_statuses, key=lambda value: rank.get(value, 3))
    return max([price_status, worst], key=lambda value: rank.get(value, 3))


def _method_rows(
    results: Sequence[Mapping[str, Any]],
    case_ids: Mapping[str, str],
    *,
    methodology_id: str,
    instrument_id: str,
) -> list[dict[str, Any]]:
    """Ubah lima baris metode per kasus menjadi baris `calc_backtest_methods`.

    `case_ids` memetakan `as_of_financial_period_id` ke id baris kasus yang sudah
    tersimpan. Pemetaan itu diperlukan karena `case_id` adalah foreign key yang
    baru ada setelah tabel kasus terisi, jadi urutannya: tulis kasus -> baca id ->
    tulis metode.
    """
    rows: list[dict[str, Any]] = []
    for result in results:
        valuation = result.get('valuation') or {}
        case = result['case']
        case_id = case_ids.get(case.as_of_financial_period_id)
        if not case_id:
            raise CalculationError(
                f'BACKTEST_CASE_ID_MISSING: {case.case_quarter}'
            )
        for method in valuation.get('methods') or []:
            rows.append({
                'case_id': case_id,
                'method_code': method['method_code'],
                'method_name': method['method_name'],
                'intrinsic_value': _json_value(method['intrinsic_value']),
                'current_price': _json_value(method['current_price']),
                'gap_ratio': _json_value(method['gap_ratio']),
                'mos': _json_value(method['mos']),
                'verdict': method['verdict'],
                'calculation_status': method['calculation_status'],
                'flags': method['flags'],
                'details': _json_value(method['details']),
            })
    return rows


def _fetch_case_ids(
    db: SupabaseRest,
    run_id: str,
    instrument_id: str,
) -> dict[str, str]:
    """Petakan `as_of_financial_period_id` -> id baris kasus untuk satu run."""
    stored = _pages(db, CASE_TABLE, {
        'calculation_run_id': 'eq.' + run_id,
        'instrument_id': 'eq.' + instrument_id,
        'select': 'id,as_of_financial_period_id',
    })
    return {
        str(row['as_of_financial_period_id']): str(row['id']) for row in stored
    }


def _create_run(
    db: SupabaseRest,
    *,
    instrument_id: str,
    methodology_id: str,
    input_snapshot: Mapping[str, Any],
) -> str:
    """Ciptakan (atau pakai ulang) satu `calculation_runs` untuk instrumen ini.

    Idempotensinya dari `calculation_contract`: kunci yang sama berarti inputnya
    sama, jadi run yang sudah SUCCEEDED dipakai ulang alih-alih membuat run
    duplikat. Perilaku ini sama dengan `calculate_valuation._store`.
    """
    contract = calculation_contract(
        calculation_type=METHOD_CODE,
        methodology_version_id=methodology_id,
        code_version=CODE_VERSION,
        source_cutoff_date=None,
        source_ingestion_run_id=None,
        scope_type='INSTRUMENT',
        scope_id=instrument_id,
        input_snapshot=dict(input_snapshot),
    )
    existing = db.get_all('calculation_runs', {
        'idempotency_key': 'eq.' + contract['idempotency_key'],
        'select': 'id,status',
    })
    if existing and existing[0]['status'] == 'SUCCEEDED':
        return str(existing[0]['id'])
    if existing:
        run_id = str(existing[0]['id'])
        db.request('PATCH', 'calculation_runs', params={'id': 'eq.' + run_id}, payload={
            'status': 'RUNNING', 'error_message': None, 'completed_at': None,
        })
        return run_id

    created = db.request(
        'POST', 'calculation_runs',
        payload={
            **contract,
            'status': 'RUNNING',
            'scope_type': 'INSTRUMENT',
            'scope_id': instrument_id,
            'methodology_version_id': methodology_id,
        },
        headers={'Prefer': 'return=representation'},
    )
    if not isinstance(created, list) or len(created) != 1:
        raise CalculationError('BACKTEST_RUN_CREATE_FAILED')
    return str(created[0]['id'])


def _stock_type_cache(db: SupabaseRest, instrument_id: str) -> dict[str, dict[str, Any]]:
    """Tipe per kasus dari run SUCCEEDED terbaru, untuk dipakai ulang.

    **Kunci cache** adalah ``(instrument_id, case_quarter)``. Nilainya dipakai
    ulang hanya bila **sidik input** yang tersimpan sama dengan sidik yang baru
    dihitung (lihat :func:`_stock_type_fingerprint`). Jadi cache ini bukan
    "percaya pada hasil lama", melainkan "hasil lama yang inputnya terbukti tidak
    berubah".

    Konsekuensi saat input berubah:

    * **revisi laporan** (fakta pada periode yang sama berubah, atau
      `revision_key` bergeser) mengubah sidik fakta, sehingga tipe kasus itu
      dihitung ulang;
    * **ambang classifier** di registry berubah -> sidik berubah -> dihitung
      ulang;
    * **harga/dividen** baru yang jatuh pada atau sebelum tanggal kasus -> sidik
      berubah -> dihitung ulang;
    * **kasus baru** (kuartal yang belum ada di run sebelumnya) tidak punya entri,
      jadi selalu dihitung.

    Baris run lama yang belum punya `details.stock_type_fingerprint` (mis. hasil
    versi metodologi sebelum D7) dilewati, sehingga cache-nya kosong dan seluruh
    tipe dihitung ulang. Itu memang yang diinginkan: hasil lama itu memakai tipe
    snapshot terbaru, bukan tipe kasus.

    Cache hanya mengurangi **perhitungan ulang**, bukan verifikasi: sidiknya tetap
    dibandingkan untuk setiap kasus pada setiap run.
    """
    runs = _pages(db, 'calculation_runs', {
        'calculation_type': 'eq.' + METHOD_CODE,
        'scope_id': 'eq.' + instrument_id,
        'status': 'eq.SUCCEEDED',
        'select': 'id,completed_at,created_at',
        'order': 'completed_at.desc.nullslast,created_at.desc',
    })
    if not runs:
        return {}

    rows = _pages(db, CASE_TABLE, {
        'calculation_run_id': 'eq.' + str(runs[0]['id']),
        'instrument_id': 'eq.' + instrument_id,
        'select': 'case_quarter,stock_type,details',
    })
    cache: dict[str, dict[str, Any]] = {}
    for row in rows:
        details = row.get('details') or {}
        fingerprint = details.get('stock_type_fingerprint')
        # Kasus yang tipenya tidak bisa dipertanggungjawabkan (`stock_type` NULL)
        # **tidak** di-cache. Cache menyimpan tipe, bukan alasan; mengubah NULL
        # menjadi string kosong akan membuat pemanggil menganggapnya tipe yang
        # sah dan melewati jalur `STOCK_TYPE_UNRESOLVED`. Kasus seperti itu
        # dihitung ulang setiap run - jumlahnya sedikit dan hasilnya tetap
        # dilaporkan apa adanya.
        if not fingerprint or not row.get('stock_type'):
            continue
        cache[str(row['case_quarter'])] = {
            'fingerprint': str(fingerprint),
            'stock_type': str(row['stock_type']),
            'stock_type_raw': details.get('stock_type_raw'),
        }
    return cache


def _store(
    db: SupabaseRest,
    rows: list[dict[str, Any]],
    *,
    instrument_id: str,
    methodology_id: str,
    input_snapshot: Mapping[str, Any],
    results: Sequence[Mapping[str, Any]] = (),
) -> str:
    """Tulis baris kasus (+ metode), lalu **verifikasi jumlahnya**.

    Urutannya penting: kasus dulu, baru metode, karena `case_id` adalah foreign
    key. Verifikasi dilakukan pada kedua tabel - pola yang sama dengan
    `calculate_valuation._store` dan loader lain.
    """
    run_id = _create_run(
        db,
        instrument_id=instrument_id,
        methodology_id=methodology_id,
        input_snapshot=input_snapshot,
    )
    try:
        stamped = [{**row, 'calculation_run_id': run_id} for row in rows]
        _persist_cases(db, stamped)
        stored = _pages(db, CASE_TABLE, {
            'calculation_run_id': 'eq.' + run_id,
            'instrument_id': 'eq.' + instrument_id,
            'select': 'id',
        })
        if len(stored) != len(rows):
            raise CalculationError(
                f'BACKTEST_VERIFY_COUNT_MISMATCH:{CASE_TABLE}:{len(stored)}:{len(rows)}'
            )

        method_rows: list[dict[str, Any]] = []
        if results:
            method_rows = _method_rows(
                results,
                _fetch_case_ids(db, run_id, instrument_id),
                methodology_id=methodology_id,
                instrument_id=instrument_id,
            )
            _persist_methods(db, method_rows)
            stored_methods = _pages(db, METHOD_TABLE, {
                'case_id': 'in.(' + ','.join(
                    sorted({row['case_id'] for row in method_rows})
                ) + ')',
                'select': 'id',
            })
            if len(stored_methods) != len(method_rows):
                raise CalculationError(
                    f'BACKTEST_VERIFY_COUNT_MISMATCH:{METHOD_TABLE}:'
                    f'{len(stored_methods)}:{len(method_rows)}'
                )
        _write_run_status(db, run_id, 'SUCCEEDED')
    except Exception as error:
        try:
            _write_run_status(db, run_id, 'PARTIAL', str(error)[:1000])
        except Exception:
            pass
        raise
    return run_id


def run_ticker(
    db: SupabaseRest,
    ticker: str,
    *,
    apply: bool,
) -> dict[str, Any]:
    """Jalankan backtest fase 1 untuk satu ticker.

    Mengembalikan ringkasan yang bisa dicetak pemanggil (dan dipakai uji
    integrasi manual). Tanpa ``apply`` tidak ada satu baris pun yang ditulis:
    ini yang membuat ``run_pipeline.py ... --only backtest`` aman dicoba lebih
    dulu.
    """
    instruments = db.get_all('instruments', {
        'exchange_code': 'eq.IDX', 'ticker': 'eq.' + ticker,
        'select': 'id,ticker,company_name,sector_name',
    })
    if len(instruments) != 1:
        raise CalculationError('INSTRUMENT_NOT_FOUND_OR_NOT_UNIQUE')
    instrument = instruments[0]
    instrument_id = str(instrument['id'])

    periods = _pages(db, 'financial_periods', {
        'instrument_id': 'eq.' + instrument_id,
        'select': 'id,instrument_id,period_type,period_label,period_end,available_date',
        'order': 'period_end.asc',
    })
    if not periods:
        raise CalculationError('FINANCIAL_PERIODS_MISSING')

    prices = _pages(db, 'prices_daily', {
        'instrument_id': 'eq.' + instrument_id,
        'select': 'trading_date,close_price,high_price,low_price',
        'order': 'trading_date.asc',
    })
    if not prices:
        raise CalculationError('PRICES_DAILY_MISSING')

    # --- input Fase 2 -------------------------------------------------------
    # Tipe saham dari classifier (sumber kebenaran, sama seperti
    # `calculate_valuation`): menebak tipe akan mengubah kelima metode sekaligus.
    #
    # Resolusi tipe **tidak** boleh menggagalkan seluruh ticker. Ticker yang
    # classifier-nya `UNCLASSIFIED` tanpa aturan yang cocok (INDF, JSMR) tidak
    # punya tipe yang bisa dipertanggungjawabkan, tetapi itu bukan alasan
    # kehilangan metrik harga Fase 1-nya: kasusnya tetap ditulis dengan
    # `VALUATION_UNAVAILABLE` dan alasannya, bukan dihilangkan. Karena itu
    # kegagalannya ditangkap di sini dan diteruskan sebagai `stock_type=None`.
    from calculate_valuation import _resolve_stock_type

    stock_type: str | None = None
    classification_run_id: str | None = None
    classification_error: str | None = None
    try:
        stock_type, classification_run_id = _resolve_stock_type(db, instrument_id)
    except CalculationError as error:
        classification_error = str(error)
        print(f'  WARNING: stock type unresolved, valuation will be unavailable: {error}')

    facts = _fetch_facts(db, [str(row['id']) for row in periods])
    dividends = _pages(db, 'dividend_facts', {
        'instrument_id': 'eq.' + instrument_id,
        'select': 'fact_type,period_year,amount_per_share',
    })
    # Bobot/ambang tipe tidak lagi diambil untuk satu tipe: sejak D7 tipe berbeda
    # per kasus, jadi seluruh baris tipe dibaca sekali dan dipilih per kasus.
    reference = fetch_reference_inputs(db, instrument.get('sector_name'))
    reference['registry_years_available'] = REGISTRY_YEARS_AVAILABLE
    risk_free_rate, risk_free_source = fetch_risk_free_rate(db)
    valuation_parameters = _methodology_parameters(db)

    # Parameter classifier ikut masuk sidik cache: kalau ambangnya berubah, tipe
    # dihitung ulang alih-alih dipakai dari cache lama.
    classifier_parameters = classifier_parameter_snapshot()
    stock_type_cache = _stock_type_cache(db, instrument_id)
    print(
        f'  stock-type cache: {len(stock_type_cache)} case(s) reusable '
        f'by input fingerprint'
    )

    results = calculate_cases(
        periods,
        prices,
        valuation_inputs={
            'ticker': ticker,
            'instrument': instrument,
            'instrument_id': instrument_id,
            'stock_type': stock_type,
            'stock_type_error': classification_error,
            # D7: tipe dihitung ulang per kasus, memakai potongan PIT kasus itu.
            'per_case_stock_type': True,
            'classifier_parameters': classifier_parameters,
            'stock_type_cache': stock_type_cache,
            'annual_periods': [row for row in periods if row.get('period_type') == 'ANNUAL'],
            'periods': periods,
            'facts': facts,
            'prices': prices,
            'dividend_rows': dividends,
            'reference': reference,
            'risk_free_rate': risk_free_rate,
            'risk_free_source': risk_free_source,
            'valuation_parameters': valuation_parameters,
        },
    )
    summary: dict[str, Any] = {
        'ticker': ticker,
        'instrument_id': instrument_id,
        'case_count': len(results),
        'period_count': len(periods),
        'price_count': len(prices),
        'stock_type': stock_type,
        'classification_run_id': classification_run_id,
        'stock_type_cache_size': len(stock_type_cache),
        'stock_type_recomputed': sum(
            1 for result in results
            if (result.get('valuation') or {}).get('stock_type_source') == 'RECOMPUTED'
        ),
        'stock_type_reused': sum(
            1 for result in results
            if (result.get('valuation') or {}).get('stock_type_source') == 'CACHE'
        ),
        'run_id': None,
    }

    if not apply:
        summary['cases'] = [
            {
                'case_quarter': result['case'].case_quarter,
                'base_year': result['case'].base_year,
                'analysis_date': result['metrics']['analysis_date'],
                'analysis_price': result['metrics']['analysis_price'],
                'high_12m': result['metrics']['high_12m'],
                'low_12m': result['metrics']['low_12m'],
                'peak_price': result['metrics']['peak_price'],
                'trough_price': result['metrics']['trough_price'],
                'peak_month': result['metrics']['peak_month'],
                'stock_type': (result.get('valuation') or {}).get('stock_type'),
                'stock_type_raw': (result.get('valuation') or {}).get('stock_type_raw'),
                'stock_type_source': (result.get('valuation') or {}).get('stock_type_source'),
                'years_available': (result.get('valuation') or {}).get('years_available'),
                'consensus': (result.get('valuation') or {}).get('consensus'),
                'mos_main': (result.get('valuation') or {}).get('mos_main'),
                'mos_method_code': (result.get('valuation') or {}).get('mos_method_code'),
                'calculation_status': _combined_status(
                    result['metrics'], result.get('valuation') or {}
                ),
                # Gabungan flag harga + flag valuasi, sama seperti yang ditulis
                # `_case_rows`. Menampilkan hanya salah satunya akan membuat dry
                # run menyembunyikan flag yang justru muncul di database.
                'flags': list(dict.fromkeys([
                    *result['metrics']['flags'],
                    *((result.get('valuation') or {}).get('flags') or []),
                ])),
            }
            for result in results
        ]
        return summary

    methodology_id = _required_methodology_id(db)
    rows = _case_rows(
        results,
        methodology_id=methodology_id,
        instrument_id=instrument_id,
        sector_name=instrument.get('sector_name'),
    )
    # Snapshot input sengaja memuat aturan pemilihan kasus, bukan hanya daftar
    # hasilnya: kalau aturannya berubah, kunci idempotensinya ikut berubah dan
    # run lama tidak dipakai ulang secara keliru.
    input_snapshot = {
        'ticker': ticker,
        'code_version': CODE_VERSION,
        'case_quarter_list': [row['case_quarter'] for row in rows],
        'period_ids': [row['as_of_financial_period_id'] for row in rows],
        'case_selection': 'annual years minus two smallest; quarters in base_year + 1',
        'window_rule': '3M inclusive start; 6M/9M/12M exclusive start; peak/trough [T0,+12]',
        'price_row_count': len(prices),
        # Input Fase 2 ikut masuk snapshot supaya perubahan referensi (tipe saham,
        # risk-free rate, parameter metodologi) menghasilkan kunci idempotensi
        # baru. Tanpa ini, run lama akan dipakai ulang walaupun IV-nya berbeda.
        'stock_type': stock_type,
        'classification_run_id': classification_run_id,
        'risk_free_rate': risk_free_rate,
        'valuation_code_version': VALUATION_CODE_VERSION,
        'reference_version': REFERENCE_VERSION,
        'years_available_rule': 'min(registry_years, annual_on_or_before_analysis_date)',
        'fact_row_count': len(facts),
        'dividend_row_count': len(dividends),
        # D7: tipe dihitung per kasus. Aturan dan sidik parameternya masuk
        # snapshot supaya perubahan aturan tipe (atau ambangnya) menghasilkan
        # kunci idempotensi baru, bukan run lama yang dipakai ulang.
        'stock_type_rule': 'metrics_classification_recomputed_per_case',
        'classifier_parameters': _json_value(classifier_parameters),
        'stock_type_fingerprint_version': STOCK_TYPE_FINGERPRINT_VERSION,
    }
    run_id = _store(
        db,
        rows,
        instrument_id=instrument_id,
        methodology_id=methodology_id,
        input_snapshot=input_snapshot,
        results=results,
    )
    summary['run_id'] = run_id
    summary['methodology_version_id'] = methodology_id
    return summary


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--ticker', help='IDX ticker, e.g. AUTO')
    parser.add_argument('--all', action='store_true', help='Run every IDX instrument.')
    parser.add_argument('--apply', action='store_true', help='Persist rows to Supabase.')
    args = parser.parse_args(argv)
    if bool(args.ticker) == bool(args.all):
        parser.error('provide exactly one of --ticker or --all')

    load_env_file(REPO_ROOT / '.env')
    db = SupabaseRest(os.getenv('SUPABASE_URL', ''), os.getenv('SUPABASE_SERVICE_ROLE_KEY', ''))

    if args.all:
        instruments = db.get_all('instruments', {
            'exchange_code': 'eq.IDX', 'select': 'ticker', 'order': 'ticker.asc',
        })
        tickers = [str(row['ticker']) for row in instruments]
    else:
        tickers = [args.ticker.strip().upper().replace('.JK', '')]

    for ticker in tickers:
        summary = run_ticker(db, ticker, apply=args.apply)
        print(
            f'{ticker}: cases={summary["case_count"]} '
            f'periods={summary["period_count"]} prices={summary["price_count"]} '
            f'stock_type={summary.get("stock_type")} '
            f'recomputed={summary.get("stock_type_recomputed")} '
            f'cached={summary.get("stock_type_reused")}'
            + (f' run_id={summary["run_id"]}' if summary.get('run_id') else '')
        )
        for case in summary.get('cases', []):
            print(
                f'  {case["case_quarter"]} base={case["base_year"]} '
                f'date={case["analysis_date"]} price={case["analysis_price"]} '
                f'h12={case["high_12m"]} l12={case["low_12m"]} '
                f'peak={case["peak_price"]} trough={case["trough_price"]} '
                f'peak_month={case["peak_month"]} '
                f'type={case.get("stock_type")} ({case.get("stock_type_source")}) '
                f'years={case["years_available"]} consensus={case["consensus"]} '
                f'mos_main={case["mos_main"]} ({case["mos_method_code"]}) '
                f'{case["calculation_status"]} {case["flags"]}'
            )
    if not args.apply:
        print('DRY RUN: no Supabase rows were written.')
    return 0


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except (CalculationError, BacktestError) as error:
        print(f'FAILED: {error}', file=sys.stderr)
        raise SystemExit(1) from error
