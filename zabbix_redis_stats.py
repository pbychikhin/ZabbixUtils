#!/usr/local/bin/python3

import redis
import argparse
import re
import pyzabbix
import time
import logging
import logging.handlers
import os
import os.path
import sys
import daemon
import pidfile

_FILE_VER = "to_be_filled_by_CI"


def tr_vars(all_vars, target_vars, spec_vars):
    """
    Extracts some vars from a total heap translating their names according to rules
    :param all_vars: total heap (namespace)
    :param target_vars: list of resulting dictionaries to be filled with translated vars
    :param spec_vars: list of dictionaries with vars to extract as keys and translation rules as values
    :return: none
    """
    for tv, sv in zip(target_vars, spec_vars):
        for var in sv.keys():
            if getattr(all_vars, var) is not None:
                tv[sv[var]] = getattr(all_vars, var)


def do_main_program(cmdargs):
    prog_info = {"prog_name": os.path.basename(sys.argv[0]).rsplit(".", 1)[0],
                 "prog_pid": os.getpid(),
                 "zabbix_host": cmdargs.zhost}
    log_handler = logging.handlers.SysLogHandler(address=cmdargs.l,
                                                 facility=logging.handlers.SysLogHandler.LOG_USER)
    log_formatter = logging.Formatter(style="{",
                                      fmt="{prog_name}[{prog_pid}][{zabbix_host}][{{levelname}}]: {{message}}".format(
                                          **prog_info))
    log_handler.setFormatter(log_formatter)
    log = logging.getLogger()
    log.addHandler(log_handler)
    log.setLevel(getattr(logging, cmdargs.ll))
    rconn_vars = dict()
    rconn_vars_tr = {"rhost": "host", "rport": "port"}
    zconn_vars = dict()
    zconn_vars_tr = {"zsrv": "zabbix_server", "zport": "zabbix_port"}
    tr_vars(cmdargs, [rconn_vars, zconn_vars], [rconn_vars_tr, zconn_vars_tr])
    redis_wanted_props = {"used_memory", "used_memory_rss", "used_memory_peak", "maxmemory",
                          "mem_fragmentation_ratio", "expired_keys", "evicted_keys", "keyspace_hits",
                          "keyspace_misses", "connected_clients", "total_connections_received",
                          "rejected_connections", "instantaneous_ops_per_sec", "instantaneous_input_kbps",
                          "instantaneous_output_kbps", "redis_version"}
    send_dest = {"print": "console", "send": "zabbix server"}
    while True:
        log.info("Performing poll/send (to {})".format(send_dest.get(cmdargs.action, "unknown")))
        try:
            redis_info = redis.StrictRedis(**rconn_vars).info()
        except Exception:
            log.exception("Problem getting data from Redis server")
        else:
            zbx_packet = list()
            redis_total_keys = 0
            for p in list(redis_info.keys()):
                if re.fullmatch("db\d+", p):
                    redis_total_keys += redis_info[p]['keys']
                if p not in redis_wanted_props:
                    del redis_info[p]
            redis_info["_total_keys"] = redis_total_keys
            redis_info["_mem_fragmentation_ratio_dev"] = abs(1 - redis_info["mem_fragmentation_ratio"])
            hits_and_misses = redis_info["keyspace_hits"] + redis_info["keyspace_misses"]
            redis_info["_keyspace_hit_ratio"] = redis_info["keyspace_hits"] / hits_and_misses if \
                hits_and_misses > 0 else 1
            redis_info["_mem_usage_ratio"] = redis_info["used_memory"] / redis_info["maxmemory"] if \
                redis_info["maxmemory"] > 0 else 0
            for kv in redis_info.items():
                zbx_packet.append(pyzabbix.ZabbixMetric(cmdargs.zhost, "redis.info." + kv[0], kv[1]))
            zbx_packet.append(pyzabbix.ZabbixMetric(cmdargs.zhost, "redis.info._getting_stats_done", "1"))
            if cmdargs.action == "send":
                try:
                    pyzabbix.ZabbixSender(**zconn_vars).send(zbx_packet)
                except Exception:
                    log.exception("Problem sending data to Zabbix server")
            elif cmdargs.action == "print":
                print(zbx_packet)
            else:
                log.error("Unknown action \"{}\"".format(cmdargs.action))
        if cmdargs.oneshot:
            break
        time.sleep(cmdargs.interval)


if __name__ == "__main__":
    defaults = {"interval": 300,
                "action": "send",
                "actions": ["print", "send"],
                "syslog_address": "/dev/log",
                "severity": "WARNING",
                "severities": ["CRITICAL", "ERROR", "WARNING", "INFO", "DEBUG", "NOTSET"],
                "oneshot": False}
    cmd = argparse.ArgumentParser(description="Redis statistics poller/sender")
    cmd.add_argument("-version", action="version", version=_FILE_VER)
    cmd.add_argument("-rhost", help="Redis host", metavar="name_or_addr")
    cmd.add_argument("-rport", help="Redis port", metavar="number", type=int)
    cmd.add_argument("-zsrv", help="Zabbix server host", metavar="name_or_addr")
    cmd.add_argument("-zport", help="Zabbix server port", metavar="number", type=int)
    cmd.add_argument("-zhost", help="Zabbix monitored host ID", metavar="name", required=True)
    cmd.add_argument("-interval", help="How frequently to poll/send ({interval})".format(**defaults), metavar="sec",
                     type=int, default=defaults["interval"])
    cmd.add_argument("-action", help="Action to perform on successful data retrieval ({action})".format(**defaults),
                     choices=defaults["actions"], default=defaults["action"])
    cmd.add_argument("-l", metavar="address_or_path",
                     help="Address of the syslog socket ({})".format(defaults["syslog_address"]),
                     default=defaults["syslog_address"])
    cmd.add_argument("-ll", help="Logging severity level ({})".format(defaults["severity"]),
                     choices=defaults["severities"], default=defaults["severity"])
    cmd.add_argument("-oneshot", help="Poll/send once and exit ({})".format(defaults["oneshot"]), action="store_true",
                     default=defaults["oneshot"])
    cmd.add_argument("-daemonpidfile", help='Daemonize and write PID to the path specified. '
                                            '"oneshot" and "action" will be set to False and "send". '
                                            'For correct operation, please specify an absolute path to the file',
                     metavar="full_path_to_file")
    cmdargs = cmd.parse_args()
    if cmdargs.daemonpidfile is not None:
        if not os.path.isabs(cmdargs.daemonpidfile):
            raise RuntimeError("The path \"{}\" is not absolute".format(cmdargs.daemonpidfile))
        cmdargs.oneshot = False
        cmdargs.action = "send"
        print('Daemon mode enabled. "oneshot" and "action" are reset to False and "send"')
        with daemon.DaemonContext(pidfile=pidfile.PidFile(cmdargs.daemonpidfile)):
            do_main_program(cmdargs)
    else:
        do_main_program(cmdargs)
