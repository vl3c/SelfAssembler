"""Tests for GitManager."""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from selfassembler.errors import GitOperationError
from selfassembler.git import GitManager


class TestGitManagerInit:
    """Tests for GitManager initialization."""

    @patch("selfassembler.git.GitManager._validate_repo")
    def test_init_with_valid_repo(self, mock_validate):
        """Test initialization with valid repo path."""
        mock_validate.return_value = None

        manager = GitManager(Path("/test/repo"))

        assert manager.repo_path == Path("/test/repo")
        mock_validate.assert_called_once()

    def test_init_validates_repo(self):
        """Test that init validates the repository."""
        with pytest.raises(GitOperationError):
            GitManager(Path("/nonexistent/path"))


class TestGitManagerCheckout:
    """Tests for checkout method."""

    @patch("selfassembler.git.GitManager._validate_repo")
    @patch("selfassembler.git.GitManager._run")
    def test_checkout_branch(self, mock_run, mock_validate):
        """Test checking out a branch."""
        mock_run.return_value = MagicMock(returncode=0)

        manager = GitManager(Path("/test/repo"))
        manager.checkout("main")

        mock_run.assert_called_once_with(["checkout", "main"], cwd=None)

    @patch("selfassembler.git.GitManager._validate_repo")
    @patch("selfassembler.git.GitManager._run")
    def test_checkout_with_cwd(self, mock_run, mock_validate):
        """Test checking out with custom working directory."""
        mock_run.return_value = MagicMock(returncode=0)

        manager = GitManager(Path("/test/repo"))
        manager.checkout("feature", cwd=Path("/other/dir"))

        mock_run.assert_called_once_with(["checkout", "feature"], cwd=Path("/other/dir"))

    @patch("selfassembler.git.GitManager._validate_repo")
    @patch("selfassembler.git.GitManager._run")
    def test_checkout_failure(self, mock_run, mock_validate):
        """Test checkout failure raises error."""
        mock_run.side_effect = GitOperationError("checkout", "branch not found")

        manager = GitManager(Path("/test/repo"))

        with pytest.raises(GitOperationError):
            manager.checkout("nonexistent")


class TestGitManagerPull:
    """Tests for pull method."""

    @patch("selfassembler.git.GitManager._validate_repo")
    @patch("selfassembler.git.GitManager._run")
    def test_pull_default(self, mock_run, mock_validate):
        """Test pulling with defaults."""
        mock_run.return_value = MagicMock(returncode=0)

        manager = GitManager(Path("/test/repo"))
        manager.pull()

        mock_run.assert_called_once_with(["pull", "origin"])

    @patch("selfassembler.git.GitManager._validate_repo")
    @patch("selfassembler.git.GitManager._run")
    def test_pull_with_remote(self, mock_run, mock_validate):
        """Test pulling from specific remote."""
        mock_run.return_value = MagicMock(returncode=0)

        manager = GitManager(Path("/test/repo"))
        manager.pull(remote="upstream")

        mock_run.assert_called_once_with(["pull", "upstream"])

    @patch("selfassembler.git.GitManager._validate_repo")
    @patch("selfassembler.git.GitManager._run")
    def test_pull_with_branch(self, mock_run, mock_validate):
        """Test pulling specific branch."""
        mock_run.return_value = MagicMock(returncode=0)

        manager = GitManager(Path("/test/repo"))
        manager.pull(branch="main")

        mock_run.assert_called_once_with(["pull", "origin", "main"])

    @patch("selfassembler.git.GitManager._validate_repo")
    @patch("selfassembler.git.GitManager._run")
    def test_pull_with_remote_and_branch(self, mock_run, mock_validate):
        """Test pulling from specific remote and branch."""
        mock_run.return_value = MagicMock(returncode=0)

        manager = GitManager(Path("/test/repo"))
        manager.pull(remote="upstream", branch="develop")

        mock_run.assert_called_once_with(["pull", "upstream", "develop"])

    @patch("selfassembler.git.GitManager._validate_repo")
    @patch("selfassembler.git.GitManager._run")
    def test_pull_failure(self, mock_run, mock_validate):
        """Test pull failure raises error."""
        mock_run.side_effect = GitOperationError("pull", "merge conflict")

        manager = GitManager(Path("/test/repo"))

        with pytest.raises(GitOperationError):
            manager.pull()


