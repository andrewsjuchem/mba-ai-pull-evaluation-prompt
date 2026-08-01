# Bug → User Story

A prompt engineering pipeline that turns bug reports into **agile User Stories**, built
with LangChain + LangSmith. The prompt lives versioned in the LangSmith Prompt Hub and
is scored automatically by a set of LLM-as-Judge metrics against a dataset of 15 bugs
with hand-written ground truth.

The core idea: treat the prompt as code — versioned, published, and tested by a suite
that grades it from 0 to 1 across five dimensions, with a pass mark of 0.8.

> **Language note:** the documentation is in English, but the prompts, the dataset and
> the generated User Stories are all in **Brazilian Portuguese** — `system_prompt`,
> few-shot examples, bug reports and expected outputs included. The judge prompts in
> `src/metrics.py` are in Portuguese too. If you translate the prompt, translate the
> dataset with it: every metric scores the answer *against the reference*, so a
> language mismatch tanks the scores.

---

## What the pipeline does

```
┌─────────────────┐   pull    ┌──────────────────────┐
│ LangSmith Hub   │ ────────► │ prompts/*.yml        │  local, editable copy
│ (source of      │ ◄──────── │                      │
│  record)        │   push    └──────────────────────┘
└─────────────────┘
        │
        │ pull (evaluate)
        ▼
┌─────────────────────────────────────────────────────────────┐
│  for each of the 15 bugs in the dataset:                    │
│                                                             │
│  bug_report ──► [ prompt v2 ] ──► LLM ──► generated story   │
│                                              │              │
│                     generated + ground truth │              │
│                                              ▼              │
│                                    [ 3 LLM judges ]         │
│                                    F1 · Clarity · Precision │
└─────────────────────────────────────────────────────────────┘
        │
        ▼
   averages + 2 derived metrics → passes if all >= 0.8
```

**Three artifacts that are easy to confuse:**

| Artifact | Role | Where |
| --- | --- | --- |
| The prompt under test | Turns a bug report into a User Story | `prompts/bug_to_user_story_v2.yml` |
| The dataset | 15 test bugs + the ideal User Story for each | `datasets/bug_to_user_story.jsonl` |
| The judge prompts | Grade the answer against the ground truth | `src/metrics.py` |

---

## Layout

```
.
├── prompts/
│   ├── bug_to_user_story_v1.yml   # original low-quality prompt (baseline)
│   └── bug_to_user_story_v2.yml   # optimized prompt — the main artifact
│
├── datasets/
│   └── bug_to_user_story.jsonl    # 15 bugs: 5 simple, 7 medium, 3 complex
│
├── src/
│   ├── pull_prompts.py            # Hub → local YAML
│   ├── push_prompts.py            # local YAML → Hub (public)
│   ├── evaluate.py                # runs the dataset, computes the 5 metrics
│   ├── metrics.py                 # the judge prompts (LLM-as-Judge)
│   └── utils.py                   # YAML, env vars, LLM factory
│
└── tests/
    └── test_prompts.py            # structural validation of the YAML (pytest)
```

---

## Requirements

