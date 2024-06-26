
from pyrosm import OSM
import geopandas as gpd
import pandas as pd
import networkx as nx
import osmnx as ox
from shapely.geometry import Point
import matplotlib.pyplot as plt
import alphashape
from faker import Faker
import time
from tqdm import tqdm
import uuid
import warnings

def load_osm_network(file_path:str, network_type:str, graph_type:str):
    """ Load an OSM file and extract the network (driving, walking etc) as a graph (e.g. networkx graph) along with its nodes and edges.
    G, nodes, edges = load_osm_network(args) to extract.
    
    Returns: 
    --------
    G (MultiDiGraph), nodes (gdf) and edges (gdf)
    
    Parameters:
    -----------
    - file_path (str): File path of OSM road data, a .pbf file.
    - network_type (str): Type of transport, e.g. driving, walking, cycling.
    - graph_type: Type of graph to create, available types: networkx, pandana, igraph. Likely choose networkx for use with rest of the methods.
    
    Example:
    ---------
    
    >>> roads = 'file/path/roads.pbf'
    >>> G, nodes, edges = services.network_bands.load_osm_network(file_path = roads, network_type = 'driving', graphy_type = 'networkx')
    >>> print(G)
    >>> 'MultiDiGraph named Made with Pyrosm library. with 222854 nodes and 440792 edges'
    >>> print(len(nodes), len(edges))
    >>> '225125 233911'
    """

    osm = OSM(file_path)
    nodes, edges = osm.get_network(network_type=network_type, nodes=True)
    G = osm.to_graph(nodes, edges, graph_type=graph_type)
    
    return G, nodes, edges

def csv_to_gdf(csv, x_col:str, y_col:str, input_crs:int, crs_conversion:int = None):
    """ function to convert csv to a gdf based off X, Y coordinates and input CRS, with an optional CRS conversion.
    
    Returns:
    --------
    GeoDataFrame (Geopandas GeoDataFrame) of input locations.
    
    Parameters:
    -----------
    - csv: source data as csv with geom x and y column separate.
    - x_col (str): column name for the x coordinate.
    - y_col (str): str, column name for the y coordinate.
    - input_crs (int): int, EPSG code for input coordinate reference system.
    - crs_conversion (int):optional EPSG code for converting CRS.
    
    Example:
    --------
    
    >>> csv_path = 'file/path/data.csv'
    >>> locations = services.network_bands.csv_to_gdf(csv = csv_path, x_col = 'X', y_col = 'Y', 
    >>>                                               input_crs = 29902, crs_conversion = 4326)
    >>> locations.head()
    >>> name     X      Y            geometry
    >>> charlie  331131 376131 POINT (-5.97089 54.61635)
    """
    #create a list for each row of geom by zipping and turn into a point tuple
    try:
        csv['geometry'] = list(zip(csv[x_col], csv[y_col]))
        csv['geometry'] = csv['geometry'].apply(Point)
        # Convert to GeoDataFrame
        gdf = gpd.GeoDataFrame(csv, geometry='geometry', crs=f'EPSG:{input_crs}')
        #Only converts if specified
        if crs_conversion:
            gdf = gdf.to_crs(epsg=crs_conversion)
            
        #adds a uuid - useful to avoid duplicates.
        uuid_list = []
        for i in range(len(gdf)):
            new_uuid = uuid.uuid4()
            uuid_list.append(new_uuid)
        gdf['uuid'] = uuid_list
        
        return gdf
    except Exception:
        print(f'Exception error: {Exception}')
        
        
