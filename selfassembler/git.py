"""Git operations for workflow management."""

from __future__ import annotations

import re
import shutil
import subprocess
from datetime import datetime
from pathlib import Path

from selfassembler.errors import GitOperationError, WorktreeError


class GitManager:
    """
    Manages all git operations for the workflow.

    Handles worktree creation, branch management, commits,
    and conflict detection/resolution.
    """

    def __init__(self, repo_path: Path):
        self.repo_path = repo_path
        self._validate_repo()

    def _validate_repo(self) -> None:
        """Validate that the path is a git repository or worktree."""
        git_dir = self.repo_path / ".git"
        # .git can be a directory (regular repo) or a file (worktree)
        if not git_dir.exists():
            raise GitOperationError("validate", f"Not a git repository: {self.repo_path}")

    def _run(
        self,
        args: list[str],
        cwd: Path | None = None,
        check: bool = True,
        capture: bool = True,
    ) -> subprocess.CompletedProcess:
        """Run a git command."""
        cmd = ["git"] + args
        working_dir = cwd or self.repo_path

        try:
            result = subprocess.run(
                cmd,
                cwd=working_dir,
                capture_output=capture,
                text=True,
                timeout=120,
            )
            if check and result.returncode != 0:
                raise GitOperationError(
                    " ".join(args[:2]),
                    result.stderr or result.stdout,
                    result.returncode,
                )
            return result
        except subprocess.TimeoutExpired as e:
            raise GitOperationError(" ".join(args[:2]), "Command timed out") from e

    def is_clean(self) -> tuple[bool, str]:
        """Check if the working directory is clean."""
        result = self._run(["status", "--porcelain"], check=False)
        output = result.stdout.strip()
        return (len(output) == 0, output)

    def fetch(self, remote: str = "origin") -> None:
        """Fetch from remote."""
        self._run(["fetch", remote])

    def get_current_branch(self, cwd: Path | None = None) -> str:
        """Get the current branch name."""
        result = self._run(["rev-parse", "--abbrev-ref", "HEAD"], cwd=cwd)
        return result.stdout.strip()

    def get_default_branch(self) -> str:
        """Get the default branch (main or master)."""
        result = self._run(["symbolic-ref", "refs/remotes/origin/HEAD"], check=False)
        if result.returncode == 0:
            # refs/remotes/origin/main -> main
            return result.stdout.strip().split("/")[-1]

        # Fallback: check if main or master exists
        for branch in ["main", "master"]:
            result = self._run(["rev-parse", "--verify", f"refs/heads/{branch}"], check=False)
            if result.returncode == 0:
                return branch

        return "main"

    def commits_behind(self, base_branch: str = "main", remote: str = "origin") -> int:
        """Check how many commits behind the remote we are."""
        self.fetch(remote)
        result = self._run(
            ["rev-list", "--count", f"HEAD..{remote}/{base_branch}"],
            check=False,
        )
        try:
            return int(result.stdout.strip())
        except ValueError:
            return 0

    def generate_branch_name(self, task_name: str, prefix: str = "feature/") -> str:
        """Generate a branch name from a task name."""
        # Slugify the task name
        slug = re.sub(r"[^\w\s-]", "", task_name.lower())
        slug = re.sub(r"[\s_]+", "-", slug)[:50].strip("-")
        timestamp = datetime.now().strftime("%Y%m%d-%H%M")
        return f"{prefix}{slug}-{timestamp}"

    def create_worktree(
        self,
        branch_name: str,
        worktree_dir: Path,
        base_branch: str = "main",
    ) -> Path:
        """
        Create a git worktree for isolated development.

        Args:
            branch_name: Name of the new branch
            worktree_dir: Directory to create worktrees in
            base_branch: Branch to base the new branch on

        Returns:
            Path to the created worktree
        """
        # Ensure worktree directory exists
        worktree_dir.mkdir(parents=True, exist_ok=True)

        # Create safe directory name for worktree
        safe_name = branch_name.replace("/", "-")
        worktree_path = worktree_dir / safe_name

        if worktree_path.exists():
            raise WorktreeError(f"Worktree already exists: {worktree_path}")

        try:
            self._run(["worktree", "add", "-b", branch_name, str(worktree_path), base_branch])
            return worktree_path
        except GitOperationError as e:
            raise WorktreeError(f"Failed to create worktree: {e}") from e

    def remove_worktree(self, worktree_path: Path, force: bool = False) -> None:
        """Remove a git worktree."""
        args = ["worktree", "remove"]
        if force:
            args.append("--force")
        args.append(str(worktree_path))

        try:
            self._run(args)
        except GitOperationError:
            # If git worktree remove fails, try manual cleanup
            if force and worktree_path.exists():
                shutil.rmtree(worktree_path, ignore_errors=True)
                self._run(["worktree", "prune"])

    def list_worktrees(self) -> list[dict[str, str]]:
        """List all worktrees."""
        result = self._run(["worktree", "list", "--porcelain"])
        worktrees = []
        current: dict[str, str] = {}

        for line in result.stdout.strip().split("\n"):
            if not line:
                if current:
                    worktrees.append(current)
                    current = {}
            elif line.startswith("worktree "):
                current["path"] = line[9:]
            elif line.startswith("HEAD "):
                current["head"] = line[5:]
            elif line.startswith("branch "):
                current["branch"] = line[7:]

        if current:
            worktrees.append(current)

        return worktrees

    def get_diff(
        self,
        base_branch: str = "main",
        cwd: Path | None = None,
        staged_only: bool = False,
    ) -> str:
        """Get diff from base branch."""
        if staged_only:
            result = self._run(["diff", "--cached"], cwd=cwd)
        else:
            result = self._run(["diff", f"{base_branch}...HEAD"], cwd=cwd)
        return result.stdout

    def get_changed_files(
        self,
        base_branch: str = "main",
        cwd: Path | None = None,
    ) -> list[str]:
        """Get list of changed files from base branch."""
        result = self._run(
            ["diff", "--name-only", f"{base_branch}...HEAD"],
            cwd=cwd,
        )
        return [f for f in result.stdout.strip().split("\n") if f]

    def add_files(self, files: list[str], cwd: Path | None = None) -> None:
        """Stage files for commit."""
        if files:
            self._run(["add"] + files, cwd=cwd)

    def commit(
        self,
        message: str,
        cwd: Path | None = None,
        author: str | None = None,
    ) -> str:
        """Create a commit and return the commit hash."""
        args = ["commit", "-m", message]
        if author:
            args.extend(["--author", author])

        self._run(args, cwd=cwd)
        # Get the commit hash
        hash_result = self._run(["rev-parse", "HEAD"], cwd=cwd)
        return hash_result.stdout.strip()

    def push(
        self,
        branch: str,
        remote: str = "origin",
        cwd: Path | None = None,
        set_upstream: bool = True,
    ) -> None:
        """Push branch to remote."""
        args = ["push"]
        if set_upstream:
            args.extend(["-u", remote, branch])
        else:
            args.extend([remote, branch])
        self._run(args, cwd=cwd)

    def delete_remote_branch(
        self,
        branch: str,
        remote: str = "origin",
    ) -> None:
        """Delete a remote branch."""
        self._run(["push", remote, "--delete", branch], check=False)

    def rebase(
        self,
        base: str,
        cwd: Path | None = None,
    ) -> tuple[bool, list[str]]:
        """
        Rebase onto base branch.

        Returns:
            Tuple of (success, conflicted_files)
        """
        result = self._run(["rebase", base], cwd=cwd, check=False)

        if result.returncode == 0:
            return True, []

        # Check for conflicts
        if "CONFLICT" in result.stdout or "CONFLICT" in result.stderr:
            # Get list of conflicted files
            status = self._run(["status", "--porcelain"], cwd=cwd, check=False)
            conflicts = []
            for line in status.stdout.split("\n"):
                if line.startswith("UU ") or line.startswith("AA "):
                    conflicts.append(line[3:])
            return False, conflicts

        # Non-conflict error
        raise GitOperationError("rebase", result.stderr or result.stdout)

    def abort_rebase(self, cwd: Path | None = None) -> None:
        """Abort an in-progress rebase."""
        self._run(["rebase", "--abort"], cwd=cwd, check=False)

    def continue_rebase(self, cwd: Path | None = None) -> bool:
        """Continue a rebase after resolving conflicts."""
        result = self._run(["rebase", "--continue"], cwd=cwd, check=False)
        return result.returncode == 0

    def get_log(
        self,
        count: int = 10,
        format_str: str = "%h %s",
        cwd: Path | None = None,
    ) -> list[str]:
        """Get recent commit log."""
        result = self._run(
            ["log", f"-{count}", f"--format={format_str}"],
            cwd=cwd,
        )
        return [line for line in result.stdout.strip().split("\n") if line]

    def get_commit_count(
        self,
        base_branch: str = "main",
        cwd: Path | None = None,
    ) -> int:
        """Get number of commits since base branch."""
        result = self._run(
            ["rev-list", "--count", f"{base_branch}..HEAD"],
            cwd=cwd,
            check=False,
        )
        try:
            return int(result.stdout.strip())
        except ValueError:
            return 0


def copy_config_files(
    source_dir: Path,
    dest_dir: Path,
    patterns: list[str],
) -> list[Path]:
    """
    Copy configuration files from source to destination.

    Args:
        source_dir: Source directory
        dest_dir: Destination directory
        patterns: Glob patterns for files to copy

    Returns:
        List of copied file paths
    """
    copied = []

    for pattern in patterns:
        for src in source_dir.glob(pattern):
            if src.is_file():
                relative = src.relative_to(source_dir)
                dst = dest_dir / relative
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src, dst)
                copied.append(dst)

    return copied
