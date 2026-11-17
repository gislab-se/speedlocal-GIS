# SpeedLocal GIS

SpeedLocal is a research application for exploring how landscape constraints,
energy scenarios and social acceptance affect wind and solar land potential in
**Bornholm, Skaraborg and Trøndelag**.

The interactive map lets users select constraints, adjust distances, compare
scenarios and inspect the resulting potential and allocation. The interface is
available in Swedish, Norwegian Bokmål, Danish and English.

## Use the application

[Open the project application](https://speedlocal-gis-test.compute.flowcore.io/)
with an approved account. For access, demonstrations, regional data or adaptations,
contact Henrik through [gislab.se](https://gislab.se/).

This repository contains the application source. Regional GIS and model datasets,
database credentials and hosting access are not included. Running it requires a
PostgreSQL/PostGIS installation containing the matching regional data revisions.
See [running the application](docs/RUNNING.md) and [data and interpretation](docs/DATA.md).

## Interpreting results

SpeedLocal is an exploratory prototype, not validated planning support.
Energy assumptions are preliminary; Skaraborg and Trøndelag currently use
demonstration or borrowed scenarios. Social acceptance values are synthetic in
all three regions. Missing inputs remain unavailable rather than being treated
as zero. Map allocation symbols do not specify exact installation locations.

## Source and license

The main entry point is `app.py`. Interface code is in `apps/v2_port/`, shared
calculations in `speedlocal/`, and regional contracts in `regions/` and `schemas/`.

This is the public source snapshot of 17 November 2026, derived from source
revision `1692f0503ec72d66b5783a0025aeb33e1681ed0d`. Application code, regional
contracts and dependency versions are preserved. Internal project records and
earlier Git history are not part of this distribution.

Original project code and documentation are available under the [MIT License](LICENSE).
Third-party libraries, map services and external datasets retain their own terms.
Publishing the source does not grant rights to redistribute regional datasets.
