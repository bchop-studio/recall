import shutil
import subprocess
import tarfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PRIVATE_NAMES = {".hermes.md", "AGENTS.md", "BUILDLOG.md", ".env.example", "auth.json"}


def test_source_archive_excludes_private_project_files(tmp_path):
    project = tmp_path / "project"
    shutil.copytree(
        ROOT,
        project,
        ignore=shutil.ignore_patterns(".git", ".venv", ".pytest_cache", "__pycache__", "dist"),
    )
    (project / ".hermes.md").write_text("private project instructions\n")
    (project / "AGENTS.md").write_text("private agent instructions\n")
    (project / ".env.example").write_text("PRIVATE_KEY_NAME=\n")
    (project / "docs").mkdir(exist_ok=True)
    (project / "docs" / "BUILDLOG.md").write_text("private build notes\n")

    output = tmp_path / "dist"
    subprocess.run(
        ["uv", "build", "--sdist", "--out-dir", str(output)],
        cwd=project,
        check=True,
        capture_output=True,
        text=True,
    )

    archive_path = next(output.glob("*.tar.gz"))
    with tarfile.open(archive_path) as archive:
        archived_names = {Path(name).name for name in archive.getnames()}

    assert not (archived_names & PRIVATE_NAMES)
