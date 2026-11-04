import contextlib
import io
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import check_fixtures
import lint_dockerfiles


def git_repo(tracked, untracked=()):
    """A temporary git repository with `tracked` files committed to the index."""
    tmp = tempfile.TemporaryDirectory()
    root = Path(tmp.name)
    subprocess.run(["git", "init", "-q", str(root)], check=True)
    for name in (*tracked, *untracked):
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("FROM scratch\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(root), "add", *tracked], check=True)
    return tmp, root


class TrackedDockerfilesTest(unittest.TestCase):
    def test_tracked_dockerfiles_skips_fixtures(self):
        tmp, root = git_repo(
            [
                "Dockerfile",
                "Dockerfile.slim",
                "app/Dockerfile",
                "fixtures/dockerfiles/x/Dockerfile",
                "Dockerfile.dockerignore",
                "README.md",
            ],
            untracked=["Dockerfile.tmp"],
        )
        self.addCleanup(tmp.cleanup)
        self.assertEqual(
            [
                p.relative_to(root).as_posix()
                for p in lint_dockerfiles.tracked_dockerfiles(root)
            ],
            ["Dockerfile", "Dockerfile.slim", "app/Dockerfile"],
        )


class MainTest(unittest.TestCase):
    def setUp(self):
        tmp, self.root = git_repo(["Dockerfile"])
        self.addCleanup(tmp.cleanup)

    def run_main(self):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = lint_dockerfiles.main([], root=self.root)
        return code, out.getvalue(), err.getvalue()

    def patch_linters(self, hadolint=(), buildcheck=()):
        stack = contextlib.ExitStack()
        stack.enter_context(mock.patch.object(check_fixtures, "ensure_docker"))
        self.hadolint = stack.enter_context(
            mock.patch.object(
                check_fixtures, "hadolint_codes", return_value=set(hadolint)
            )
        )
        stack.enter_context(
            mock.patch.object(
                check_fixtures, "buildcheck_codes", return_value=set(buildcheck)
            )
        )
        self.addCleanup(stack.close)

    def test_main_reports_findings(self):
        self.patch_linters({"DL3008"}, {"JSONArgsRecommended"})
        code, _, err = self.run_main()
        self.assertEqual(code, 1)
        self.assertIn("Dockerfile: DL3008", err)
        self.assertIn("Dockerfile: JSONArgsRecommended", err)

    def test_main_passes_and_filters_hadolint_levels(self):
        self.patch_linters()
        code, out, _ = self.run_main()
        self.assertEqual(code, 0)
        self.assertIn("1 Dockerfiles pass", out)
        self.assertEqual(
            self.hadolint.call_args.kwargs["levels"], lint_dockerfiles.FAIL_LEVELS
        )

    def test_main_docker_unavailable_exits_2(self):
        with mock.patch.object(
            check_fixtures,
            "ensure_docker",
            side_effect=check_fixtures.DockerUnavailable("no daemon"),
        ):
            code, _, err = self.run_main()
        self.assertEqual(code, 2)
        self.assertIn("no daemon", err)

    def test_main_reports_linter_error_with_path(self):
        self.patch_linters()
        self.hadolint.side_effect = check_fixtures.LinterError(
            "Hadolint printed nothing"
        )
        code, _, err = self.run_main()
        self.assertEqual(code, 1)
        self.assertIn("Dockerfile: Hadolint printed nothing", err)

    def test_main_fails_without_dockerfiles(self):
        tmp, self.root = git_repo(["README.md"])
        self.addCleanup(tmp.cleanup)
        self.patch_linters()
        code, _, _ = self.run_main()
        self.assertEqual(code, 1)


if __name__ == "__main__":
    unittest.main()
