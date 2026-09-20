"""Build the print-ready one-page SchemaBridge approach brief with macOS textutil.

The generator uses only Python's standard library plus macOS' built-in document
converter, so it is deliberately isolated from the FastAPI runtime dependencies.
"""

from __future__ import annotations

import subprocess
import tempfile
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUTPUT = ROOT / "docs" / "deliverables" / "SchemaBridge_Approach_Brief.docx"

SECTIONS = (
    (
        "Approach",
        "SchemaBridge turns inconsistent CSV and Excel exports into records for a declared target "
        "schema through an explicit workflow: ingest and profile, map, conservatively reconcile, "
        "apply only meaning-preserving cleanup, validate, deliver, and preserve an audit trail. A "
        "clean export proceeds without a review stop; a messy one produces a small queue with source "
        "evidence rather than a hidden guess.",
    ),
    (
        "Autonomy boundary",
        "The agent works alone when a shipped or approved schema-scoped rule matches without "
        "contention, deterministic policy can make a safe transformation, or a model proposal passes "
        "independent target, occupancy, and type-compatibility checks. It escalates competing "
        "interpretations, identity conflicts, missing required values, ambiguous dates, unsafe cleanup, "
        "and records that remain invalid after one bounded repair pass. The model is never an execution "
        "authority: it cannot rewrite rows freely, invent facts, bypass validation, or call the target API.",
    ),
    (
        "Engineering beyond the model",
        "MongoDB-backed LangGraph checkpoints make human review durable across serverless requests; "
        "corrections are reprocessed instead of trusted blindly. Audit events distinguish system, rule, "
        "model-assisted, and reviewer actions. Delivery uses bounded HTTP retry with stable idempotency "
        "keys, giving at-least-once transport with idempotent target effects rather than an unrealistic "
        "exactly-once claim. Inputs, repairs, model calls, and provider throughput are all bounded.",
    ),
    (
        "Learning, cost, and next steps",
        "A reviewed decision or verified mapping can produce a proposed rule. A person must approve it; "
        "the saved rule is previewable, schema-scoped, provenance-carrying, and helps future runs without "
        "altering an active run's snapshot. This is selective LLM use: deterministic policy and approved "
        "rules remove repeated work, while the model is reserved for genuine semantic uncertainty and rule "
        "drafting. Next, I would add background execution, production data controls, real destination "
        "connectors, larger-workload handling, and systematic mapping-quality evaluation.",
    ),
)


def _rtf_escape(value: str) -> str:
    """Encode plain text safely for an ANSI RTF stream."""
    pieces: list[str] = []
    for char in value:
        if char in {"\\", "{", "}"}:
            pieces.append(f"\\{char}")
        elif ord(char) > 127:
            signed = ord(char) if ord(char) < 32768 else ord(char) - 65536
            pieces.append(f"\\u{signed}?")
        else:
            pieces.append(char)
    return "".join(pieces)


def _rtf() -> str:
    """Return compact, A4-sized RTF that converts to a normal DOCX page."""
    parts = [
        r"{\rtf1\ansi\deff0{\fonttbl{\f0 Aptos;}{\f1 Aptos Display;}}",
        r"\paperw11907\paperh16840\margl822\margr822\margt765\margb765",
        r"\pard\qc\sa40\f1\fs28\b\cf1 ",
        _rtf_escape("SchemaBridge — Approach and decision boundary"),
        r"\par\pard\qc\sa100\f0\fs17\i One-page technical brief\i0\par",
    ]
    for heading, body in SECTIONS:
        parts.extend(
            (
                r"\pard\sa20\sb80\keepn\f1\fs20\b\cf1 ",
                _rtf_escape(heading),
                r"\par\pard\sa35\f0\fs18\b0\cf0 ",
                _rtf_escape(body),
                r"\par",
            )
        )
    parts.append("}")
    return "".join(parts)


def _validate_docx(path: Path) -> None:
    """Check the OOXML package and its core content without a third-party reader."""
    with zipfile.ZipFile(path) as archive:
        broken = archive.testzip()
        if broken is not None:
            raise RuntimeError(f"Broken DOCX member: {broken}")
        document_xml = archive.read("word/document.xml").decode("utf-8")
    for heading, _ in SECTIONS:
        if heading not in document_xml:
            raise RuntimeError(f"Generated DOCX is missing section: {heading}")


def build() -> Path:
    """Convert the compact RTF source to the requested DOCX deliverable."""
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="schemabridge-docx-") as directory:
        rtf_path = Path(directory) / "SchemaBridge_Approach_Brief.rtf"
        rtf_path.write_text(_rtf(), encoding="ascii")
        subprocess.run(
            ["textutil", "-convert", "docx", "-output", str(OUTPUT), str(rtf_path)],
            check=True,
        )
    _validate_docx(OUTPUT)
    return OUTPUT


if __name__ == "__main__":
    print(build())
