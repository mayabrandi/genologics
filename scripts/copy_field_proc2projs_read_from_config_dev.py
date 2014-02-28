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
import ConfigParser

from ast import literal_eval
from argparse import ArgumentParser

from genologics.lims import Lims
from genologics.config import BASEURI,USERNAME,PASSWORD
from genologics.entities import Process
from genologics.epp import EppLogger
from genologics.epp import CopyField

config = ConfigParser.SafeConfigParser()
config.readfp(open('/home/glsai/.genologicsargsrc'))
CONFSECTION = 'FieldProc2ProjArgs'

def copy_fields(s_elt, d_elts, s_udf, d_udf, changelog):
    incorrect_udfs = 0
    no_updated = 0
    for d_elt in d_elts:
        with open(changelog, 'a') as changelog_f:
            if s_udf in s_elt.udf:
                copy_sesion = CopyField(s_elt, d_elt, s_udf, d_udf)
                test = copy_sesion.copy_udf(changelog_f)
                if test:
                    no_updated = no_updated + 1
            else:
                logging.warning(("Udf: {1} in Process {0} is undefined/blank, exiting").format(s_elt.id, args.source_udf))
                incorrect_udfs = incorrect_udfs + 1
    if incorrect_udfs > 0:
        warn = "Failed to update %s project(s) due to wrong source udf info." %incorrect_udfs
    else:
        warn = ''

    d = {'up': no_updated,
         'ap': len(d_elts),
         'w' : warn}
    return ("Updated {up} projects(s), out of {ap} in total. {w}").format(**d)



def main(lims, args, epp_logger):
    d_elts = []
    s_elt = Process(lims,id = args.pid)
    analytes, inf = s_elt.analytes()
    changelog = args.status_changelog

    for analyte in analytes:
        for samp in analyte.samples:
            d_elts.append(samp.project)
    d_elts = list(set(d_elts))

    if changelog:
        dir = os.getcwd()
        destination = os.path.join(dir, changelog)
        if not os.path.isfile(destination):
            epp_logger.prepend_old_log(changelog)

    if args.source_udf:
        abstract = copy_fields(s_elt, d_elts, args.source_udf, args.dest_udf, changelog)
        print >> sys.stderr, abstract
    elif args.conf_arg:
        print '"""""""""""""""'
        print args.conf_arg
        print '******'
        field_dict = config.get(CONFSECTION, args.conf_arg).rstrip()
        field_dict = literal_eval(field_dict)
        print field_dict
        for s_udf, d_udf in field_dict.items():
            abstract = copy_fields(s_elt, d_elts, s_udf, d_udf, changelog)
            print >> sys.stderr, abstract


if __name__ == "__main__":
    parser = ArgumentParser(description=DESC)
    parser.add_argument('--pid',
                        help='Lims id for current Process')
    parser.add_argument('--log',
                        help=('File name for standard log file, '
                              'for runtime information and problems.'))
    parser.add_argument('-s', '--source_udf', type=str, default=None,
                        help=('Name of the source user defined field'
                               'that will be copied.'))
    parser.add_argument('-d', '--dest_udf', type=str, default=None,
                        help=('Name of the destination user defined'
                              'field that will be written to. This'
                              'argument is optional, if left empty'
                              'the source_udf argument is used instead.'))
    parser.add_argument('-c', '--status_changelog',
                        help=('File name for status changelog file, for'
                              'concise information on who, what and when'
                              'for status change events. '
                              'Prepends the old changelog file by default.'))
    parser.add_argument('-f', '--field_dict',
                        help=('Specify a dict of fields that will be copied all at once.'
                               'Keys will be used as source udf. Values as target udf'))
    parser.add_argument('-a', '--conf_arg',
                        help=('Argument in CONFSECTION specifyed in configfile.'))

    args = parser.parse_args()

    lims = Lims(BASEURI,USERNAME,PASSWORD)
    lims.check_version()

    with EppLogger(log_file=args.log, lims=lims, prepend=True) as epp_logger:
        main(lims, args, epp_logger)

