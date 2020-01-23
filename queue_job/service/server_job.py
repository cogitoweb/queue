# -*- coding: utf-8 -*-
from odoo import api, http

from odoo.service.server import Worker as OdooWorker
from odoo.service.server import WorkerHTTP as OdooWorkerHTTP
from odoo.service.server import PreforkServer as OdooPreforkServer
from odoo.service.server import memory_info

from odoo.addons.queue_job.job import JOB_PID_FOLDER_LONGRUNNING

import odoo.tools.config as config

import os
import psutil
import resource
import signal
import time

import pprint
import logging
_logger = logging.getLogger(__name__)


def get_longrunning_uuid_from_pid(pid_number):
    expected_longrunning_pid_file = "%s/%s.pid" % (JOB_PID_FOLDER_LONGRUNNING, pid_number)
    job_uuid = False

    if os.path.exists(expected_longrunning_pid_file):
        with open(expected_longrunning_pid_file) as f:
            job_uuid = f.readline()

    return job_uuid


def monkey_process_limit(self):

    # _logger.info('-- MONKEY PATCH')
    # if http:
    #     _logger.info('--- A')
    #     if http.request:
    #         _logger.info('--- B')
    #         if http.request.httprequest:
    #             _logger.info('--- C')
    #             _logger.info(http.request.httprequest)

    # If our parent changed sucide
    if self.ppid != os.getppid():
        _logger.info("Worker (%s) Parent changed", self.pid)
        self.alive = False

    # check for lifetime
    if self.request_count >= self.request_max:
        _logger.info("Worker (%d) max request (%s) reached.", self.pid, self.request_count)
        self.alive = False

    # Reset the worker if it consumes too much memory
    # (e.g. caused by a memory leak).
    rss, vms = memory_info(psutil.Process(os.getpid()))
    if vms > config['limit_memory_soft']:
        _logger.info('Worker (%d) virtual memory limit (%s) reached.', self.pid, vms)
        self.alive = False  # Commit suicide after the request.

    # VMS and RLIMIT_AS are the same thing: virtual memory,
    # a.k.a. address space
    soft, hard = resource.getrlimit(resource.RLIMIT_AS)
    resource.setrlimit(resource.RLIMIT_AS, (config['limit_memory_hard'], hard))

    # SIGXCPU (exceeded CPU time) signal handler will raise an exception.
    r = resource.getrusage(resource.RUSAGE_SELF)
    cpu_time = r.ru_utime + r.ru_stime

    def time_expired(n, stack):
        # if is_longrunning_job:
        #     _logger.info('Worker (%d) CPU time limit (%s) reached BUT its a longrunning job.', self.pid, config['limit_time_cpu'])
        #     return True

        _logger.info('Worker (%d) CPU time limit (%s) reached.', self.pid, config['limit_time_cpu'])
        # We dont suicide in such case
        raise Exception('CPU time limit exceeded.')

    signal.signal(signal.SIGXCPU, time_expired)
    soft, hard = resource.getrlimit(resource.RLIMIT_CPU)
    resource.setrlimit(resource.RLIMIT_CPU, (cpu_time + config['limit_time_cpu'], hard))
    # _logger.debug(" ------- PID %s SOFT %s HARD %s CPU_TIME %s COMBO %s" % (self.pid, soft, hard, cpu_time, cpu_time + config['limit_time_cpu']))


def monkey_process_timeout(self):
    now = time.time()

    for (pid, worker) in self.workers.items():
        worker_time = (now - worker.watchdog_time)  # alias

        # choose which timeout to respect
        if get_longrunning_uuid_from_pid(pid):
            worker_timeout = worker.watchdog_longrunning_timeout
            worker_class = 'Longrunning' + worker.__class__.__name__
        else:
            worker_timeout = worker.watchdog_timeout
            worker_class = worker.__class__.__name__

        # check if you are out of bounds
        if worker_timeout is not None and worker_time >= worker_timeout:
            msg_error = "{worker_type} ({worker_pid}) timeout after {worker_timeout}s".format(
                worker_type=worker_class, worker_pid=pid, worker_timeout=worker_timeout,
            )

            _logger.error(msg_error)
            self.worker_kill(pid, signal.SIGKILL)


def monkey_preforkserver_init(self, app):
    self.address = config['xmlrpc'] and (config['xmlrpc_interface'] or '0.0.0.0', config['xmlrpc_port'])
    self.population = config['workers']
    self.timeout = config['limit_time_real']
    self.limit_request = config['limit_request']
    self.cron_timeout = config['limit_time_real_cron'] or None
    if self.cron_timeout == -1:
        self.cron_timeout = self.timeout

    # working vars
    self.beat = 4
    self.app = app
    self.pid = os.getpid()
    self.socket = None
    self.workers_http = {}
    self.workers_cron = {}
    self.workers = {}
    self.generation = 0
    self.queue = []
    self.long_polling_pid = None

    # [cgt-edit] add a different timeout from longrunning jobs
    self.timeout_longrunning = config['limit_time_longrunning'] or config['limit_time_real']


def monkey_worker_init(self, multi):
    self.multi = multi
    self.watchdog_time = time.time()
    self.watchdog_pipe = multi.pipe_new()

    # Can be set to None if no watchdog is desired.
    self.watchdog_timeout = multi.timeout
    self.ppid = os.getpid()
    self.pid = None
    self.alive = True

    # should we rename into lifetime ?
    self.request_max = multi.limit_request
    self.request_count = 0

    # [cgt-edit] add a different timeout from longrunning jobs
    self.watchdog_longrunning_timeout = multi.timeout_longrunning


# apply monkey patch
OdooWorkerHTTP.process_limit = monkey_process_limit
OdooPreforkServer.process_timeout = monkey_process_timeout
OdooPreforkServer.__init__ = monkey_preforkserver_init
OdooWorker.__init__ = monkey_worker_init
