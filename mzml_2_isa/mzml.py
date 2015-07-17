from lxml import etree
import collections
import json
import textwrap
import argparse
import os

from obo import oboparse, oboTranslator

class mzMLmeta(object):
    """ Class to store and obtain the meta information from the mzML file

    The class uses the xpaths of mzML locations and then extracts meta information at these locations.

    The meta info taken is determined by the ontology terms and a set of rules associated with that term e.g.
    if it can be repeated, if has associated software if it has a value as well as name.

    Creates a dictionary of meta information and a JSON structure e.g:

        "mass_analyzer_type": {
            "accession": "MS:1000484",
            "name": "orbitrap"
        },
        "ionization_type": {
            "accession": "MS:1000073",
            "name": "electrospray ionization"
        }
    """

    def __init__(self, in_file):
        """ **Constructor**: Setup the xpaths and terms. Then run the various extraction methods

        :param str in_file: path to mzML file
        :ivar obj self.tree: The xml tree object
        :ivar dict self.ns: Dictionary of the namespace of the mzML file
        :ivar obj self.obo: Parsing object used to get children and parents of the ontological terms
        :ivar obj self.meta: Meta information in python dictionary
        :ivar obj self.meta_json: Meta information in json format
        :ivar obj self.meta_isa: Meta information with names compatible with ISA-Tab
        """
        print "Parsing mzml file:", in_file

        # setup lxml parsing
        self.in_file = in_file
        self.tree = etree.parse(in_file)
        self.ns = {'s':'http://psi.hupo.org/ms/mzml'} # namespace

        # Get controlled vocb from the obo ontology file
        dirname = os.path.dirname(os.path.realpath(__file__))
        obo_path = os.path.join(dirname, "psi-ms.obo")
        self.obo = oboparse(obo_path)

        #initalize the meta variables
        self.meta = collections.OrderedDict()
        self.meta_isa = collections.OrderedDict()
        self.meta_json = ""

        # xpaths for the mzML locations that we want the meta information from any cvParam elements
        xpaths = {'file_content': '//s:indexedmzML/s:mzML/s:fileDescription/s:fileContent/s:cvParam',
                  'source_file': '//s:indexedmzML/s:mzML/s:fileDescription/s:sourceFileList/s:sourceFile/s:cvParam',
                  'ionization': '//s:indexedmzML/s:mzML/s:instrumentConfigurationList/s:instrumentConfiguration/s:componentList/s:source/s:cvParam',
                  'analyzer': '//s:indexedmzML/s:mzML/s:instrumentConfigurationList/s:instrumentConfiguration/s:componentList/s:analyzer/s:cvParam',
                  'detector': '//s:indexedmzML/s:mzML/s:instrumentConfigurationList/s:instrumentConfiguration/s:componentList/s:detector/s:cvParam',
                  'data_processing': '//s:indexedmzML/s:mzML/s:dataProcessingList/s:dataProcessing/s:processingMethod/s:cvParam'
                  }

        # We create a dictionary that contains "search parameters" that we use to parse the xml location from the xpaths
        # above
        #
        # name: [string], What the CV will be saved as
        # plus1: [Boolean], If there are multiple of this CV
        # value: [Boolean], if there is an associated value with this CV
        # soft: [Boolean], If there is associated software CV associated with this CV
        # attribute: [Boolean], if the CV is an attribute then has to be handled differently
        terms = collections.OrderedDict()
        terms['file_content'] = {
                'MS:1000524': {'attribute': False, 'name': 'Data file content', 'plus1': True, 'value':False, 'soft': False},
                'MS:1000525': {'attribute': False, 'name': 'Spectrum representation', 'plus1': False, 'value':False, 'soft': False}
        }

        terms['source_file'] = {
            'MS:1000767': {'attribute': False, 'name':'Native spectrum identifier format', 'plus1': False, 'value':False, 'soft': False},
            'MS:1000561': {'attribute': False, 'name':'Raw data file checksum type', 'plus1': True, 'value':True, 'soft': False},
            'MS:1000560': {'attribute': False, 'name':'Raw data file format', 'plus1': False, 'value':False, 'soft': False}
        }

        terms['ionization'] = {
                'MS:1000482': {'attribute': True, 'name':'source_attribute', 'plus1': True, 'value':True, 'soft': False},
                'MS:1000008': {'attribute': False, 'name':'Ion source', 'plus1': False, 'value':False, 'soft': False},
                'MS:1000007': {'attribute': False, 'name':'Inlet type', 'plus1': False, 'value':False, 'soft': False}
        }

        terms['analyzer'] = {
                'MS:1000480': {'attribute': True, 'name':'analyzer_attribute', 'plus1': True, 'value':True, 'soft': False},
                'MS:1000443': {'attribute': False, 'name':'Mass analyzer', 'plus1': False, 'value':False, 'soft': False}
        }

        terms['detector'] = {
                'MS:1000481': {'attribute': True, 'name':'detector_attribute', 'plus1': True, 'value': True, 'soft': False},
                'MS:1000026': {'attribute': False, 'name':'Detector', 'plus1': False, 'value': False, 'soft': False},
                'MS:1000027': {'attribute': False, 'name':'Detector mode', 'plus1': True, 'value':False, 'soft': False}
        }

        terms['data_processing'] = {
                'MS:1000630': {'attribute': True, 'name':'data_processing_parameter', 'plus1': True, 'value': True, 'soft': True},
                'MS:1000452': {'attribute': False, 'name':'data transformation', 'plus1': True, 'value': False, 'soft': True},
        }

        # update self.meta with the relevant meta infromation
        self.extract_meta(terms, xpaths)

        # The instrument information has to be extracted separately
        self.instrument()

        # get derived data e.g. file count, polarity
        self.derived()

        # Get the isa_tab compatible meta dictionary
        self.isa_tab_compatible()

        # get meta information in json format
        self.meta_json = json.dumps(self.meta, indent=2)

    def extract_meta(self, terms, xpaths):
         """ Extract meta information for CV terms based on their location in the xml file

         Updates the self.meta dictionary with the relevant meta information

        :param dict terms: The CV and "search parameters" required at the xml locations
        :param dict xpath: The xpath locations to be searched
        .. seealso::
            :func:`cvParam_loop`
        """

        # loop though the xpaths
        for location_name, xpath in xpaths.iteritems():

            # get the elements from the xpath
            elements = self.tree.xpath(xpath,namespaces=self.ns)

            # loop through the elements and see if the terms are found
            self.cvParam_loop(elements, location_name, terms)

    def cvParam_loop(self, elements, location_name, terms):
         """ loop through the elements and see if the terms are found. If they are update the self.meta dict

         :param obj elements: lxml object
         :param str location_name: Name of the xml location
         :param dict terms: CV terms we want
         """
        # get associated meta information from each file
        descendents = {k:self.obo.getDescendents(k) for k in terms[location_name]}

        #print descendents
        c = 1

        # go through every cvParam element
        for e in elements:
            # go through the terms available for this location
            for accession, info in terms[location_name].iteritems():
                # check if the element is one of the terms we are looking for
                if e.attrib['accession'] in descendents[accession]:
                    if(info['attribute']):
                        meta_name = e.tag
                    else:
                        meta_name = info['name']
                    # Check if there can be more than one of the same term
                    if(info['plus1']):
                        # Setup the dictionary for multiple entries
                        try:
                            self.meta[meta_name]['entry_list'][c] = {'accession':e.attrib['accession'], 'name':e.attrib['name']}
                        except KeyError:
                            self.meta[meta_name] = {'entry_list':{c:{'accession':e.attrib['accession'], 'name':e.attrib['name']}}}
                        # Check if a value is associated with this CV
                        if (info['value']):
                            self.meta[meta_name]['entry_list'][c]['value'] = e.attrib['value']
                        c += 1
                    else:
                        # Standard CV with only with entry
                        self.meta[meta_name] = {'accession':e.attrib['accession'], 'name':e.attrib['name']}
                        # Check if value associated
                        if (info['value']):
                            self.meta[meta_name]['value'] = e.attrib['value']
                    # Check if there is expected associated software
                    if (info['soft']):
                        soft_ref = e.getparent().attrib['softwareRef']
                        self.software(soft_ref, meta_name)

    def instrument(self):
        """ The instrument meta information is more complicated to extract so it has its own function

        Updates the self.meta with the relevant meta information.

        Requires looking at the hierarchy of ontological terms to get all the instrument information
        """
        # To convert accession number to name
        translator = oboTranslator()

        # gets the first Instrument config (something to watch out for)
        ic_ref = self.tree.xpath('//s:indexedmzML/s:mzML/s:instrumentConfigurationList/s:instrumentConfiguration/'
                             's:referenceableParamGroupRef/@ref', namespaces=self.ns)[0]

        elements = self.tree.xpath('//s:indexedmzML/s:mzML/s:referenceableParamGroupList/s:referenceableParamGroup',
                                 namespaces=self.ns)
        # Loop through xml elements
        for e in elements:
            # get all CV information from the instrument config
            if e.attrib['id']==ic_ref:
                instrument_e = e.findall('s:cvParam', namespaces=self.ns)

                for ie in instrument_e:

                    # Get the instrument manufacturer
                    if ie.attrib['accession'] in self.obo.getDescendents('MS:1000031'):
                        self.meta['Instrument'] = {'accession': ie.attrib['accession'], 'name':ie.attrib['name']}

                        # get manufacturer (actually just derived from instrument model). Want to get the top level
                        # so have to go up (should only be a maximum of 3 steps above in the heirachy but do up 10 to be
                        # sure.
                        # directly related children of the instrument model
                        direct_c = self.obo.terms['MS:1000031']['c']

                        parent = self.obo.terms[ie.attrib['accession']]['p']

                        for i in range(10):
                            # first get direct parent of the current instrument element
                            if parent[0] in direct_c:
                                self.meta['Instrument manufacturer'] = {'accession': parent[0], 'name':translator[parent[0]]}
                                break
                            else:
                                parent = self.obo.terms[parent[0]]['p']

                    # get serial number
                    elif ie.attrib['accession'] == 'MS:1000529':
                        self.meta['Instrument serial number'] = {'value': ie.attrib['value']}

        soft_ref = self.tree.xpath('//s:indexedmzML/s:mzML/s:instrumentConfigurationList/s:instrumentConfiguration/'
                             's:softwareRef/@ref', namespaces=self.ns)[0]

        # Get associated software
        self.software(soft_ref, 'Instrument')

    def software(self, soft_ref, name):
        """ Get associated software of cv term. Updates the self.meta dictionary

        :param str soft_ref: Reference to software found in xml file
        :param str name: Name of the associated CV term that the software is associated to
        """

        elements = self.tree.xpath('//s:indexedmzML/s:mzML/s:softwareList/s:software',
                                 namespaces=self.ns)

        for e in elements:

            if e.attrib['id'] == soft_ref:
                if e.attrib['version']:
                    self.meta[name+' software version'] = {'value': e.attrib['version']}

                software_cvParam = e.findall('s:cvParam', namespaces=self.ns)

                for ie in software_cvParam:
                    self.meta[name+' software'] = {'accession':ie.attrib['accession'], 'name':ie.attrib['name']}

    def derived(self):
        """ Get the derived meta information. Updates the self.meta dictionary"""
        #######################
        # Get polarity and time
        #######################
        sp_cv = self.tree.xpath('//s:indexedmzML/s:mzML/s:run/s:spectrumList/s:spectrum/s:cvParam',
                                   namespaces=self.ns)
        pos = False
        neg = False

        for i in sp_cv:
            if i.attrib['accession'] == 'MS:1000130':
                pos = True
            if i.attrib['accession'] == 'MS:1000129':
                neg = True

        if pos & neg:
            polarity = "positive/negative"
        elif pos:
            polarity = "positive"
        elif neg:
            polarity = "negative"
        else:
            polarity = "Not determined"

        #######################
        # Get mzrange
        #######################
        scan_window_cv = self.tree.xpath('//s:indexedmzML/s:mzML/s:run/s:spectrumList/s:spectrum/s:scanList/s:scan/'
                                 's:scanWindowList/s:scanWindow/s:cvParam',
                                   namespaces=self.ns)
        minmz_l = []
        maxmz_l = []

        for i in scan_window_cv:

            if i.attrib['accession'] == 'MS:1000501':
                minmz_l.append(float(i.attrib['value']))
            if i.attrib['accession'] == 'MS:1000500':
                maxmz_l.append(float(i.attrib['value']))

        minmz = str(int(min(minmz_l)))
        maxmz = str(int(max(maxmz_l)))
        mzrange = minmz + " - " + maxmz

        #######################
        # Get timerange
        #######################
        scan_cv =  self.tree.xpath('//s:indexedmzML/s:mzML/s:run/s:spectrumList/s:spectrum/s:scanList/s:scan/s:cvParam',
                                   namespaces=self.ns)

        time = [ float(i.attrib['value']) for i in scan_cv if i.attrib['accession'] == 'MS:1000016']

        minrt = str(round(min(time),4))
        maxrt = str(round(max(time),4))
        timerange = minrt + " - " + maxrt

        #####################
        # Some other stuff
        ####################
        scan_num = self.tree.xpath('//s:indexedmzML/s:mzML/s:run/s:spectrumList/@count', namespaces=self.ns)[0]

        cv = self.tree.xpath('//s:indexedmzML/s:mzML/s:cvList/s:cv/@id', namespaces=self.ns)[0]

        if not 'MS' in cv:
            print "Standard controlled vocab not available. Can not parse "
            return
        else:
            self.meta['term_source'] = {'value': 'MS'}

        raw_file = self.tree.xpath('//s:indexedmzML/s:mzML/s:fileDescription/s:sourceFileList/'
                             's:sourceFile/@name', namespaces=self.ns)[0]

        self.meta['Raw Spectral Data File'] = {'value': raw_file}
        self.meta['MS Assay Name'] = {'value': os.path.splitext(os.path.basename(raw_file))[0]}
        self.meta['Number of scans'] = {'value': int(scan_num)}
        self.meta['Scan m/z range'] = {'value': mzrange}
        self.meta['Scan polarity'] = {'value': polarity}
        self.meta['Time range'] = {'value': timerange}
        self.meta['Derived Spectral Data File'] = {'value': os.path.basename(self.in_file)} # mzML file name

    def isa_tab_compatible(self):
        """ Get the ISA-tab comptibale meta dictionary. Updates self.meta_isa"""
        keep = ["data transformation", "data transformation software version", "data transformation software",
                "term_source", "Raw Spectral Data File", "MS Assay Name"]

        for meta_name in self.meta:
            if meta_name in keep:
                self.meta_isa[meta_name] = self.meta[meta_name]
            else:
                self.meta_isa["Parameter Value["+meta_name+"]"] = self.meta[meta_name]