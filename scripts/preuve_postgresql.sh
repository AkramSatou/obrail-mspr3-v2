#!/usr/bin/env bash
set -euo pipefail

COMPOSE_FILE="${COMPOSE_FILE:-docker/docker-compose.yml}"
DB_CONTAINER="${DB_CONTAINER:-docker-db-1}"

echo "Verification du conteneur PostgreSQL"
docker ps --filter "name=${DB_CONTAINER}" --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}"

echo
echo "Liste des bases disponibles"
docker exec "${DB_CONTAINER}" psql -U obrail -d obrail -c "\\l"

echo
echo "Tables de la base obrail"
docker exec "${DB_CONTAINER}" psql -U obrail -d obrail -c "\\dt"

echo
echo "Nombre de trajets importes"
docker exec "${DB_CONTAINER}" psql -U obrail -d obrail -c "SELECT COUNT(*) AS nombre_de_trajets FROM trips;"

echo
echo "Exemple de lignes stockees"
docker exec "${DB_CONTAINER}" psql -U obrail -d obrail -c "SELECT trip_id, origin_stop_name, destination_stop_name, country FROM trips ORDER BY id LIMIT 5;"

echo
echo "Rappel demarrage complet si besoin : docker compose -f ${COMPOSE_FILE} up --build"