def nearest_node_and_name(graph, locations: gpd.GeoDataFrame, location_name: str = None, 
                          anon_name: bool = False):
    """ Creates a dictionary of location names and nearest node on Graph. If no location name column specified, creates a list.
    Anonymised naming can be enabled by not inputting location_name and anon_name = True. This also forces a dictionary type if you only have point data.
    
    Returns:
    --------
    Dictionary (dict) of points and nearest node id on the graph.
    
    Parameters:
    -----------
        graph (networkx.Graph): The graph representing the network.
        locations (GeoDataFrame): Geopandas GeoDataFrame of start locations.
        location_name (str): Optional; column storing name of location, if no column name do not specify.
        anon_name (bool): If True, generates fake names, location_name doesn't have to be specified.
        
    Example:
    --------
    
    >>> name = gdf['name']
    >>> node_dict = services.network_bands.nearest_node_and_name(graph = G, locations = gdf, location_name = name
    >>>                                                          anon_name = False)
    >>> print(node_dict)
    >>>  {'Ardoyne Library': {'nearest_node': 475085580},
    >>> 'Ballyhackamore Library': {'nearest_node': 73250694},
    >>> 'Belfast Central Library': {'nearest_node': 4513699587}}
    
    """   
    # Initialise service_xy based on the presence of location_name
    service_xy = {}
    
    # Generate fake names if required. Anonymised naming. Also forces a workaround forcing dictionary if no name data, 
    # could just use uuid though. Bit experimental
    if location_name is None and anon_name:
        fake = Faker()
        fake_names = []
        
        for i in range(len(locations)):
            fake_names.append(fake.city())
            
        locations['Fake Name'] = fake_names
        location_name = 'Fake Name' 
        
    # Calculate the nearest note for each location
    for index, row in tqdm(locations.iterrows(), total=locations.shape[0], desc="Processing start locations"):
        location_x = row['geometry'].x
        location_y = row['geometry'].y
        nearest_node = ox.distance.nearest_nodes(graph, location_x, location_y)
        
        # Add nearest node name to service_xy, no location name specified, location_{index} is the name
        if location_name:
            name = row[location_name]
            service_xy[name] = {'nearest_node': nearest_node}        
        else:
            name = f"location_{index}"
        
        service_xy[name] = {'nearest_node': nearest_node}

    return service_xy



def service_areas(nearest_node_dict:dict, graph, search_distances:list, alpha_value:int, weight:str, 
                  save_output:bool = False):
    """
    Generates a GeoDataFramecontaining polygons of service areas calculated using Dijkstra's shortest path algorithm within a networkx graph. 
    Each polygon represents a service area contour defined by a maximum distance from a source node.

    Returns:
    --------
    Polygons in a GeoDataFrame.
    
    Parameters:
    -----------
        nearest_node_dict (dict): A dictionary with names as keys and the nearest node on the graph as values. This is an output from the `nearest_node_and_name` function.
        graph (networkx.Graph): The graph representing the network, often designated as `G` in networkx.
        cutoffs (list of int): Distances in meters that define the bounds of each service area.
        alpha_value (int): The alpha value used to create non-convex polygons via the alphashape method.
        weight (str): The edge attribute in the graph to use as a weight, e.g. 'length', 'speed' etc.
        progress (bool): If True, will print progress of the function.
        save_output (bool): If True, will save output as `service_areas.gpkg` to root folder.
    
    Example:
    --------
    >>> node_dict = services.network_bands.nearest_node_and_name(...)
    >>> dist_list = [1000, 2000, 3000]
    >>> polygon = services.network_bands.service_areas(nearest_node_dict = node_dict, graph = G, search_distances = dist_list
                                                       alpha_value = 500, weight = 'length', progress = False, save_output = True)
    >>> 'service area polygons have been successfully saved to a geopackage'
    """

    data_for_gdf = []

    print(f'Creating network service areas of sizes: {search_distances} metres')    
    #For each start location [name] creates a polygon around the point.
    for index, (name, node_info) in tqdm(enumerate(nearest_node_dict.items()), total=len(nearest_node_dict), desc='Processing nodes'):        
        # print(f'Processing: location {index+1} of {len(nearest_node_dict)}: {name}. ')
        #cycle through each distance in list supplied creating service areas for each
        for distance in tqdm(search_distances, total=len(search_distances), desc=f'Processing: location {index+1} of {len(nearest_node_dict)}: {name} : '):
            #Extract nearest node to the name (start location)
            nearest_node = node_info['nearest_node']
            subgraph = nx.single_source_dijkstra_path_length(graph, nearest_node, cutoff=distance, weight = weight)
            
            #Creates a list of all nodes which are reachable within the cutoff.
            reachable_nodes = list(subgraph.keys())
            node_points_list = []
            for node in reachable_nodes:
                x = graph.nodes[node]['x']
                y = graph.nodes[node]['y']
                node_points_list.append(Point(x, y))

            # Makes the x,y values into just a list of tuples to be used to create alphashapes
            node_point_series_tuples = (pd.Series(node_points_list)).apply(lambda point: (point.x, point.y))
            node_point_tuple_list = node_point_series_tuples.tolist()
            
            #Create an alpha shape for each polygon and append to dataframe.
            alpha_shape = alphashape.alphashape(node_point_tuple_list, alpha_value)
            data_for_gdf.append({'name': name, 'distance':distance, 'geometry': alpha_shape})
            # service_areas_dict[name] = alpha_shape #uncomment to check if function returns correct variables

    gdf_alpha = gpd.GeoDataFrame(data_for_gdf, crs= 4326)
    
    if save_output:
        gdf_alpha.to_file('service_areas.gpkg')
        print(f'service area polygons have been successfully saved to a geopackage')
     #return the geodataframe
    return gdf_alpha


