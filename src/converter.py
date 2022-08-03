import matsim
import config
import tools
import pandas as pd
import geopandas as gpd
from geoalchemy2 import Geometry
from shapely.geometry import LineString
import collections

def importVehicles():
    vehicleDataframes = matsim.Vehicle.vehicle_reader(config.PATH_ALLVEHICLE)
    vehicleTypes = vehicleDataframes.vehicle_types
    vehicles = vehicleDataframes.vehicles
    
    # Renamming the columns to match the database
    vehicleTypes.rename(columns={
        'pce':'passengerCarEquivalents',
        'factor': 'flowEfficiencyFactor'
    }, inplace = True)
    
    vehicles.rename(columns={
        'type': 'vehicleTypeId'
    }, inplace = True)
    
    
    # Importing the data to the database
    conn = tools.connectToDatabase()
    vehicleTypes.to_sql('vehicleType', con=conn, if_exists='append', index=False)
    vehicles.to_sql('vehicle', con=conn, if_exists='append', index=False)





def importHouseholds():
    householdReader = matsim.Household.houshold_reader(config.PATH_HOUSEHOLDS)
    householdDataframe = householdReader.households
    
    # Formating dataframe
    householdDataframe.drop(columns=['members'], inplace=True)
    
    # Importing the data to the database
    conn = tools.connectToDatabase()
    householdDataframe.to_sql('household', con=conn, if_exists='append', index=False)





def importPersons():
    personsDataframe = pd.read_csv(config.PATH_PERSONS, sep=';')
    personGeoDataframe = gpd.GeoDataFrame(personsDataframe)
    
    # Renaming the columns to match the database
    personGeoDataframe.rename(columns={
        'person': 'id',
    }, inplace = True)
    
    # Creating a point from first activity coordinates
    personGeoDataframe['first_act_point'] = personGeoDataframe.apply(lambda row: 'POINT({} {})'.format(row['first_act_x'], row['first_act_y']), axis=1)
    personGeoDataframe.drop(columns=['first_act_x', 'first_act_y'], inplace=True)
        
    # Importing the data to the database
    conn = tools.connectToDatabase()
    personGeoDataframe.to_sql('person', con=conn, if_exists='append', index=False, dtype={'first_act_coord': Geometry('POINT', srid=config.DB_SRID)})





# TODO Optimize this function by modifying matsim package
# -> Modify Network.py to return add or modify network reader, to return links links with their attributes in the same dataframe
def importNetworkLinks():
    network = matsim.Network.read_network(config.PATH_NETWORK)
    nodes = gpd.GeoDataFrame(network.nodes)
    links = network.links
    nodeAttributes = network.node_attrs
    linkAttributes = network.link_attrs
    
    # Creating lines in links from "from_node" and "to_node" coordinates
    # attach xy to links
    full_net = (links
    .merge(nodes,
            left_on='from_node',
            right_on='node_id')
    .merge(nodes,
            left_on='to_node',
            right_on='node_id',
            suffixes=('_from_node', '_to_node'))
    )

    # create the geometry column from coordinates
    geometry = [LineString([(ox,oy), (dx,dy)]) for ox, oy, dx, dy in zip(full_net.x_from_node, full_net.y_from_node, full_net.x_to_node, full_net.y_to_node)]

    # build the geopandas geodataframe
    links = (gpd.GeoDataFrame(full_net,
        geometry=geometry)
        .drop(columns=['x_from_node','y_from_node','node_id_from_node','node_id_to_node','x_to_node','y_to_node'])
    )
    
    
    # Renaming the attributes columns to match the database
    attributesColumnsNames = linkAttributes.name.unique()
    finalLinksAttributes = {'link_id': []}
    for column in attributesColumnsNames:
        finalLinksAttributes[column] = [] 
    
    
    # Creating a dataframe with the links attributes for each link
    currentLinkId = linkAttributes.iloc[0]['link_id']
    currentElementAttributes = {'link_id': currentLinkId}
    
    for index, row in linkAttributes.iterrows():
        if row['link_id'] != currentLinkId:
            for column in finalLinksAttributes:
                if column in currentElementAttributes:
                    finalLinksAttributes[column].append(currentElementAttributes[column])
                else:
                    finalLinksAttributes[column].append(None)
            currentLinkId = row['link_id']
            currentElementAttributes = {'link_id': currentLinkId}

        currentElementAttributes[row['name']] = row['value']
    
    linksAttributesDataframe = pd.DataFrame.from_dict(finalLinksAttributes)
    
    
    # Merging the links attributes with the links dataframe in a geodataframe
    links = gpd.GeoDataFrame(pd.merge(links, linksAttributesDataframe, on='link_id', how='left'))
    
    
    # Renaming the columns to match the database
    links.rename(columns={
        'link_id': 'id',
        'geometry': 'geom',
    }, inplace = True)
    
    for columnName in attributesColumnsNames:
        links.rename(columns={
            columnName: columnName.replace(':', '_')
        }, inplace = True)
    
    
    # Conversion of the geometry column to object
    links['geom']  = links['geom'].apply(lambda x: x.wkt)
    
    
    # Importing the data to the database
    conn = tools.connectToDatabase()
    links.to_sql('networkLink', con=conn, if_exists='append', index=False, dtype={'geom': Geometry('LINESTRING', srid=config.DB_SRID)})





