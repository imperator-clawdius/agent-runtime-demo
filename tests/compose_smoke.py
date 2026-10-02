"""One synthetic request against the disposable local CI Compose stack only."""
import json
import time
from http.client import HTTPException
from urllib.request import Request, urlopen


def request(route, payload=None, *, timeout=15):
    body = json.dumps(payload).encode('utf-8') if payload is not None else None
    message = Request('http://127.0.0.1:8000' + route, data=body,
                      headers={'Content-Type': 'application/json'})
    with urlopen(message, timeout=timeout) as response:
        assert response.status == 200
        return json.load(response)


def main():
    deadline = time.monotonic() + 30
    while True:
        try:
            health = request('/health', timeout=max(0.1, min(5, deadline - time.monotonic())))
            break
        except (OSError, HTTPException):
            if time.monotonic() >= deadline:
                raise RuntimeError('Local Compose app did not become healthy within 30 seconds.') from None
            time.sleep(0.5)
    assert health['scope'] == 'process_liveness'
    assert health['mode'] == 'simulation'
    assert health['external_actions_supported'] is False
    result = request('/agent/execute', {'task': 'Synthetic CI workflow draft; no business action',
                                      'context': {'fixture': 'disposable-local-compose'}})
    assert result['mode'] == 'simulation'
    assert result['execution_status'] == 'not_executed'
    assert result['identity_verified'] is False
    assert result['event_delivery'] == 'acknowledged', result
    print(json.dumps({'localCompose': 'passed', 'simulation': True,
                      'businessActionsExecuted': False, 'localKafkaReceipt': 'acknowledged'}))


if __name__ == '__main__':
    main()
