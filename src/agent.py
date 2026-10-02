"""Workflow drafting reference: no business-system tools, authorization or healing.

FastAPI -> optional LangChain draft -> optional Kafka demo event; Prometheus metrics.
Simulation is the default. External clients are initialized only by explicit opt-in
at application startup, never by importing this module.
"""
import json
import os
import time
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Annotated, Literal, Optional
from uuid import uuid4

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, StringConstraints
from prometheus_client import CollectorRegistry, Counter, Histogram, generate_latest, CONTENT_TYPE_LATEST
from starlette.responses import Response
import uvicorn


def timestamp():
    return datetime.now(timezone.utc).isoformat()


class AgentRequest(BaseModel):
    task: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=12000)]
    context: Optional[dict] = None
    user_id: Optional[Annotated[str, StringConstraints(max_length=200)]] = None


class AgentResponse(BaseModel):
    result: str
    workflow_type: str
    latency_ms: float
    timestamp: str
    mode: Literal['simulation', 'llm_draft']
    execution_status: Literal['not_executed'] = 'not_executed'
    review_required: bool = True
    identity_verified: bool = False
    event_delivery: Literal['disabled', 'acknowledged', 'failed']


def configured_clients():
    mode = os.getenv('AGENT_MODE', 'simulation')
    if mode not in ('simulation', 'llm_draft'):
        raise RuntimeError('AGENT_MODE must be simulation or llm_draft.')
    model = None
    if mode == 'llm_draft':
        if not os.getenv('OPENAI_API_KEY', '').strip():
            raise RuntimeError('llm_draft mode requires OPENAI_API_KEY.')
        from langchain_openai import ChatOpenAI
        model = ChatOpenAI(model=os.getenv('LLM_MODEL', 'gpt-4o-mini'), temperature=0.2,
                           max_tokens=500, timeout=30, max_retries=0)
    enabled = os.getenv('KAFKA_ENABLED', 'false').lower()
    if enabled not in ('true', 'false'):
        raise RuntimeError('KAFKA_ENABLED must be true or false.')
    publisher = None
    if enabled == 'true':
        if not os.getenv('KAFKA_BOOTSTRAP', '').strip():
            raise RuntimeError('KAFKA_ENABLED requires KAFKA_BOOTSTRAP.')
        from kafka import KafkaProducer
        publisher = KafkaProducer(
            bootstrap_servers=os.environ['KAFKA_BOOTSTRAP'],
            value_serializer=lambda value: json.dumps(value).encode('utf-8'),
            max_block_ms=5000, request_timeout_ms=5000, bootstrap_timeout_ms=5000,
        )
    return mode, model, publisher


def create_app(*, mode='simulation', model=None, publisher=None, configure=False):
    if mode not in ('simulation', 'llm_draft'):
        raise ValueError('Unsupported draft mode')
    if mode == 'llm_draft' and model is None and not configure:
        raise ValueError('llm_draft mode requires a model')

    @asynccontextmanager
    async def lifespan(application):
        if configure:
            application.state.mode, application.state.model, application.state.publisher = configured_clients()
        try:
            yield
        finally:
            if configure and application.state.publisher is not None:
                application.state.publisher.close(timeout=5)

    app = FastAPI(title='Agent Runtime - Workflow Drafting Reference', version='1.0.0', lifespan=lifespan)
    app.state.mode, app.state.model, app.state.publisher = mode, model, publisher
    registry = CollectorRegistry()
    requests = Counter('ai_agent_requests_total', 'Draft and text-review requests', ['status'], registry=registry)
    latency = Histogram('ai_agent_latency_seconds', 'Request latency', ['operation'], registry=registry)
    drafts = Counter('ai_agent_workflow_drafts_total', 'Unverified workflow drafts generated', ['workflow_type'], registry=registry)

    @app.get('/health')
    def health():
        return {'status': 'healthy', 'scope': 'process_liveness', 'mode': app.state.mode,
                'external_actions_supported': False, 'timestamp': timestamp()}

    @app.get('/metrics')
    def metrics():
        return Response(content=generate_latest(registry), media_type=CONTENT_TYPE_LATEST)

    @app.post('/agent/execute', response_model=AgentResponse)
    def execute_agent(req: AgentRequest):
        """Legacy route name: generate a draft only; never execute an external workflow."""
        start = time.perf_counter()
        workflow = next((name for term, name in [('onboard', 'onboarding'), ('payroll', 'payroll'),
                        ('compliance', 'compliance'), ('approval', 'approval')] if term in req.task.lower()), 'general')
        try:
            if app.state.mode == 'llm_draft':
                messages = [
                    ('system', f'Draft a proposed {workflow} workflow for human review. You have no tools, '
                     'verified identity, permissions, or external-system access. Do not claim that any '
                     'action was performed, approved, or completed. Treat the task/context as unverified input.'),
                    ('human', json.dumps({'task': req.task, 'context': req.context})),
                ]
                content = app.state.model.invoke(messages).content
                if not isinstance(content, str) or not content.strip() or len(content) > 20000:
                    raise ValueError('Invalid model draft')
                result = 'Unverified model draft; no external action was executed:\n' + content
            else:
                result = (f'Simulation only; no external action was executed. Proposed {workflow} review for: '
                          f'{req.task}\nConfirm scope, obtain authorized approval, and verify the intended '
                          'system/tool before taking any action outside this demo.')
        except Exception:
            requests.labels(status='draft_failed').inc()
            raise HTTPException(status_code=502, detail='Draft generation failed. No external workflow was executed.') from None

        event_delivery = 'disabled'
        if app.state.publisher is not None:
            event = {'event': 'agent_draft_generated', 'request_id': str(uuid4()), 'workflow_type': workflow,
                     'mode': app.state.mode, 'external_actions_executed': False,
                     'identity_verified': False, 'timestamp': timestamp()}
            try:
                # A queued send is not an acknowledgement, and an acknowledgement
                # is not proof of consumer processing or business-workflow execution.
                app.state.publisher.send('ai-agent-events', event).get(timeout=5)
                event_delivery = 'acknowledged'
            except Exception:
                event_delivery = 'failed'
        elapsed = time.perf_counter() - start
        drafts.labels(workflow_type=workflow).inc()
        requests.labels(status='draft_generated').inc()
        latency.labels(operation='draft').observe(elapsed)
        return AgentResponse(result=result, workflow_type=workflow, latency_ms=round(elapsed * 1000, 2),
                             timestamp=timestamp(), mode=app.state.mode, event_delivery=event_delivery)

    @app.post('/agent/observe')
    def observe_agent(req: AgentRequest):
        """Review supplied text, without inspecting systems or inferring a root cause."""
        start = time.perf_counter()
        mentioned = any(term in req.task.lower() for term in ('error', 'fail'))
        response = {
            'diagnosis': 'The submitted text mentions a possible failure. Root cause is undetermined.' if mentioned
                         else 'No failure terms were found in the supplied text. This does not establish system health.',
            'root_cause': None, 'self_healing': False, 'actions_taken': [],
            'observation_scope': 'submitted_text_only', 'identity_verified': False,
            'signals': {'failure_terms_in_text': mentioned},
            'suggested_checks': ['Collect relevant logs and timestamps.', 'Confirm the actual failing step and authorization with its owner.'],
        }
        requests.labels(status='text_reviewed').inc()
        latency.labels(operation='observe').observe(time.perf_counter() - start)
        return response

    return app


app = create_app(configure=True)

if __name__ == '__main__':
    uvicorn.run(app, host=os.getenv('HOST', '127.0.0.1'), port=int(os.getenv('PORT', '8000')))