def importFacilities():
    facilityReader = matsim.Facility.facility_reader(config.PATH_FACILITIES)
    facilities = gpd.GeoDataFrame(facilityReader.facilities)
    
    # Renaming the columns to match the database
    facilities.rename(columns={
        'type': 'activityType'
    }, inplace = True)
    
    
    # Creating a point from coordinates
    facilities['location'] = facilities.apply(lambda row: 'POINT({} {})'.format(row['x'], row['y']), axis=1)
    facilities.drop(columns=['x', 'y'], inplace=True)
    
    # Importing the data to the database
    conn = tools.connectToDatabase()
    facilities.to_sql('facility', con=conn, if_exists='append', index=False, dtype={'location': Geometry('POINT', srid=config.DB_SRID)})





def importTrips():
    tripsDataframe = pd.read_csv(config.PATH_TRIPS, sep=';')   
    
    tripsDataframe.drop(columns=[
        'start_activity_type',
        'end_activity_type',
        'start_x',
        'start_y',
        'end_x',
        'end_y',
    ], inplace=True)
    
    # Renaming the columns to match the database
    tripsDataframe.rename(columns={
        'trip_id': 'id',
        'person': 'personId',
    }, inplace = True)
    
    # Correcting dep_time format
    tripsDataframe['dep_time'] = tripsDataframe['dep_time'].apply(lambda x: tools.checkAndCorrectTime(x))
    
    # Importing the data to the database
    conn = tools.connectToDatabase()
    tripsDataframe.to_sql('trip', con=conn, if_exists='append', index=False)





def importActivities():
    plansDataframes = matsim.Plans.plan_reader_dataframe(config.PATH_PLANS, selected_plans_only=True)
    activitiesDataframe = plansDataframes.activities
    plans = plansDataframes.plans
    
    # Correcting start_time and end_time format
    activitiesDataframe['start_time'] = activitiesDataframe['start_time'].apply(lambda x: tools.checkAndCorrectTime(x))
    activitiesDataframe['end_time'] = activitiesDataframe['end_time'].apply(lambda x: tools.checkAndCorrectTime(x))
    
    # Creating a point from coordinates
    activitiesDataframe['location'] = activitiesDataframe.apply(lambda row: 'POINT({} {})'.format(row['x'], row['y']), axis=1)
    
    # associating the activities to the persons in the plans
    plans.rename(columns={'id':'plan_id'}, inplace=True)
    activitiesDataframe = pd.merge(activitiesDataframe, plans, on=['plan_id'], how='left')
    
    # Renaming the columns to match the database
    activitiesDataframe.rename(columns={
        'link': 'linkId',
        'facility': 'facilityId',
        'person_id': 'personId',
    }, inplace = True)
    
    # removing unused columns
    activitiesDataframe.drop(columns=['x', 'y', 'plan_id', 'score', 'selected'], inplace=True)
    
    # Importing the data to the database
    conn = tools.connectToDatabase()
    activitiesDataframe.to_sql('activity', con=conn, if_exists='append', index=False, dtype={'location': Geometry('POINT', srid=config.DB_SRID)})





