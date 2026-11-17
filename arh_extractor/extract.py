#!/usr/bin/env python3
"""Extract first InTAS passages into the fixed URB ingolstadt21 network."""
import argparse
import csv
import json
import math
import re
import shutil
from pathlib import Path

from lxml import etree as ET

from lib.passage_core import find_paths, first_passage, load_network, valid_route

HERE = Path(__file__).resolve().parent
TARGET = HERE / "source/target_network"
REFERENCE = HERE / "source/target_reference/ingolstadt21"
N_PATHS = 6


def clock(value):
    hours, minutes = map(int, value.split(":"))
    return hours * 3600 + minutes * 60


def write_csv(path, columns, rows):
    with path.open("w", newline="") as file:
        writer = csv.writer(file)
        writer.writerow(columns)
        writer.writerows(rows)


def write_xml(path, root):
    ET.ElementTree(root).write(str(path), encoding="UTF-8", xml_declaration=True, pretty_print=True)


def vehicle_xml(identifier, passage, start, agent=False):
    kind = "Human" if agent else f"background_{passage.kind}"
    depart = math.floor(passage.entry - start) if agent else format(passage.entry - start, ".12g")
    vehicle = ET.Element("vehicle", id=str(identifier), type=kind, depart=str(depart))
    if not agent:
        vehicle.set("departLane", "best")
        for name, value in (("departPos", passage.depart_pos), ("arrivalPos", passage.arrival_pos)):
            if value is not None:
                vehicle.set(name, value)
    ET.SubElement(vehicle, "route", edges=" ".join(passage.edges))
    for stop in passage.stops:
        ET.SubElement(vehicle, "stop", **stop)
    ET.SubElement(vehicle, "param", key="source_id", value=passage.source_id)
    return vehicle


def write_export(directory, agents, background, start, end, seed, network, options):
    name = directory.resolve().name
    directory.mkdir(parents=True)
    support = directory / "_extraction"
    support.mkdir()
    for suffix in ("net.xml", "rou.xml", "con.xml", "edg.xml", "nod.xml", "tll.xml", "typ.xml"):
        # JanuX's .rou.xml input contains network lane attributes.
        source = "net.xml" if suffix == "rou.xml" else suffix
        shutil.copyfile(TARGET / f"ingolstadt_custom2.{source}", directory / f"{name}.{suffix}")
        if suffix in ("net.xml", "rou.xml", "tll.xml"):
            exported = directory / f"{name}.{suffix}"
            tree = ET.parse(str(exported))
            for light in tree.iter("tlLogic"):
                light.set("type", "actuated")
            tree.write(str(exported), encoding="UTF-8", xml_declaration=True)
    shutil.copyfile(REFERENCE / "ingolstadt21_network.png", directory / f"{name}_network.png")

    origins = list(dict.fromkeys(p.edges[0] for p in agents))
    destinations = list(dict.fromkeys(p.edges[-1] for p in agents))
    oi = {edge: i for i, edge in enumerate(origins)}
    di = {edge: i for i, edge in enumerate(destinations)}
    write_csv(directory / "agents.csv", ["id", "start_time", "origin", "destination", "kind"],
              [(i, math.floor(p.entry - start), oi[p.edges[0]], di[p.edges[-1]], "Human") for i, p in enumerate(agents)])
    (directory / f"od_{name}.txt").write_text(json.dumps({"origins": origins, "destinations": destinations}, indent=2) + "\n")
    write_csv(directory / "demand_routes.csv", ["agent_id", "source_id", "route_id", "probability", "free_flow_time", "edges"],
              [(i, p.source_id, 0, 1, format(sum(network.costs[e] for e in p.edges), ".15g"), " ".join(p.edges)) for i, p in enumerate(agents)])

    fixed = ET.Element("routes")
    ET.SubElement(fixed, "vType", id="background_bus", vClass="bus", color="green")
    ET.SubElement(fixed, "vType", id="background_passenger", vClass="passenger")
    for i, passage in enumerate(background, 1_000_000):
        fixed.append(vehicle_xml(i, passage, start))
    write_xml(directory / "background_buses.rou.xml", fixed)

    reference = ET.Element("routes")
    ET.SubElement(reference, "vType", id="Human", vClass="passenger")
    reference.extend(ET.fromstring(ET.tostring(item)) for item in fixed)
    reference.extend(vehicle_xml(i, p, start, agent=True) for i, p in enumerate(agents))
    vehicles = reference.findall("vehicle")
    for vehicle in vehicles:
        reference.remove(vehicle)
    reference.extend(sorted(vehicles, key=lambda v: (float(v.get("depart")), v.get("id"))))
    write_xml(support / "reference_demand.rou.xml", reference)

    (support / "reference.sumocfg").write_text(f'''<configuration>
  <input>
    <net-file value="../{name}.net.xml"/>
    <route-files value="reference_demand.rou.xml"/>
  </input>
  <time><begin value="0"/><end value="{end - start + 7200}"/><step-length value="1"/></time>
  <processing><time-to-teleport value="600"/><time-to-teleport.remove value="true"/></processing>
  <random_number><seed value="{seed}"/></random_number>
  <output><statistic-output value="reference.statistics.xml"/><tripinfo-output value="reference.tripinfo.xml"/></output>
  <report><no-step-log value="true"/></report>
</configuration>
''')
    rows = [(p.source_id, p.entry, p.exit, p.edges[0], p.edges[-1], role, i + offset)
            for role, passages, offset in (("agent", agents, 0), ("background", background, 1_000_000))
            for i, p in enumerate(passages)]
    write_csv(support / "passages.csv", ["source_id", "entry", "exit", "origin", "destination", "role", "export_id"], rows)
    witnesses = [{"origin": o, "destination": d, "paths": paths} for (o, d), paths in options.items()]
    (support / "od_feasibility.json").write_text(json.dumps(witnesses, indent=2) + "\n")
    settings = {"seed": seed, "start": start, "end": end, "required_paths": N_PATHS, "station_stops": False,
                "agents": len(agents), "background": len(background)}
    (support / "settings.json").write_text(json.dumps(settings, indent=2) + "\n")


