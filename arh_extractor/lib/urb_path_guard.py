"""Small helpers for using the extracted demand in a URB task."""
from pathlib import Path
from types import MethodType

from lxml import etree as ET

from .passage_core import find_paths, load_network


def generate_for_od(directory, origin, destination, number_of_paths=6):
    """Generate fresh AV alternatives with the extractor's bounded search."""
    import pandas as pd
    directory = Path(directory).resolve()
    network = load_network(directory / f"{directory.name}.net.xml")
    paths = find_paths(network, origin, destination, number_of_paths)
    if len(paths) < number_of_paths:
        raise ValueError(f"Could not find {number_of_paths} suitable routes: {origin} -> {destination}")
    return pd.DataFrame([{"origins": origin, "destinations": destination, "path": ",".join(path),
                          "free_flow_time": sum(network.costs[edge] for edge in path) / 60} for path in paths])


def attach_background(directory, route_file):
    """Call once after generating routes and before starting SUMO."""
    directory = Path(directory)
    tree = ET.parse(str(route_file))
    root = tree.getroot()
    fixed = ET.parse(str(directory / "background_buses.rou.xml")).getroot()
    ids = {vehicle.get("id") for vehicle in fixed.findall("vehicle")}
    root.extend(fixed)
    vehicles = root.findall("vehicle")
    for vehicle in vehicles:
        root.remove(vehicle)
    root.extend(sorted(vehicles, key=lambda vehicle: (float(vehicle.get("depart")), vehicle.get("id"))))
    tree.write(str(route_file), encoding="UTF-8", xml_declaration=True, pretty_print=True)
    return ids


def install_background_accounting(simulator, background_ids):
    """Exclude fixed vehicles from learner results and share the stuck timer."""
    background_ids = set(map(str, background_ids))
    regular_step = simulator.step

    def step(current):
        if not current.use_sumo_teleport:
            for identifier in current.sumo_connection.simulation.getDepartedIDList():
                if identifier in background_ids:
                    current.waiting_vehicles.setdefault(identifier, 0)
        timestep, stopped, arrivals, teleported = regular_step()
        return (timestep, stopped, [i for i in arrivals if i not in background_ids],
                [i for i in teleported if i not in background_ids])

    simulator.step = MethodType(step, simulator)
