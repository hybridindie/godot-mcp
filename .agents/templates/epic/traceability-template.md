<!--
  traceability-template.md — Traceability table for mapping Epic claims to sources
  Referenced by: epic-composer (optional, when the user asks for traceability)
  version: 3.0.1, owner: John D
-->

## Traceability Map

Each row maps an Epic element back to its source, classifies it, and states
how it can be verified. Replace the example rows with actual entries.

| ID | Epic Element | Statement | Source | Type | Confidence | Verification |
|----|-------------|-----------|--------|------|------------|-------------|
| R1 | Problem | "Users cannot export reports in PDF format" | Meeting transcript 2024-01-15, line 34 | explicit | high | stakeholder confirmation |
| R2 | Scope | "PDF export for reports under 500 rows is in scope" | Product doc v2, section 3.1 | explicit | high | role-based review |
| R3 | NFR | "Export completes within 10 seconds" | Inferred from user complaint about "slow exports" | inferred | medium | user confirmation + performance test |
| R4 | Success | "Reduce support tickets about export failures by 80%" | Meeting transcript 2024-01-15, line 52 | explicit | high | post-release metric |
| R5 | Migration | "Legacy CSV export remains available during transition" | Not mentioned in any source | unresolved | n/a | stakeholder decision required |

### Type legend
- **explicit**: directly stated in source material
- **inferred**: reasonable implication from source material
- **unresolved**: required but not established in any source