def extract(capture, directory, start, end):
    network = load_network(TARGET / "ingolstadt_custom2.net.xml")
    teleported = set(re.findall(r"Teleporting vehicle '([^']+)'", (capture / "warnings.log").read_text()))
    agents, background, options = [], [], {}
    for _, vehicle in ET.iterparse(str(capture / "realized.rou.xml"), events=("end",), tag="vehicle"):
        if vehicle.get("id") not in teleported:
            passage = first_passage(vehicle, network.costs)
            if passage and start <= passage.entry < end:
                graph = network.bus_graph if passage.kind == "bus" else network.graph
                if valid_route(passage.edges, graph):
                    if passage.kind == "bus" or passage.stops:
                        background.append(passage)
                    else:
                        od = passage.edges[0], passage.edges[-1]
                        if od not in options:
                            options[od] = find_paths(network, *od, count=N_PATHS)
                        (agents if len(options[od]) == N_PATHS else background).append(passage)
        vehicle.clear()
        while vehicle.getprevious() is not None:
            del vehicle.getparent()[0]
    agents.sort(key=lambda p: (p.entry, p.source_id))
    background.sort(key=lambda p: (p.entry, p.source_id))
    seed = int((capture / "seed.txt").read_text())
    write_export(directory, agents, background, start, end, seed, network, options)
    print(f"Saved {len(agents)} agents and {len(background)} background vehicles to {directory}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--capture", type=Path, required=True)
    parser.add_argument("--start", type=clock, default=clock("10:00"), help="HH:MM")
    parser.add_argument("--end", type=clock, default=clock("10:30"), help="HH:MM")
    parser.add_argument("--output", type=Path, default=HERE / "output/ingolstadt21")
    args = parser.parse_args()
    extract(args.capture, args.output, args.start, args.end)
