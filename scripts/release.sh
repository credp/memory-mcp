#!/usr/bin/env bash
set -euo pipefail

cd "$(git rev-parse --show-toplevel)"

bump="${BUMP:-patch}"
case "$bump" in
    major|minor|patch|stable|alpha|beta|rc|post|dev) ;;
    *)
        echo "BUMP must be one of: major, minor, patch, stable, alpha, beta, rc, post, dev" >&2
        exit 2
        ;;
esac

if [[ -n "$(git status --porcelain)" ]]; then
    echo "Refusing to release from a dirty working tree." >&2
    exit 1
fi

uv run pytest

changed=false
restore_version_files() {
    if [[ "$changed" == true ]]; then
        git restore --staged --worktree -- pyproject.toml uv.lock
    fi
}
trap restore_version_files ERR

uv version --bump "$bump" --no-sync
changed=true

version="$(uv version --short)"
tag="v$version"

if git rev-parse --verify --quiet "refs/tags/$tag" >/dev/null; then
    echo "Tag $tag already exists." >&2
    exit 1
fi

RELEASE_TAG="$tag" uv run pytest

git add pyproject.toml uv.lock
git commit -m "Release $tag"
changed=false
git tag -a "$tag" -m "Release $tag"

echo "Created release commit and tag $tag."
echo "Publish it with: git push origin HEAD --follow-tags"
