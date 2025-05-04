import janux as jx
import xml.etree.ElementTree as ET
import signal

import pandas as pd

#########

def parse_trips(xml_file):
    tree = ET.parse(xml_file)
    root = tree.getroot()
    trips_data = []
    for trip in root.findall("trip"):
        trip_info = trip.attrib
        trips_data.append(trip_info)

    return pd.DataFrame(trips_data)

#########

class TimeoutException(Exception):
    pass

def handler(signum, frame):
    raise TimeoutException("Function timed out")

def run_with_timeout(func, timeout, *args, **kwargs):
    signal.signal(signal.SIGALRM, handler)
    signal.alarm(timeout)  # Set the timeout alarm

    try:
        result = func(*args, **kwargs)
        signal.alarm(0)
        return result
    except TimeoutException as e:
        return None
    
#########   
 
def route_gen_process(network, df, num_paths, timeout=10):
    print(f"\nGenerating paths for {num_paths} paths...")
    path_gen_kwargs = {
                "number_of_paths": num_paths,
                "random_seed": 42,
                "num_samples": 20,
                "beta": -5,
                "weight": "time",
                "verbose": False
            }
    
    bad_demand = set()
    for idx, row in df.iterrows():
        print(f"\r{idx}/{len(df)}", end="")
        if (row["origin"], row["destination"]) in bad_demand:
            continue
        # Generate paths with timeout
        try:
            routes = run_with_timeout(jx.extended_generator, timeout, network, [row["origin"]], [row["destination"]], as_df=True, calc_free_flow=True, **path_gen_kwargs)
        except:
            routes = None
        if routes is None:
            bad_demand.add((row["origin"], row["destination"]))
    
    bad_demand  = list(bad_demand)
    print(f"\nBad demands for num_paths {num_paths}: {bad_demand}")
    
    return bad_demand