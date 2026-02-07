"""Integration tests for SelfAssembler.

These tests use real git repos (via tmp_path) and real subprocess calls.
No mocking — verifies actual behavior end-to-end.

Run with:
    python3 -m pytest tests/test_integration.py -v
    python3 -m pytest tests/test_integration.py -v -m integration
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

from selfassembler.git import GitManager


pytestmark = pytest.mark.integration


# ── Helpers ──────────────────────────────────────────────────────────────


def make_repo(path: Path) -> Path:
    """Create a minimal git repo with one commit."""
    path.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "init", "-q"], cwd=path, check=True)
    subprocess.run(["git", "config", "user.name", "IntegTest"], cwd=path, check=True)
    subprocess.run(["git", "config", "user.email", "integ@test.local"], cwd=path, check=True)
    (path / "README.md").write_text("# test\n")
    subprocess.run(["git", "add", "."], cwd=path, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "init"], cwd=path, check=True)
    return path


# ── Git Identity Tests ───────────────────────────────────────────────────


class TestGitIdentityIntegration:
    """Tests for ensure_identity() against real git repos."""

    def test_reads_local_git_config(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """ensure_identity() reads real repo-local config."""
        repo = make_repo(tmp_path / "repo")
        # Clear env vars so git config is the source
        for var in ("GIT_AUTHOR_NAME", "GIT_AUTHOR_EMAIL",
                     "GIT_COMMITTER_NAME", "GIT_COMMITTER_EMAIL"):
            monkeypatch.delenv(var, raising=False)

        gm = GitManager(repo)
        identity = gm.ensure_identity()

        assert identity["name"] == "IntegTest"
        assert identity["email"] == "integ@test.local"
        assert identity["source"] == "git-config"

    def test_env_vars_take_priority(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """GIT_AUTHOR_* env vars override repo config."""
        repo = make_repo(tmp_path / "repo")
        monkeypatch.setenv("GIT_AUTHOR_NAME", "EnvName")
        monkeypatch.setenv("GIT_AUTHOR_EMAIL", "env@test.local")

        gm = GitManager(repo)
        identity = gm.ensure_identity()

        assert identity["name"] == "EnvName"
        assert identity["email"] == "env@test.local"
        assert identity["source"] == "env"

    def test_fallback_when_no_config(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """Falls back to SelfAssembler/localhost when nothing is configured."""
        repo = tmp_path / "bare"
        repo.mkdir()
        subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
        # Remove any local config
        subprocess.run(["git", "config", "--unset", "user.name"], cwd=repo, check=False)
        subprocess.run(["git", "config", "--unset", "user.email"], cwd=repo, check=False)
        # Clear env vars and block ALL global config sources
        for var in ("GIT_AUTHOR_NAME", "GIT_AUTHOR_EMAIL",
                     "GIT_COMMITTER_NAME", "GIT_COMMITTER_EMAIL"):
            monkeypatch.delenv(var, raising=False)
        empty_home = tmp_path / "emptyhome"
        empty_home.mkdir()
        monkeypatch.setenv("GIT_CONFIG_NOSYSTEM", "1")
        monkeypatch.setenv("GIT_CONFIG_GLOBAL", "/dev/null")
        monkeypatch.setenv("XDG_CONFIG_HOME", str(empty_home))
        monkeypatch.setenv("HOME", str(empty_home))

        gm = GitManager(repo)
        identity = gm.ensure_identity()

        assert identity["source"] in ("fallback", "github-cli")
        if identity["source"] == "fallback":
            assert identity["name"] == "SelfAssembler"
            assert identity["email"] == "selfassembler@localhost"

    def test_exports_env_vars_for_subprocess(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Child processes see the exported env vars after ensure_identity()."""
        repo = make_repo(tmp_path / "repo")
        for var in ("GIT_AUTHOR_NAME", "GIT_AUTHOR_EMAIL",
                     "GIT_COMMITTER_NAME", "GIT_COMMITTER_EMAIL"):
            monkeypatch.delenv(var, raising=False)

        gm = GitManager(repo)
        gm.ensure_identity()

        # Spawn a child and check it sees the vars
        result = subprocess.run(
            ["python3", "-c", "import os; print(os.environ.get('GIT_AUTHOR_NAME', ''))"],
            capture_output=True, text=True,
        )
        assert result.stdout.strip() == "IntegTest"

    def test_commit_works_after_ensure_identity(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Real git commit succeeds with resolved identity."""
        repo = make_repo(tmp_path / "repo")
        for var in ("GIT_AUTHOR_NAME", "GIT_AUTHOR_EMAIL",
                     "GIT_COMMITTER_NAME", "GIT_COMMITTER_EMAIL"):
            monkeypatch.delenv(var, raising=False)

        gm = GitManager(repo)
        gm.ensure_identity()

        # Create a file and commit
        (repo / "new.txt").write_text("hello\n")
        gm.add_files(["new.txt"])
        commit_hash = gm.commit("integration test commit")

        assert len(commit_hash) >= 7
        log = gm.get_log(count=1)
        assert "integration test commit" in log[0]


# ── Preflight Phase Tests ────────────────────────────────────────────────


class TestPreflightIntegration:
    """Tests for PreflightPhase against real repos."""

    def _make_preflight(self, repo: Path):
        """Create a PreflightPhase with minimal mocked context/executor/config."""
        from unittest.mock import MagicMock

        from selfassembler.phases import PreflightPhase

        context = MagicMock()
        context.repo_path = repo
        executor = MagicMock()
        executor.check_available.return_value = (True, "1.0.0")
        executor.AGENT_TYPE = "claude"
        config = MagicMock()
        config.git.base_branch = "main"
        config.git.auto_update = False
        return PreflightPhase(context, executor, config)

    def test_preflight_passes_clean_repo(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """PreflightPhase.run() passes on a clean repo."""
        repo = make_repo(tmp_path / "repo")
        for var in ("GIT_AUTHOR_NAME", "GIT_AUTHOR_EMAIL",
                     "GIT_COMMITTER_NAME", "GIT_COMMITTER_EMAIL"):
            monkeypatch.delenv(var, raising=False)

        pf = self._make_preflight(repo)
        result = pf.run()
        assert result.success is True

    def test_preflight_detects_dirty_repo(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """PreflightPhase fails on a dirty repo."""
        repo = make_repo(tmp_path / "repo")
        for var in ("GIT_AUTHOR_NAME", "GIT_AUTHOR_EMAIL",
                     "GIT_COMMITTER_NAME", "GIT_COMMITTER_EMAIL"):
            monkeypatch.delenv(var, raising=False)
        # Dirty the repo
        (repo / "dirty.txt").write_text("uncommitted\n")

        pf = self._make_preflight(repo)
        result = pf.run()
        assert result.success is False
        assert "clean" in str(result.error).lower()

    def test_preflight_git_identity_check(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """_check_git_identity() returns passed on a configured repo."""
        repo = make_repo(tmp_path / "repo")
        for var in ("GIT_AUTHOR_NAME", "GIT_AUTHOR_EMAIL",
                     "GIT_COMMITTER_NAME", "GIT_COMMITTER_EMAIL"):
            monkeypatch.delenv(var, raising=False)

        pf = self._make_preflight(repo)
        check = pf._check_git_identity()
        assert check["passed"] is True
        assert check["name"] == "git_identity"


# ── Setup Phase Tests ────────────────────────────────────────────────────


class TestSetupIntegration:
    """Tests for SetupPhase worktree creation against real repos."""

    def test_setup_creates_worktree(self, tmp_path: Path) -> None:
        """SetupPhase creates a real git worktree."""
        repo = make_repo(tmp_path / "repo")
        # Also need a 'main' branch for base_branch
        subprocess.run(
            ["git", "branch", "-M", "main"], cwd=repo, check=True,
        )

        gm = GitManager(repo)
        worktree_dir = tmp_path / "worktrees"
        branch = gm.generate_branch_name("test-task")
        wt_path = gm.create_worktree(branch, worktree_dir, base_branch="main")

        assert wt_path.exists()
        assert (wt_path / ".git").exists()
        assert (wt_path / "README.md").exists()

        # Clean up
        gm.remove_worktree(wt_path, force=True)

    def test_setup_worktree_cleanup(self, tmp_path: Path) -> None:
        """Worktree removed cleanly via remove_worktree."""
        repo = make_repo(tmp_path / "repo")
        subprocess.run(
            ["git", "branch", "-M", "main"], cwd=repo, check=True,
        )

        gm = GitManager(repo)
        worktree_dir = tmp_path / "worktrees"
        branch = gm.generate_branch_name("cleanup-task")
        wt_path = gm.create_worktree(branch, worktree_dir, base_branch="main")

        assert wt_path.exists()
        gm.remove_worktree(wt_path, force=True)
        assert not wt_path.exists()


# ── CLI Tests ────────────────────────────────────────────────────────────


class TestCLIIntegration:
    """Tests for the selfassembler CLI via real subprocess calls."""

    def _run_cli(self, *args: str) -> subprocess.CompletedProcess:
        return subprocess.run(
            ["python3", "-m", "selfassembler.cli", *args],
            capture_output=True,
            text=True,
            timeout=30,
        )

    def test_cli_version(self) -> None:
        """selfassembler --version outputs a version string."""
        result = self._run_cli("--version")
        assert result.returncode == 0
        assert "selfassembler" in result.stdout.lower() or "0." in result.stdout

    def test_cli_dry_run(self, tmp_path: Path) -> None:
        """selfassembler --dry-run shows phases without executing."""
        repo = make_repo(tmp_path / "repo")
        result = subprocess.run(
            ["python3", "-m", "selfassembler.cli", "--dry-run", "test task", "--name", "test"],
            capture_output=True, text=True, timeout=30,
            cwd=repo,
        )
        assert result.returncode == 0, f"dry-run exited {result.returncode}: {result.stderr}"
        combined = result.stdout + result.stderr
        assert "phase" in combined.lower() or "preflight" in combined.lower(), (
            f"dry-run output missing phase info: {combined[:500]}"
        )

    def test_cli_help(self) -> None:
        """selfassembler --help prints usage."""
        result = self._run_cli("--help")
        assert result.returncode == 0
        assert "selfassembler" in result.stdout.lower()
        assert "task" in result.stdout.lower()

    def test_cli_list_phases(self) -> None:
        """selfassembler --list-phases lists all workflow phases."""
        result = self._run_cli("--list-phases")
        assert result.returncode == 0
        output = result.stdout.lower()
        assert "preflight" in output
        assert "setup" in output
        assert "implementation" in output
