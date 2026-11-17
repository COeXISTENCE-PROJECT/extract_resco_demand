import csv
import json
from types import SimpleNamespace

import networkx as nx
import pytest
from lxml import etree as ET

from extract import REFERENCE, TARGET, clock, extract
from lib.passage_core import Network, find_paths, first_passage, load_network
from lib.urb_path_guard import attach_background, generate_for_od, install_background_accounting


def branches():
    graph = nx.DiGraph()
    nodes = {"o": ("start", "split"), "d": ("merge", "end")}
    for i in range(6):
        a, b = f"a{i}", f"b{i}"
        nodes[a], nodes[b] = ("split", f"j{i}"), (f"j{i}", "merge")
        graph.add_edges_from([("o", a), (a, b), (b, "d")], travel_time=1.0)
    return Network(graph, graph.copy(), {edge: 1.0 for edge in nodes}, nodes)


def test_six_distinct_paths():
    paths = find_paths(branches(), "o", "d")
    assert len({tuple(path) for path in paths}) == 6


def test_trivial_ods_do_not_qualify_for_six():
    network = branches()
    network.graph.add_edge("o", "d", travel_time=1.0)
    assert find_paths(network, "o", "d") == [["o", "d"]]
    assert find_paths(network, "o", "o") == [["o"]]


def test_long_detours_do_not_supply_the_sixth_path():
    network = branches()
    network.costs["a5"] = 100
    network.graph["o"]["a5"]["travel_time"] = 100
    assert len(find_paths(network, "o", "d")) == 5


def observed(edges, exits, arrival="100"):
    vehicle = ET.Element("vehicle", id="source", type="car", depart="0", arrival=arrival)
    ET.SubElement(vehicle, "route", edges=" ".join(edges), exitTimes=" ".join(map(str, exits)))
    return vehicle


def test_first_visit_uses_internal_edge_timing_and_discards_reentry():
    vehicle = observed(["outside", ":j", "a", "b", "outside2", "c"], [1, 2, 3, 4, 5, 6])
    passage = first_passage(vehicle, {"a", "b", "c"})
    assert passage.edges == ("a", "b")
    assert passage.entry == 2
    assert passage.exit == 4


def test_unfinished_visit_is_discarded_but_completed_earlier_visit_survives():
    assert first_passage(observed(["a", "b"], [1, -1], arrival="-1"), {"a", "b"}) is None
    vehicle = observed(["a", "outside", "future"], [1, 2, -1], arrival="-1")
    assert first_passage(vehicle, {"a"}).edges == ("a",)


def test_station_stops_are_omitted_and_other_local_stops_are_preserved():
    vehicle = observed(["a", "b", "outside"], [1, 3, 4])
    ET.SubElement(vehicle, "stop", busStop="station", started="1.2", ended="2.5")
    ET.SubElement(vehicle, "stop", lane="b_0", started="1.2", ended="2.5")
    passage = first_passage(vehicle, {"a", "b"})
    assert passage.stops == [{"lane": "b_0", "duration": "1.3"}]


@pytest.mark.parametrize("network_name", ["ingolstadt21", "ingolstadt21_10_30"])
def test_extraction_produces_standard_folder_and_keeps_background_out_of_agents(tmp_path, network_name):
    capture = tmp_path / "capture"
    capture.mkdir()
    network = load_network(TARGET / "ingolstadt_custom2.net.xml")
    origin, destination = "-136728347#4", "201956820"
    route = nx.shortest_path(network.graph, origin, destination, weight="travel_time")
    edge = "124812856#0"
    root = ET.Element("routes")
    for identifier, depart, edges, kind in [("choice", 25, route, "car"), ("trivial", 30, [edge], "car"), ("bus", 30, [edge], "bus"), ("teleported", 35, [edge], "car")]:
        vehicle = ET.SubElement(root, "vehicle", id=identifier, type=kind, depart=str(depart), arrival=str(depart + len(edges)))
        ET.SubElement(vehicle, "route", edges=" ".join(edges), exitTimes=" ".join(str(depart + i + 1) for i in range(len(edges))))
        if kind == "bus":
            ET.SubElement(vehicle, "stop", busStop="station", started="30.2", ended="30.7")
    vehicle = ET.SubElement(root, "vehicle", id="reentry", type="car", depart="10", arrival="30")
    ET.SubElement(vehicle, "route", edges=f"{edge} outside {edge} outside2", exitTimes="11 25 26 30")
    ET.ElementTree(root).write(str(capture / "realized.rou.xml"))
    (capture / "warnings.log").write_text("Teleporting vehicle 'teleported'")
    (capture / "seed.txt").write_text("7\n")
    output = tmp_path / network_name
    extract(capture, output, 20, 60)
    agents = list(csv.DictReader((output / "agents.csv").open()))
    assert len(agents) == 1 and agents[0]["start_time"] == "5"
    routes = list(csv.DictReader((output / "demand_routes.csv").open()))
    assert routes[0]["source_id"] == "choice" and routes[0]["probability"] == "1"
    expected = {p.name.replace("ingolstadt21", network_name) for p in REFERENCE.iterdir() if p.is_file() and not p.name.startswith(".")}
    assert {p.name for p in output.iterdir() if p.is_file()} == expected
    assert (output / f"{network_name}.net.xml").read_bytes() == (TARGET / "ingolstadt_custom2.net.xml").read_bytes()
    assert (output / f"{network_name}.rou.xml").read_bytes() == (output / f"{network_name}.net.xml").read_bytes()
    fixed = ET.parse(str(output / "background_buses.rou.xml")).getroot()
    assert {v.get("id") for v in fixed.findall("vehicle")} == {"1000000", "1000001"}
    assert fixed.find("vehicle/stop") is None
    assert not (output / "_extraction/background_stops.add.xml").exists()
    support = output / "_extraction"
    config = ET.parse(str(support / "reference.sumocfg")).getroot()
    assert config.find("random_number/seed").get("value") == "7"
    assert config.find("input/additional-files") is None
    assert ET.parse(str(support / "reference_demand.rou.xml")).find(".//stop[@busStop]") is None
    assert all((support / item.get("value")).is_file() for item in config.findall("input/*"))
    assert json.loads((support / "settings.json").read_text())["background"] == 2
    assert len(generate_for_od(output, origin, destination)) == 6
    runtime = tmp_path / "runtime.add.xml"
    runtime.write_text('<additional><vType id="Human"/><vType id="AV"/></additional>')
    assert attach_background(output, runtime) == {"1000000", "1000001"}
    merged = ET.parse(str(runtime)).getroot()
    assert len(merged.findall("vehicle")) == 2
    assert merged.find("busStop") is None
    assert merged.find(".//stop[@busStop]") is None


def test_clock_and_background_accounting():
    assert clock("10:30") == 37800
    simulation = SimpleNamespace(getDepartedIDList=lambda: ["1000000", "0"])
    simulator = SimpleNamespace(use_sumo_teleport=False, waiting_vehicles={},
                                sumo_connection=SimpleNamespace(simulation=simulation),
                                step=lambda: (10, None, ["0", "1000000"], ["1000001"]))
    install_background_accounting(simulator, {"1000000", "1000001"})
    assert simulator.step() == (10, None, ["0"], [])
    assert simulator.waiting_vehicles == {"1000000": 0}
