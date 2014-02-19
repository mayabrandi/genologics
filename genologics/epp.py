"""Contains useful and reusable code for EPP scripts.

Classes, methods and exceptions.

Johannes Alneberg, Science for Life Laboratory, Stockholm, Sweden.
Copyright (C) 2013 Johannes Alneberg
"""

import logging
import sys
import os
import pkg_resources
from pkg_resources import DistributionNotFound
from shutil import copy
from requests import HTTPError
from genologics.entities import Artifact
from genologics.config import MAIN_LOG
from logging.handlers import RotatingFileHandler
from time import strftime, localtime

def attach_file(src,resource):
    """Attach file at src to given resource

    Copies the file to the current directory, EPP node will upload this file
    automatically if the process output is properly set up"""
    original_name = os.path.basename(src)
    new_name = resource.id + '_' + original_name
    dir = os.getcwd()
    location = os.path.join(dir,new_name)
    copy(src,location)
    return location

class EmptyError(ValueError):
    "Raised if an iterator is unexpectedly empty."
    pass

class NotUniqueError(ValueError):
    "Raised if there are unexpectedly more than 1 item in an iterator"
    pass

def unique_check(l,msg):
    "Check that l is of length 1, otherwise raise error, with msg appended"
    if len(l)==0:
        raise EmptyError("No item found for {0}".format(msg))
    elif len(l)!=1:
        raise NotUniqueError("Multiple items found for {0}".format(msg))

    
class EppLogger(object):

    """Context manager for logging module useful for EPP script execution.

    This context manager (CM) automatically logs what script that is executed,
    with what parameters it was executed and what version (including) commit
    hash of the genologics package used. Since EPP scripts are often ran
    automatically by the genologics LIMS client, the stdout and stderr is 
    captured and logged within this CM. Stderr is duplicated so that the
    last line can be shown in the GUI. In order to track multiple runs
    of the same process from the genologics LIMS GUI, the previous log 
    files can be prepended. Also a main log file can be used that is
    supposed to be common for all scripts executed on the server.
    
    """

    PACKAGE = 'genologics'
    def __enter__(self):
        logging.info('Executing file: {0}'.format(sys.argv[0]))
        logging.info('with parameters: {0}'.format(sys.argv[1:]))
        try:
            logging.info('Version of {0}: '.format(self.PACKAGE) + 
                         pkg_resources.require(self.PACKAGE)[0].version)
        except DistributionNotFound as e:
            logging.error(e)
            logging.error(('Make sure you have the {0} '
                           'package installed').format(self.PACKAGE))
            sys.exit(-1)
        return self

    def __exit__(self,exc_type,exc_val,exc_tb):
        # If no exception has occured in block, turn off logging.
        if not exc_type:
            logging.shutdown()
            sys.stderr = self.saved_stderr
            sys.stdout = self.saved_stdout
        # Do not repress possible exception
        return False

    def __init__(self,log_file=None,level=logging.INFO,lims=None,prepend=False):
        """ Initialize the logger with custom settings.

        Arguments:
        log_file  -- file to write individual log to
        
        Keyword Arguments:
        level   -- Logging level, default logging.INFO
        lims    -- Lims instance, needed for prepend to work
        prepend -- If True, prepend old log file to new, requires lims
        """
        self.lims = lims
        self.log_file = log_file
        self.level = level
        self.prepend = prepend

        if prepend and self.log_file:
            self.prepend_old_log()

        # Loggers that will capture stdout and stderr respectively
        stdout_logger = logging.getLogger('STDOUT')
        self.slo = self.StreamToLogger(stdout_logger, logging.INFO)
        self.saved_stdout = sys.stdout
        sys.stdout = self.slo

        stderr_logger = logging.getLogger('STDERR')
        self.saved_stderr = sys.stderr
        # Duplicate stderr stream to log
        self.sle = self.StreamToLogger(stderr_logger, logging.INFO,
                                       self.saved_stderr)
        sys.stderr = self.sle

        # Root logger with filehandler(s)
        self.logger = logging.getLogger()
        self.logger.setLevel(self.level)
        formatter = logging.Formatter(
            '%(asctime)s:%(levelname)s:%(name)s:%(message)s')
        if self.log_file:
            individual_fh = logging.FileHandler(self.log_file,mode='a')
            individual_fh.setFormatter(formatter)
            self.logger.addHandler(individual_fh)

        if MAIN_LOG:
            # Rotating file handler, that will create up to 10 backup logs,
            # each no bigger than 100MB.
            main_fh = RotatingFileHandler(MAIN_LOG,mode='a',
                                          maxBytes=1e8,backupCount=10)
            main_fh.setFormatter(formatter)
            self.logger.addHandler(main_fh)
        else:
            self.logger.warning('No main log file found.')

    def prepend_old_log(self, external_log_file = None):
        """Prepend the old log to the new log. 

        The location of the old log file is retrieved through the REST api. 
        In order to work, the script should be executed on the LIMS server
        since the location on the disk is parsed out from the sftp string
        and then used for local copy of file. 

        This method does not use logging since that could mess up the
        logging settings, instead warnings are printed to stderr."""
        if external_log_file:
            log_file = external_log_file
        else:
            log_file = self.log_file
        try:
            log_artifact = Artifact(self.lims,id=log_file)
            log_artifact.get()
            if log_artifact.files:
                log_path = log_artifact.files[0].content_location.split(
                    self.lims.baseuri.split(':')[1])[1]
                dir = os.getcwd()
                destination = os.path.join(dir,log_file)
                copy(log_path,destination)
                with open(destination,'a') as f:
                    f.write('='*80+'\n')
        except HTTPError: # Probably no artifact found, skip prepending
            print >> sys.stderr, ('No log file artifact found '
                                  'for id: {0}').format(log_file)
        except IOError as e: # Probably some path was wrong in copy
            print >> sys.stderr, ('Log could not be prepended, '
                                  'make sure {0} and {1} are '
                                  'proper paths.').format(log_path,log_file)
            raise e

    class StreamToLogger(object):
        """Fake file-like stream object that redirects writes to a logger instance.
        
        source: 
        http://www.electricmonk.nl/log/2011/08/14/
        redirect-stdout-and-stderr-to-a-logger-in-python/
        """
        def __init__(self, logger, log_level=logging.INFO, stream=None):
            self.logger = logger
            self.log_level = log_level
            self.linebuf = ''
            self.stream = stream

        def write(self, buf):
            if self.stream:
                self.stream.write(buf)
            for line in buf.rstrip().splitlines():
                self.logger.log(self.log_level, line.rstrip())


