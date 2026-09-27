# Tests

The stable offline baseline is the Phase 4.1 regression test. It uses the small saved fixture in `tests/fixtures/` and does not call Sectors or Supabase.

Run it from the project root:

```powershell
python -m unittest tests.test_phase_4_1_registry_and_pit -v
```

Some older calculation test ideas remain in the ignored `Testing/` folder. They are not part of the passing baseline yet; they depend on unfinished calculation modules.