class TestGitManagerGetCurrentBranch:
    """Tests for get_current_branch method."""

    @patch("selfassembler.git.GitManager._validate_repo")
    @patch("selfassembler.git.GitManager._run")
    def test_get_current_branch(self, mock_run, mock_validate):
        """Test getting current branch name."""
        mock_run.return_value = MagicMock(returncode=0, stdout="feature/my-branch\n")

        manager = GitManager(Path("/test/repo"))
        branch = manager.get_current_branch()

        assert branch == "feature/my-branch"
        mock_run.assert_called_once_with(["rev-parse", "--abbrev-ref", "HEAD"], cwd=None)

    @patch("selfassembler.git.GitManager._validate_repo")
    @patch("selfassembler.git.GitManager._run")
    def test_get_current_branch_with_cwd(self, mock_run, mock_validate):
        """Test getting current branch with custom cwd."""
        mock_run.return_value = MagicMock(returncode=0, stdout="main\n")

        manager = GitManager(Path("/test/repo"))
        manager.get_current_branch(cwd=Path("/other"))

        mock_run.assert_called_once_with(["rev-parse", "--abbrev-ref", "HEAD"], cwd=Path("/other"))


class TestGitManagerCommitsBehind:
    """Tests for commits_behind method."""

    @patch("selfassembler.git.GitManager._validate_repo")
    @patch("selfassembler.git.GitManager._run")
    @patch("selfassembler.git.GitManager.fetch")
    def test_commits_behind_zero(self, mock_fetch, mock_run, mock_validate):
        """Test when not behind."""
        mock_run.return_value = MagicMock(returncode=0, stdout="0\n")

        manager = GitManager(Path("/test/repo"))
        behind = manager.commits_behind("main")

        assert behind == 0
        mock_fetch.assert_called_once_with("origin")

    @patch("selfassembler.git.GitManager._validate_repo")
    @patch("selfassembler.git.GitManager._run")
    @patch("selfassembler.git.GitManager.fetch")
    def test_commits_behind_positive(self, mock_fetch, mock_run, mock_validate):
        """Test when behind by commits."""
        mock_run.return_value = MagicMock(returncode=0, stdout="5\n")

        manager = GitManager(Path("/test/repo"))
        behind = manager.commits_behind("main")

        assert behind == 5

    @patch("selfassembler.git.GitManager._validate_repo")
    @patch("selfassembler.git.GitManager._run")
    @patch("selfassembler.git.GitManager.fetch")
    def test_commits_behind_invalid_output(self, mock_fetch, mock_run, mock_validate):
        """Test handling invalid output."""
        mock_run.return_value = MagicMock(returncode=0, stdout="not a number\n")

        manager = GitManager(Path("/test/repo"))
        behind = manager.commits_behind("main")

        assert behind == 0  # Returns 0 on parse error


class TestGitManagerFetch:
    """Tests for fetch method."""

    @patch("selfassembler.git.GitManager._validate_repo")
    @patch("selfassembler.git.GitManager.has_remote")
    @patch("selfassembler.git.GitManager._run")
    def test_fetch_default(self, mock_run, mock_has_remote, mock_validate):
        """Test fetching with default remote."""
        mock_has_remote.return_value = True
        mock_run.return_value = MagicMock(returncode=0)

        manager = GitManager(Path("/test/repo"))
        manager.fetch()

        mock_has_remote.assert_called_once_with("origin")
        mock_run.assert_called_once_with(["fetch", "origin"])

    @patch("selfassembler.git.GitManager._validate_repo")
    @patch("selfassembler.git.GitManager.has_remote")
    @patch("selfassembler.git.GitManager._run")
    def test_fetch_custom_remote(self, mock_run, mock_has_remote, mock_validate):
        """Test fetching from custom remote."""
        mock_has_remote.return_value = True
        mock_run.return_value = MagicMock(returncode=0)

        manager = GitManager(Path("/test/repo"))
        manager.fetch(remote="upstream")

        mock_has_remote.assert_called_once_with("upstream")
        mock_run.assert_called_once_with(["fetch", "upstream"])

    @patch("selfassembler.git.GitManager._validate_repo")
    @patch("selfassembler.git.GitManager.has_remote")
    @patch("selfassembler.git.GitManager._run")
    def test_fetch_no_remote_skips(self, mock_run, mock_has_remote, mock_validate):
        """Test fetching with no remote skips fetch."""
        mock_has_remote.return_value = False

        manager = GitManager(Path("/test/repo"))
        manager.fetch()

        mock_has_remote.assert_called_once_with("origin")
        mock_run.assert_not_called()


