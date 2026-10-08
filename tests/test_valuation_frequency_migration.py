from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]


class ValuationFrequencyMigrationTests(unittest.TestCase):
    def test_schema_migrations_are_additive_transactional_and_private(self) -> None:
        schema = (ROOT / 'supabase/migrations/0033_valuation_frequency_snapshots.sql').read_text(encoding='utf-8')
        rpc = (ROOT / 'supabase/migrations/0034_stock_valuation_frequency_rpc.sql').read_text(encoding='utf-8')
        for source in (schema, rpc):
            self.assertTrue(source.lstrip().startswith('--'))
            self.assertIn('\nbegin;', source)
            self.assertIn('\ncommit;', source)
        for name in (
            'calc_valuation_fundamental_snapshots',
            'calc_valuation_fundamental_methods',
            'calc_valuation_daily_status',
            'calc_valuation_daily_methods',
        ):
            self.assertIn(name, schema)
        self.assertNotRegex(schema.lower(), r'\b(drop|truncate)\s+(table|public\.)')
        self.assertIn('revoke all on table', schema.lower())
        self.assertIn('public.get_stock_valuation_frequency', rpc)
        self.assertIn('grant execute on function public.get_stock_valuation_frequency(text) to anon, authenticated', rpc)

    def test_daily_mode_excludes_intrinsic_and_backtest_steps(self) -> None:
        pipeline = (ROOT / 'run_pipeline.py').read_text(encoding='utf-8')
        self.assertIn("'daily': ('load-prices', 'daily-status')", pipeline)
        self.assertIn("'backtest': ('backtest',)", pipeline)
        self.assertIn("'fundamental': (", pipeline)

    def test_rebuild_and_fundamental_end_with_backtest(self) -> None:
        # The backtest was folded into the two full-operator modes so one command
        # produces every tab and the market card. It must run last, because it
        # reads the canonical periods/prices the earlier loaders refreshed and
        # writes only calc_backtest_* (never calc_valuation_*).
        import importlib.util

        spec = importlib.util.spec_from_file_location('run_pipeline', ROOT / 'run_pipeline.py')
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        modes = module.PIPELINE_MODE_STEPS
        self.assertEqual(modes['rebuild'][-1], 'backtest')
        self.assertEqual(modes['fundamental'][-1], 'backtest')
        # A routine daily price update must never trigger the backtest.
        self.assertNotIn('backtest', modes['daily'])
        # The backtest reads these; both full modes must load them before it runs.
        for mode in ('rebuild', 'fundamental'):
            self.assertIn('load-prices', modes[mode])
            self.assertLess(
                modes[mode].index('valuation'), modes[mode].index('backtest')
            )

    def test_storage_preflight_is_scoped_to_reader_steps(self) -> None:
        # The bug this guards: the preflight that requires raw to already be in
        # Storage used to run for every `rebuild`/`fundamental` invocation,
        # including `--only ingest-raw` - the very step that POPULATES Storage.
        # That made fetching a brand-new ticker impossible: the fetch was blocked
        # by the check that the fetch had not run yet. The preflight must key off
        # the selected steps that READ raw, not the mode name.
        pipeline = (ROOT / 'run_pipeline.py').read_text(encoding='utf-8')
        self.assertIn('storage_reader_steps', pipeline)
        # The reader steps are exactly the canonical loaders that read Storage.
        for step in ('load-identity', 'load-annual', 'load-quarterly', 'load-dividend', 'load-prices'):
            self.assertIn(f"'{step}'", pipeline)
        # The old mode-based guard must be gone.
        self.assertNotIn("if args.mode in ('rebuild', 'fundamental') and not args.dry_run:", pipeline)
        # The preflight must not fire for the raw-populating steps.
        self.assertNotIn("'ingest-raw', 'load-identity'", pipeline)


if __name__ == '__main__':
    unittest.main()