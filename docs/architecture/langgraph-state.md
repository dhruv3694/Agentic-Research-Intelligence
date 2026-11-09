# LangGraph shared state

The graph passes a `ResearchWorkflowState` `TypedDict` between nodes. The
compiled graph is reused by the application, while each `ainvoke` receives a
fresh initial state and its own generated research ID.

| Field | Purpose |
| --- | --- |
| `research_id`, `question`, `max_subquestions` | Request identity and planner inputs |
| `plan` | Validated plan returned by the planning service |
| `sources` | Deduplicated sources gathered by the researcher |
| `findings` | Schema-validated analytical claims and source IDs |
| `verification` | Per-finding support status, research gaps, and optional follow-up queries |
| `report` | Deterministically assembled report sections and limitations |
| `current_stage`, `next_stage` | Current node and supervisor's next routing decision |
| `execution_history` | Stage timestamps, durations, outcome, and retry count |
| `errors` | Sanitized errors from failed stages |
| `retrieval_partial` | Whether any retrieval batch returned partial results |
| `attempted_queries`, `targeted_queries` | Query de-duplication and bounded retry inputs |
| `retry_count`, `max_retries` | Retry guard; the workflow caps `max_retries` at one |
| `status`, `started_at`, `completed_at` | Overall lifecycle status and timestamps |

Nodes return only the state updates they own. The supervisor is the sole
component that routes between stages and derives the final `completed`,
`partial`, or `failed` status. Errors stop normal routing and proceed directly
to the graph end. Execution records are appended for the supervisor and each
agent invocation, including a failed invocation.

No checkpointer is configured. The state exists only while a request is
running and is returned in the API response; it is not recoverable after a
process restart.
