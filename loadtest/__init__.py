"""RastiSi Phase 3 Locust load-test suite.

This package is intentionally standalone — it has NO dependency on Django,
the ``apps.*`` codebase, or ``shop_core.settings``. It is an external HTTP
client tool meant to run from an operator's machine or a dedicated
load-generator host against a target RastiSi deployment's public HTTP
surface, exactly the way a real browser/customer would. See
``loadtest/README.md`` for the full operator runbook, and
``loadtest/safety.py`` for the hard target-host safety guard that every
entry point in this package goes through before sending a single request.
"""
