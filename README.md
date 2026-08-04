# Agent Runtime — Enterprise AI Agent Infrastructure Demo

<img src="https://img.shields.io/badge/Python-3.11-blue" alt="Python">
<img src="https://img.shields.io/badge/Kubernetes-Ready-green" alt="Kubernetes">
<img src="https://img.shields.io/badge/Status-Reference%20Implementation-success" alt="Reference Implementation">

A reference implementation of enterprise AI agent infrastructure: autonomous workflow agents, event streaming, observability, and Kubernetes orchestration. Built as an architecture study of the patterns production AI-platform teams use — background agents, event-sourced audit trails, permission-aware execution, and self-healing systems.

## Architecture

```
                    ┌─────────────────────────────────┐
                    │        Load Balancer             │
                    └─────────────┬───────────────────┘
                                  │
                    ┌─────────────▼───────────────────┐
                    │     FastAPI Agent (2 replicas)   │
                    │  ┌─────────────────────────────┐ │
                    │  │   LangChain Agent           │ │
                    │  │   • Workflow classification │ │
                    │  │   • LLM-powered execution   │ │
                    │  │   • Permission-aware        │ │
                    │  └─────────────┬───────────────┘ │
                    │                │                  │
                    │    ┌───────────▼──────────────┐  │
                    │    │   Kafka Event Stream      │  │
                    │    │   • Audit trail           │  │
                    │    │   • Workflow events       │  │
                    │    └──────────────────────────┘  │
                    │                │                  │
                    │    ┌───────────▼──────────────┐  │
                    │    │   Prometheus + Grafana    │  │
                    │    │   • Request metrics       │  │
                    │    │   • Latency histograms    │  │
                    │    │   • Workflow dashboards   │  │
                    │    └──────────────────────────┘  │
                    └─────────────────────────────────┘
```

## Quick Start

```bash
# 1. Clone
git clone https://github.com/imperator-clawdius/agent-runtime-demo.git && cd agent-runtime-demo

# 2. Set your LLM key
export OPENAI_API_KEY="sk-..."

# 3. Launch full stack
docker compose up -d

# 4. Test the agent
curl -X POST http://localhost:8000/agent/execute \
  -H "Content-Type: application/json" \
  -d '{"task": "Onboard new employee: set up payroll, benefits, and IT access", "user_id": "hr_admin"}'

# 5. Check metrics
curl http://localhost:8000/metrics

# 6. View dashboards
open http://localhost:3000  # Grafana (admin/admin)
open http://localhost:9090  # Prometheus
```

## Kubernetes Deployment

```bash
# Build image
docker build -t agent-runtime-demo:latest .

# Deploy
kubectl apply -f k8s/deployment.yaml

# Create secrets
kubectl create secret generic ai-agent-secrets --from-literal=openai-key=$OPENAI_API_KEY

# Scale
kubectl scale deployment ai-agent --replicas=5
```

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/agent/execute` | Execute AI agent workflow |
| `POST` | `/agent/observe` | Self-healing diagnosis |
| `GET`  | `/health` | Health check |
| `GET`  | `/metrics` | Prometheus metrics |

## What This Demonstrates

- **AI Agents**: LLM-powered workflow execution with context awareness
- **Event Streaming**: Kafka for audit trails and async processing
- **Observability**: Prometheus metrics + Grafana dashboards
- **Kubernetes**: Production-grade deployment with health checks, resource limits, replicas
- **Self-Healing**: `/agent/observe` endpoint detects failures and suggests root causes
- **Permission-Aware**: Designed with enterprise permissions model in mind
- **Workflow Patterns**: Classification and routing for onboarding, payroll, compliance, and approval flows

## Why This Exists

This repo is an honest study of how enterprise AI platforms are structured — agents scoped to single jobs, events as the audit backbone, metrics as the source of truth, and deployments that survive restarts. It's the pattern set I run in production daily (multi-agent orchestration with scoped tools and autonomy gates) distilled into a clean, runnable reference. No demo theater — the same architectural decisions apply whether you're automating HR workflows or any other domain.

---

**Built by Teddy Alston** • [teddyalston.com](https://teddyalston.com) • [github.com/imperator-clawdius](https://github.com/imperator-clawdius)
