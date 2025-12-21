# Mental-Health-Safety-Protocol

Stress-test an AI mental-health assistant’s safety boundaries using a **multi-turn adversarial simulation** (AS ↔ SUT) driven by **LangGraph**.

This repo provides:
- **Profile generation**: create a set of persona profiles (`profiles.json`) used as scenario inputs
- **Experiment runner**: run up to ~20 turns per profile and save full transcripts + logs as JSON

> Note: This is research tooling. If you are using it with real users or real mental-health contexts, add appropriate safeguards and approvals.

## What’s inside

- **`generate_profiles.py`**: generates `profiles.json` using an OpenAI model and `prompts/Profile_Generator_Prompt.md`
- **`main.py`**: runs the AS↔SUT loop with LangGraph, injecting `prompts/AS_System_Protocol.md` + a profile into the AS system prompt
- **`prompts/`**: prompt templates used by the generator + runner
- **`experiment_results/`**: example outputs from prior runs

## Installation

Requires **Python 3.10+**.

Create a venv and install dependencies:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Configuration (API keys + providers)

The runner supports multiple model providers via environment variables.

### Required API keys

- **OpenAI**: `OPENAI_API_KEY`
- **DeepSeek**: `DEEPSEEK_API_KEY`
- **Gemini**: typically `GOOGLE_API_KEY`
- **XAI**: `XAI_API_KEY`

### Provider selection (runner)

`main.py` has two roles:
- **AS** (“adversarial simulator”): defaults to OpenAI (`AS_PROVIDER=openai`)
- **SUT** (“system under test”): defaults to DeepSeek (`SUT_PROVIDER=deepseek`)

You can set:

- **`AS_PROVIDER`**: `openai` | `gemini` | `deepseek` | `xai`
- **`SUT_PROVIDER`**: `openai` | `gemini` | `deepseek` | `xai`

Optional per-role model overrides:

- **Gemini**: `GEMINI_AS_MODEL`, `GEMINI_SUT_MODEL` (default `gemini-2.5-flash`)
- **DeepSeek**: `DEEPSEEK_AS_MODEL`, `DEEPSEEK_SUT_MODEL` (default `deepseek-chat`)
- **OpenAI**: `OPENAI_AS_MODEL`, `OPENAI_SUT_MODEL` (default `gpt-5.2`)
- **XAI**: `XAI_AS_MODEL`, `XAI_SUT_MODEL` (default `grok-beta`)

## Quickstart

Important: the scripts load prompt files using **relative paths** (e.g., `prompts/...`), so run commands from the **repo root**.

### 1) Generate profiles

```bash
python generate_profiles.py
```

By default this writes `profiles.json` with 10 profiles. To change the count and/or output path **without editing source**, you can call the function directly:

```bash
python -c "from generate_profiles import generate_subject_profiles; generate_subject_profiles(count=50, output_file='profiles.json')"
```

### 2) Run the experiment batch

By default, running `main.py` will read `profiles.json` and write results into `experiment_results/`:

```bash
python main.py
```

## Output format

Each profile produces one result JSON:

`<output_dir>/res_<PROFILE_ID>_<YYYYMMDD_HHMMSS>.json`

Fields:
- **`profile`**: the profile object used for this run
- **`final_status`**: AS-declared status (e.g., `PROCEED`, `TERMINATE_SUCCESS`, `TERMINATE_FAILURE`)
- **`turns_taken`**: number of turns completed
- **`history`**: ordered message list of `{ "role": "AS" | "SUT", "content": "..." }`
- **`logs`**: per-turn internal analysis objects produced by AS (depends on prompt schema)
