"""The fixed road graph, six-route search, and first local passage."""
import heapq
from dataclasses import dataclass, field

import networkx as nx
import sumolib


@dataclass
class Network:
    graph: nx.DiGraph
    bus_graph: nx.DiGraph
    costs: dict
    nodes: dict


def load_network(path):
    net = sumolib.net.readNet(str(path), withInternal=False)
    edges = sorted(net.getEdges(), key=lambda edge: edge.getID())
    costs = {edge.getID(): edge.getLength() / edge.getSpeed() for edge in edges}
    nodes = {edge.getID(): (edge.getFromNode().getID(), edge.getToNode().getID()) for edge in edges}
    graphs = []
    for kind in ("passenger", "bus"):
        graph = nx.DiGraph()
        graph.add_nodes_from(edge.getID() for edge in edges if edge.allows(kind))
        for source in edges:
            for target, connections in source.getOutgoing().items():
                if source.getID() in graph and target.getID() in graph:
                    if any(c.getFromLane().allows(kind) and c.getToLane().allows(kind) for c in connections):
                        graph.add_edge(source.getID(), target.getID(), travel_time=costs[target.getID()])
        graphs.append(graph)
    return Network(*graphs, costs, nodes)


def valid_route(route, graph):
    return all(edge in graph for edge in route) and all(graph.has_edge(a, b) for a, b in zip(route, route[1:]))


def find_paths(network, origin, destination, count=6):
    """Find short, distinct routes without repeated junctions.

    Match JanuX's rule of finishing immediately when the destination is next.
    The expansion cap keeps unsuitable ODs from causing an endless search.
    """
    graph = network.graph
    remaining = nx.single_source_dijkstra_path_length(graph.reverse(copy=False), destination, weight="travel_time")
    if origin not in remaining or network.nodes[origin][0] == network.nodes[origin][1]:
        return []
    shortest = network.costs[origin] + remaining[origin]
    limit = 1.5 * shortest + 30
    queue = [(shortest, (origin,), network.costs[origin], frozenset(network.nodes[origin]))]
    paths = []
    for _ in range(50000):
        if not queue:
            break
        bound, route, cost, visited = heapq.heappop(queue)
        if bound > limit:
            break
        current = route[-1]
        if current == destination:
            paths.append(list(route))
            if len(paths) == count:
                break
            continue
        if len(route) >= 200:
            continue
        following = [destination] if graph.has_edge(current, destination) else graph.successors(current)
        for edge in following:
            junction = network.nodes[edge][1]
            if junction in visited or edge not in remaining:
                continue
            next_cost = cost + network.costs[edge]
            bound = next_cost + remaining[edge]
            if bound <= limit:
                heapq.heappush(queue, (bound, route + (edge,), next_cost, visited | {junction}))
    return paths


@dataclass
class Passage:
    source_id: str
    kind: str
    entry: float
    exit: float
    edges: tuple
    stops: list = field(default_factory=list)
    depart_pos: str | None = None
    arrival_pos: str | None = None


def first_passage(vehicle, area):
    """Return the first complete visit; never promote a later re-entry."""
    route = vehicle.find("route")
    edges = route.get("edges").split()
    exits = [float(value) for value in route.get("exitTimes").split()]
    local = []
    for i, (edge, exit_time) in enumerate(zip(edges, exits)):
        if exit_time < 0:
            return None
        if edge.startswith(":"):
            continue
        if edge in area:
            local.append(i)
        elif local:
            break
    else:
        if float(vehicle.get("arrival", "-1")) < 0:
            return None
    if not local:
        return None
    begin, end = local[0], local[-1]
    entry = float(vehicle.get("depart")) if begin == 0 else exits[begin - 1]
    passage = Passage(vehicle.get("id"), "bus" if vehicle.get("type") == "bus" else "passenger",
                      entry, exits[end], tuple(edges[i] for i in local))
    for stop in vehicle.findall("stop"):
        if stop.get("busStop"):
            continue
        started, ended = float(stop.get("started", "-1")), float(stop.get("ended", "-1"))
        edge = stop.get("lane", "").rsplit("_", 1)[0]
        if entry <= started <= ended <= passage.exit and edge in passage.edges:
            attrs = {key: stop.get(key) for key in ("lane", "startPos", "endPos", "friendlyPos") if stop.get(key) is not None}
            passage.stops.append(attrs | {"duration": format(ended - started, ".10g")})
    if begin == 0:
        passage.depart_pos = vehicle.get("departPos")
    if end == len(edges) - 1:
        passage.arrival_pos = vehicle.get("arrivalPos")
    return passage