def service_bands(geodataframe:gpd.GeoDataFrame, dissolve_cat:str, aggfunc:str ='first', 
                          show_graph:bool = False, save_output:bool = False):
    """ 
    Dissolves polygons in a GeoDataFrame by category type; useful for creating clean network service areas. Currently only supports dissolve categories which are buffer area integers.
    
    Returns:
    --------
    Dissolved polygons in a GeoDataFrame.
    
    Parameters:
    -----------
        geodataframe (gpd.GeoDataFrame): Geopandas Data Frame, can use the output of network_bands.service_aras().
        dissolve_cat (str): Column to dissolve dataframe by.
        aggfunc (func or str): Same as geopandas aggfunc aggregation. Defaults to first.
        show_graph (bool): If true, will show a basic graph of output. Defaults to False.
        save_output (bool): If True, will save output as `service_areas.gpkg` to root folder. Defaults to False.
        
    Example:
    --------
    
    >>> service_areas = services.network_bands.service_areas(...)
    >>> polygon = services.network_bands.service_bands(geodataframe = service_areas, dissolve_cat = 'distance',
    >>>                                                aggfunc = 'first', show_graph = True, save_output = True)
    >>> 'A map showing network contours has been created.'
    
        """
        
        #Smallest first, e.g. 1000, then 2000, then 3000
    data_for_gdf = []
    differenced_geoms = []
    category_values = []
    #Subset dataframe by dissolve category then run dissolve, dissolving and then subsetting creates invalid geoms.
    search_distances = geodataframe[dissolve_cat].unique()
    for distance in search_distances:
        filtered_data = geodataframe[geodataframe[dissolve_cat] == distance].reset_index(drop=True)
        filtered_data_dissolved = filtered_data.dissolve(aggfunc=aggfunc)
        data_for_gdf.append(filtered_data_dissolved)
    #Create gdf for each dissolved category
    gdf_dissolve = gpd.GeoDataFrame(pd.concat(data_for_gdf, ignore_index=True), crs='EPSG:4326')
    
    #sort data so that the smallest area which cannot be differenced is exluded.
    #iterates so that the larger area which is a lower indexis differenced by the geom above it.
    #note to self: next step to make it work without dissolving prior.
    gdf_dissolve_sorted = gdf_dissolve.sort_values(by=dissolve_cat, ascending=False)
    for index in range(0,len(gdf_dissolve_sorted)-1):
        differenced_part = gdf_dissolve_sorted.geometry.iloc[index].difference(gdf_dissolve_sorted.geometry.iloc[index+1])
        differenced_geoms.append(differenced_part)
        category_values.append(gdf_dissolve_sorted.iloc[index][dissolve_cat])

    #append the smallest geom as this is excluded from the dissolve difference loop.
    final_index = (len(gdf_dissolve_sorted)-1)
    differenced_geoms.append(gdf_dissolve_sorted.iloc[final_index]['geometry'])
    category_values.append(gdf_dissolve_sorted.iloc[final_index][dissolve_cat])
    #append geometry to geodataframe to return as final result
    differenced_gdf = gpd.GeoDataFrame({'geometry': differenced_geoms, dissolve_cat: category_values}, crs=geodataframe.crs)
    print('Network areas have successfully been dissolved and differenced')
    #produces a quick and ready map for instant analysis.
    if show_graph:
        fig, ax = plt.subplots(1, 1, figsize=(10, 8))
        differenced_gdf.plot(column=dissolve_cat, cmap='cividis', alpha=0.8, ax=ax, legend=True,
                                legend_kwds={'label': dissolve_cat, 'orientation': 'horizontal',
                                            'fraction': 0.036})
        plt.autoscale(enable=True, axis='both', tight=True)
        plt.show()
        print('A map showing network contours has been created.')
    
    if save_output:
        differenced_gdf.to_file('service_bands.gpkg')
        print(f'service area polygons have been successfully saved to a geopackage')    
    return differenced_gdf



