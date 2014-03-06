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
    qubit_result_file = file_handler.shared_files['Qubit Result File']
    qubit_result_file = file_handler.format_parsed_file(qubit_result_file)
    analytes, inf = process.analytes()

    for analyte in analytes:
        sample = analyte.samples[0].name
        if qubit_result_file.has_key(sample):
            sample_mesurements = qubit_result_file[sample]
            if "Sample Concentration" in sample_mesurements.keys():
                conc, unit = sample_mesurements["Sample Concentration"]
                if conc == 'Out Of Range':
                    analyte.qc_flag = "FAILED"
                else:
                    analyte.qc_flag = "PASSED"
                    conc = float(conc)
                    if unit == 'ng/mL':
                        conc = np.true_divide(conc, 1000)
                    analyte.udf['Concentration'] = conc
                    analyte.udf['Conc. Units'] = 'ng/ul'
                try:
                    analyte.put()
                    #logging.info(('Qubit mesurements were copied sucsessfully.'))
                except (TypeError, HTTPError) as e:
                    print >> sys.stderr, "Error while updating element: {0}".format(e)
            else:
                    logging.info(('Sample Concentration missing for Sample {0} in Qubit Result File'.format(sample)))
                
        else:
            logging.info(('Sample {0} missing in Qubit Result File'.format(sample)))
        
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

