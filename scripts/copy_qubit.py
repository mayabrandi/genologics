#!/usr/bin/env python
DESC = """EPP script to copy user defined field from any process to associated 
project/projects in Clarity LIMS. If the specifyed process handles many artifacts 
associated to different projects, all these projects will get the specifyed udf.
 
Can be executed in the background or triggered by a user pressing a "blue button".

The script can output two different logs, where the status_changelog 
contains notes with the technician, the date and changed status for each 
copied status. The regular log file contains regular execution information.

Written by Maya Brandi 
"""
import os
import sys
import logging
import numpy as np

from argparse import ArgumentParser
from requests import HTTPError
from genologics.lims import Lims
from genologics.config import BASEURI,USERNAME,PASSWORD
from genologics.entities import Process
from genologics.epp import EppLogger
from genologics.epp import ReadResultFiles
lims = Lims(BASEURI,USERNAME,PASSWORD)

def main(lims, pid, epp_logger):
    process = Process(lims,id = pid)
    file_handler = ReadResultFiles(process) # logging
    qubit_result_file = file_handler.shared_csv_files['Qubit Result File']
    qubit_result_file, warn = file_handler.format_csv_file(qubit_result_file)
    target_files = process.result_files()
    logg = {'sucsessfully_copied' : {'samples':[],
                'log_string':'Qubit mesurements were copied sucsessfully for samples:',
                'user_string': ''},
            'un_sucsessfully_copied' : {'samples':[],
                'log_string':'Qubit mesurements were found but not sucsessfully copied for samples:',
                'user_string': 'Qubit mesurements were found but not successfully copied for some samples.'},
            'missing' : {'samples':[],
                'log_string':'Samples missing in Qubit Result File:',
                'user_string': 'Some samples are missing in Qubit Result File, and were not copied.'},
            'missing_info' : {'samples':[],
                'log_string':'Sample Concentration missing in Qubit Result File for Samples:',
                'user_string': 'Some Samples had missing or bad formated info in Qubit Result File and were not copied.'}}
    abstract = ''

    for target_file in target_files:
        sample = target_file.samples[0].name
        if qubit_result_file.has_key(sample):
            sample_mesurements = qubit_result_file[sample]
            if "Sample Concentration" in sample_mesurements.keys():
                conc, unit = sample_mesurements["Sample Concentration"]
                if conc == 'Out Of Range':
                    target_file.qc_flag = "FAILED"
                else:
                    try:
                        conc = float(conc)
                        target_file.qc_flag = "PASSED"
                        if unit == 'ng/mL':
                            conc = np.true_divide(conc, 1000)
                        target_file.udf['Concentration'] = conc
                        target_file.udf['Conc. Units'] = 'ng/ul'
                    except:
                        logg['missing_info']['samples'].append(sample)
                try:
                    target_file.put()
                    logg['sucsessfully_copied']['samples'].append(sample)
                except (TypeError, HTTPError) as e:
                    logg['un_sucsessfully_copied']['samples'].append(sample)
                    print >> sys.stderr, "Error while updating element: {0}".format(e)    
        else:
            logg['missing']['samples'].append(sample)

    for subj, inf in logg.items():
        if inf['samples']:
            logging.info( '{0} {1}.'.format(inf['log_string'], ', '.join(inf['samples'])))
            abstract = ' '.join([abstract, inf['user_string']])
    print >> sys.stderr, ' '.join([abstract, warn])

if __name__ == "__main__":
    parser = ArgumentParser(description=DESC)
    parser.add_argument('--pid', default = '24-38458', dest = 'pid',
                        help='Lims id for current Process')
    parser.add_argument('--log', dest = 'log',
                        help=('File name for standard log file, '
                              'for runtime information and problems.'))

    args = parser.parse_args()

    lims = Lims(BASEURI,USERNAME,PASSWORD)
    lims.check_version()

    with EppLogger(log_file=args.log, lims=lims, prepend=True) as epp_logger:
        main(lims, args.pid, epp_logger)

