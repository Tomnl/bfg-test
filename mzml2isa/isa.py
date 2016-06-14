"""
Content
-----------------------------------------------------------------------------
This module contains an ISA_Tab class which is used to create an ISA-Tab 
structure based on a python meta dictionary generated by the mzMLmeta class.
The default ISA-tab present in ./default was created using the ISA-Tab
configuration tool.

About
-----------------------------------------------------------------------------
The mzml2isa parser was created by Tom Lawson (University of Birmingham, UK) 
as part of a NERC funded placement at EBI Cambridge in June 2015. Python 3
port and small enhancements were carried out by Martin Larralde (ENS Cachan, 
France) in June 2016 during an internship at the EBI Cambridge.

License
-----------------------------------------------------------------------------
GNU General Public License version 3.0 (GPLv3)
"""

import csv
import os
import sys
import warnings

from mzml2isa.versionutils import RMODE, WMODE, iterdict, dict_update


USERMETA = {'characteristics':           {'organism':       {'value':'', 'accession':'', 'ref':''},
                                          'variant':        {'value':'', 'accession':'', 'ref':''},
                                          'organism_part':  {'value':'', 'accession':'', 'ref':''},
                                         },
            'investigation':             {'identifier': '', 'title': 'Investigation', 'description': '',
                                          'submission_date':'', 'release_date':''
                                         },
            'investigation_publication': {'pubmed': '', 'doi': '', 'author_list': '', 'title':'',
                                          'status': {'value':'', 'accession':'', 'ref':'PSO'},
                                         },                                     
            'investigation_contacts':     {'first_name': '', 'last_name': '', 'mid_initials':'', 'email':'', 
                                          'fax': '', 'phone':'', 'adress':'', 'affiliation':'',
                                          'roles': {'value':'', 'accession':'', 'ref':''},
                                         },
            'study':                     {
                                          'title': '', 'description': '', 'submission_date':'', 'release_date':'',
                                         },
            'study_publication':         {'pubmed': '', 'doi': '', 'author_list': '', 'title':'',
                                          'status': {'value':'', 'accession':'', 'ref':'PSO'},
                                         },
            'study_factors':             {'name': '',
                                          'type': {'value':'', 'accession':'', 'ref':''},
                                         },
            'study_contacts':             {'first_name': '', 'last_name': '', 'mid_initials':'', 'email':'', 
                                          'fax': '', 'phone':'', 'adress':'', 'affiliation':'',
                                          'roles': {'value':'', 'accession':'', 'ref':''},
                                         },                                         

            'description':               {'sample_collect':'', 'extraction':'', 'chroma':'', 'mass_spec':'', 
                                          'data_trans':'', 'metabo_id':''
                                         },

           }


