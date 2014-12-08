#!/usr/bin/env python
DESC = """This EPP script reads demultiplex end undemultiplexed yields from file
system and then does the following

1)  Sets the output artifact udfs based demultiplex resultfile.
 
2)  Sets the output artifact qc-flaggs based on the threshold-udfs if the process: 
        % Perfect Index Reads < 60 (default)
        %Q30 < 80 (default)
        expected index < 0.1 M (default)

3)  Warns if anny unexpected index has yield > 0.5M

4)  Loads a result file with demultiplex end undemultiplexed yields. This should
    be checked if warnings are given.

Reads from:
    --files--
    Demultiplex_Stats.htm                           in mfs file system
    Undemultiplexed_stats.metrics                   in mfs file system

Writes to:
    --Lims fields--
    qc-flag                                         per artifact (result file)
    % One Mismatch Reads (Index)                    per artifact (result file)
    % of Raw Clusters Per Lane                      per artifact (result file)
    %PF                                             per artifact (result file)
    Ave Q Score                                     per artifact (result file)
    Yield PF (Gb)                                   per artifact (result file)
    % Perfect Index Read                            per artifact (result file)
    % Bases >=Q30                                   per artifact (result file)
    # Reads                                         per artifact (result file)
    # Read Pairs

Logging:
    The script outputs a regular log file with regular execution information.

Written by Maya Brandi 
"""

import os
import sys
import logging
import glob
import csv
import numpy as np

from argparse import ArgumentParser
from genologics.lims import Lims
from genologics.config import BASEURI, USERNAME, PASSWORD
from genologics.entities import Process
from genologics.epp import EppLogger
from genologics.epp import set_field
from qc_parsers import FlowcellRunMetricsParser

