"""Tests for release integrity, checksum separation, trust root authenticity, and publishing safety."""

import hashlib
import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent


def test_runtime_and_release_checksum_filenames_do_not_collide():
    """Runtime manifest and release checksums must not use the same filename."""
    runtime_manifest = REPO_ROOT / "runtime-SHA256SUMS.txt"
    ambiguous_manifest = REPO_ROOT / "SHA256SUMS.txt"
    release_workflow = REPO_ROOT / ".github" / "workflows" / "release.yml"

    # Ambiguous SHA256SUMS.txt must be removed from repo root
    assert not ambiguous_manifest.exists(), (
        "SHA256SUMS.txt is ambiguous and must be replaced with runtime-SHA256SUMS.txt"
    )

    # runtime-SHA256SUMS.txt must exist
    assert runtime_manifest.exists(), "runtime-SHA256SUMS.txt must exist"

    # release.yml must produce release-SHA256SUMS.txt and not overwrite runtime manifest
    content = release_workflow.read_text(encoding="utf-8")
    assert "release-SHA256SUMS.txt" in content, "release.yml must generate release-SHA256SUMS.txt"
    assert not re.search(r"(?<!runtime-)(?<!release-)SHA256SUMS\.txt", content), (
        "release.yml must not reference or produce ambiguous bare SHA256SUMS.txt"
    )


def test_runtime_manifest_does_not_contain_bootstrap_cycle():
    """bootstrap.sh must not be inside runtime-SHA256SUMS.txt to avoid a self-referential hash cycle."""
    runtime_manifest = REPO_ROOT / "runtime-SHA256SUMS.txt"
    assert runtime_manifest.exists(), "runtime-SHA256SUMS.txt must exist"
    content = runtime_manifest.read_text(encoding="utf-8")
    assert "scripts/bootstrap.sh" not in content, (
        "scripts/bootstrap.sh must not be in runtime-SHA256SUMS.txt to prevent a self-referential hash cycle"
    )


def test_runtime_assets_match_manifest():
    """All runtime assets declared in runtime-SHA256SUMS.txt must match their computed SHA-256 hashes."""
    runtime_manifest = REPO_ROOT / "runtime-SHA256SUMS.txt"
    assert runtime_manifest.exists(), "runtime-SHA256SUMS.txt must exist"

    lines = [
        line.strip()
        for line in runtime_manifest.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.startswith("#")
    ]
    assert len(lines) >= 4, "runtime manifest must contain at least the 4 runtime assets"

    for line in lines:
        parts = line.split(maxsplit=1)
        assert len(parts) == 2, f"Invalid manifest line: {line}"
        expected_hash, rel_path = parts[0], parts[1].strip()
        asset_file = REPO_ROOT / rel_path
        assert asset_file.exists(), f"Asset declared in manifest does not exist: {rel_path}"
        actual_hash = hashlib.sha256(asset_file.read_bytes()).hexdigest()
        assert actual_hash == expected_hash, f"Hash mismatch for asset {rel_path}"


def test_embedded_manifest_digest_matches_committed_manifest():
    """bootstrap.sh must embed the exact SHA-256 digest of runtime-SHA256SUMS.txt."""
    bootstrap_file = REPO_ROOT / "scripts" / "bootstrap.sh"
    runtime_manifest = REPO_ROOT / "runtime-SHA256SUMS.txt"
    assert bootstrap_file.exists()
    assert runtime_manifest.exists()

    expected_digest = hashlib.sha256(runtime_manifest.read_bytes()).hexdigest()
    bootstrap_content = bootstrap_file.read_text(encoding="utf-8")

    match = re.search(r'RUNTIME_MANIFEST_SHA256="([a-f0-9]{64})"', bootstrap_content)
    assert match is not None, "scripts/bootstrap.sh must declare RUNTIME_MANIFEST_SHA256"
    embedded_digest = match.group(1)
    assert embedded_digest == expected_digest, (
        f"Embedded digest {embedded_digest} != computed manifest digest {expected_digest}"
    )


def test_bootstrap_production_default_points_at_immutable_ref():
    """bootstrap.sh default distribution URL must point to an immutable tag, not mutable main/master."""
    bootstrap_file = REPO_ROOT / "scripts" / "bootstrap.sh"
    content = bootstrap_file.read_text(encoding="utf-8")
    match = re.search(r'DEFAULT_DIST_URL="([^"]+)"', content)
    assert match is not None, "DEFAULT_DIST_URL must be defined in scripts/bootstrap.sh"
    url = match.group(1)
    assert "/main" not in url and "/master" not in url and "@main" not in url, (
        f"DEFAULT_DIST_URL must point to an immutable ref, not a mutable branch: {url}"
    )
    assert re.search(r"/v\d+\.\d+\.\d+", url), (
        f"DEFAULT_DIST_URL must point to a versioned release tag: {url}"
    )


def test_release_workflow_verifies_embedded_digest():
    """release.yml must verify that the embedded manifest digest in bootstrap.sh matches runtime-SHA256SUMS.txt."""
    release_workflow = REPO_ROOT / ".github" / "workflows" / "release.yml"
    content = release_workflow.read_text(encoding="utf-8")
    assert "runtime-SHA256SUMS.txt" in content, "release.yml must reference runtime-SHA256SUMS.txt"
    assert "RUNTIME_MANIFEST_SHA256" in content, (
        "release.yml must verify RUNTIME_MANIFEST_SHA256 against runtime-SHA256SUMS.txt"
    )


def test_release_workflow_does_not_overwrite_or_repurpose_runtime_manifest():
    """release.yml must produce release-SHA256SUMS.txt without overwriting runtime manifest."""
    release_workflow = REPO_ROOT / ".github" / "workflows" / "release.yml"
    content = release_workflow.read_text(encoding="utf-8")
    assert "release-SHA256SUMS.txt" in content
    assert "> SHA256SUMS.txt" not in content
    assert "> runtime-SHA256SUMS.txt" not in content


def test_publishing_policy_rejects_public_first_and_requires_safe_tags():
    """docs/publishing.md must mandate private-first repository creation and annotated/signed tags."""
    publishing_doc = REPO_ROOT / "docs" / "publishing.md"
    assert publishing_doc.exists()
    content = publishing_doc.read_text(encoding="utf-8")

    # Private-first check
    assert "--private" in content, "docs/publishing.md must mandate private repo creation"
    assert "gh repo create" in content
    for line in content.splitlines():
        if "gh repo create" in line:
            assert "--public" not in line, (
                "docs/publishing.md must not instruct public repo creation in initial flow"
            )

    # Visibility transition flag check
    assert "--accept-visibility-change-consequences" in content, (
        "docs/publishing.md must document --accept-visibility-change-consequences for public transition"
    )

    # Annotated tag check: git tag must use -a or -s
    for line in content.splitlines():
        if line.strip().startswith("git tag ") and "v" in line:
            assert "-a " in line or "-s " in line, (
                f"docs/publishing.md must use annotated or signed tags, not lightweight: {line}"
            )


def test_no_uncommitted_client_claims():
    """Documentation must not claim support for uncommitted clients like Open WebUI or Cursor."""
    for rel_path in ["README.md", "docs/compatibility.md", "docs/architecture.md"]:
        doc_file = REPO_ROOT / rel_path
        if doc_file.exists():
            text = doc_file.read_text(encoding="utf-8")
            assert "Open WebUI" not in text, f"{rel_path} claims uncommitted client Open WebUI"
            assert "Cursor" not in text, f"{rel_path} claims uncommitted client Cursor"
