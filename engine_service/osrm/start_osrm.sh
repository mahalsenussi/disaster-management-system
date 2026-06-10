#!/bin/bash
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo "=========================================="
echo "OSRM Libya Local Setup"
echo "=========================================="

# Check if map data exists
if [ ! -f "data/libya-latest.osm.pbf" ]; then
    echo "ERROR: Map data not found at data/libya-latest.osm.pbf"
    echo "Please download the Libya OSM data first:"
    echo "  mkdir -p data"
    echo "  curl -L -o data/libya-latest.osm.pbf https://download.geofabrik.de/africa/libya-latest.osm.pbf"
    exit 1
fi

echo "[1/3] Map data found: $(ls -lh data/libya-latest.osm.pbf | awk '{print $5}')"

# Check if OSRM files already exist
if [ -f "data/libya-latest.osrm" ]; then
    echo "[2/3] OSRM data files already exist, skipping extraction..."
else
    echo "[2/3] Extracting OSRM data (this may take a few minutes)..."
    docker run --rm -v "$SCRIPT_DIR/data:/data" osrm/osrm-backend:latest \
        osrm-extract -p /opt/car.lua /data/libya-latest.osm.pbf
    
    echo "Partitioning OSRM data..."
    docker run --rm -v "$SCRIPT_DIR/data:/data" osrm/osrm-backend:latest \
        osrm-partition /data/libya-latest.osrm
    
    echo "Customizing OSRM data..."
    docker run --rm -v "$SCRIPT_DIR/data:/data" osrm/osrm-backend:latest \
        osrm-customize /data/libya-latest.osrm
fi

echo "[3/3] Starting OSRM server..."
docker compose up -d

echo ""
echo "=========================================="
echo "OSRM is starting..."
echo "Server will be available at: http://localhost:5000"
echo ""
echo "To check status: docker compose ps"
echo "To view logs:    docker compose logs -f"
echo "To stop:         docker compose down"
echo "=========================================="
