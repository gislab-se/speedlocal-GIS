# Running SpeedLocal

## Prerequisites

- Python 3.12, or Docker with Linux/amd64 support.
- A reachable PostgreSQL/PostGIS database with the GIS and context revisions
  declared by each region's `analysis-runtime.json` and `context-runtime.json`.
- A private database connection with the required read permissions, supplied as
  `DATABASE_URL` in the launching environment.

A clone or an empty PostGIS database is insufficient for regional analysis.
Regional imports and private data deliveries are outside this source distribution.
Arrange access to compatible inputs through [gislab.se](https://gislab.se/).
Do not put connection strings or datasets in Git.

## Docker

The Dockerfile pins Python 3.12.13 and installs the hash-locked Linux dependencies.
Set `DATABASE_URL` securely in your shell before running these commands:

```sh
docker build --platform linux/amd64 --build-arg APP_REVISION="$(git rev-parse HEAD)" -t speedlocal-gis .
docker run --rm -p 127.0.0.1:8501:8501 \
  -e DATABASE_URL \
  -e SPEEDLOCAL_LOCAL_REVIEW_REGIONS=bornholm,skaraborg \
  speedlocal-gis
```

Open <http://localhost:8501/>. The container runs as a non-root user. Its health
check confirms that Streamlit responds; it does not establish database or result
readiness. The database address must be reachable from inside the container.

## Local Python

Create and activate a virtual environment using Python 3.12, then run:

```sh
python -m pip install -r requirements.txt
python -m streamlit run app.py --server.address=127.0.0.1
```

On Linux x86_64, use the reproducible deployment dependencies instead:

```sh
python -m pip install --only-binary=:all: --require-hashes -r requirements-linux.lock
```

Supply `DATABASE_URL` in the same environment. For the existing Bornholm and
Skaraborg review routes, also set `SPEEDLOCAL_LOCAL_REVIEW_REGIONS` to
`bornholm,skaraborg`. This allowlist is not authentication and does not change
dataset reuse permissions. Keep these review routes within approved access.

The region links are `/?region=bornholm`, `/?region=skaraborg` and
`/?region=trondelag`. Choose a region, change a setting and use **Apply** to
update its results. Reset restores that region's defaults.

## Hosting and data updates

Any hosted installation needs its own access control and database configuration.
The source distribution contains no deployment workflow. Web maps also require
network access to their map assets and selected basemap service.

Compatible data replacements use regional contracts and imports. Keep revision
bindings, source attribution, missing-data rules and region isolation intact.
Changes in input meaning require corresponding validation; editing a manifest
alone does not install new data. Database preparation and hosting are separate
from running this source snapshot.
