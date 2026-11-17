# Data and interpretation

The regional JSON files describe inputs, provenance, configuration and validation
bindings. They do not contain the regional GIS or energy-model deliveries. The
small files under `regions/fixture_region_a/assets/` and
`regions/fixture_region_standard/assets/` are synthetic test examples.

## Current model scope

| Region | Energy scenario | Landscape display |
| --- | --- | --- |
| Bornholm | Preliminary EML capacity inputs; independent wind and ground-solar MW controls. Annual generation remains unknown. | Existing LABLAB classification. |
| Skaraborg | Bornholm capacities scaled for demonstration, not a regional forecast. Annual generation remains unknown. | No regional classification supplied. |
| Trøndelag | Exploratory energy-based scenario borrowed from Bornholm, with its existing rooftop accounting. | Existing LABLAB classification. |

Social acceptance is synthetic in all three regions. Missing acceptance is
unassessed, not observed opposition or support. Source availability, selection
and licensing vary between regions; different source counts do not establish
equivalent regional evidence.

Display cells can aggregate or simplify exact analytical results. Their drawn
outlines and allocation markers should not be interpreted as precise sites,
physical overlap or measured installation footprints.

## Source rights and attribution

The MIT License covers original project code and documentation. It does not
replace the terms of libraries, basemap services, energy models or GIS datasets.
Retain the source-specific metadata in each region's `source-catalog.json` and
other contracts when replacing inputs or distributing results.

- OpenStreetMap-derived sources retain their recorded ODbL attribution and terms.
  The application also retains attribution for its selected basemap services.
- Some Bornholm population inputs have unverified reuse terms and are restricted
  to the documented local review context. They are not supplied here.
- The historical LABLAB landscape metadata does not establish a distribution
  license. Access to the code does not authorize redistribution of those inputs.
- Other excluded or restricted sources remain excluded or restricted according
  to their contracts. A public source repository does not change that status.

Before publishing regional inputs or derived datasets, establish the applicable
rights and attribution with their provider. Contact [gislab.se](https://gislab.se/)
for project data and integration questions.
