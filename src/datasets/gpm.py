""" RHEAS module for retrieving the GPM daily precipitation data product (IMERG).

.. module:: prism
   :synopsis: Retrieve GPM precipitation data

.. moduleauthor:: Kostas Andreadis <kandread@jpl.nasa.gov>

"""


from ftplib import FTP
from datetime import datetime, timedelta
import tempfile
import subprocess
import datasets
import dbio
import re
import os
import rpath
import logging


table = "precip.gpm"


def dates(dbname):
    dts = datasets.dates(dbname, table)
    return dts


def download(dbname, dts, bbox):
    """Downloads the PRISM data products for a set of
    dates *dt* and imports them into the PostGIS database *dbname*."""
    log = logging.getLogger(__name__)
    url = "jsimpson.pps.eosdis.nasa.gov"
    ftp = FTP(url)
    # FIXME: Change to RHEAS-specific password
    ftp.login('kandread@jpl.nasa.gov', 'kandread@jpl.nasa.gov')
    ftp.cwd("data/imerg/gis")
    outpath = tempfile.mkdtemp()
    for dt in [dts[0] + timedelta(t) for t in range((dts[-1] - dts[0]).days+1)]:
        try:
            if dt.year < datetime.today().year:
                ftp.cwd("/data/imerg/gis/{0}/{1:02d}".format(dt.year, dt.month))
            else:
                ftp.cwd("/data/imerg/gis/{0:02d}".format(dt.month))
            filenames = [f for f in ftp.nlst() if re.match(r"3B.*{0}.*S000000.*1day\.tif.*".format(dt.strftime("%Y%m%d")), f) is not None]
            if len(filenames) > 0:
                fname = filenames[0]
                with open("{0}/{1}".format(outpath, fname), 'wb') as f:
                    ftp.retrbinary("RETR {0}".format(fname), f.write)
                with open("{0}/{1}".format(outpath, fname.replace("tif", "tfw")), 'wb') as f:
                    ftp.retrbinary("RETR {0}".format(fname.replace("tif", "tfw")), f.write)
                tfname = fname.replace("tif", "tfw")
                fname = datasets.uncompress(fname, outpath)
                datasets.uncompress(tfname, outpath)
                proc = subprocess.Popen(["gdalwarp", "-t_srs", "-ot", "Float32", "epsg:4326", "{0}/{1}".format(outpath, fname), "{0}/prec.tif".format(outpath)], stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
                out, err = proc.communicate()
                log.debug(out)
                if bbox is not None:
                    proc = subprocess.Popen(["gdal_translate", "-ot", "Float32", "-a_srs", "epsg:4326", "-projwin", "{0}".format(bbox[0]), "{0}".format(bbox[3]), "{0}".format(bbox[2]), "{0}".format(bbox[1]), "{0}/prec.tif".format(outpath), "{0}/prec1.tif".format(outpath)], stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
                    out, err = proc.communicate()
                    log.debug(out)
                else:
                    proc = subprocess.Popen(["gdal_translate", "-a_srs", "epsg:4326", "{0}/prec.tif".format(outpath), "{0}/prec1.tif".format(outpath)], stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
                    out, err = proc.communicate()
                    log.debug(out)
                # multiply by 0.1 to get mm/hr and 24 to get mm/day
                if not os.path.isdir("{0}/precip/gpm".format(rpath.data)):
                    os.makedirs("{0}/precip/gpm".format(rpath.data))
                filename = "{0}/precip/gpm/gpm_{1}.tif".format(rpath.data, dt.strftime("%Y%m%d"))
                proc = subprocess.Popen(["gdal_calc.py", "-A", "{0}/prec1.tif".format(outpath), "--outfile={0}".format(filename), "--calc=\"2.4*A\""], stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
                out, err = proc.communicate()
                log.debug(out)
                dbio.ingest(dbname, filename, dt, table, True)
        except:
            log.warning("No data were available to import into {0} for {1}.".format(table, dt.strftime("%Y-%m-%d")))
