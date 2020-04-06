#!/usr/bin/env python3

import requests
import datetime
from numpy import nan
import pandas as pd
from cvpy.static import Headers


country = 'US'
url = 'https://services1.arcgis.com/PlCPCPzGOwulHUHo/ArcGIS/rest/services/DEMA_COVID_County_Boundary_Time_VIEW/FeatureServer/0/query?where=1%3D1&objectIds=&time=&geometry=&geometryType=esriGeometryPoint&inSR=&spatialRel=esriSpatialRelIntersects&resultType=none&distance=0.0&units=esriSRUnit_Meter&returnGeodetic=false&outFields=*&returnGeometry=false&returnCentroid=false&featureEncoding=esriDefault&multipatchOption=xyFootprint&maxAllowableOffset=&geometryPrecision=&outSR=&datumTransformation=&applyVCSProjection=false&returnIdsOnly=false&returnUniqueIdsOnly=false&returnCountOnly=false&returnExtentOnly=false&returnQueryGeometry=false&returnDistinctValues=false&cacheHint=false&orderByFields=&groupByFieldsForStatistics=&outStatistics=&having=&resultOffset=&resultRecordCount=&returnZ=false&returnM=false&returnExceededLimitFeatures=true&quantizationParameters=&sqlFormat=none&f=pjson&token='
state_url_death = 'https://services1.arcgis.com/PlCPCPzGOwulHUHo/arcgis/rest/services/DEMA_COVID_County_Boundary_Time_VIEW/FeatureServer/0/query?f=json&where=1%3D1&returnGeometry=false&spatialRel=esriSpatialRelIntersects&outFields=*&outStatistics=%5B%7B%22statisticType%22%3A%22sum%22%2C%22onStatisticField%22%3A%22Total_Death%22%2C%22outStatisticFieldName%22%3A%22value%22%7D%5D&cacheHint=true'
state_url_cases = 'https://services1.arcgis.com/PlCPCPzGOwulHUHo/arcgis/rest/services/DEMA_COVID_County_Boundary_Time_VIEW/FeatureServer/0/query?f=json&where=NAME%3C%3E%27Statewide%27&returnGeometry=false&spatialRel=esriSpatialRelIntersects&outFields=*&outStatistics=%5B%7B%22statisticType%22%3A%22sum%22%2C%22onStatisticField%22%3A%22Presumptive_Positive%22%2C%22outStatisticFieldName%22%3A%22value%22%7D%5D&cacheHint=true'
state = 'Delaware'
columns = Headers.updated_site


raw_data = requests.get(url).json()
access_time = datetime.datetime.utcnow()

row_csv = []
state_keys = ['Range1', 'Range2', 'Range3', 'Range4', 'Range5']
alias = {}

for field in raw_data['fields']:
    name = field['name']
    if 'Range' in name:
        alias[name] = field['alias']

for feature in raw_data['features']:
    attribute = feature['attributes']
    if attribute["TYPE"] == 'mainland' and attribute['NAME'] != 'Statewide':
        resolution = 'county'
        county = attribute['NAME']
        cases = attribute['Presumptive_Positive']
        recovered = attribute['Recovered']
        deaths = attribute['Total_Death']
        hospitalized = attribute['Hospitalizations']
        negative_tests = attribute['NegativeCOVID']
        update_date = attribute['Last_Updated']
        if update_date is None:
            updated = nan
        else:
            update_date = float(attribute['Last_Updated'])
            updated = str(datetime.datetime.fromtimestamp(update_date/1000.0))

        row_csv.append([
            'state', country, state, nan,
            url, str(raw_data), access_time, county,
            cases, updated, deaths, nan,
            recovered, nan, hospitalized, negative_tests,
            nan, nan, nan, nan, nan,
            nan, nan, nan,
            nan, nan, nan,
            nan, nan, nan,
            resolution, nan, nan, nan,
            nan, nan, nan, nan,
            nan, nan, nan, nan,
            nan, nan, nan,
            nan, nan,
            nan, nan, nan, nan,
            nan, nan])

    elif attribute['NAME'] == 'Statewide':
        resolution = 'state'
        county = nan
        cases = attribute['Presumptive_Positive']
        recovered = attribute['Recovered']
        deaths = attribute['Total_Death']
        hospitalized = attribute['Hospitalizations']
        negative_tests = attribute['NegativeCOVID']
        cases_male = attribute['Male']
        cases_female = attribute['Female']
        update_date = attribute['Last_Updated']
        if update_date is None:
            updated = nan
        else:
            update_date = float(attribute['Last_Updated'])
            updated = str(datetime.datetime.fromtimestamp(update_date / 1000.0))
        for key in state_keys:

            age_range = alias[key]
            age_cases = attribute[key]

            row_csv.append([
                'state', country, state, nan,
                url, str(raw_data), access_time, county,
                nan, updated, nan, nan,
                recovered, nan, hospitalized, negative_tests,
                nan, nan, nan, nan, nan,
                nan, nan, nan,
                nan, nan, nan,
                nan, nan, nan,
                resolution, nan, cases_male, cases_female,
                nan, nan, nan, nan,
                age_range, age_cases, nan, nan,
                nan, nan, nan,
                nan, nan,
                nan, nan, nan, nan,
                nan, nan])

raw_data = requests.get(state_url_death).json()
access_time = datetime.datetime.utcnow()
resolution = 'state'
deaths = raw_data['features'][0]['attributes']['value']
row_csv.append([
    'state', country, state, nan,
    state_url_death, str(raw_data), access_time, nan,
    nan, nan, deaths, nan,
    nan, nan, nan, nan,
    nan, nan, nan, nan, nan,
    nan, nan, nan,
    nan, nan, nan,
    nan, nan, nan,
    resolution, nan, nan, nan,
    nan, nan, nan, nan,
    nan, nan, nan, nan,
    nan, nan, nan,
    nan, nan,
    nan, nan, nan, nan,
    nan, nan])

raw_data = requests.get(state_url_cases).json()
access_time = datetime.datetime.utcnow()
resolution = 'state'
cases = raw_data['features'][0]['attributes']['value']
row_csv.append([
    'state', country, state, nan,
    state_url_death, str(raw_data), access_time, nan,
    cases, nan, nan, nan,
    nan, nan, nan, nan,
    nan, nan, nan, nan, nan,
    nan, nan, nan,
    nan, nan, nan,
    nan, nan, nan,
    resolution, nan, nan, nan,
    nan, nan, nan, nan,
    nan, nan, nan, nan,
    nan, nan, nan,
    nan, nan,
    nan, nan, nan, nan,
    nan, nan])

df = pd.DataFrame(row_csv, columns=columns)
# "Last_Updated" field is not reported all the time so there is a need to fill
# missing data
df[['updated']] = df[['updated']].fillna(method='ffill')
df.to_csv('deleware_.csv', index=False)
