# -*- coding: utf-8 -*-
import os
import logging
import signal

import resource
import psutil

import odoo
import odoo.tools.config as config

from odoo import models, fields, api, _, http
from odoo.service.server import WorkerHTTP as OdooWorker

_logger = logging.getLogger(__name__)
import pprint


def process_limit_job(self):

    _logger.info('--------- MONKEY PATCH ---------')
    _logger.info('----------------------------------')
    if http:
        _logger.info('A')
        if http.request:
            _logger.info('B')
            if http.request.httprequest:
                _logger.info('C')
                _logger.info(http.request.httprequest)

    # If our parent changed sucide
    if self.ppid != os.getppid():
        _logger.info("Worker (%s) Parent changed", self.pid)
        self.alive = False
    # check for lifetime
    if self.request_count >= self.request_max:
        _logger.info(
            "Worker (%d) max request (%s) reached.",
            self.pid,
            self.request_count
        )
        self.alive = False
    # Reset the worker if it consumes too much memory
    # (e.g. caused by a memory leak).
    rss, vms = odoo.service.server.memory_info(psutil.Process(os.getpid()))
    if vms > config['limit_memory_soft']:
        _logger.info(
            'Worker (%d) virtual memory limit (%s) reached.',
            self.pid,
            vms
        )
        self.alive = False      # Commit suicide after the request.

    # VMS and RLIMIT_AS are the same thing: virtual memory,
    # a.k.a. address space
    soft, hard = resource.getrlimit(resource.RLIMIT_AS)
    resource.setrlimit(resource.RLIMIT_AS, (
        config['limit_memory_hard'], hard
    ))

    # SIGXCPU (exceeded CPU time) signal handler will raise an exception.
    r = resource.getrusage(resource.RUSAGE_SELF)
    cpu_time = r.ru_utime + r.ru_stime

    def time_expired(n, stack):
        _logger.info(
            'Worker (%d) CPU time limit (%s) reached.',
            self.pid,
            config['limit_time_cpu']
        )
        # We dont suicide in such case
        raise Exception('CPU time limit exceeded.')
    signal.signal(signal.SIGXCPU, time_expired)
    soft, hard = resource.getrlimit(resource.RLIMIT_CPU)
    resource.setrlimit(resource.RLIMIT_CPU, (
        cpu_time + config['limit_time_cpu'], hard
    ))


OdooWorker.process_limit = process_limit_job