class TestGitManagerCleanupUnreachableRemote:
    """Tests for cleanup_unreachable_remote method."""

    @patch("selfassembler.git.GitManager._validate_repo")
    @patch("selfassembler.git.GitManager._run")
    def test_removes_unreachable_local_path(self, mock_run, mock_validate):
        """Test that an origin pointing to a nonexistent local path is removed."""
        mock_run.side_effect = [
            # get_remote_url: returns a local path
            MagicMock(returncode=0, stdout="/var/lib/code/my-project\n"),
            # remove_remote
            MagicMock(returncode=0),
        ]

        manager = GitManager(Path("/test/repo"))
        removed = manager.cleanup_unreachable_remote()

        assert removed is True
        mock_run.assert_any_call(["remote", "remove", "origin"], check=False)

    @patch("selfassembler.git.GitManager._validate_repo")
    @patch("selfassembler.git.GitManager._run")
    def test_keeps_https_remote(self, mock_run, mock_validate):
        """Test that an HTTPS origin is not removed."""
        mock_run.return_value = MagicMock(
            returncode=0, stdout="https://github.com/owner/repo\n"
        )

        manager = GitManager(Path("/test/repo"))
        removed = manager.cleanup_unreachable_remote()

        assert removed is False

    @patch("selfassembler.git.GitManager._validate_repo")
    @patch("selfassembler.git.GitManager._run")
    def test_keeps_ssh_remote(self, mock_run, mock_validate):
        """Test that a git@ origin is not removed."""
        mock_run.return_value = MagicMock(
            returncode=0, stdout="git@github.com:owner/repo.git\n"
        )

        manager = GitManager(Path("/test/repo"))
        removed = manager.cleanup_unreachable_remote()

        assert removed is False

    @patch("selfassembler.git.GitManager._validate_repo")
    @patch("selfassembler.git.GitManager._run")
    def test_no_remote_returns_false(self, mock_run, mock_validate):
        """Test that no origin returns False."""
        mock_run.return_value = MagicMock(returncode=2, stdout="", stderr="")

        manager = GitManager(Path("/test/repo"))
        removed = manager.cleanup_unreachable_remote()

        assert removed is False

    @patch("selfassembler.git.Path.exists", return_value=True)
    @patch("selfassembler.git.GitManager._validate_repo")
    @patch("selfassembler.git.GitManager._run")
    def test_keeps_reachable_local_path(self, mock_run, mock_validate, mock_exists):
        """Test that a reachable local path origin is not removed."""
        mock_run.return_value = MagicMock(
            returncode=0, stdout="/var/lib/code/existing-repo\n"
        )

        manager = GitManager(Path("/test/repo"))
        removed = manager.cleanup_unreachable_remote()

        assert removed is False


class TestGitManagerIsClean:
    """Tests for is_clean method."""

    @patch("selfassembler.git.GitManager._validate_repo")
    @patch("selfassembler.git.GitManager._run")
    def test_is_clean_true(self, mock_run, mock_validate):
        """Test clean working directory."""
        mock_run.return_value = MagicMock(returncode=0, stdout="")

        manager = GitManager(Path("/test/repo"))
        is_clean, output = manager.is_clean()

        assert is_clean is True
        assert output == ""

    @patch("selfassembler.git.GitManager._validate_repo")
    @patch("selfassembler.git.GitManager._run")
    def test_is_clean_false(self, mock_run, mock_validate):
        """Test dirty working directory."""
        mock_run.return_value = MagicMock(
            returncode=0, stdout="M modified_file.py\n?? untracked.py"
        )

        manager = GitManager(Path("/test/repo"))
        is_clean, output = manager.is_clean()

        assert is_clean is False
        assert "modified_file.py" in output