class UndemuxInd():
    def __init__(self, process):
        self.process = process
        self.input_pools = process.all_inputs()
        self.dem_stat = None
        self.undem_stat = None 
        self.QC_thresholds = {}
        self.abstract = []
        self.missing_fields = []
        self.un_exp_ind_warn = ''
        self.qc_error = ''
        self.nr_lane_samps_updat = 0
        self.nr_lane_samps_tot = 0
        self.miseq = False
        self.single = True
        self.read_pairs = None


    def _get_file_path(self):
        try:
            cont_name = self.process.all_inputs()[0].location[0].name
        except:
            sys.exit('Could not find container name.')
        try:
            run  = lims.get_processes(type = 'MiSeq Run (MiSeq) 4.0',
                                         udf={'Reagent Cartridge ID':cont_name})
            logging.info('looking for mi-seq run ID')
            ID = run[0].udf['Flow Cell ID']
            self.miseq = True
        except:
            logging.info('Could not find mi-seq run ID with Reagent Cartridge '
                            'ID {0}. Looking for Hiseq run.'.format(cont_name))
            run  = lims.get_processes(type = 'Illumina Sequencing (Illumina SBS) 4.0',
                                         udf={'Reagent Cartridge ID':cont_name})
            ID = cont_name
        logging.info('looking for sequencing setup')
        try:
            Read_1_Cycles = run[0].udf['Read 1 Cycles']
            try:
                Read_2_Cycles = run[0].udf['Read 2 Cycles']
                self.single = False
            except:
                self.single = True
        except:
            sys.exit('Could not get sequencing set up.')
        try:
            return glob.glob(("/srv/mfs/*iseq_data/*{0}/Unaligned/Basecall_Stats_*/".format(ID)))[0]
        except:
            sys.exit("Failed to get file path") 

    def get_demultiplex_files(self):
        """ Files are read from the file msf system. Path hard coded."""
        FRMP = FlowcellRunMetricsParser()
        file_path = self._get_file_path()
        try:
            fp_dem = file_path + 'Demultiplex_Stats.htm'
            self.dem_stat = FRMP.parse_demultiplex_stats_htm(fp_dem)
            logging.info("Parsed file {0}".format(fp_dem))
        except:
            sys.exit("Failed to find or parse Demultiplex_Stats.htm.")
        try:
            fp_und = file_path + 'Undemultiplexed_stats.metrics'
            self.undem_stat = FRMP.parse_undemultiplexed_barcode_metrics(fp_und)
            logging.info("Parsed file {0}".format(fp_und))
        except:
            sys.exit("Failed to find or parse Undemultiplexed_stats.metrics")
 

    def set_result_file_udfs(self):
        """populates the target file qc-flags"""
        for pool in self.input_pools:
            if self.miseq:
                lane = '1'
            else:
                lane = pool.location[1][0] #getting lane number
            outarts_per_lane = self.process.outputs_per_input(
                                          pool.id, ResultFile = True)
            for target_file in outarts_per_lane:
                self.nr_lane_samps_tot += 1
                samp_name = target_file.samples[0].name
                for lane_samp in self.dem_stat['Barcode_lane_statistics']:
                    if lane == lane_samp['Lane']:
                        samp = lane_samp['Sample ID']
                        if samp == samp_name:
                            self._set_fields(target_file, lane_samp)

    def _set_fields(self, target_file, sample_info):
        try:
            target_file.udf['% One Mismatch Reads (Index)'] = float(sample_info['% One Mismatch Reads (Index)'])
        except:
            self.missing_fields.append('% One Mismatch Reads (Index)')
        try:
            target_file.udf['% of Raw Clusters Per Lane'] = float(sample_info['% of raw clusters per lane'])
        except:
            self.missing_fields.append('% of Raw Clusters Per Lane')
        try:
            target_file.udf['%PF'] = float(sample_info['% PF'])
        except:
            self.missing_fields.append('%PF')
        try:
            target_file.udf['Ave Q Score'] = float(sample_info['Mean Quality Score (PF)'])
        except:
            self.missing_fields.append('Ave Q Score')
        try:
            Yield_PF_Gb = np.true_divide(float(sample_info['Yield (Mbases)'].replace(',','')), 1000)
            target_file.udf['Yield PF (Gb)'] = float(Yield_PF_Gb)
        except:
            self.missing_fields.append('Yield PF (Gb)')
        try:
            target_file.udf['% Perfect Index Read'] = float(sample_info['% Perfect Index Reads'])
        except:
            self.missing_fields.append('% Perfect Index Read')
        try:
            if not dict(target_file.udf.items()).has_key('% Bases >=Q30'):
                target_file.udf['% Bases >=Q30'] = float(sample_info['% of >= Q30 Bases (PF)'])
        except:
            self.missing_fields.append('% Bases >=Q30')
        try:
            if not dict(target_file.udf.items()).has_key('# Reads'):
                target_file.udf['# Reads'] = float(sample_info['# Reads'].replace(',',''))
        except:
            self.missing_fields.append('# Reads')
        try:
            if self.single:
                self.read_pairs = float(target_file.udf['# Reads'])
            else:
                self.read_pairs = np.true_divide(float(target_file.udf['# Reads']),2)
            target_file.udf['# Read Pairs'] = self.read_pairs
        except:
            self.missing_fields.append('# Read Pairs')
        try:
            target_file.qc_flag = self._QC(target_file, sample_info)
            self.nr_lane_samps_updat += 1
        except:
            self.qc_error = 'WARNING: Could not generate QC for some samples. '
        set_field(target_file)

    def _QC(self, target_file, sample_info):
        """Makes per sample warnings if any of the following holds: 
        % Perfect Index Reads < 60
        % of >= Q30 Bases (PF) < 80
        # Reads < 100000
        OBS: Reads from target file udf if they are already set. Otherwise from 
        file system!!! This is to take into account yield and quality after 
        quality filtering if performed."""
        perf_ind_read = float(sample_info['% Perfect Index Reads'])
        Q30 = float(sample_info['% of >= Q30 Bases (PF)'])
        self._get_QC_thresholds()
        QC1 = (perf_ind_read >= self.QC_thresholds['perf_ind'])
        QC2 = (Q30 >= self.QC_thresholds['%Q30'])
        QC3 = (self.read_pairs >= self.QC_thresholds['nr_read'])
        if QC1 and QC2 and QC3:
            return 'PASSED'
        else:
            return 'FAILED'

    def _get_QC_thresholds(self):
        """Fetching QC_thresholds from process udfs"""
        try:
            self.QC_thresholds['perf_ind'] = self.process.udf['Threshold for % Perfect Index Reads']
            self.QC_thresholds['%Q30'] = self.process.udf['Threshold for % bases >= Q30']
            self.QC_thresholds['nr_read'] = self.process.udf['Threshold for # Reads']
            self.QC_thresholds['undem_yield'] = self.process.udf['Threshold for Undemultiplexed Index Yield']
        except:
            sys.exit("Set QC thresholds and try again!")


    def make_demultiplexed_counts_file(self, demuxfile):
        """Reformats the content of the demultiplex and undemultiplexed files
        to be more easy to read."""

        demuxfile = demuxfile + '.csv'
        keys = ['Project', 'Sample ID', 'Lane', '# Reads', 'Index', 
                                    'Index name', '% of >= Q30 Bases (PF)']
        toCSV = []
        for pool in self.input_pools:
            if self.miseq:
                lane = '1'
            else:
                lane = pool.location[1][0]
            for row in self.dem_stat['Barcode_lane_statistics']:
                if row['Lane'] == lane:
                    row_dict = dict([(x, row[x]) for x in keys if x in row])
                    row_dict['Index name'] = ''
                    toCSV.append(row_dict)
            if lane in self.undem_stat.keys():
                undet_per_lane = self.undem_stat[lane]['undemultiplexed_barcodes']
                nr_undet = len(undet_per_lane['count'])
                for row in range(nr_undet):
                    row_dict = dict([(x, '') for x in keys])
                    row_dict['# Reads'] = undet_per_lane['count'][row]
                    row_dict['Index'] = undet_per_lane['sequence'][row]
                    row_dict['Index name'] = undet_per_lane['index_name'][row]
                    row_dict['Lane'] = undet_per_lane['lane'][row]
                    toCSV.append(row_dict)    
        try:
            f = open(demuxfile, 'wb')
            dict_writer = csv.DictWriter(f, keys, dialect='excel')
            dict_writer.writer.writerow(keys)
            dict_writer.writerows(toCSV)
            f.close
            self.abstract.append("INFO: A Metrics file has been created with "
                      "demultiplexed and undemultiplexed counts for debugging.")
        except:
            self.abstract.append("WARNING: Could not generate a Metrics file "
                               "with demultiplexed and undemultiplexed counts.")

    def logging(self):
        """Collects and prints logging info."""
        self._check_unexpected_yield()
        self.abstract.append("INFO: QC-data found and QC-flags uploaded for {0}"
              " out of {1} analytes. Flags are set based on the selected thresh"
              "olds. ".format(self.nr_lane_samps_updat, self.nr_lane_samps_tot))
        self.abstract.append(self.qc_error)
        if self.missing_fields:
            self.missing_fields = list(set(self.missing_fields))
            self.abstract.append("WARNING: Could not get demultiplexing info for some samples: {0}."
              "".format(', '.join(self.missing_fields)))
        if self.un_exp_ind_warn or self.missing_fields or self.qc_error:
            sys.exit(' '.join(self.abstract))
        else:
            print >> sys.stderr, ' '.join(self.abstract)

    def _check_unexpected_yield(self):
        """Warning if any unexpected index has yield > 0.5M"""
        warn = {'1':[],'2':[],'3':[],'4':[],'5':[],'6':[],'7':[],'8':[]}
        for pool in self.input_pools:
            if self.miseq:
                lane = '1'
            else: 
                lane = pool.location[1][0]
            lane_inf = self.undem_stat[lane]
            counts = lane_inf['undemultiplexed_barcodes']['count']
            sequence = lane_inf['undemultiplexed_barcodes']['sequence']
            index_name = lane_inf['undemultiplexed_barcodes']['index_name']
            lanes = lane_inf['undemultiplexed_barcodes']['lane']
            for i, c in enumerate(counts):
                if int(c) > self.QC_thresholds['undem_yield']:
                    ##  Format warning message
                    lane = lanes[i]
                    if index_name[i]:
                        s = ' '.join([sequence[i],'(',index_name[i],')'])
                        warn[lane].append(s)
                    else:
                        warn[lane].append(sequence[i])
        for l, w in warn.items():
            if w:
                inds = ', '.join(w)
                self.un_exp_ind_warn = self.un_exp_ind_warn + ''.join([inds,
                                                          ' on Lane ', l, ', '])
        if self.un_exp_ind_warn:
            self.abstract.insert(0, "WARNING: High yield of unexpected index:"
                                  " {0}. Please check the Metrics file!".format(
                                                          self.un_exp_ind_warn))

def main(lims, pid, epp_logger, demuxfile):
    process = Process(lims,id = pid)
    UDI = UndemuxInd(process)
    UDI.get_demultiplex_files()
    UDI.set_result_file_udfs()
    UDI.make_demultiplexed_counts_file(demuxfile)
    UDI.logging()
    

if __name__ == "__main__":
    parser = ArgumentParser(description=DESC)
    parser.add_argument('--pid', default = None , dest = 'pid',
                        help='Lims id for current Process')
    parser.add_argument('--log', dest = 'log',
                        help=('File name for standard log file, '
                              'for runtime information and problems.'))
    parser.add_argument('--file', dest = 'file', default = 'demux',
                        help=('File path to demultiplexed metrics files'))
    args = parser.parse_args()
    lims = Lims(BASEURI, USERNAME, PASSWORD)
    lims.check_version()

    with EppLogger(log_file=args.log, lims=lims, prepend=True) as epp_logger:
        main(lims, args.pid, epp_logger, args.file)
