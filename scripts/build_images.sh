#!/usr/bin/env bash

# builds the docker images locally and pushes them to the repo

APP_VERSION=$(poetry version | sed 's/opennem-backend\ //g')

# Build and push the database image
docker buildx build \
  -f infra/database/Dockerfile \
  --push \
  --platform linux/arm/v7,linux/arm64/v8,linux/amd64 \
  --tag opennem/database:dev .
