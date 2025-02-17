import os
import ssl

import tempfile
import sys, shutil
import urllib.request as ulib
import urllib.parse as urlparse

try:
    import requests
except ModuleNotFoundError:
    requests = None


# following files must exist withing data folder for CAMELS-GB data
DATA_FILES = {
    'CAMELS-GB': [
        'CAMELS_GB_climatic_attributes.csv',
        'CAMELS_GB_humaninfluence_attributes.csv',
        'CAMELS_GB_hydrogeology_attributes.csv',
        'CAMELS_GB_hydrologic_attributes.csv',
        'CAMELS_GB_hydrometry_attributes.csv',
        'CAMELS_GB_landcover_attributes.csv',
        'CAMELS_GB_soil_attributes.csv',
        'CAMELS_GB_topographic_attributes.csv'
    ],
    'HYSETS': [  # following files must exist in a folder containing HYSETS dataset.
        'HYSETS_2020_ERA5.nc',
        'HYSETS_2020_ERA5Land.nc',
        'HYSETS_2020_ERA5Land_SWE.nc',
        'HYSETS_2020_Livneh.nc',
        'HYSETS_2020_nonQC_stations.nc',
        'HYSETS_2020_SCDNA.nc',
        'HYSETS_2020_SNODAS_SWE.nc',
        'HYSETS_elevation_bands_100m.csv',
        'HYSETS_watershed_boundaries.zip',
        'HYSETS_watershed_properties.txt'
    ]
}


def download_all_http_directory(url, outpath=None, filetypes=".zip", match_name=None):
    """
    Download all the files which are of category filetypes at the location of
    outpath. If a file is already present. It will not be downloaded.
    filetypes str: extension of files to be downloaded. By default only .zip files
        are downloaded.
    mathc_name str: if not None, then only those files will be downloaded whose name
        have match_name string in them.
    """
    import bs4
    if os.name == 'nt':
        ssl._create_default_https_context = ssl._create_unverified_context
    page = list(urlparse.urlsplit(url))[2].split('/')[-1]
    basic_url = url.split(page)[0]

    r = requests.get(url)
    data = bs4.BeautifulSoup(r.text, "html.parser")
    match_name = filetypes if match_name is None else match_name

    for l in data.find_all("a"):

        if l["href"].endswith(filetypes) and match_name in l['href']:
            _outpath = outpath
            if outpath is not None:
                _outpath = os.path.join(outpath, l['href'])

            if os.path.exists(_outpath):
                print(f"file {l['href']} already exists at {outpath}")
                continue
            download(basic_url + l["href"], _outpath)
            print(r.status_code, l["href"], )


def download(url, out=None):
    """High level function, which downloads URL into tmp file in current
    directory and then renames it to filename autodetected from either URL
    or HTTP headers.

    :param url:
    :param out: output filename or directory
    :return:    filename where URL is downloaded to
    """
    # detect of out is a directory
    if out is not None:
        outdir = os.path.dirname(out)
        out_filename = os.path.basename(out)
        if not os.path.exists(outdir):
            os.makedirs(outdir)
    else:
        outdir = os.getcwd()
        out_filename = None

    # get filename for temp file in current directory
    prefix = filename_from_url(url)
    (fd, tmpfile) = tempfile.mkstemp(".tmp", prefix=prefix, dir=".")
    os.close(fd)
    os.unlink(tmpfile)

    # set progress monitoring callback
    def callback_charged(blocks, block_size, total_size):
        # 'closure' to set bar drawing function in callback
        callback_progress(blocks, block_size, total_size, bar_function=bar)

    callback = callback_charged

    # Python 3 can not quote URL as needed
    binurl = list(urlparse.urlsplit(url))
    binurl[2] = urlparse.quote(binurl[2])
    binurl = urlparse.urlunsplit(binurl)

    (tmpfile, headers) = ulib.urlretrieve(binurl, tmpfile, callback)
    filename = filename_from_url(url)

    if out_filename:
        filename = out_filename

    filename = outdir + "/" + filename

    # add numeric ' (x)' suffix if filename already exists
    if os.path.exists(filename):
        filename = filename + '1'
    shutil.move(tmpfile, filename)

    # print headers
    return filename


__current_size = 0


def callback_progress(blocks, block_size, total_size, bar_function):
    """callback function for urlretrieve that is called when connection is
    created and when once for each block

    draws adaptive progress bar in terminal/console

    use sys.stdout.write() instead of "print,", because it allows one more
    symbol at the line end without linefeed on Windows

    :param blocks: number of blocks transferred so far
    :param block_size: in bytes
    :param total_size: in bytes, can be -1 if server doesn't return it
    :param bar_function: another callback function to visualize progress
    """
    global __current_size

    width = 100

    if sys.version_info[:3] == (3, 3, 0):  # regression workaround
        if blocks == 0:  # first call
            __current_size = 0
        else:
            __current_size += block_size
        current_size = __current_size
    else:
        current_size = min(blocks * block_size, total_size)
    progress = bar_function(current_size, total_size, width)
    if progress:
        sys.stdout.write("\r" + progress)


def filename_from_url(url):
    """:return: detected filename as unicode or None"""
    # [ ] test urlparse behavior with unicode url
    fname = os.path.basename(urlparse.urlparse(url).path)
    if len(fname.strip(" \n\t.")) == 0:
        return None
    return fname


def bar(current_size, total_size, width):
    percent = current_size/total_size * 100
    if round(percent % 1, 4) == 0.0:
        print(f"{round(percent)}% of {round(total_size*1e-6, 2)} MB downloaded")
    return


def check_attributes(attributes, check_against:list)->list:
    if attributes == 'all' or attributes is None:
        attributes = check_against
    elif not isinstance(attributes, list):
        assert isinstance(attributes, str)
        assert attributes in check_against
        attributes = [attributes]
    else:
        assert isinstance(attributes, list), f'unknown attributes {attributes}'

    assert all(elem in check_against for elem in attributes)

    return attributes


def sanity_check(dataset_name, path):
    if dataset_name in DATA_FILES:
        if dataset_name == 'CAMELS-GB':
            if not os.path.exists(os.path.join(path, 'data')):
                raise FileNotFoundError(f"No folder named `data` exists inside {path}")
            else:
                data_path = os.path.join(path, 'data')
                for file in DATA_FILES[dataset_name]:
                    if not os.path.exists(os.path.join(data_path, file)):
                        raise FileNotFoundError(f"File {file} must exist inside {data_path}")
    return