- Python 3.9+
- A [LangSmith](https://smith.langchain.com) account with an API key
- A public LangSmith Hub handle (required to publish a prompt publicly)
- An API key for one provider: OpenAI **or** Google Gemini

---

## Setup

```bash
python3 -m venv venv
source venv/bin/activate          # Windows: venv\Scripts\activate
pip install -r requirements.txt

cp .env.example .env              # then fill in your keys
```

### Environment variables

| Variable | Purpose |
| --- | --- |
| `LANGSMITH_API_KEY` | Auth for LangSmith (pull, push and dataset) |
| `LANGSMITH_PROJECT` | Project name; the eval dataset becomes `<project>-eval` |
| `USERNAME_LANGSMITH_HUB` | Your Hub handle; forms `handle/bug_to_user_story_v2` |
| `LLM_PROVIDER` | `openai` or `google` |
| `LLM_MODEL` | The model that **generates** the User Stories |
| `EVAL_MODEL` | The model that **judges** the answers |
| `OPENAI_API_KEY` / `GOOGLE_API_KEY` | Key for the provider you picked |

Two configurations that work:

```bash
# OpenAI — tracks the ground truth more closely, costs a few dollars per run
LLM_PROVIDER=openai
LLM_MODEL=gpt-4o-mini
EVAL_MODEL=gpt-4o

# Gemini — free, but capped at 15 req/min
LLM_PROVIDER=google
LLM_MODEL=gemini-2.5-flash
EVAL_MODEL=gemini-2.5-flash
```

Every evaluation run makes **60 API calls**: 15 generations + 45 judgements (3 per
example). On Gemini's free tier, expect the run to take several minutes.

---

## Commands

Run everything from the repository root.

### Pull — fetch the prompt from the Hub

```bash
python src/pull_prompts.py
```

Fetches `leonanluppi/bug_to_user_story_v1` from the Hub and writes
`prompts/bug_to_user_story_v1.yml`, splitting `system_prompt` from `user_prompt` and
recording the source commit. Only needed to rebuild the starting point.

### Push — publish the optimized prompt

```bash
python src/push_prompts.py
```

Reads `prompts/bug_to_user_story_v2.yml`, validates it, and publishes it as
`$USERNAME_LANGSMITH_HUB/bug_to_user_story_v2` — **public**, with a description, tags,
and a README listing the techniques applied. Running it again creates a new version of
the same prompt.

Validation runs before the upload and blocks the push when:

- `description`, `system_prompt` or `version` is missing
- a stray `[TODO]` is left in the text
- fewer than 2 techniques are listed in `techniques_applied`
- the template does not expose exactly the `{bug_report}` variable (which would break evaluation)

### Evaluate — score the prompt

```bash
python src/evaluate.py
```

Creates (or reuses) the dataset in LangSmith, **pulls the prompt from the Hub** — not
from the local file, which is why you push first — runs all 15 examples and prints the
scores.

> Edited the YAML? Push before evaluating, or you are measuring the previous version.

### Tests

```bash
pytest tests/test_prompts.py
```

Structural validation of the YAML: system prompt present, persona defined, output
format required, few-shot examples present, no leftover `[TODO]`, and at least two
declared techniques. These tests are still skeletons and need to be implemented.

### Full loop

```bash
python src/push_prompts.py && python src/evaluate.py
```

---

## How the evaluation works

Three independent judges (`src/metrics.py`), all comparing the generated answer against
the dataset's ground truth:

| Metric | What it measures |
| --- | --- |
| **F1-Score** | Harmonic mean of precision (what was said is correct) and recall (what the reference asked for was said) |
| **Clarity** | Structure, language, absence of ambiguity, conciseness |
| **Precision** | No hallucination, stays on topic, factually correct |

Plus two derived by arithmetic, with no extra call:

```
Helpfulness = (Clarity + Precision) / 2
Correctness = (F1 + Precision) / 2
```

**Passing requires all 5 metrics >= 0.8** — the average alone is not enough.

The practical consequence that matters most: because every score is relative to the
reference, writing too little hurts recall and writing too much hurts precision. The
right response length depends on the bug — the references range from ~400 characters
(simple bug) to ~5,700 (complex bug).

---

## Prompt engineering techniques applied in v2

**Exactly three techniques are used.** They are declared in the YAML itself, under
`techniques_applied`, and published as metadata on the Hub:

```yaml
techniques_applied:
  - Role Prompting
  - Chain of Thought (CoT)
  - Few-shot Learning
```

| # | Technique | Where it lives in the YAML |
| --- | --- | --- |
| 1 | **Role Prompting** | `# PAPEL` |
| 2 | **Chain of Thought (CoT)** | `# RACIOCÍNIO PASSO A PASSO (INTERNO)` |
| 3 | **Few-shot Learning** | `# EXEMPLOS` (7 examples) |

### 1. Role Prompting

A detailed persona instead of the v1's generic "assistant": a senior Product Manager on
an agile team. The persona carries whole conventions — backlog vocabulary,
business-value focus, testable criteria — without having to enumerate them, and sets the
register the metrics reward: professional without being overly technical.

```yaml
Você é um Product Manager sênior, com mais de 10 anos de experiência em times
ágeis (Scrum/Kanban) de produtos digitais. Sua especialidade é traduzir relatos
de bugs — escritos por usuários, suporte ou QA — em User Stories acionáveis, que
desenvolvedores conseguem implementar e QA consegue testar sem precisar de
reuniões de esclarecimento.
```

### 2. Chain of Thought (CoT)

Nine reasoning steps the model runs before writing: classify complexity, identify the
persona, turn the defect into expected behaviour, extract the business value, inventory
the facts and set numeric targets, diagnose the root cause, walk the coverage checklist,
pick the output format, and self-check the result.

```yaml
# RACIOCÍNIO PASSO A PASSO (INTERNO)

Antes de escrever, pense passo a passo, executando mentalmente as etapas abaixo:
```

The reasoning is deliberately **silent** — the steps must not appear in the output:

```yaml
IMPORTANTE: esse raciocínio é interno. NUNCA escreva as etapas, títulos como
"Etapa 1", análises preliminares ou comentários sobre o seu processo. A resposta
final contém apenas a User Story.
```

That is not a detail: Clarity penalises redundancy and Precision penalises "information
not asked for", so visible reasoning would cost points. The benefit of CoT comes from
running it, not from showing it.

### 3. Few-shot Learning

Seven complete input → output pairs, covering every tier and every block type:

| Example | Tier | What it demonstrates |
| --- | --- | --- |
| 1, 2, 3 | Simple | Story + exactly 5 acceptance criteria, nothing else |
| 4 | Medium | Complementary block of type `Critérios Técnicos` |
| 5 | Medium | Complementary block of type `Critérios Adicionais para Admins` |
| 6 | Medium | Complementary block of type `Exemplo de Cálculo` |
| 7 | Complex | Full `=== ... ===` structure with technical depth |

All seven are **original**. None of the 15 evaluation examples was copied into the
prompt — using the test set as few-shot examples would contaminate the evaluation.

### Structural reinforcements (not named techniques)

Everything else in the prompt supports the three techniques above rather than adding a
fourth:

- **Calibration by complexity** (`# CALIBRAÇÃO POR COMPLEXIDADE`) — distinct format,
  item counts and prohibitions for simple, medium and complex bugs. Highest-impact
  single piece.
- **12 explicit rules** (`# REGRAS OBRIGATÓRIAS`) — language, no preamble, persona
  specificity, never invent facts, preserve technical values, positive phrasing.
- **Coverage checklist** (`# COBERTURA OBRIGATÓRIA`) and **criteria vocabulary**
  (`# VOCABULÁRIO DE CRITÉRIOS`) — recurring acceptance criteria worth including.
- **Catalogue of technical solutions** (`# CATÁLOGO DE SOLUÇÕES TÉCNICAS`) — standard
  fixes per root cause (index, pagination, `SELECT FOR UPDATE`, retry with backoff).
- **Edge cases** (`# CASOS DE BORDA`) — vague reports, non-bugs, contradictory input.
- **System vs User split** — the system prompt carries role, reasoning, rules and
  examples; the user prompt carries only the delimited `{bug_report}` and the
  classification reminder. In v1 the report was duplicated in both.

---

## Results

| Metric | v1 (low quality) | v2 first version | v2 current |
| --- | --- | --- | --- |
| Helpfulness | 0.45 | 0.84 ✓ | 0.86 |
| Correctness | 0.52 | 0.79 ✗ | 0.83 |
| F1-Score | 0.48 | 0.77 ✗ | 0.83 |
| Clarity | 0.50 | 0.87 ✓ | 0.88 |
| Precision | 0.46 | 0.82 ✓ | 0.84 |

The v1 and "v2 first version" columns are runs of `src/evaluate.py`. The "v2 current"
column is a local measurement using the same models and the same judge functions, still
**pending confirmation** by an official run.

Worth noting: the evaluation varies by roughly ±0.03 on F1 between runs, since both
generation and judging are stochastic. The same prompt has measured 0.79 and 0.83 on
different rounds.

Public LangSmith dashboard: _to be filled in after the official run_

---

## References

- [LangSmith Documentation](https://docs.smith.langchain.com/)
- [Prompt Engineering Guide](https://www.promptingguide.ai/)
