#!/usr/bin/env bash
# do-release.sh — bump version + create a git tag.
#
# Computes the next version from the most recent `v*` tag and the chosen
# bump kind (major / minor / patch), then runs `git tag` and prints the
# follow-up push command. Defaults to a minor bump if BUMP is unset.
#
# Tag format:
#   - major / minor → vMAJOR.MINOR (two-component)
#   - patch         → vMAJOR.MINOR.PATCH (three-component)
#
# Usage: BUMP=major|minor|patch scripts/do-release.sh

set -eu

BUMP=${BUMP:-minor}
LATEST=$(git tag --list 'v*' --sort=-version:refname | head -1)
if [ -z "$LATEST" ]; then LATEST="v0.0"; fi

MAJOR=$(echo "$LATEST" | sed 's/v\([0-9]*\)\..*/\1/')
MINOR=$(echo "$LATEST" | sed 's/v[0-9]*\.\([0-9]*\).*/\1/')
PATCH=$(echo "$LATEST" | sed 's/v[0-9]*\.[0-9]*\.\([0-9]*\).*/\1/')
if [ "$PATCH" = "$LATEST" ]; then PATCH=0; fi

if [ "$BUMP" = "major" ]; then
    MAJOR=$((MAJOR + 1)); MINOR=0; PATCH=0
elif [ "$BUMP" = "minor" ]; then
    MINOR=$((MINOR + 1)); PATCH=0
else
    PATCH=$((PATCH + 1))
fi

VERSION="v$MAJOR.$MINOR"
if [ "$BUMP" = "patch" ]; then VERSION="v$MAJOR.$MINOR.$PATCH"; fi

git tag "$VERSION"
echo "🏷️  Tagged $VERSION — push with: git push && git push --tags"
