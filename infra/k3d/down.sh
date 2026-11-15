#!/usr/bin/env bash
# Tear down the optional k3d cluster (s-x1) and everything in it, volumes included.
set -euo pipefail
k3d cluster delete sec-agent
