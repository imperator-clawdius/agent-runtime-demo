from types import SimpleNamespace
from unittest.mock import Mock, patch

import pytest
from fastapi.testclient import TestClient
from src.agent import create_app, configured_clients


def test_simulation_is_truthful_and_uses_task_without_trusting_user_identity():
    with TestClient(create_app()) as client:
        response = client.post('/agent/execute', json={'task': 'Review payroll for synthetic team', 'user_id': 'hr_admin'})
        assert response.status_code == 200
        body = response.json()
        assert body['workflow_type'] == 'payroll'
        assert body['mode'] == 'simulation'
        assert body['execution_status'] == 'not_executed'
        assert body['review_required'] is True
        assert body['identity_verified'] is False
        assert body['event_delivery'] == 'disabled'
        assert 'Review payroll for synthetic team' in body['result']
        assert 'no external action was executed' in body['result']


@pytest.mark.parametrize('task', ['Synthetic workflow failed with error 17', 'No failure report was supplied', 'Routine draft review'])
def test_observe_never_invents_a_root_cause_or_repairs(task):
    model, publisher = Mock(), Mock()
    with TestClient(create_app(mode='llm_draft', model=model, publisher=publisher)) as client:
        result = client.post('/agent/observe', json={'task': task}).json()
        assert result['root_cause'] is None
        assert result['self_healing'] is False
        assert result['actions_taken'] == []
        assert result['observation_scope'] == 'submitted_text_only'
        assert 'step 3' not in result['diagnosis']
        model.invoke.assert_not_called()
        publisher.send.assert_not_called()


def test_model_output_is_an_unverified_draft_with_context_preserved():
    model = Mock(invoke=Mock(return_value=SimpleNamespace(content='Proposed review checklist')))
    with TestClient(create_app(mode='llm_draft', model=model)) as client:
        result = client.post('/agent/execute', json={'task': 'Onboard a synthetic employee', 'context': {'constraint': 'approval needed'}}).json()
        assert result['execution_status'] == 'not_executed'
        assert result['result'].endswith('Proposed review checklist')
        assert result['result'].startswith('Unverified model draft; no external action was executed:')
        messages = model.invoke.call_args.args[0]
        assert 'no tools' in messages[0][1]
        assert 'approval needed' in messages[1][1]


@pytest.mark.parametrize('content', ['', None, [{'type': 'unexpected'}]])
def test_invalid_model_content_does_not_emit_success_events(content):
    publisher = Mock()
    model = Mock(invoke=Mock(return_value=SimpleNamespace(content=content)))
    with TestClient(create_app(mode='llm_draft', model=model, publisher=publisher)) as client:
        assert client.post('/agent/execute', json={'task': 'Draft an approval flow'}).status_code == 502
        publisher.send.assert_not_called()


def test_provider_failure_is_generic_and_never_emits_a_completion_event():
    model, publisher = Mock(), Mock()
    model.invoke.side_effect = RuntimeError('private provider key details')
    with TestClient(create_app(mode='llm_draft', model=model, publisher=publisher)) as client:
        response = client.post('/agent/execute', json={'task': 'Synthetic request'})
        assert response.status_code == 502
        assert 'private' not in response.text
        publisher.send.assert_not_called()


@pytest.mark.parametrize('accepted', [True, False])
def test_event_receipt_distinguishes_broker_acknowledgement_and_failure(accepted):
    publisher = Mock()
    if not accepted:
        publisher.send.return_value.get.side_effect = TimeoutError('private broker details')
    with TestClient(create_app(publisher=publisher)) as client:
        result = client.post('/agent/execute', json={'task': 'Synthetic payroll draft', 'user_id': 'sensitive-label'}).json()
        assert result['event_delivery'] == ('acknowledged' if accepted else 'failed')
        assert result['execution_status'] == 'not_executed'
        publisher.send.return_value.get.assert_called_once_with(timeout=5)
        topic, event = publisher.send.call_args.args
        assert topic == 'ai-agent-events'
        assert event['event'] == 'agent_draft_generated'
        assert event['external_actions_executed'] is False
        assert event['identity_verified'] is False
        assert 'task' not in event and 'user_id' not in event


def test_invalid_requests_do_not_call_providers_and_metrics_count_drafts():
    publisher = Mock()
    with TestClient(create_app(publisher=publisher)) as client:
        for body in [{}, {'task': ''}, {'task': ' '}, {'task': 'x' * 12001}, {'task': 'ok', 'context': []}]:
            for route in ['/agent/execute', '/agent/observe']:
                assert client.post(route, json=body).status_code == 422
        publisher.send.assert_not_called()
        client.post('/agent/execute', json={'task': 'Synthetic task'})
        metrics = client.get('/metrics').text
        assert 'ai_agent_workflow_drafts_total' in metrics
        assert 'ai_agent_workflow_runs_total' not in metrics
        assert client.get('/health').json()['scope'] == 'process_liveness'
        assert client.get('/health').json()['external_actions_supported'] is False


def test_default_configuration_never_initializes_external_clients_even_with_inherited_api_key():
    with patch.dict('os.environ', {'OPENAI_API_KEY': 'must-not-be-used'}, clear=True), \
         patch('langchain_openai.ChatOpenAI') as model, patch('kafka.KafkaProducer') as publisher:
        assert configured_clients() == ('simulation', None, None)
        model.assert_not_called()
        publisher.assert_not_called()


def test_explicit_clients_start_and_close_in_lifespan_with_mocked_io_only():
    model = Mock(invoke=Mock(return_value=SimpleNamespace(content='Unverified claim: payroll completed')))
    publisher = Mock()
    settings = {'AGENT_MODE': 'llm_draft', 'OPENAI_API_KEY': 'mock-only',
                'KAFKA_ENABLED': 'true', 'KAFKA_BOOTSTRAP': 'mock.invalid:9092'}
    with patch.dict('os.environ', settings, clear=True), \
         patch('langchain_openai.ChatOpenAI', return_value=model) as create_model, \
         patch('kafka.KafkaProducer', return_value=publisher) as create_publisher:
        with TestClient(create_app(configure=True)) as client:
            result = client.post('/agent/execute', json={'task': 'Synthetic payroll plan'}).json()
            assert result['mode'] == 'llm_draft'
            assert result['execution_status'] == 'not_executed'
            assert result['result'].startswith('Unverified model draft; no external action was executed:')
            assert result['event_delivery'] == 'acknowledged'
        assert create_model.call_args.kwargs['max_retries'] == 0
        assert create_model.call_args.kwargs['timeout'] == 30
        assert create_publisher.call_args.kwargs['max_block_ms'] == 5000
        publisher.close.assert_called_once_with(timeout=5)


@pytest.mark.parametrize('environment', [{'AGENT_MODE': 'execute'}, {'AGENT_MODE': 'llm_draft'}, {'KAFKA_ENABLED': 'yes'}, {'KAFKA_ENABLED': 'true'}])
def test_invalid_explicit_configuration_fails_without_silent_fallback(environment):
    with patch.dict('os.environ', environment, clear=True), pytest.raises(RuntimeError):
        configured_clients()
