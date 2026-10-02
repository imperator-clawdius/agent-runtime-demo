# Agent Runtime - Workflow Drafting Reference

A small FastAPI reference for task classification, optional LangChain text drafting,
optional Kafka event emission, Prometheus metrics, and container deployment.

**This demo does not execute business workflows.** It has no HR/payroll tools,
authorization model, verified user identity, repair mechanism, or durable audit log.
A supplied `user_id` is an untrusted label. `/agent/observe` reviews words in the
submitted text; it cannot inspect permissions, identify a root cause, or heal a system.

```text
Request -> FastAPI -> simulation or optional LangChain draft
                  -> optional Kafka demo event (broker receipt only)
                  -> Prometheus request/draft metrics
```

## Run without providers

Python 3.11 or 3.12:

```bash
python -m venv .venv
# Activate .venv using your platform's activation script.
python -m pip install -r requirements.txt
python src/agent.py
```

The default listens on `127.0.0.1:8000`, uses simulation, and initializes neither
an LLM nor Kafka. Even an inherited OpenAI key does not enable model calls.

```bash
curl -X POST http://127.0.0.1:8000/agent/execute \
  -H "Content-Type: application/json" \
  -d '{"task":"Draft an onboarding review checklist","context":{"approval":"not yet verified"}}'
curl http://127.0.0.1:8000/metrics
```

The legacy `/agent/execute` name remains compatible, but the result always reports
`execution_status: "not_executed"`, `review_required: true`, and
`identity_verified: false`. Original `result`, `workflow_type`, `latency_ms`, and
`timestamp` fields remain. `mode` distinguishes `simulation` from `llm_draft`.
Model prose is prefixed as unverified; text saying an action completed is not
evidence of execution. Context is passed to the model only in explicitly enabled
model mode. Task text must be nonempty and at most 12,000 characters.

| Route | Actual behavior |
| --- | --- |
| `POST /agent/execute` | Generate an unverified draft; no tool or business-system action |
| `POST /agent/observe` | Report text signals and suggested checks, with null root cause, false self-healing, and no actions taken |
| `GET /health` | Process liveness, not provider/broker/system health |
| `GET /metrics` | Draft/request counters and latency; no workflow-execution counter |

## Optional integrations

To enable model drafting, set `AGENT_MODE=llm_draft` and `OPENAI_API_KEY` before
starting the process. `LLM_MODEL` defaults to `gpt-4o-mini`. This can incur provider
charges and sends supplied task/context to that provider. Missing required config
fails startup rather than silently pretending a model ran. Model calls use a
30-second timeout and no automatic retries; failure returns a generic 502 with
no completed-action claim. This uses the [LangChain ChatOpenAI integration](https://reference.langchain.com/python/langchain-openai/langchain_openai).

Kafka is enabled only by `KAFKA_ENABLED=true` plus `KAFKA_BOOTSTRAP`. Enabled but
unavailable startup dependencies fail startup. Each generated draft sends an
`agent_draft_generated` metadata event to `ai-agent-events`, omitting task/context
and user labels. The API's `event_delivery` is `disabled`, `acknowledged`, or `failed`.
Acknowledgement requires the send future to complete within five seconds; it says
nothing about consumer processing or external workflow completion. A timeout can
be ambiguous. There is no retry queue, exactly-once delivery, or persistent result
store. Event failure does not erase a successfully generated draft.

## Local Compose example

```bash
docker compose config --quiet
docker compose up -d --build
```

The included stack starts the reference app, a single-node Kafka broker, Prometheus
and Grafana. Model calls and event sends remain disabled by default. All published
ports bind to localhost: app 8000, Prometheus 9090, Grafana 3000; Kafka is available
only within the Compose network. For local event experimentation, explicitly set
`KAFKA_ENABLED=true` and recreate the agent service after the broker is healthy.
Do not use real business data in this demo. Grafana's demo login is `admin/admin`;
no prebuilt dashboards are included. Add Prometheus at `http://prometheus:9090` as
a Grafana data source if exploring the emitted metrics.

Kafka's combined broker/controller configuration follows the
[Confluent 7.5 Docker example](https://docs.confluent.io/platform/7.5/installation/docker/config-reference.html).
The default cluster ID is only for this disposable local example; use a unique
`KAFKA_CLUSTER_ID` for a separate cluster. There are no configured persistent
volumes, authentication or TLS. This example is not a production broker deployment.

## Kubernetes example

```bash
docker build -t agent-runtime-demo:local .
# Make this image available to your cluster (for example, load it into local kind).
kubectl apply -f k8s/deployment.yaml
kubectl port-forward service/ai-agent-service 8000:80 --address 127.0.0.1
```

The manifest defaults to simulation with no missing secret or Kafka-service
dependency. It creates a ClusterIP service, not a public load balancer. The probes
check process liveness only. For model mode, create the provider secret first,
inject `OPENAI_API_KEY`, then explicitly set `AGENT_MODE=llm_draft`. Kafka requires
its own reachable broker and explicit configuration; this manifest does not deploy
one. Image availability, actual cluster rollout and live integrations must be
verified in the intended environment.

The API has **no authentication or authorization**. Keep this reference on a trusted
local/private environment; it is not suitable as a public paid endpoint. A production
design would need identity, scoped tools, approvals, rate/spend controls, secrets
management and real execution receipts. None are implied by this example.

## Tests

```bash
python -m pip install -r requirements-dev.txt
python -m pytest -q
python -m pip check
```

Tests use in-process HTTP clients and mocked model/Kafka clients. They cover truthful
simulation/model/observation responses, supplied context, input validation, provider
errors, broker acknowledgement versus failure, safe defaults, metrics and deployment
configuration. No paid model calls, Kafka writes, business-system operations or
deployments are performed. CI checks Python 3.11/3.12 on Windows/Linux, Compose
configuration and the Docker image build; it does not validate a live broker or cluster.

Built by Teddy Alston - [teddyalston.com](https://teddyalston.com) -
[GitHub](https://github.com/imperator-clawdius)
