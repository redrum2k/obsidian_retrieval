#!/bin/bash
set -euo pipefail
cd "$(dirname "$0")"
mkdir -p .build
swiftc Sources/VaultApproval/Review.swift Tests/main.swift -o .build/review-tests
.build/review-tests "$@"
