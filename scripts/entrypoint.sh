#!/bin/bash
set -e

echo "Waiting for PostgreSQL..."
until pg_isready -h "$DB_HOST" -U "$DB_USER"; do sleep 1; done

echo "Seeding database..."
python seed.py

echo "Seeding application users..."
python seed_users.py

echo "Starting API..."
exec uvicorn app.main:app --host 0.0.0.0 --port 8000
