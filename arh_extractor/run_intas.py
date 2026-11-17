#!/usr/bin/env python3
"""Run the original full-day InTAS scenario and save its driven routes."""
import argparse
import subprocess
from pathlib import Path

from lxml import etree as ET

HERE = Path(__file__).resolve().parent
SCENARIO = HERE / "source/intas_full/InTAS-master/scenario"


def run(seed, directory, end=86400):
    directory = Path(directory).resolve()
    directory.mkdir(parents=True)
    config = ET.parse(str(SCENARIO / "InTAS_buildings.sumocfg"))

    for option in ("net-file", "route-files"):
        item = config.find(f"input/{option}")
        item.set("value", ",".join(str(SCENARIO / name) for name in item.get("value").split(",")))

    # Detector output paths are inside the additional files themselves.
    additional = config.find("input/additional-files")
    files = []
    for name in additional.get("value").split(","):
        tree = ET.parse(str(SCENARIO / name))
        for item in tree.xpath("//*[@file]"):
            item.set("file", str(directory / Path(item.get("file")).name))
        path = directory / name
        tree.write(str(path), encoding="UTF-8", xml_declaration=True)
        files.append(str(path))
    additional.set("value", ",".join(files))

    for item in config.findall("output/*"):
        item.set("value", str(directory / Path(item.get("value")).name))
    config.find("report/log").set("value", str(directory / "sumo.log"))
    config.find("report/no-warnings").set("value", "false")
    config.find("time/end").set("value", str(end))
    random = ET.SubElement(config.getroot(), "random_number")
    ET.SubElement(random, "seed", value=str(seed))
    path = directory / "intas.sumocfg"
    config.write(str(path), encoding="UTF-8", xml_declaration=True)

    print(f"Running InTAS, seed {seed}: {directory}", flush=True)
    subprocess.run([
        "sumo", "-c", str(path),
        "--vehroute-output", "realized.rou.xml",
        "--vehroute-output.exit-times", "true",
        "--vehroute-output.internal", "true",
        "--vehroute-output.last-route", "true",
        "--vehroute-output.write-unfinished", "true",
        "--error-log", "warnings.log", "--aggregate-warnings", "-1",
    ], cwd=directory, check=True)
    (directory / "seed.txt").write_text(f"{seed}\n")
    print(f"Capture saved: {directory}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seed", type=int, required=True)
    args = parser.parse_args()
    run(args.seed, HERE / "captures" / f"seed{args.seed}")
