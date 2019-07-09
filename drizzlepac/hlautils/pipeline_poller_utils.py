"""Utilities to interpret the pipeline poller obset information and generate product filenames

The function, interpret_obset_input, parses the file generated by the pipeline
poller, and produces a tree listing of the output products.  The function,
parse_obset_tree, converts the tree into product catagories.  The filename
generator routines produce the specific image product and source catalog files.

"""

from astropy.table import Table, Column

# Define information/formatted strings to be included in output dict
SEP_STR = 'single exposure product {:02d}'
FP_STR = 'filter product {:02d}'
TDP_STR = 'total detection product {:02d}'

# Define the mapping between the first character of the filename and the associated instrument
INSTRUMENT_DICT = {'i': 'WFC3', 'j': 'ACS', 'o': 'STIS', 'u': 'WFPC2', 'x': 'FOC', 'w': 'WFPC'}

__taskname__ = 'pipeline_poller_utils'

def interpret_obset_input(results):
    """
    Interpret the database query for a given obset to prepare the returned
    values for use in generating the names of all the expected output products.

    Input will have format of:
        ia1s70jtq_flt.fits,11150,A1S,70,149.232269,F110W,IR,/ifs/archive/ops/hst/public/ia1s/ia1s70jtq/ia1s70jtq_flt.fits
        ia1s70iwq_flt.fits,11150,A1S,70,0.91161000000000003,F160W,IR,/ifs/archive/ops/hst/public/ia1s/ia1s70iwq/ia1s70iwq_flt.fits
        which are
        filename, proposal_id, program_id, obset_id, exptime, filters, detector, pathname

    Output dict will have format (as needed by further code for creating the
        product filenames) of:

        obs_info_dict["single exposure product 00"] = {'info': '11150 70 WFC3 IR F110W IA1S70JTQ',
                                                        'files':['ia1s70jtq_flt.fits']}
        obs_info_dict["single exposure product 01"] = {'info': '11150 70 WFC3 IR F160W IA1S70JWQ',
                                                        'files':['ia1s70jwq_flt.fits']}

        obs_info_dict["filter product 00"] = {"info": '11150 70 WFC3 IR F110W',
                                              "files":['ia1s70jtq_flt.fits']}
        obs_info_dict["filter product 01"] = {"info": '11150 70 WFC3 IR F160W',
                                              "files":['ia1s70jwq_flt.fits']}
        obs_info_dict["total detection product 00"] = {'info': '11150 70 WFC3 IR',
                                                       'files':['ia1s70jtq_flt.fits',
                                                                'ia1s70iwq_flt.fits']}

    """
    colnames = ['filename', 'proposal_id', 'program_id', 'obset_id',
                'exptime', 'filters', 'detector', 'pathname']
    obset_table = Table.read(results, format='ascii.fast_no_header', names=colnames)
    # Add INSTRUMENT column
    instr = INSTRUMENT_DICT[obset_table['filename'][0][0]]
    # convert input to an Astropy Table for parsing
    obset_table.add_column(Column([instr] * len(obset_table)), name='instrument')
    # parse Table into a tree-like dict
    obset_tree = build_obset_tree(obset_table)
    # Now create final dict
    obset_dict = parse_obset_tree(obset_tree)

    return obset_dict

# Translate the database query on an obset into actionable lists of filenames
def build_obset_tree(obset_table):
    """Convert obset table into a tree listing all products to be created."""

    # Each product will consist of the appropriate string as the key and
    # a dict of 'info' and 'files' information

    # Start interpreting the obset table
    obset_tree = {}
    for row in obset_table:
        # Get some basic information from the first row - no need to check
        # for multiple instruments as data from different instruments will
        # not be combined.
        det = row['detector']
        orig_filt = row['filters']
        # Potentially need to manipulate the 'filters' string for instruments
        # with two filter wheels
        filt = determine_filter_name(orig_filt)
        row['filters'] = filt
        row_info, filename = create_row_info(row)
        # Initial population of the obset tree for this detector
        if det not in obset_tree:
            obset_tree[det] = {}
            obset_tree[det][filt] = [(row_info, filename)]
        else:
            det_node = obset_tree[det]
            if filt not in det_node:
                det_node[filt] = [(row_info, filename)]
            else:
                det_node[filt].append((row_info, filename))

    return obset_tree

def create_row_info(row):
    """Build info string for a row from the obset table"""
    info_list = [str(row['proposal_id']), "{:02d}".format(row['obset_id']), row['instrument'],
                 row['detector'], row['filters'], row['filename'][:row['filename'].find('_')]]
    return ' '.join(map(str.upper, info_list)), row['filename']

