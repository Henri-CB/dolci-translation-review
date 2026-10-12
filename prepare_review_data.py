#!/usr/bin/env python3
"""Prepare privacy-minimized static JSON for a Dolci-Think GitHub Pages viewer.

Input: reconstructed_samples.json from translate_prechunked_mn5.py.
Optional: manifest.json + translated_chunks.jsonl for truncation warnings.
Only reconstructed conversation text and limited metadata are exported. Absolute
cluster paths, full prompts, checkpoint raw outputs and HF-cache details are not.
No external Python packages are required.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any


def load_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise ValueError(f"Could not read JSON at {path}: {exc}") from exc


def text_field(row: dict, key: str) -> str:
    value = row.get(key, "")
    if value is None:
        return ""
    if not isinstance(value, str):
        raise ValueError(f"Expected string for {key}, received {type(value).__name__}")
    return value


def decode_message(msg: dict) -> dict:
    if not isinstance(msg, dict):
        raise ValueError("Each reconstructed message must be an object")
    think = text_field(msg, "think")
    main = text_field(msg, "main")
    if not think and not main and isinstance(msg.get("content"), str):
        main = msg["content"]
    return {"think": think, "main": main}


def read_chunk_status(path: Path | None) -> dict[str, str]:
    if path is None:
        return {}
    statuses = {}
    with path.open(encoding="utf-8") as handle:
        for lineno, line in enumerate(handle, 1):
            if not line.strip():
                continue
            try:
                entry = json.loads(line)
                chunk_id = str(entry["chunk_id"])
            except (KeyError, ValueError, TypeError) as exc:
                raise ValueError(f"Bad chunk record {path}:{lineno}") from exc
            if chunk_id in statuses:
                raise ValueError(f"Duplicate translated chunk ID: {chunk_id}")
            statuses[chunk_id] = str(entry.get("finish_reason", "unknown"))
    return statuses


def convert(source: list[dict], *, manifest: dict | None = None,
            chunk_status: dict[str, str] | None = None,
            dataset_label: str = "Dolci-Think · Gemma 4 · European Portuguese") -> dict:
    if not isinstance(source, list):
        raise ValueError("Expected top-level list from reconstructed_samples.json")
    if not source:
        raise ValueError("No samples found in reconstructed_samples.json")
    selected = (manifest or {}).get("selected", [])
    chunk_status = chunk_status or {}
    output = []
    ids = set()
    for i, row in enumerate(source):
        if not isinstance(row, dict):
            raise ValueError(f"Sample {i+1} must be an object")
        original = row.get("original_messages")
        translated = row.get("translated_messages")
        if not isinstance(original, list) or not isinstance(translated, list) or len(original) != len(translated):
            raise ValueError(f"Sample {i+1}: original_messages and translated_messages must be matching lists")
        if not original:
            raise ValueError(f"Sample {i+1} has no messages")
        source_id = str(row.get("original_id") or f"sample-{i+1}")
        if source_id in ids:
            raise ValueError(f"Duplicate original_id in source: {source_id}")
        ids.add(source_id)
        turns = []
        for j, (a, b) in enumerate(zip(original, translated)):
            if not isinstance(a, dict) or not isinstance(b, dict):
                raise ValueError(f"Sample {i+1}, turn {j+1}: expected objects")
            role_a = str(a.get("role", "unknown"))
            role_b = str(b.get("role", "unknown"))
            if role_a != role_b:
                raise ValueError(f"Sample {i+1}, turn {j+1}: roles differ: {role_a} / {role_b}")
            turns.append({"role": role_a, "original": decode_message(a), "translated": decode_message(b)})
        manifest_entry = selected[i] if i < len(selected) else {}
        if manifest_entry and str(manifest_entry.get("original_id")) != source_id:
            raise ValueError(f"Manifest sample #{i+1} does not correspond to {source_id}")
        chunk_ids = manifest_entry.get("chunk_ids", []) if manifest_entry else []
        if not isinstance(chunk_ids, list):
            raise ValueError(f"Manifest sample #{i+1} has invalid chunk_ids")
        truncated = [str(cid) for cid in chunk_ids if chunk_status.get(str(cid)) == "length"]
        sample = {
            "id": source_id,
            "number": i + 1,
            "messages": turns,
            "chunkCount": len(chunk_ids) if manifest_entry else None,
            "truncatedChunkCount": len(truncated) if manifest_entry and chunk_status else None,
        }
        output.append(sample)
    canonical = json.dumps(output, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return {
        "schemaVersion": 1,
        "datasetId": hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:20],
        "datasetLabel": dataset_label,
        "sourceLanguage": "English",
        "targetLanguage": "Português (Portugal)",
        "samples": output,
    }


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--input", type=Path, required=True,
                   help="MN5 reconstructed_samples.json")
    p.add_argument("--output", type=Path, default=Path("data/samples.json"))
    p.add_argument("--manifest", type=Path, default=None,
                   help="Optional MN5 manifest.json, used only for chunk counts")
    p.add_argument("--chunks", type=Path, default=None,
                   help="Optional translated_chunks.jsonl, used only for truncation counts")
    p.add_argument("--label", default="Dolci-Think · Gemma 4 · European Portuguese")
    args = p.parse_args()
    if args.chunks and not args.manifest:
        p.error("--chunks requires --manifest to associate chunks with each sample")
    data = convert(load_json(args.input),
                   manifest=load_json(args.manifest) if args.manifest else None,
                   chunk_status=read_chunk_status(args.chunks),
                   dataset_label=args.label)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {len(data['samples'])} samples to {args.output}")
    print(f"Dataset ID: {data['datasetId']}")
    print("Only reconstructed messages and limited chunk statistics were included.")
    print("WARNING: These texts become PUBLIC if you commit them to GitHub Pages.")


if __name__ == "__main__":
    main()