class TestGitManagerRun:
    """Tests for _run method."""

    @patch("selfassembler.git.GitManager._validate_repo")
    @patch("subprocess.run")
    def test_run_success(self, mock_subprocess, mock_validate):
        """Test successful command execution."""
        mock_subprocess.return_value = MagicMock(returncode=0, stdout="success", stderr="")

        manager = GitManager(Path("/test/repo"))
        result = manager._run(["status"])

        mock_subprocess.assert_called_once()
        assert result.returncode == 0

    @patch("selfassembler.git.GitManager._validate_repo")
    @patch("subprocess.run")
    def test_run_failure_raises(self, mock_subprocess, mock_validate):
        """Test failed command raises GitOperationError."""
        mock_subprocess.return_value = MagicMock(returncode=1, stdout="", stderr="error message")

        manager = GitManager(Path("/test/repo"))

        with pytest.raises(GitOperationError) as exc_info:
            manager._run(["bad", "command"])

        assert "error message" in str(exc_info.value)

    @patch("selfassembler.git.GitManager._validate_repo")
    @patch("subprocess.run")
    def test_run_no_check(self, mock_subprocess, mock_validate):
        """Test running without checking return code."""
        mock_subprocess.return_value = MagicMock(returncode=1, stdout="", stderr="error")

        manager = GitManager(Path("/test/repo"))
        result = manager._run(["status"], check=False)

        # Should not raise, just return the result
        assert result.returncode == 1

    @patch("selfassembler.git.GitManager._validate_repo")
    @patch("subprocess.run")
    def test_run_timeout(self, mock_subprocess, mock_validate):
        """Test command timeout."""
        import subprocess

        mock_subprocess.side_effect = subprocess.TimeoutExpired(cmd=["git"], timeout=120)

        manager = GitManager(Path("/test/repo"))

        with pytest.raises(GitOperationError) as exc_info:
            manager._run(["long", "command"])

        assert "timed out" in str(exc_info.value).lower()


class TestGitManagerGenerateBranchName:
    """Tests for generate_branch_name method."""

    @patch("selfassembler.git.GitManager._validate_repo")
    def test_basic_name(self, mock_validate):
        """Test basic branch name generation."""
        manager = GitManager(Path("/test/repo"))
        branch = manager.generate_branch_name("Add user authentication")

        assert branch.startswith("feature/")
        assert "add-user-authentication" in branch

    @patch("selfassembler.git.GitManager._validate_repo")
    def test_custom_prefix(self, mock_validate):
        """Test branch name with custom prefix."""
        manager = GitManager(Path("/test/repo"))
        branch = manager.generate_branch_name("Fix bug", prefix="bugfix/")

        assert branch.startswith("bugfix/")
        assert "fix-bug" in branch

    @patch("selfassembler.git.GitManager._validate_repo")
    def test_special_characters_removed(self, mock_validate):
        """Test special characters are removed."""
        manager = GitManager(Path("/test/repo"))
        branch = manager.generate_branch_name("Add @feature! with $pecial chars?")

        # Special chars should be removed
        assert "@" not in branch
        assert "!" not in branch
        assert "$" not in branch
        assert "?" not in branch

    @patch("selfassembler.git.GitManager._validate_repo")
    def test_name_truncated(self, mock_validate):
        """Test long names are truncated."""
        manager = GitManager(Path("/test/repo"))
        long_name = "This is a very long task name " * 10
        branch = manager.generate_branch_name(long_name)

        # The slug part should be max 50 chars, plus prefix and timestamp
        assert len(branch) < 100


class TestGitManagerWorktree:
    """Tests for worktree methods."""

    @patch("selfassembler.git.GitManager._validate_repo")
    @patch("selfassembler.git.GitManager._run")
    def test_create_worktree(self, mock_run, mock_validate):
        """Test creating a worktree."""
        mock_run.return_value = MagicMock(returncode=0)

        manager = GitManager(Path("/test/repo"))
        with patch.object(Path, "exists", return_value=False), patch.object(Path, "mkdir"):
            path = manager.create_worktree(
                branch_name="feature/test", worktree_dir=Path("/worktrees"), base_branch="main"
            )

        assert "feature-test" in str(path)  # / replaced with -

    @patch("selfassembler.git.GitManager._validate_repo")
    @patch("selfassembler.git.GitManager._run")
    def test_list_worktrees(self, mock_run, mock_validate):
        """Test listing worktrees."""
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout="worktree /path/to/main\nHEAD abc123\nbranch refs/heads/main\n\nworktree /path/to/feature\nHEAD def456\nbranch refs/heads/feature",
        )

        manager = GitManager(Path("/test/repo"))
        worktrees = manager.list_worktrees()

        assert len(worktrees) == 2
