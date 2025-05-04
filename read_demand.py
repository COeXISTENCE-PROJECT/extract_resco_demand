import janux as jx
import networkx as nx

import warnings
warnings.filterwarnings("ignore", category=RuntimeWarning)

from utils import *

if __name__ == "__main__":
    
    TRY_UP_TO_NUM_PATHS = 5
    TIMEOUT = 10
    
    """
    Read Demand XML
    """
    demand_rou_file = "data/ingolstadt21.rou.xml"
    connection_file = "data/ingolstadt.con.xml"
    edge_file = "data/ingolstadt.edg.xml"
    route_file = "data/ingolstadt.rou.xml"

    df = parse_trips(demand_rou_file)

    """
    Reformat DataFrame
    """
    # Scale departure times
    df["depart"] = df["depart"].astype(float)
    df["depart"] = df["depart"].astype(int)
    df["depart"] = df["depart"] - min(df["depart"])
    # Fix IDs
    df["id"] = df.index
    # Add kind column
    df["kind"] = "Human"
    # Rename columns
    df.rename(columns={"depart": "start_time"}, inplace=True)
    df.rename(columns={"from": "origin"}, inplace=True)
    df.rename(columns={"to": "destination"}, inplace=True)
    # Drop unnecessary columns
    df.drop(columns=["type"], inplace=True)

    
    # Build network
    network = jx.build_digraph(connection_file, edge_file, route_file)


    """
    Filter out undesirable trips
    """
    # Remove isolated nodes
    print("Removing trips with inaccessible origins or destinations...")

    origins, destinations = df["origin"].unique(), df["destination"].unique()
    bad_origins, bad_destinations = [], []

    # origins with no outlinks
    for origin in origins:
        paths_from_origin = nx.multi_source_dijkstra_path(network, [origin])
        del paths_from_origin[origin]
        if len(paths_from_origin) == 0:
            bad_origins.append(origin)
    
    # inaccessible destinations       
    for destination in destinations:
        paths_from_destination = nx.multi_source_dijkstra_path(network.reverse(), [destination])
        del paths_from_destination[destination]
        if len(paths_from_destination) == 0:
            bad_destinations.append(destination)
            
    for idx, row in df.iterrows():
        if row["origin"] in bad_origins or row["destination"] in bad_destinations:
            df.drop(idx, inplace=True)
            
    print(f"Deleted {len(bad_origins)} origins and {len(bad_destinations)} destinations")

    # Remove same OD demands
    print("Removing trips with identical origin and destination...")
    counter = 0
    for idx, row in df.iterrows():
        if row["origin"] == row["destination"]:
            df.drop(idx, inplace=True)
            counter += 1
    print(f"Deleted {counter} trips with identical origin and destination")

    # Reset indices
    df.reset_index(drop=True, inplace=True)
    df["id"] = [i for i in range(len(df))]

    """
    - We cannot generate multiple routes for some of the trips.
    - Therefore, they are not suitable for route choice.
    - We will remove these trips from the demand.
    - We will use JanuX for this purpose, see: ```https://github.com/COeXISTENCE-PROJECT/JanuX```.
    - JanuX assumes that it is always possible to find desired number of routes between any two nodes.
    - However, this is not the case in our network.
    
    We will use the following approach:
    1. For increasing number of paths, we will try to find the routes.
    2. For each trip, we will try to find the routes.
    3. If we cannot find the routes before a predefined timeout, we will remove the trip from the demand.
    4. We will repeat this process for all trips.
    """
    
    bad_demand = set()
    counter = 0

    for num_paths in range(TRY_UP_TO_NUM_PATHS):
        results = route_gen_process(network, df, num_paths+1, timeout=TIMEOUT)
        for idx, row in df.iterrows():
            if (row["origin"], row["destination"]) in results:
                df.drop(idx, inplace=True)       
                counter += 1
        for d in results:
            bad_demand.add(d)
        
    bad_demand = list(bad_demand)
    print(f"\nOverall bad demands: {bad_demand}")
    print(f"Deleted {counter} trips with bad demand")
            
    # Reset indices
    df["id"] = [i for i in range(len(df))]
    df.reset_index(drop=True, inplace=True)

    """
    Reformat and save data for URB.
    Following lines can be modified to save the data in a different format.
    """

    # Convert origin and destination names to indices
    origin_indices = {origin_name : idx for idx, origin_name in enumerate(df["origin"].unique())}
    destination_indices = {destination_name : idx for idx, destination_name in enumerate(df["destination"].unique())}
    origin_names = {value: key for key, value in origin_indices.items()}
    destination_names = {value: key for key, value in destination_indices.items()}

    for idx, row in df.iterrows():
        df.at[idx, "origin"] = origin_indices[row["origin"]]
        df.at[idx, "destination"] = destination_indices[row["destination"]]

    # Save the demand data to a CSV file
    df.to_csv("agents.csv", index=False)
    print("Agents saved to agents.csv")

    # We saved trip origin and destinations by their indices.
    # Now we need to save their edge IDs, ordered by their indices.
    # This will be resolved by `URB` scripts appropriately.
    keys = [k for k in origin_names.keys()]
    origins = [origin_names[k] for k in keys]
    keys = [k for k in destination_names.keys()]
    destinations = [destination_names[k] for k in keys]
    
    filename = f"od_ingolstadt_custom.txt"
    with open(filename, 'w') as f:
        f.write("{\n")
        f.write(f"\"origins\" : {origins},\n")
        f.write(f"\"destinations\" : {destinations},\n")
        f.write("}")
    print(f"OD pairs are saved to {filename}")
    
    print("Done.")
    print("--------------------------------------------------")


