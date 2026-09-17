"""Contract: in-repo prebuilt launcher and compose share docker/data."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_deploy_compose_template_uses_data_dir_env() -> None:
    text = (ROOT / "scripts/deploy-docker-compose.yml").read_text(encoding="utf-8")
    assert "${LORECHAT_DATA_DIR:-./data}/knowledge:/data/knowledge" in text
    assert "${LORECHAT_DATA_DIR:-./data}/backups:/data/backups" in text


def test_source_compose_uses_data_dir_env() -> None:
    text = (ROOT / "docker/docker-compose.yml").read_text(encoding="utf-8")
    assert "${LORECHAT_DATA_DIR:-./data}/knowledge:/data/knowledge" in text


def test_generated_bash_launcher_prefers_repo_docker_data() -> None:
    text = (ROOT / "deploy/lorechat.sh").read_text(encoding="utf-8")
    assert "in_repo_deploy" in text
    assert '$(basename "${ROOT}")" == "deploy"' in text
    assert "../docker/docker-compose.yml" in text
    assert "../docker/data" in text
    assert "prepare_data_dir" in text


def test_generated_ps1_launcher_prefers_repo_docker_data() -> None:
    text = (ROOT / "deploy/lorechat.ps1").read_text(encoding="utf-8")
    assert "Test-InRepoDeploy" in text
    assert '$leaf -eq "deploy"' in text
    assert "docker\\data" in text
    assert "Prepare-DataDir" in text


def test_root_launcher_has_prebuilt_flag() -> None:
    text = (ROOT / "lorechat.sh").read_text(encoding="utf-8")
    assert "--prebuilt" in text
    assert "docker-compose.prebuilt.yml" in text
    assert "lorechat_prepare_data_dir" in text