class CopyField(object):
    """Class to copy any filed (or udf) from any lims element to any 
    udf on any other lims element

    argumnets:

    s_elt           source elemement - instance of a type
    d_elt           destination element - instance of a type
    s_field_name    name of source field (or udf) to be copied 
    d_udf_name      name of destination udf name. If not specifyed
                    s_field_name will be used.

    The copy_udf() function takes a logfile as optional argument.
    If this is given the changes will be logged there.

    Written by Maya Brandi and Johannes Alnberg
    """
    def __init__(self, s_elt, d_elt, s_field_name, d_udf_name = None):
        if not d_udf_name:
            d_udf_name = s_field_name
        self.s_elt = s_elt
        self.s_field_name = s_field_name
        self.s_field = self._get_field(s_elt, s_field_name)
        self.d_elt = d_elt
        self.d_udf_name = d_udf_name
        self.old_dest_udf = self._get_field(d_elt, d_udf_name)

    def _current_time(self):
        return strftime("%Y-%m-%d %H:%M:%S", localtime())

    def _get_field(self, elt, field):
        if field in elt.udf:
            return elt.udf[field]
        else:
            try:
                return elt.field
            except:
                return None

    def _set_udf(self, elt, udf_name, val):
        try:
            elt.udf[udf_name] = val
            elt.put()
            return True
        except (TypeError, HTTPError) as e:
            print >> sys.stderr, "Error while updating element: {0}".format(e)
            sys.exit(-1)
            return False

    def _log_before_change(self, changelog_f=None):
        if changelog_f:
            d = {'ct' : self._current_time(),
                 's_udf' : self.s_field_name,
                 'sn' : self.d_elt.name,
                 'si' : self.d_elt.id,
                 'su' : self.old_dest_udf,
                 'nv' : self.s_field}

            changelog_f.write(("{ct}: udf: {s_udf} on {sn} (id: {si}) from "
                               "{su} to {nv}.\n").format(**d))

        logging.info(("Copying from element with id: {0} to sample with "
                      " id: {1}").format(self.s_elt.id, self.d_elt.id))

    def _log_after_change(self):
        d = {'s_udf': self.s_field_name,
             'd_udf': self.d_udf_name,
             'su': self.old_dest_udf,
             'nv': self.s_field,
             'd_elt_type': self.d_elt._URI}

        logging.info("Updated {d_elt_type} udf: {d_udf}, from {su} to {nv}.".format(**d))

    def copy_udf(self, changelog_f = None):
        if self.s_field != self.old_dest_udf:
            self._log_before_change(changelog_f)
            log = self._set_udf(self.d_elt, self.d_udf_name, self.s_field)
            self._log_after_change()
            return log
        else:
            return False