def shortest_path_iterator(start_locations:gpd.GeoDataFrame, destination_locations:gpd.GeoDataFrame, networkx_graph):
    """ Shortest distance to destination using dijkstra's algorithm. The function iterates over destination for 
    each start location, returning a dataframe with the closest destination. 
    
    WARNING - TAKES A VERY LONG TIME - advised to not use!
    
    Paramters:
        start_locations (GeoDataFrame): geopandas DataFrame of start locations such as houses.
        destination_dataset (GeoDatFrame): geopandas DataFrame of end locations such as hospitals or supermarkets.
        network_x_graph (MultiDiGraph): graph created using networkx. Default 'G'.
        
    Example:
    --------
    
    >>> shortest_path_iterator(start_locations = house_data, destination_locations = hospitals, networkx_graph = G)
    """
    #warning.
    
    if len(start_locations) >= 100 or len(destination_locations) >= 100:
        warnings.warn('Your dataset is quite large, this may take an incredibly long time to process. ' 
            'Consider using the service_areas function instead for more efficient computation.',
            UserWarning)
    else:
        warnings.warn("Iterating over large datasets takes a very long time. To stop the process, interrupt with a keyboard command such as Ctrl+C.",
            UserWarning)
    
    #Preload the nearest nodes to destination to reduce insane run times using nearest_node_and_name function into a nameless dict
    print(f'Calculating the nearest node on the network graph for each start location')
    dest_node_ids = nearest_node_and_name(graph= networkx_graph, locations=destination_locations)
    
    start_locations['shortest_dist_to_dest'] = float('inf')
    #iterate over each house, then library.

    for index, row in tqdm(start_locations.iterrows(), total=len(start_locations), desc=f"Calculating and identifying the shortest path between each start location and the nearest of the destination locations"):
        orig_x = row['geometry'].x
        orig_y = row['geometry'].y       
        orig_node_id = ox.distance.nearest_nodes(networkx_graph, orig_x, orig_y)
        

        # iterate over destination node id dictionary for shortest distance out of all desitnations
        shortest_distance = float('inf')

        for dest_name, dest_info in dest_node_ids.items():
            dest_node_id = dest_info['nearest_node']  # gets the node ID

            path_length = nx.shortest_path_length(networkx_graph, source=orig_node_id, target=dest_node_id, weight='length')
            if path_length < shortest_distance:
                shortest_distance = path_length

        # Updates the shortest distance in the gdf
        start_locations.at[index, 'shortest_dist_to_dest'] = shortest_distance
        
    return start_locations
        
        
        
