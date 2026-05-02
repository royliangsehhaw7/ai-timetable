
# SPECIFICATIONS.md — Enterprise Adaptive Scheduler

## 1. Project Overview
The **Enterprise Adaptive Scheduler** is a multi-agent system built with **Pydantic AI** designed to autonomously generate valid, conflict-free schedules. This system relies on a strict **Constraint-Based** model, prioritizing state-space reduction, the **Orchestration Pattern**, and the **Reflexion Pattern** to manage domain constraints.

### Core Technologies
*   **Framework:** Pydantic AI (Strict schema validation for LLM outputs).
*   **Language:** Python 3.12+ (Asyncio for parallel validation).
*   **Data Layer:** Abstracted Data Contracts (Agnostic to JSON, SQL, or API backends).

---
## 4.D Architecture Enforcement Rules [NEW]

### **Strict Mediator Pattern Requirements:**

1. **No Direct Agent Communication:**
   - Agents MUST NOT import, reference, or have any awareness of other agents
   - Agent output models MUST NOT be used as input models for other agents
   - All inter-agent data MUST pass through Orchestrator transformation

2. **Orchestrator Sovereignty:**
   - The Orchestrator owns ALL workflow and sequencing logic
   - Agents MUST be stateless regarding workflow position
   - The Orchestrator decides which agents to involve and when

3. **Context Isolation:**
   - Each agent receives ONLY the context it needs from the Orchestrator
   - The Orchestrator MUST transform outputs before sending to next agent
   - No agent should infer workflow state from its input context

4. **Implementation Verification:**
   - Code reviews MUST check for direct agent dependencies
   - Import statements MUST NOT cross agent boundaries
   - All agent communication MUST be traceable through the Orchestrator


## 2. Implementation Philosophy: "Imperative First"
This project adheres to a strict hierarchy of authority and the Single Responsibility Principle (SRP) to ensure system reliability:

*   **Deterministic Guardrails:** Mathematical clashes, temporal availability are handled exclusively by **Python tools**. The AI is never trusted to "calculate" availability.
*   **Heuristic Reasoning:** The AI is reserved for **Strategy and Pedagogy**, deciding which execution paths or time slots are "optimal" based on non-mathematical factors (e.g., preventing subject fatigue).
*   **The "Flavor vs. Fact" Rule:** The Python Engine ensures the **Facts** (the schedule is physically and temporally valid); the AI provides the **Flavor** (the schedule is strategically optimized).