class ISA_Tab(object):
    """ Class to create an ISA-Tab structure from on a python meta dictionary.

    The meta dictionnary is generated by the mzMLmeta class. This class uses
    the default ISA-tab found in ./default, created using the ISA-Tab 
    configuration tool, as a template.

    Investigation, study and assay files are created based on the metadata
    extracted from the meta dictionary.
    """
    def __init__(self, metalist, out_dir, name, usermeta = {}, separate_polarity = True):
        """ Setup the xpaths and terms & run the various extraction methods

        :param list metalist: list of dictionaries containing mzML metadata
        :param str out_dir:   path to out directory
        :param str name:      study identifier name
        :param dict usermeta: a dict containing more info about the study
        """
        print("Parse mzML meta information into ISA-Tab structure")
        print(separate_polarity)

        # Setup the instance variables
        # dictionary allow for easy formatting of the study file.
        dirname = os.path.dirname(os.path.realpath(__file__))
        self.isa_env = {
            'out_dir': os.path.join(out_dir, name),
            'study_identifier':  name, 
            'study_file_name': 's_'+ name+'.txt',
            'assay_file_name': 'a_'+ name+'_metabolite_profiling_mass_spectrometry.txt',
            'assay_polar_file_name': 'a_'+ name+'_metabolite_profiling_mass_spectrometry_{}.txt',
            'investigation_file_name': 'i_'+ name+'.txt',
            'default_path': os.path.join(dirname, 'default'),
            'platform': {},
        }
        
        # create the new out dir
        if not os.path.exists(self.isa_env['out_dir']):
            os.makedirs(self.isa_env['out_dir'])

        # Complete usermeta with empty fields
        self.usermeta_complete(usermeta)

        # Check what instrument to use for the platform used to desribe the assay
        self.check_assay_name(metalist)

        # Create a new assay file based on the relevant meta information
        self.create_assay(metalist, separate_polarity)

        # Create a new investigation file
        self.create_investigation()

        # Create a new study file (will just be copy of the default)
        self.create_study()


    def check_assay_name(self, metalist):
        """ Check what instrument to use to describe the assay

        :param list metalist: list of dictionaries containing mzML metadata
        """
        instruments = []
        accession = []
        for meta in metalist:
            
            try: 
                instruments.append(meta['Parameter Value[Instrument]']['name'])
                accession.append(meta['Parameter Value[Instrument]']['accession'])

            except KeyError: # Missing Instrument (quite often with Waters Models)
                warnings.warn("No instrument was found in the source file.", UserWarning)
            

        if len(set(instruments)) > 1:
            #print("Warning: More than one instrument platform used. Metabolights by default divides assays based on" \
            #      " platform. For convenience here though only one assay file will be created including all files, " \
            #      " the investigation file though will detail the most common platform used" \
            #      )
            warnings.warn("More than one instrument platform used."
                          " Investigation file will detail the most common platform used.",
                          UserWarning)


        # get most common item in list
        try:
            c_name = max(set(instruments), key=instruments.count)
            c_accession = max(set(accession), key=accession.count)
        except ValueError:
            c_name = ''
            c_accession = ''

        self.isa_env['platform'] = {
            'name':c_name,
            'accession':c_accession,
            'ref': c_accession.split(':')[0]
        }

    def create_investigation(self):
        """ Create the investigation file."""

        investigation_file = os.path.join(self.isa_env['default_path'], 'i_Investigation.txt')
        new_i_path = os.path.join(self.isa_env['out_dir'], self.isa_env['investigation_file_name'])

        with open(investigation_file, RMODE) as i_in:
            with open(new_i_path, "w") as i_out:
                for l in i_in:
                    
                    # If more than one study assay was written, more columns must be added
                    if l[:11] == 'Study Assay' and len(self.written_assays) != 1:
                        assay_row = l.split("\t") 
                        if assay_row[0] == "Study Assay File Name":     # Change the
                            l = assay_row[0]                            # filename
                            for assay in self.written_assays:           # section
                                l += '\t"{}"'.format(assay)
                        else:                                           # duplicate other sections
                            l = assay_row[0] + "\t" + "\t".join(len(self.written_assays)*[assay_row[1].strip()])
                        l += '\n'

                    l = l.format(**self.isa_env, **self.usermeta).format()
                    i_out.write(l)

    def create_study(self):
        """ Create the study file   """

        study_file = os.path.join(self.isa_env['default_path'], 's_mzML_parse.txt')
        new_s_path = os.path.join(self.isa_env['out_dir'], self.isa_env['study_file_name'])

        # get default rows
        with open(study_file, RMODE) as isa_default:
            #headers_row, default_row = [x.rstrip().replace('"', '').split('\t') for x in isa_default]
            headers_line, default_line = [x.rstrip().replace('"', '') for x in isa_default]

        with open(new_s_path, 'w') as isa_new:
            writer = csv.writer(isa_new, quotechar='"', quoting=csv.QUOTE_ALL, delimiter='\t')

            # Write headers rows
            # sample_name_idx = headers_row.index("Sample Name")
            writer.writerow(headers_line.split('\t'))

            # Write default row
            for sample_name in self.sample_names:
                #default_row[sample_name_idx] = sample_name
                writer.writerow(default_line.format(name=sample_name, **self.usermeta).split('\t'))


    def create_assay(self, metalist, separate_polarity):
        """ Create the assay file.
        
        - Loops through a default assay file and locates the columns for the 
          mass spectrometry (MS) section.
        - Get associated meta information for each column of the MS section
        - Deletes any unused MS columns
        - Creates the the new assay file

        :param list metalist: list of dictionaries containing mzML metadata
        """

        assay_file = os.path.join(self.isa_env['default_path'], 'a_mzML_parse.txt')

        #=================================================
        # Get location of the mass spectrometry section
        #=================================================
        with open(assay_file, RMODE) as isa_default:
            headers_row, standard_row = [x.rstrip().replace('"', '').split('\t') for x in isa_default]

        sample_name_idx = headers_row.index("Sample Name")
        mass_protocol_idx = standard_row.index("Mass spectrometry")
        mass_end_idx = standard_row.index("Metabolite identification")
        polarity_idx = headers_row.index('Parameter Value[Scan polarity]')

        mass_headers = headers_row[mass_protocol_idx+1:mass_end_idx]

        pre_row = standard_row[:mass_protocol_idx+1]
        mass_row = standard_row[mass_protocol_idx+1:mass_end_idx]
        post_row = standard_row[mass_end_idx:]

        self.new_mass_row = [""]*len(mass_headers)
        self.sample_names = []

        full_row = []

        #=================================================
        # Get associated meta information for each column
        #=================================================
        # The columns need to correspond to the names of the dictionary
        # Loop through list of the meta dictionaries
        for file_meta in metalist:
            # get the names and associated dictionaries for each meta term
            for key, value in file_meta.items():
                # special case for sample name as it is not amongst the mass columns
                if key == "Sample Name":
                    pre_row[sample_name_idx] = value['value']
                    self.sample_names.append(value['value'])

                # if key is an entry list it means this means there can be more than one of this meta type
                # This will check all meta data where there might be multiple columns of the same data e.g.
                # data file content
                if "entry_list" in value.keys():
                    # loop through the multiple entries on the entry list
                    for list_item in value.values():
                        # Locate the available columns
                        indices = [i for i, val in enumerate(mass_headers) if val == key]
                        # needs to be in reverse order
                        indices = indices[::-1]
                        # Add the items to the available columns untill they are all full up
                        for meta_id, meta_val in list_item.items():
                            try:
                                main = indices.pop()
                            except IndexError as e:
                                pass
                            else:
                                # update row with meta information
                                self.update_row(main, meta_val)
                else:
                    try:
                        # get matching column for meta information
                        main = mass_headers.index(key)
                    except ValueError as e:
                        pass
                    else:
                        # update row with meta information
                        self.update_row(main, value)

            # Add a list a fully updated row
            full_row.append(pre_row+self.new_mass_row+post_row)

        #=================================================
        # Delete unused mass spectrometry columns
        #=================================================
        headers_row, full_row = self.remove_blank_columns(mass_protocol_idx, mass_end_idx, full_row,headers_row)

        #=================================================
        # Check if the assay contains differents polarities
        #=================================================
        polarities = set([x[polarity_idx] for x in full_row])

        #=================================================
        # Create the the new assay file
        #=================================================
        self.written_assays = []
        if len(polarities) == 1 or not separate_polarity:
            with open(os.path.join(self.isa_env['out_dir'],self.isa_env['assay_file_name']), WMODE) as new_file:
                writer = csv.writer(new_file, quotechar='"', quoting=csv.QUOTE_ALL, delimiter='\t')
                writer.writerow(headers_row)

                # need to add in data-transformation info that is lost in the above processing
                data_tran_idx = headers_row.index("Derived Spectral Data File")-2

                for row in full_row:
                    row[data_tran_idx] = "Data transformation"
                    writer.writerow(row)
            self.written_assays.append(self.isa_env['assay_file_name'])

        else:
            for polarity in polarities:
                polarity_row = [x for x in full_row if x[polarity_idx] == polarity]
                
                with open(os.path.join(self.isa_env['out_dir'], self.isa_env['assay_polar_file_name'].format(polarity[:3].upper())), 
                          WMODE) as new_file:

                    writer = csv.writer(new_file, quotechar='"', quoting=csv.QUOTE_ALL, delimiter='\t')
                    writer.writerow(headers_row)

                    data_tran_idx = headers_row.index("Derived Spectral Data File")-2

                    for row in polarity_row:
                        row[data_tran_idx] = "Data transformation"
                        writer.writerow(row)
                self.written_assays.append(self.isa_env['assay_polar_file_name'].format(polarity[:3].upper()))



    def update_row(self, main, meta_val):
        """ Updates the MS section of a row based on the meta information.

        i.e. updates self.new_mass_row with the meta info to the location 
        provided.

        :param int main:      index of the matched column
        :param dict meta_val: dictionary of the associated meta values
        """
        # First add the "name" of the meta, for instrument this would something like "Q Exactive"
        try:
            name = meta_val['name']
        except KeyError as e:
            pass
        else:
            self.new_mass_row[main] = name
            main = main+1

        # Add associated accession
        try:
            accession = meta_val['accession']
        except KeyError as e:
            pass
        else:
            self.new_mass_row[main] = "MS"
            main = main+1
            self.new_mass_row[main] = accession
            main = main+1

        # Add associated value e.g. for number of scans this would be 58
        try:
            value = meta_val['value']
        except KeyError as e:
            pass
        else:
            self.new_mass_row[main] = value

    def remove_blank_columns(self, start, end, full_row, headers_row):
        """ Delete unused mass spectrometry columns between start & end.

        :param int start:      index of the column to start at
        :param int end:        index of the column to end at
        :param list full_row:  row to remove columns from
        :param list headers_row: headers to remove columns from
        
        :returns list update_headers, list updated_row
        """
        delete_cols = []
        updated_row = []
        for i in range(start,end-3):
            # check if a column is empty
            column = [col[i] for col in full_row]
            if column.count('') == len(full_row):
                delete_cols.append(i)

        for row in full_row:
            # pythons way of deleting multiple entries of a list. So much more hassle than numpy/pandas....
            row[:] = [ item for i, item in enumerate(row) if i not in delete_cols ]
            updated_row.append(row)

        updated_headers = []
        updated_headers[:] = [ item for i, item in enumerate(headers_row) if i not in delete_cols ]

        return updated_headers, updated_row

    def usermeta_complete(self, usermeta):
        self.usermeta = dict_update(USERMETA, usermeta)