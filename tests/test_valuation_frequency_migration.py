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


if __name__ == '__main__':
    unittest.main()