def parse_obset_tree(det_tree):
    """Convert tree into products

    Tree generated by `create_row_info()` will always have the following
    levels:
          * detector
              * filters
                  * exposure
    Each exposure will have an entry dict with keys 'info' and 'filename'.

    Products created will be:
      * total detection product per detector
      * filter products per detector
      * single exposure product
    """
    # Initialize products dict
    obset_products = {}

    # For each level, define a product, starting with the detector used...
    prev_det_indx = 0
    det_indx = 0
    filt_indx = 0
    sep_indx = 0

    # Determine if the individual files being processed are flt or flc and
    # set the filetype accordingly (flt->drz or flc->drc).
    filetype = ''

    # Setup products for each detector used
    for filt_tree in det_tree.values():
        tdp = TDP_STR.format(det_indx)
        obset_products[tdp] = {'info': "", 'files': []}
        det_indx += 1
        # Find all filters used...
        for filter_files in filt_tree.values():
            # Use this to create and populate filter products entry
            fprod = FP_STR.format(filt_indx)
            obset_products[fprod] = {'info': "", 'files': []}
            filt_indx += 1
            # Populate single exposure entry now as well
            for filename in filter_files:
                # Parse the first filename[1] to determine if the products are flt or flc
                if det_indx != prev_det_indx:
                    filetype = "drc"
                    if filename[1][10:13].lower().endswith("flt"):
                        filetype = "drz"
                    prev_det_indx = det_indx
                sep = SEP_STR.format(sep_indx)  # keep 80 char wide code
                sep_info = (filename[0] + " " + filetype).lower()
                obset_products[sep] = {'info': sep_info,
                                       'files': [filename[1]]}
                # Initialize `info` key for this filter product
                if not obset_products[fprod]['info']:
                    # Use all but last entry in filter level info
                    fp_info = (" ".join(filename[0].split()[:])+" "+filetype).lower()
                    obset_products[fprod]['info'] = fp_info
                # Populate filter product with input filename
                obset_products[fprod]['files'].append(filename[1])
                # Initialize `info` key for total detection product
                if not obset_products[tdp]['info']:
                    tdp_info = (" ".join(filename[0].split()[:-2]) + " " + filename[0].split()[-1] + " " + filetype).lower()
                    obset_products[tdp]['info'] = tdp_info
                # Append exposure filename to input list for total detection product
                obset_products[tdp]['files'].append(filename[1])
                # Increment single exposure master index
                sep_indx += 1

    # Done... return dict
    return obset_products

def run_generator(product_category, obs_info):
    """
    This is the main calling subroutine. It decides which filename generation subroutine should be run based
    on the input product_category, and then passes the information stored in input obs_info to the subroutine
    so that the appropriate filenames can be generated.

    Parameters
    ----------
    product_category : string
        The type of final output product which filenames will be generated for
    obs_info : string
        A string containing space-separated items that will be used to
        generate the filenames.

    Returns
    --------
    product_filename_dict : dictionary
        A dictionary containing the generated filenames.
    """
    category_generator_mapping = {'single exposure product': single_exposure_product_filename_generator,
                                  'filter product': filter_product_filename_generator,
                                  'total detection product': total_detection_product_filename_generator,
                                  'multivisit mosaic product': multivisit_mosaic_product_filename_generator}

    # Determine which name generator to use based on input product_category
    category_key = ""
    for ikey in category_generator_mapping:
        if product_category.startswith(ikey):
            generator_name = category_generator_mapping[ikey]
            category_key = ikey
            break

    # parse out obs_info into a list
    obs_info = obs_info.split(" ")

    # pad 4-character proposal_id values with leading 0s so that proposal_id is
    # a 5-character string.
    if category_key != "multivisit mosaic product":  # pad
        obs_info[0] = "{}{}".format("0" * (5 - len(obs_info[0])), obs_info[0])

    # generate and return filenames
    product_filename_dict = generator_name(obs_info)
    return product_filename_dict
# ----------------------------------------------------------------------------------------------------------

def single_exposure_product_filename_generator(obs_info):
    """
    Generate image and sourcelist filenames for single-exposure products

    Parameters
    ----------
    obs_info : list
        list of items that will be used to generate the filenames: proposal_id,
        obset_id, instrument, detector, filter, ipppssoot, and filetype

    Returns
    --------
    product_filename_dict : dictionary
        A dictionary containing the generated filenames.

    Clarification of variables:
    proposal_id = obs_info[0]
    obset_id    = obs_info[1]
    instrument  = obs_info[2]
    detector    = obs_info[3]
    filter      = obs_info[4]
    ipppssoot   = obs_info[5]
    filetype    = obs_info[6]
    """

    basename = 'hst_' + '_'.join(map(str, obs_info[:5])) + "_" + obs_info[5][:8] + "_" + obs_info[6]
    product_filename_dict = {}
    product_filename_dict["image"] = basename + ".fits"

    return product_filename_dict

