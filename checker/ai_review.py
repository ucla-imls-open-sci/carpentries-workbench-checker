"""AI narrative review of a lesson episode's writing and pedagogy.

The mechanical checks in lesson_check.py already catch structural problems
(missing blocks, bad headings, broken links) deterministically and for free.
This module is for the qualitative pass an LLM is actually good at: does the
episode read well, does it follow the Carpentries style guide, are the
challenges pedagogically sound. Retrieval context (the style guide + episode
structure docs) is embedded locally with Ollama regardless of which backend
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
]

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
    return f"""You are reviewing a Carpentries Workbench lesson episode for writing quality
and pedagogy, using the official Carpentries style guide as your reference.

Style guide excerpts (retrieved for relevance to this episode):
{style_context}

Mechanical structure issues already found by an automated checker (do not
repeat these -- focus on what a checker can't catch):
{mechanical_summary}

Episode text:
---
{episode_text}
---

Give a short narrative review (bulleted is fine) covering:
1. Whether the challenges are pedagogically well-formed (clear goal, appropriate difficulty).
2. Tone and clarity against the Carpentries style guide.
3. Anything confusing or under-explained for a learner encountering this material fresh.
Keep it concrete -- point at specific lines or phrases, don't just restate the checklist above."""


def _check_with_ollama(prompt: str, model: str) -> str:
    from langchain_ollama import ChatOllama

    llm = ChatOllama(model=model)
    return llm.invoke(prompt).content


def _check_with_claude(prompt: str, model: str) -> str:
    import anthropic

    client = anthropic.Anthropic()
    response = client.messages.create(
        model=model,
        max_tokens=4096,
        messages=[{"role": "user", "content": prompt}],
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
