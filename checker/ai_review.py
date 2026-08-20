"""AI narrative review of a lesson episode's writing and pedagogy.

The mechanical checks in lesson_check.py already catch structural problems
(missing blocks, bad headings, broken links) deterministically and for free.
This module is for the qualitative pass an LLM is actually good at: does the
episode read well, are the objectives genuinely SMART, do the challenges
actually assess them with diagnostic power, is the pacing/difficulty right
for the stated audience. The review criteria and retrieval context both come
from the Carpentries style guide, the Collaborative Lesson Development
Training guidance, and The Carpentries Lab's own reviewer checklist --
retrieval is embedded locally with Ollama regardless of which backend
answers the question, since embeddings are cheap and fast to run on-device.

Three backends:
  ollama  -- fully local, via a pulled Ollama model (see README for picks
             sized for a 16GB Mac).
  claude  -- Anthropic API (`pip install anthropic`, ANTHROPIC_API_KEY or an
             `ant auth login` profile).
  codex   -- shells out to the OpenAI Codex CLI (`codex exec`), using
             whatever model/auth is already configured for that CLI.
"""

from __future__ import annotations

import os
import subprocess

os.environ.setdefault("USER_AGENT", "imls-tools-lesson-checker/0.2")

from langchain_chroma import Chroma
from langchain_community.document_loaders import WebBaseLoader
from langchain_ollama import OllamaEmbeddings
from langchain_text_splitters import CharacterTextSplitter

from checker.report import Finding

REFERENCE_URLS = [
    "https://carpentries.github.io/sandpaper-docs/instructor/style.html",
    "https://carpentries.github.io/sandpaper-docs/episodes.html",
    # Collaborative Lesson Development Training: backward design, SMART
    # objectives, formative assessment cadence, scope management, accessibility.
    # Retrieval is fine for this one -- it's long, and we only want the parts
    # relevant to a given episode (elaboration/examples), not the whole thing
    # verbatim in every prompt.
    "https://carpentries.github.io/lesson-development-training/aio.html",
]

# The Carpentries Lab's actual lesson-reviewer checklist -- the rubric a human
# reviewer grades against. This is pinned directly into every prompt rather
# than left to retrieval: it's short, and a rubric that might or might not
# surface depending on chunk similarity isn't a rubric the review can be held
# to. Retrieval above is for elaboration/examples; this is the actual grading
# criteria. Verbatim from https://github.com/carpentries-lab/reviews/blob/main/docs/reviewer_guide.md
LAB_CHECKLIST = """\
Accessibility:
- The alternative text of all figures is accurate and sufficiently detailed
- The lesson content does not make extensive use of colloquialisms, region- or \
culture-specific references, or idioms
- The lesson content does not make extensive use of contractions

Content:
- Meets the objectives defined by the authors
- Is appropriate for the target audience identified for the lesson
- Is accurate, descriptive, and easy to understand
- Is appropriately structured to manage cognitive load
- Does not use dismissive language
- The solutions to all exercises are accurate and sufficiently explained
- The lesson includes exercises in a variety of formats
- Exercise tasks and formats are appropriate for the expected experience level
- All lesson and episode objectives are assessed by exercises or another \
opportunity for formative assessment
- Exercises are designed with diagnostic power

Design:
- Learning objectives for the lesson and its episodes are clear, descriptive, \
and measurable
- The target audience identified for the lesson is specific and realistic

Supporting Information:
- The list of required prior skills and/or knowledge is complete and accurate
- The setup and installation instructions are complete, accurate, and easy to follow
- No key terms are missing from the lesson glossary
"""

EMBED_MODEL = "nomic-embed-text"

DEFAULT_MODELS = {
    "ollama": "qwen3.5:9b-q4_K_M",
    "claude": "claude-opus-5",
    "codex": None,  # None = let the codex CLI use its own configured default
}

_RETRIEVER_CACHE: dict[str, object] = {}


def _get_retriever(embed_model: str):
    if embed_model not in _RETRIEVER_CACHE:
        docs = [WebBaseLoader(url).load() for url in REFERENCE_URLS]
        docs_list = [doc for sub in docs for doc in sub]
        splitter = CharacterTextSplitter.from_tiktoken_encoder(chunk_size=1200, chunk_overlap=100)
        chunks = splitter.split_documents(docs_list)
        vectorstore = Chroma.from_documents(
            documents=chunks,
            collection_name="imls-tools-style-guide",
            embedding=OllamaEmbeddings(model=embed_model),
        )
        _RETRIEVER_CACHE[embed_model] = vectorstore.as_retriever()
    return _RETRIEVER_CACHE[embed_model]


def _style_context(episode_text: str, embed_model: str) -> str:
    retriever = _get_retriever(embed_model)
    query = episode_text[:2000]
    docs = retriever.invoke(query)
    return "\n\n---\n\n".join(d.page_content for d in docs)


