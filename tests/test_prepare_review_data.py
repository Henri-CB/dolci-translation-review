import json
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from prepare_review_data import convert, read_chunk_status


def fake_input():
    return [
        {"sample_number": 1, "original_id": "example_0101",
         "dataset_source": "private_source", "shard_template": "/gpfs/private/shard_0_template.json",
         "shard_row": 22,
         "original_messages": [
             {"role": "user", "think": "", "main": "What is 2 + 2?", "content": "What is 2 + 2?"},
             {"role": "assistant", "think": "I should add 2 to 2.", "main": "It is four.",
              "content": "<think> I should add 2 to 2. </think> It is four."}],
         "translated_messages": [
             {"role": "user", "think": "", "main": "Quanto é 2 + 2?"},
             {"role": "assistant", "think": "Devo somar dois a dois.", "main": "São quatro."}]},
        {"sample_number": 2, "original_id": "example_0102",
         "original_messages": [{"role": "user", "think": "", "main": "Hello"}],
         "translated_messages": [{"role": "user", "think": "", "main": "Olá"}]}
    ]


class ConverterTests(unittest.TestCase):
    def test_maps_real_mn5_fields(self):
        data = convert(fake_input())
        self.assertEqual(len(data["samples"]), 2)
        self.assertEqual(data["samples"][0]["messages"][1]["original"]["think"], "I should add 2 to 2.")
        self.assertEqual(data["samples"][0]["messages"][1]["translated"]["main"], "São quatro.")
        self.assertEqual(data["samples"][0]["chunkCount"], None)
        s = json.dumps(data, ensure_ascii=False)
        self.assertNotIn("/gpfs", s)
        self.assertNotIn("private_source", s)
        self.assertNotIn("shard_row", s)

    def test_checks_counts_and_flags(self):
        manifest = {"selected": [
            {"original_id": "example_0101", "chunk_ids": ["c1", "c2"]},
            {"original_id": "example_0102", "chunk_ids": ["c3"]}
        ]}
        data = convert(fake_input(), manifest=manifest, chunk_status={"c1": "stop", "c2": "length", "c3": "stop"})
        self.assertEqual(data["samples"][0]["chunkCount"], 2)
        self.assertEqual(data["samples"][0]["truncatedChunkCount"], 1)
        self.assertEqual(data["samples"][1]["truncatedChunkCount"], 0)
        with self.assertRaisesRegex(ValueError, "does not correspond"):
            convert(fake_input(), manifest={"selected": [{"original_id": "not_the_same", "chunk_ids": []}]})

    def test_rejects_mismatch(self):
        samples = fake_input()
        samples[0]["translated_messages"] = []
        with self.assertRaisesRegex(ValueError, "matching lists"):
            convert(samples)
        samples = fake_input()
        samples[1]["original_id"] = samples[0]["original_id"]
        with self.assertRaisesRegex(ValueError, "Duplicate"):
            convert(samples)

    def test_stable_fingerprint_and_change_isolation(self):
        data1 = convert(fake_input())
        data2 = convert(fake_input())
        self.assertEqual(data1["datasetId"], data2["datasetId"])
        changed = fake_input()
        changed[0]["translated_messages"][1]["main"] = "São cinco."
        self.assertNotEqual(data1["datasetId"], convert(changed)["datasetId"])

    def test_status_jsonl(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td)/"chunks.jsonl"
            path.write_text('{"chunk_id":"c1","finish_reason":"length"}\n')
            self.assertEqual(read_chunk_status(path)["c1"], "length")



if __name__ == "__main__":
    unittest.main()
