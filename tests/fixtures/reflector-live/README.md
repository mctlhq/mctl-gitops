Synthetic metadata listings for tests/test_live_reflector_drift.py: namespaces and Secret names
are invented (apart from the three platform source names), no real cluster data, no values.
converged.txt is the intended end state; mirror-survivor.txt adds one mirror;
truncated.txt is a listing cut short (no trailer).
Every listing starts with the collector's "#CLUSTER context=... server=..." header (here the invented fixture-ctx);
D2 requires --expect-context/--expect-server to match it.
