import importlib.util
from pathlib import Path
from unittest.mock import Mock

import pytest

spec = importlib.util.spec_from_file_location('compose_smoke', Path(__file__).with_name('compose_smoke.py'))
smoke = importlib.util.module_from_spec(spec)
spec.loader.exec_module(smoke)


def test_startup_connection_reset_retries_health_but_submits_only_one_draft(monkeypatch):
    request = Mock(side_effect=[ConnectionResetError('starting'),
        {'scope': 'process_liveness', 'mode': 'simulation', 'external_actions_supported': False},
        {'mode': 'simulation', 'execution_status': 'not_executed', 'identity_verified': False,
         'event_delivery': 'acknowledged'}])
    monkeypatch.setattr(smoke, 'request', request)
    monkeypatch.setattr(smoke.time, 'sleep', lambda _: None)
    smoke.main()
    assert [call.args[0] for call in request.call_args_list] == ['/health', '/health', '/agent/execute']


def test_startup_failure_has_a_deadline_and_never_submits_a_draft(monkeypatch):
    request = Mock(side_effect=ConnectionResetError('unavailable'))
    monkeypatch.setattr(smoke, 'request', request)
    monkeypatch.setattr(smoke.time, 'monotonic', Mock(side_effect=[0, 0, 31]))
    with pytest.raises(RuntimeError, match='30 seconds'):
        smoke.main()
    assert request.call_count == 1
    assert request.call_args.args == ('/health',)