def _build_prompt(episode_text: str, findings: list[Finding], style_context: str) -> str:
    mechanical_summary = (
        "\n".join(
            f"- [{f.severity}] {f.category}: {f.message}" for f in findings if f.location
        )
        or "(none -- the episode passed all mechanical structure checks)"
    )
    return f"""You are reviewing a Carpentries Workbench lesson episode the way a human
reviewer for The Carpentries Lab would.

The Carpentries Lab reviewer checklist -- grade against this directly, it is
the actual rubric, not just background reading:
{LAB_CHECKLIST}

Supporting guidance (style guide + Collaborative Lesson Development Training,
retrieved for relevance to this episode -- use for elaboration and examples,
the checklist above is the grading criteria):
{style_context}

Mechanical structure issues already found by an automated checker (do not
repeat these -- focus on what a checker can't catch):
{mechanical_summary}

One of the mechanical checks flags objectives that *open* with a vague verb
(know/understand/appreciate/...) as a cheap heuristic. Do not treat that as
your own standard: a verb not matching that denylist does not make an
objective assessable, and a verb matching it does not make it unassessable
("recognize" and "distinguish" can both be perfectly observable with the
right exercise, "explain" can still be vague without one). Judge each
objective by whether attainment is actually observable given what the
episode assesses -- and if nothing does, say so, since that is the more
useful finding than quibbling over the opening word.

Episode text:
---
{episode_text}
---

Give a short narrative review (bulleted is fine), grading against the
checklist above:
1. Learning objectives: are they specific and measurable, genuinely
   observable/assessable given what the episode actually tests?
2. Formative assessment: do challenges/exercises actually test each
   objective, with enough variety and diagnostic power to catch
   misconceptions -- not just "type this command and see what happens"?
3. Audience fit: is exercise difficulty and pacing appropriate for the
   stated target audience, and is content free of unstated
   expert-assumptions or sudden difficulty jumps?
4. Scope and cognitive load: is this episode trying to cover too much, or
   is content well-sequenced with worked examples before exercises?
5. Tone: dismissive language ("simply", "just"), unstated assumptions, or
   unexplained jargon that would trip up a learner encountering this fresh.
Keep it concrete -- point at specific lines or phrases, don't just restate
the checklist above."""


def _check_with_ollama(prompt: str, model: str) -> str:
    from langchain_ollama import ChatOllama

    llm = ChatOllama(model=model)
    return llm.invoke(prompt).content


def _check_with_claude(prompt: str, model: str) -> str:
    import anthropic

    client = anthropic.Anthropic()
    kwargs = {}
    # `effort` isn't accepted by every model (e.g. Haiku) -- only current-gen
    # Opus/Sonnet reliably support it, and this is intelligence-sensitive work
    # (judging pedagogy and style), so ask for more of it where we can.
    if "opus" in model or "sonnet" in model:
        kwargs["output_config"] = {"effort": "high"}
    response = client.messages.create(
        model=model,
        max_tokens=4096,
        messages=[{"role": "user", "content": prompt}],
        **kwargs,
    )
    return "".join(block.text for block in response.content if block.type == "text")


CODEX_TIMEOUT_SECONDS = 300


def _check_with_codex(prompt: str, model: str | None) -> str:
    cmd = ["codex", "exec", "--skip-git-repo-check"]
    if model:
        cmd += ["-m", model]
    cmd.append(prompt)
    try:
        # codex exec has been known to block on stdin even with a prompt passed
        # as an argument (https://github.com/openai/codex/issues/20919), so
        # close stdin explicitly and bound the wait.
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            stdin=subprocess.DEVNULL,
            timeout=CODEX_TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError(
            f"codex exec did not finish within {CODEX_TIMEOUT_SECONDS}s -- "
            "check `codex login` / network access, then retry"
        ) from exc
    if result.returncode != 0:
        detail = result.stderr.strip() or result.stdout.strip() or "(no output -- check `codex exec \"hello\"` runs standalone)"
        raise RuntimeError(f"codex exec failed ({result.returncode}): {detail}")
    return result.stdout.strip()


BACKENDS = {
    "ollama": _check_with_ollama,
    "claude": _check_with_claude,
    "codex": _check_with_codex,
}


def review_episode(
    episode_text: str,
    findings: list[Finding],
    backend: str,
    model: str | None,
    embed_model: str = EMBED_MODEL,
) -> str:
    if backend not in BACKENDS:
        raise ValueError(f"unknown backend `{backend}`, expected one of {sorted(BACKENDS)}")
    resolved_model = model or DEFAULT_MODELS[backend]
    style_context = _style_context(episode_text, embed_model)
    prompt = _build_prompt(episode_text, findings, style_context)
    return BACKENDS[backend](prompt, resolved_model)
