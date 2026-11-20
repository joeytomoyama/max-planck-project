#!/bin/bash
# Simple CI test script for Max Planck Project

set -e

echo "Testing Docker setup..."

# Check Docker is available
if ! command -v docker &> /dev/null; then
    echo "Docker is not installed. Skipping container tests."
else
    # Build and run the containers
    docker compose up --build -d
    
    echo "Containers started successfully!"
    
    # Health check for PostgreSQL
    echo "Waiting for PostgreSQL to be ready..."
    until docker exec mpp_postgres pg_isready; do
        sleep 2
    done
    
    echo "PostgreSQL is ready!"
    
    # Build frontend
    echo "Building frontend..."
    docker compose build frontend
    
    echo "Build completed!"
fi

echo "All checks passed."
