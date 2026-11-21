import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import check_base_image

DIGEST = "sha256:" + "a" * 64


class PinnedReferenceTest(unittest.TestCase):
    def reference(self, dockerfile_text):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "Dockerfile"
            path.write_text(dockerfile_text, encoding="utf-8")
            with mock.patch.object(check_base_image, "DOCKERFILE", path):
                return check_base_image.pinned_reference()

    def test_reads_a_written_out_reference(self):
        image, digest = self.reference(
            f"FROM python:3.14-alpine3.24@{DIGEST} AS base\n"
        )
        self.assertEqual(image, "python:3.14-alpine3.24")
        self.assertEqual(digest, DIGEST)

    def test_rejects_a_reference_built_from_args(self):
        with self.assertRaisesRegex(check_base_image.CheckError, "written out"):
            self.reference(
                "ARG PYTHON_VERSION=3.14\n"
                f"FROM python:${{PYTHON_VERSION}}-alpine3.24@{DIGEST} AS base\n"
            )

    def test_rejects_a_reference_without_a_tag(self):
        with self.assertRaisesRegex(check_base_image.CheckError, "written out"):
            self.reference(f"FROM python@{DIGEST} AS base\n")

    def test_fails_when_there_is_no_pinned_base_stage(self):
        with self.assertRaisesRegex(check_base_image.CheckError, "AS base"):
            self.reference("FROM python:3.14-alpine3.24 AS base\n")


if __name__ == "__main__":
    unittest.main()
