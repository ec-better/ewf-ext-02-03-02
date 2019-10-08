#from __future__ import absolute_import, division, print_function
import os
import numpy as np
import gdal
import osr
from urlparse import urlparse
import pandas as pd
import datetime
import matplotlib.pyplot as plt

def hello_world():
    
    print 'Hello World!'
    
    
def get_vsi_url(enclosure, user, api_key):
    
    
    parsed_url = urlparse(enclosure)

    url = '/vsicurl/%s://%s:%s@%s/api%s' % (list(parsed_url)[0],
                                            user, 
                                            api_key, 
                                            list(parsed_url)[1],
                                            list(parsed_url)[2])
    
    return url 

def analyse_row(row):
    
    series = dict()
    
    series['day'] = row['title'][11:19]
    series['jday'] = '{}{}'.format(datetime.datetime.strptime(series['day'], '%Y%m%d').timetuple().tm_year,
                                   "%03d"%datetime.datetime.strptime(series['day'], '%Y%m%d').timetuple().tm_yday)
    
    return pd.Series(series)


def analyse_subtile(row, parameters):
    
    series = dict()
    
    src_ds = gdal.Open(get_vsi_url(row.enclosure, 
                                   parameters['username'], 
                                   parameters['api_key']))
    
    bands = dict()

    for band in range(src_ds.RasterCount):

        band += 1

        bands[src_ds.GetRasterBand(band).GetDescription()] = band 
        
    vsi_mem = '/vsimem/t.tif'
   
    gdal.Translate(vsi_mem, 
                   src_ds,
                    srcWin=[row.start_x, row.start_y, row.cols, row.rows])
    
    ds_mem = gdal.Open(vsi_mem)
    
    if ds_mem is None:
        raise

    for band in ['B04', 'B08', 'SCL', 'MSK_CLDPRB', 'MSK_SNWPRB']:
        # read the data
        series[band] = np.array(ds_mem.GetRasterBand(bands[band]).ReadAsArray())
     
    #series['MASK'] = np.ones((row.cols, row.rows), dtype=bool)
    
    series['MASK'] = ((series['SCL'] == 2) | (series['SCL'] == 4) | (series['SCL'] == 5) | (series['SCL'] == 6) | (series['SCL'] == 7) | (series['SCL'] == 10) | (series['SCL'] == 11)) & (series['B08'] + series['B04'] != 0)
    
    series['NDVI'] = np.where(series['MASK'], (series['B08'] - series['B04']) / (series['B08'] + series['B04']).astype(np.float), np.nan)
    
    return pd.Series(series)

class DateHelper(object):
    """Helper class for handling dates in temporal interpolation."""

    def __init__(self, rawdates, rtres, stres, start=None, nupdate=0):
        """Creates the date lists from input.

        Args:
             rawdates: list of dates from raw file(s)
             rtres: raw temporal resolution
             stres: smooth temporal resolution
             start: start date for custom interpolation
             nupdate: number of points in time to be updated in file (backwards)
            """

        if start:
            stop = (fromjulian(rawdates[-1]) + datetime.timedelta(rtres)).strftime('%Y%j')
            tdiff = (fromjulian(stop) - fromjulian(rawdates[0])).days
            self.daily = [(fromjulian(rawdates[0]) + datetime.timedelta(x)).strftime('%Y%j') for x in range(tdiff+1)]
            self.target = [self.daily[x] for x in range(self.daily.index(start), len(self.daily), stres)]
            self.target = self.target[-nupdate:]
        else:
            yrmin = int(min([x[:4] for x in rawdates]))
            yrmax = int(max([x[:4] for x in rawdates]))
            daily_tmp = [y for x in range(yrmin, yrmax+2, 1) for y in tvec(x, 1)]
            stop = (fromjulian(rawdates[-1]) + datetime.timedelta(rtres)).strftime('%Y%j')
            self.daily = daily_tmp[daily_tmp.index(rawdates[0]):daily_tmp.index(stop)+1]

            if stres == 5:
                target_temp = [y for x in range(yrmin, yrmax+1, 1) for y in pentvec(x)]
            elif stres == 10:
                target_temp = [y for x in range(yrmin, yrmax+1, 1) for y in dekvec(x)]
            else:
                target_temp = [y for x in range(yrmin, yrmax+1, 1) for y in tvec(x, stres)]
            target_temp.sort()

            for sd in self.daily:
                if sd in target_temp:
                    start_target = sd
                    del sd
                    break
            for sd in reversed(self.daily):
                if sd in target_temp:
                    stop_target = sd
                    del sd
                    break
            self.target = target_temp[target_temp.index(start_target):target_temp.index(stop_target)+1]
            self.target = self.target[-nupdate:]

    def getDV(self, nd):
        """Gets an array of no-data values in daily timesteps.

        Args:
            nd: no-data value

        Returns:
            numpy array with no-data values in daily steps
        """

        return np.full(len(self.daily), nd, dtype='double')

    def getDIX(self):
        """Gets indices of target dates in daily no-data array.

        Returns:
            list with indices of target dates in no-data array
        """

        return [self.daily.index(x) for x in self.target]

def fromjulian(x):
    """Parses julian date string to datetime object.

    Args:
        x: julian date as string YYYYJJJ

    Returns:
        datetime object parsed from julian date
    """

    return datetime.datetime.strptime(x, '%Y%j').date()

def tvec(yr, step):
    """Create MODIS-like date vector with given timestep.

    Args:
        yr: year
        step: timestep

    Returns:
        list with dates
    """

    start = fromjulian('{}001'.format(yr)) + datetime.timedelta()
    tdiff = fromjulian('{}001'.format(yr+1)) - start
    tv = [(start + datetime.timedelta(x)).strftime('%Y%j') for x in range(0, tdiff.days, step)]
    return tv

def dekvec(yr):
    """Create dekadal date vector for given year with fixed days.

    Args:
        yr: year

    Returns:
        list of dates
    """

    return([
        datetime.datetime.strptime(str(yr)+y+x, '%Y%m%d').date().strftime('%Y%j')
        for x in ['05', '15', '25'] for y in [str(z).zfill(2)
                                              for z in range(1, 13)]
    ])


def plot(y, dts,z=None,z_asy=None):
    plt.close()
    xax = [fromjulian(x) for x in dts]
    plt.figure(figsize=(15,8))
    plt.ylim(0,1)
    plt.plot(xax,y,label='y')

    try:
        plt.plot(xax,z,label='z')
    except ValueError:
        pass
    
    try:
        plt.plot(xax,z_asy,label='z_asy')
    except ValueError:
        pass
    
    plt.legend()
    plt.show()