set -euxo pipefail

pytest

# run flake
flake8 . --count --select=E9,F63,F7,F82 --show-source --statistics
flake8 . --count --exit-zero --max-complexity=14 --max-line-length=127 --statistics

# @TODO run mypy

poetry version ${1-prerelease}

VERSION=$(poetry version | sed 's/opennem-backend\ //g')

echo "Building version $VERSION"

poetry export --format requirements.txt -E postgres --without-hashes > requirements.txt
poetry export --dev --format requirements.txt --without-hashes > requirements_dev.txt

git add pyproject.toml requirements.txt requirements_dev.txt

git ci -m "v$VERSION"

git tag v$VERSION
git push -u origin v$VERSION

rm -rf build/
