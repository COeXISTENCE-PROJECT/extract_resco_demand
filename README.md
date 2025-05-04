# Demand conversion from RESCO data for URB

<img src="https://raw.githubusercontent.com/COeXISTENCE-PROJECT/URB/refs/heads/main/docs/urb.png" align="right" width="20%"/>

This repository is dedicated to generating input data for use with [URB](https://github.com/COeXISTENCE-PROJECT/URB).

## Contents

- Ingolstadt demand data ([data/ingolstadt21.rou.xml](data/ingolstadt21.rou.xml)) from [**RESCO**](https://github.com/Pi-Star-Lab/RESCO), with other network files created from [`ingolstadt21.net.xml`](https://github.com/Pi-Star-Lab/RESCO/blob/main/resco_benchmark/environments/ingolstadt21/ingolstadt21.net.xml)
- Script ([read_demand.py](/read_demand.py)) for converting this data into demand data compatible with `URB` and `RouteRL`.

## Output

- `URB` and `RouteRL` compatible demand data for route choice experiments.