#!/usr/bin/env python3

import requests
import datetime
from numpy import nan
import pandas as pd


country = 'US'
url = 'https://services.arcgis.com/njFNhDsUCentVYJW/arcgis/rest/services/MD_COVID19_Case_Counts_by_County/FeatureServer/0/query?where=1%3D1&objectIds=&time=&geometry=&geometryType=esriGeometryEnvelope&inSR=&spatialRel=esriSpatialRelIntersects&resultType=none&distance=0.0&units=esriSRUnit_Meter&returnGeodetic=false&outFields=*&returnGeometry=false&returnCentroid=false&featureEncoding=esriDefault&multipatchOption=xyFootprint&maxAllowableOffset=&geometryPrecision=&outSR=&datumTransformation=&applyVCSProjection=false&returnIdsOnly=false&returnUniqueIdsOnly=false&returnCountOnly=false&returnExtentOnly=false&returnQueryGeometry=false&returnDistinctValues=false&cacheHint=false&orderByFields=&groupByFieldsForStatistics=&outStatistics=&having=&resultOffset=&resultRecordCount=&returnZ=false&returnM=false&returnExceededLimitFeatures=true&quantizationParameters=&sqlFormat=standard&f=pjson&token='
state = 'Maryland'
resolution = 'county'
columns = ['country', 'state', 'url', 'raw_page', 'access_time', 'county',
           'cases', 'updated', 'deaths', 'presumptive', 'recovered', 'tested',
           'hospitalized', 'negative', 'counties', 'severe', 'lat', 'lon',
           'parish', 'monitored', 'private_test', 'state_test',
           'no_longer_monitored', 'pending_tests', 'active', 'inconclusive',
           'scrape_group', 'icu',
           'cases_0_9', 'cases_10_19', 'cases_20_29', 'cases_30_39',
           'cases_40_49', 'cases_50_59', 'cases_60_69', 'cases_70_79',
           'cases_80',
           'hospitalized_0_9', 'hospitalized_10_19', 'hospitalized_20_29',
           'hospitalized_30_39', 'hospitalized_40_49', 'hospitalized_50_59',
           'hospitalized_60_69', 'hospitalized_70_79', 'hospitalized_80',
           'deaths_0_9', 'deaths_10_19', 'deaths_20_29', 'deaths_30_39',
           'deaths_40_49', 'deaths_50_59', 'deaths_60_69', 'deaths_70_79',
           'deaths_80']


raw_data = requests.get(url).json()
access_time = datetime.datetime.utcnow()

row_csv = []

for feature in raw_data['features']:
    attribute = feature['attributes']

    county = attribute['COUNTY']
    cases = attribute['COVID19Cases']
    recovered = attribute['COVID19Recovered']
    deaths = attribute['COVID19Deaths']

    row_csv.append([
        country, state, url, str(raw_data), access_time, county,
        cases, nan, deaths, nan, recovered, nan,
        nan, nan, nan, nan, nan, nan,
        nan,  nan, nan, nan,
        nan, nan, nan, nan,
        nan, nan,
        nan, nan, nan, nan,
        nan, nan, nan, nan,
        nan,
        nan, nan, nan,
        nan, nan, nan,
        nan, nan, nan,
        nan, nan, nan, nan,
        nan, nan, nan, nan, nan])


df = pd.DataFrame(row_csv, columns=columns)
df.to_csv('maryland_.csv', index=False)
