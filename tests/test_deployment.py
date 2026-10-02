from pathlib import Path
import yaml

ROOT = Path(__file__).resolve().parents[1]


def test_local_stack_defaults_to_no_provider_or_event_calls_and_loopback_ports():
    services = yaml.safe_load((ROOT / 'docker-compose.yml').read_text())['services']
    environment = services['agent']['environment']
    assert 'AGENT_MODE=${AGENT_MODE:-simulation}' in environment
    assert 'KAFKA_ENABLED=${KAFKA_ENABLED:-false}' in environment
    for service in services.values():
        assert all(port.startswith('127.0.0.1:') for port in service.get('ports', []))
    kafka = services['kafka']['environment']
    assert kafka['KAFKA_PROCESS_ROLES'] == 'broker,controller'
    assert kafka['KAFKA_CONTROLLER_QUORUM_VOTERS'] == '1@kafka:29093'
    assert 'CONTROLLER://0.0.0.0:29093' in kafka['KAFKA_LISTENERS']
    assert kafka['CLUSTER_ID']
    assert 'ports' not in services['kafka']


def test_kubernetes_simulation_has_no_missing_secret_or_broker_requirement():
    deployment, service = yaml.safe_load_all((ROOT / 'k8s/deployment.yaml').read_text())
    container = deployment['spec']['template']['spec']['containers'][0]
    environment = {item['name']: item['value'] for item in container['env']}
    assert environment['AGENT_MODE'] == 'simulation'
    assert environment['KAFKA_ENABLED'] == 'false'
    assert environment['HOST'] == '0.0.0.0'
    assert service['spec']['type'] == 'ClusterIP'
