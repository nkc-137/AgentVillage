

# Agent Village Backend Implementation Plan

This document serves as a reference guide while building the backend for the Agent Village assignment. It summarizes the architecture, implementation steps, and design decisions needed to complete the prototype efficiently.

The goal of the project is not to build a production‑ready system but to demonstrate strong **architecture judgment, trust‑boundary design, and systems thinking**.

---

# 1. Core Objective of the Assignment

The backend must enable AI agents to behave like inhabitants of a shared world. Each agent should:

- Maintain a personal identity
- Interact with its owner privately
- Interact with strangers safely
- Post to a public shared feed
- Occasionally act proactively without being triggered by HTTP requests

The most important requirement is **trust boundary separation** between:

1. Owner conversations (full trust)
2. Stranger conversations (limited trust)
3. Public feed posts (fully public)

The architecture must ensure that **private owner information never leaks into stranger conversations or public feed posts**.

---

# 2. Technology Stack

The backend will use a lightweight Python stack designed for rapid prototyping.

Core technologies:

- **FastAPI** — backend API framework
- **Supabase (Postgres)** — data storage
- **OpenAI API** — language model for agent responses
- **APScheduler or async worker loop** — background agent scheduler
- **Pydantic** — request/response validation
- **httpx** — async API calls

This stack allows the system to remain simple while demonstrating strong backend architecture.

---

# 3. High‑Level System Architecture

The system consists of four main layers:

Frontend

- Provided dashboard UI
- Reads public data directly from Supabase

Backend API

- Handles messaging
- Applies trust boundary logic
- Builds prompts for agents

Agent Runtime Engine

- Evaluates agent behavior
- Generates diary entries
- Processes proactive actions

Database

- Stores agents, memories, logs, activities, and feed posts

The backend primarily orchestrates agent behavior and data access rather than serving all frontend data.

---

# 4. Key System Components

The backend should be structured into clear services to separate responsibilities.

API Layer

Handles incoming requests such as agent messages.

Trust Service

Determines what information an agent is allowed to access based on the trust context.

Memory Service

Reads and writes agent memories.

Prompt Builder

Constructs prompts tailored for owner conversations, stranger conversations, or public posts.

LLM Service

Communicates with the language model API.

Behavior Engine

Decides what proactive actions agents should take.

Scheduler

Runs a background loop that periodically evaluates each agent.

Logging Service

Records agent behavior for observability and debugging.

---

## Suggested Backend Project Structure

A clean project structure will make the prototype easier to build, debug, and explain in the architecture document. The goal is to keep responsibilities separated without over-engineering.

Recommended structure:

- `app/main.py`
  - FastAPI app entrypoint
  - startup and shutdown hooks
  - scheduler bootstrapping
  - route registration

- `app/dependencies.py`
  - shared dependency providers
  - environment/config loading
  - Supabase client setup
  - OpenAI client setup

- `app/api/`
  - API route layer
  - request handling only
  - delegates business logic to services

- `app/api/routes_messages.py`
  - message endpoint for owner and stranger conversations

- `app/api/routes_agents.py`
  - agent-related endpoints such as manual agent tick or debug actions

- `app/api/routes_feed.py`
  - optional feed/debug endpoints if needed for testing

- `app/services/`
  - business logic layer
  - keeps route files thin and focused

- `app/services/agent_service.py`
  - high-level agent orchestration
  - loads agent state
  - coordinates trust, memory, prompt, and LLM services

- `app/services/trust_service.py`
  - applies trust-boundary rules
  - decides what data is visible in owner, stranger, and public contexts

- `app/services/memory_service.py`
  - reads and writes memories
  - filters private vs public memory
  - decides what should be persisted

- `app/services/prompt_service.py`
  - builds prompts for different contexts
  - owner conversation prompts
  - stranger conversation prompts
  - public diary prompts

- `app/services/llm_service.py`
  - wraps calls to the language model provider
  - central place for response generation

- `app/services/behavior_service.py`
  - proactive behavior engine
  - decides whether an agent should write a diary entry, update status, or do nothing

- `app/services/scheduler_service.py`
  - background worker loop
  - periodically evaluates all active agents

- `app/services/logging_service.py`
  - structured logging helper
  - writes observability events to `living_log`

- `app/clients/`
  - thin wrappers around external systems

- `app/clients/supabase_client.py`
  - optional helper layer for Supabase interactions if database access starts spreading too much across services

- `app/clients/openai_client.py`
  - optional helper layer for LLM-specific request code

- `app/domain/`
  - optional place for small domain-specific constants, enums, or policy definitions
  - useful if trust contexts or behavior rules grow in complexity

- `demo/`
  - curl scripts or small demo helpers for owner and stranger conversations
  - manual scheduler trigger scripts if needed

- `requirements.txt`
  - Python dependencies

- `.env`
  - environment variables for Supabase, OpenAI, and scheduler settings

- `architecture.md`
  - final architecture writeup for the assignment submission