def importEvents():
    print('') # TODO: remove this line 
    timeRangeInMinutes = 60 #* 10
    timeRangeInSeconds = timeRangeInMinutes * 60
    
    events = matsim.Events.event_reader(config.PATH_EVENTS)    
    eventsDataframe = pd.DataFrame(events)
    
    network = matsim.Network.read_network(config.PATH_NETWORK)
    networkLinksDataframe = network.links
    networkLinksLengthDict = dict(zip(networkLinksDataframe['link_id'], networkLinksDataframe['length']))
    networkLinksFreespeedDict = dict(zip(networkLinksDataframe['link_id'], networkLinksDataframe['freespeed']))
    
    # Removing unused rows
    eventsDataframe.drop(eventsDataframe[
        (eventsDataframe['type'] != 'left link') &
        (eventsDataframe['type'] != 'entered link') &
        (eventsDataframe['type'] != 'departure') &
        (eventsDataframe['type'] != 'arrival')].index, inplace=True)

    # Removing starting and ending events not using car as mode
    eventsDataframe.drop(eventsDataframe[
        (eventsDataframe['type'] == 'departure') &
        (eventsDataframe['legMode'] != 'car')
    ].index, inplace=True)
    
    eventsDataframe.drop(eventsDataframe[
        (eventsDataframe['type'] == 'arrival') &
        (eventsDataframe['legMode'] != 'car')
    ].index, inplace=True)
    
    # removing rows using public transport
    eventsDataframe.drop(eventsDataframe[
        (eventsDataframe['type'] == 'departure') &
        (eventsDataframe['person'].astype(str).str.startswith('pt'))
    ].index, inplace=True)
    
    # eventsDataframe.sort_values(by=['link','time'], inplace=True)
    eventsDataframe.reset_index(drop=True, inplace=True)
    print(eventsDataframe)
    
    # Calculating the number of vehicles in each link at each time step
    # Calculating the mean speed of each link at each time step
    currentStartingTime = eventsDataframe['time'][0]
    currentEndingTime = currentStartingTime + timeRangeInSeconds

    enteredLinksQueueDict = collections.defaultdict(list)
    meanSpeedInLinksDict = collections.defaultdict(list)
    vehiclesPerLinkDict = collections.defaultdict(int)
    
    resultsDict = {'linkId': [], 'timeSpan': [], 'totalVehicle': [], 'meanSpeed': []}
    
    # Parsing the events
    for row in eventsDataframe.itertuples():
        if row.type in ['entered link', 'departure']:
            enteredLinksQueueDict[row.link].append(row.time)
        else:
            if row.time > currentEndingTime:
                for linkId, speeds in meanSpeedInLinksDict.items():
                    vehicleCount = vehiclesPerLinkDict[linkId]
                    speeds = [i for i in speeds if i != 0] # removing 0 values
                    meanSpeed = sum(speeds) / vehicleCount if vehicleCount > 0 else 0
                    timespan = f'{int(currentStartingTime)}_{int(currentEndingTime)}'
                    
                    # Checking if meanspeed is above links freespeed limit
                    if meanSpeed > networkLinksFreespeedDict[linkId]:
                        meanSpeed = networkLinksFreespeedDict[linkId]                    
                    
                    resultsDict['linkId'].append(linkId)
                    resultsDict['timeSpan'].append(timespan)
                    resultsDict['totalVehicle'].append(vehicleCount)
                    resultsDict['meanSpeed'].append(meanSpeed)

                break
            if row.link in enteredLinksQueueDict:
                # Calculating time spent in the link
                try: 
                    startingTimeInLink = enteredLinksQueueDict[row.link].pop(0)
                except:
                    startingTimeInLink = row.time
                    print(f'Error: link {row.link} has an empty queue')
                
                secondsSpentInLink = row.time - startingTimeInLink
                
                # Calculating the mean speed in the link (in meter/second)
                linkLength = networkLinksLengthDict[row.link]
                try:
                    speed = linkLength / secondsSpentInLink
                except:
                    speed = 0
                    # print(f'Error: \nlink => {row.link} \nlinkLength => {linkLength} \nsecondsSpentInLink => {secondsSpentInLink} \nstartingTimeInLink => {startingTimeInLink} \nrow.time => {row.time} \ntype => {row.type} \nlegMode => {row.legMode}')
                meanSpeedInLinksDict[row.link].append(speed)
                vehiclesPerLinkDict[row.link] += 1
                
            else:
                print(f'Error: link {row.link} not found in the queue person: {row.person} / legMode: {row.legMode}')

    resultsDict = pd.DataFrame(resultsDict)
    print(resultsDict)