# ----------------------------------------------------------------------------------------------------------

def filter_product_filename_generator(obs_info):
    """
    Generate image and sourcelist filenames for filter products

    Parameters
    ----------
    obs_info : list
        list of items that will be used to generate the filenames: proposal_id,
        obset_id, instrument, detector, filter, ipppssoot, and filetype

    Returns
    --------
    product_filename_dict : dictionary
        A dictionary containing the generated filenames.

    Clarification of variables:
    proposal_id = obs_info[0]
    obset_id    = obs_info[1]
    instrument  = obs_info[2]
    detector    = obs_info[3]
    filter      = obs_info[4]
    ipppssoot   = obs_info[5]
    filetype    = obs_info[6]
    """

    basename = 'hst_' + '_'.join(map(str, obs_info[:5])) + "_" + obs_info[5][:6]
    product_filename_dict = {}
    product_filename_dict["image"] = basename + "_" + obs_info[6] + ".fits"
    product_filename_dict["point source catalog"] = basename + "_point-cat.ecsv"
    product_filename_dict["segment source catalog"] = basename + "_segment-cat.ecsv"

    return product_filename_dict


# ----------------------------------------------------------------------------------------------------------

def total_detection_product_filename_generator(obs_info):
    """
    Generate image and sourcelist filenames for total detection products

    Parameters
    ----------
    obs_info : list
        list of items that will be used to generate the filenames: proposal_id,
        obset_id, instrument, detector, filter, ipppssoot, and filetype

    Returns
    --------
    product_filename_dict : dictionary
        A dictionary containing the generated filenames.

    Clarification of variables:
    proposal_id = obs_info[0]
    obset_id    = obs_info[1]
    instrument  = obs_info[2]
    detector    = obs_info[3]
    ipppssoot   = obs_info[4]
    filetype    = obs_info[5]
    """

    basename = 'hst_' + '_'.join(map(str, obs_info[:4])) + '_total_' + obs_info[4][:6]
    product_filename_dict = {}
    product_filename_dict["image"] = basename + "_" + obs_info[5] + ".fits"
    product_filename_dict["point source catalog"] = basename + "_point-cat.ecsv"
    product_filename_dict["segment source catalog"] = basename + "_segment-cat.ecsv"

    return product_filename_dict

# ----------------------------------------------------------------------------------------------------------

def multivisit_mosaic_product_filename_generator(obs_info):
    """
    Generate image and sourcelist filenames for multi-visit mosaic products

    Parameters
    ----------
    obs_info : list
        list of items that will be used to generate the filenames: group_id,
        instrument, detector, filter, and filetype

    Returns
    --------
    product_filename_dict : dictionary
        A dictionary containing the generated filenames.

    Clarification of variables:
    group_num   = obs_info[0]
    instrument  = obs_info[1]
    detector    = obs_info[2]
    filter      = obs_info[3]
    filetype    = obs_info[4]
    """

    basename = 'hst_mos' + '_'.join(map(str, obs_info[:4]))
    product_filename_dict = {}
    product_filename_dict["image"] = basename + " " + obs_info[5] + ".fits"
    product_filename_dict["point source catalog"] = basename + "_point-cat.ecsv"
    product_filename_dict["segment source catalog"] = basename + "_segment-cat.ecsv"

    return product_filename_dict

# ----------------------------------------------------------------------------------------------------------

def determine_filter_name(raw_filter):
    """
    Generate the final filter name to be used for an observation.

    Parameters
    ----------
    raw_filter : string
        filters component one exposure from an input observation visit

    Returns
    -------
    filter_name : string
        final filter name

    If the raw_filter is actually a combination of two filter names, as
    can be true for instruments with two filter wheels, then generate
    a new filter string according the following rules:
    - If one filter name is 'clear*', then use the other filter name.
    - If both filter names are 'clear*', then use 'clear'.
    - If there are two filters in use, then use 'filter1-filter2'.
    - If one filter is a polarizer ('pol*'), then always put the polarizer
      name second (e.g., 'f606w-pol60').
    - NOTE: There should always be at least one filter name provided to
      this routine or this input is invalid.
    """

    raw_filter = raw_filter.lower()

    # There might be two filters, so split the filter names into a list
    filter_list = raw_filter.split(';')
    output_filter_list = []

    for filt in filter_list:
        # Get the names of the non-clear filters
        if 'clear' not in filt:
            output_filter_list.append(filt)

    if not output_filter_list:
        filter_name = 'clear'
    else:
        if output_filter_list[0].startswith('pol'):
            output_filter_list.reverse()

        delimiter = '-'
        filter_name = delimiter.join(output_filter_list)

    return filter_name