This structure is intentionally simple. It shows clear separation between API handling, agent behavior, trust logic, storage access, and background scheduling, which will make the design easier to explain during the demo and in the architecture document.

---

# 6. Data Model Overview

The system relies primarily on the schema provided with the assignment.

Important tables include:

living_agents

Stores public identity information such as name, personality, and avatar.

living_memory

Stores private relationship memories between the owner and the agent.

living_diary

Stores public diary entries written by agents.

living_activity_events

Tracks public actions such as posting diary entries.

living_log

Stores internal system logs for observability.

The main design principle is that **private owner memories are stored separately from public diary content**.

---

# 7. Trust Boundary Design

Trust boundaries determine what data the agent is allowed to access.

Owner Context

Agents may access:

- private memories
- owner preferences
- conversation history
- public agent state

Stranger Context

Agents may access:

- public diary entries
- public identity
- general personality

Agents must not access:

- private owner memories
- personal details about the owner

Public Feed

Public feed posts must only use information that is safe to share publicly.

Private memories should never appear directly in public content.

---

# 8. API Endpoints

The prototype only requires a small set of endpoints.

Message Endpoint

Allows a user to send a message to an agent.

The request must include:

- agent id
- user id
- trust context (owner or stranger)
- message text

The backend processes the request, applies trust filtering, generates a response using the LLM, and returns the reply.

Agent Tick Endpoint

Optional endpoint that manually triggers an agent behavior cycle. Useful for debugging or demos.

Scheduler Endpoint

Optional endpoint that triggers behavior for all agents.

Debug Endpoints

Optional endpoints to inspect memories or logs.

---

# 9. Message Processing Flow

When a message is sent to an agent, the backend should follow this sequence:

1. Load the agent's identity and public state
2. Determine the trust context
3. Retrieve only the allowed memory for that context
4. Build the appropriate prompt
5. Generate a response using the language model
6. Optionally store new memories
7. Log the interaction

This ensures that the agent's response always respects the trust boundary rules.

---

# 10. Memory Storage Strategy

Not every conversation message should become a stored memory.

Memories should only be stored when the message contains meaningful personal information, such as:

- preferences
- important dates
- emotional events
- recurring facts

Examples include personal interests, reminders, or important relationship information.

Routine conversation or small talk should not be stored.

---

# 11. Proactive Behavior Engine

Agents should occasionally act on their own.

The behavior engine evaluates each agent and decides whether they should perform an action.

Possible proactive behaviors include:

- writing a diary entry
- reflecting on recent events
- updating their status

These actions should be triggered by logical conditions rather than purely random timers.

For example:

- if no diary entry has been written for several hours
- if the agent recently learned something meaningful
- if there has been a long period of inactivity

---

# 12. Agent Scheduler

Agents must be able to act without relying on external HTTP requests.

A background worker loop will periodically evaluate each agent.

The scheduler should:

- run at regular intervals
- iterate through all agents
- trigger the behavior engine

For this prototype, a simple in‑process scheduler is sufficient.

In a production system this would likely be replaced by a distributed job queue.

---

# 13. Observability and Logging

Understanding agent behavior is important for debugging and system monitoring.

The system should log events such as:

- incoming messages
- generated responses
- memory creation
- behavior decisions
- diary posts

These logs allow developers to understand why an agent acted in a particular way.

---

# 14. Demo Plan

The demo should demonstrate the following capabilities:

Agent Posting to Feed

Show that agents can write diary entries that appear in the shared feed.

Owner Conversation

Send a message from the owner containing private information and verify that the agent remembers it.

Stranger Conversation

Send a message from a stranger asking about the owner and verify that the agent does not reveal private details.

Proactive Behavior

Demonstrate that an agent writes a diary entry automatically through the scheduler.

---

# 15. Scaling Considerations

If the system were expanded to support thousands of agents, several components would become bottlenecks.

LLM Inference

Running many LLM calls simultaneously would become expensive and slow.

Agent Scheduling

A single in‑process scheduler would not scale to many agents.

Memory Growth

Agent memories would grow indefinitely without summarization or pruning.

Feed Aggregation

The public feed would require ranking and filtering to remain usable.

These issues could be solved using distributed workers, job queues, memory summarization, and caching strategies.

---

# 16. Implementation Roadmap

Step 1

Set up Supabase and run the provided database schema.

Step 2

Verify that the frontend dashboard loads agents and feed data from Supabase.

Step 3

Create the FastAPI backend skeleton.

Step 4

Implement the agent messaging endpoint.

Step 5

Add trust boundary filtering and prompt generation.

Step 6

Implement memory storage for meaningful owner messages.

Step 7

Build the agent behavior engine.

Step 8

Add the background scheduler loop.

Step 9

Implement logging and observability.

Step 10

Run the demo scenarios and document the architecture.

---

This document should be used as a checklist while implementing the system to ensure the architecture remains clean, the trust boundaries are respected, and the prototype remains focused on the core goals of the assignment.
