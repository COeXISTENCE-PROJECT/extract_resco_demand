# InTAS → URB ingolstadt21

Two scripts: run the original full-city simulation, then extract a local demand
window. The exported network always uses the fixed RESCO ingolstadt21 roads
and the existing traffic-light modification in `source/target_network`.

## Run InTAS

From this directory, using the existing URB Python environment:

```bash
python3 run_intas.py --seed 42
```

This runs the complete original scenario from 00:00 to 24:00, at its original
0.1-second step length. InTAS's route distributions and rerouting settings are
unchanged. SUMO must be on your PATH.

The recording goes to `captures/seed42/`. It includes the driven routes and
per-edge exit times in `realized.rou.xml`, warnings, bus-stop definitions,
the copied SUMO configuration, and `seed.txt`. All simulation outputs,
including detector outputs, stay in that folder. Source files are unchanged.
Another seed produces another folder, for example `--seed 43`.

## Extract a window

```bash
python3 extract.py \
  --capture captures/seed42 \
  --start 10:00 --end 10:30 \
  --output output/ingolstadt21_10_30
```

Times use `HH:MM`. Change them to select another window, including one longer
than 30 minutes. Use a new output directory for each extraction.

The extractor always:

- Keeps only each original trip's first local visit. Later re-entries are
  discarded, including when the first visit was before the chosen window.
- Selects trips by their local entry time. The start is inclusive and the end
  exclusive. Local time zero is the selected start; there is no warm-up.
- Preserves the observed human route with probability 1. It does not bridge
  excursions outside the area or regenerate human routes.
- Excludes teleported trajectories, unfinished local visits, and routes that
  are invalid on the fixed target network.
- Requires six suitable alternative routes for a learning-agent OD. Other
  passenger trips, buses, and vehicles with observed stops stay fixed background.
- Omits station stops from exported buses. They follow their fixed routes
  without station dwell time. Other observed lane stops are retained.

The six-route search uses legal passenger connections, no repeated junctions,
a cost limit of `1.5 × fastest free-flow time + 30 seconds`, and JanuX's rule
of finishing immediately when the destination is next. It stops after at
most 50,000 expansions and uses at most 200 edges per path. Finding fewer
than six paths makes the trip background; its human route is never repaired.
These fixed settings are in `lib/passage_core.py`; the required count is `N_PATHS`
in `extract.py`.

## Output

Network filenames follow the output directory name. For example,
`--output output/ingolstadt21_10_30` produces `ingolstadt21_10_30.net.xml`,
`ingolstadt21_10_30.con.xml`, the other five network XML companions,
`ingolstadt21_10_30_network.png`, and `od_ingolstadt21_10_30.txt`.
The fixed filenames are `agents.csv`, `demand_routes.csv`, and
`background_buses.rou.xml`. The last file contains all fixed background,
including passenger cars. The root still has the same 12-file structure as
`source/target_reference/ingolstadt21`.

The `_extraction/` subfolder contains the provenance CSV, path witnesses,
settings, and a standalone SUMO reference scenario. Exported traffic has no
bus-stop references or additional stop-definition file to load:

```bash
sumo-gui -c output/ingolstadt21_10_30/_extraction/reference.sumocfg
```

That scenario already includes agents and background. It allows two hours
for vehicles to finish after demand stops, uses one-second local steps, and
removes vehicles after a 600-second teleport threshold.

The original full-city `run_intas.py` simulation still uses InTAS's original
bus stops. Removing station stops applies only to the extracted experiments.

For a URB task, copy the whole network folder and load humans from
`demand_routes.csv`. `lib/urb_path_guard.py` supplies fresh bounded AV path
search, a one-time background merge, and background arrival accounting.
The witness paths are not preselected AV actions. An unchanged URB task
that generates its own human routes will not automatically preserve the
recorded human routes.

## Code

```text
extractor/
  README.md
  run_intas.py        # Run the full InTAS scenario with a seed
  extract.py          # Export a selected demand window
  requirements.txt
  lib/                # Shared helpers, optional URB integration, and tests
  source/             # Inputs used by the current pipeline
  archive/            # Old extractor, analyses, and historical inputs
```

`source/` contains `intas_full/`, `target_network/`, and `target_reference/`.
New runs will create `captures/` and `output/` beside these folders.
For URB integration, import helpers from `lib.urb_path_guard` after adding
this project directory to the task's Python path.

Dependencies: `python3 -m pip install -r requirements.txt`.
The optional URB adapter also uses pandas, already in the URB environment.
Tests: `python3 -m pytest -q lib/tests`.
