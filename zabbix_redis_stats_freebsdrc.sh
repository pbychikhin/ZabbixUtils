#!/bin/sh

# PROVIDE: zabbix_redis_stats
# REQUIRE: redis
# KEYWORD: shutdown

# Add the following line to /etc/rc.conf to enable `zabbix_redis_stats':
#
#zabbix_redis_stats_enable="YES"
#
# Define profiles here to run separate zabbix_redis_stats instances:
#
#zabbix_redis_stats_profiles="foo bar" #  Script uses zabbix_redis_stats_args_NAME respectively.
#                                      #  Each profile is a set of command args which substitutes command_args
#                                      #  on each run_rc_command call.
#                                      #  Plese do not specify -pidfile arg. This will be set automatically.

. /etc/rc.subr

name="zabbix_redis_stats"
rcvar="${name}_enable"

command="/usr/local/bin/zabbix_redis_stats.py"
command_interpreter="/usr/local/bin/python3"

load_rc_config "$name"
eval ${name}_enable=\${${name}_enable:-"NO"}
eval ${name}_user=\${${name}_user:-"redis"}
eval profiles=\$${name}_profiles

for profile in $profiles
do
    eval profile_args=\$${name}_args_$profile
    if [ ! -z "$profile_args" ]
    then
        echo "--- Doing action for profile $profile ---"
        pidfile=/var/run/redis/${name}_$profile.pid
        command_args="$profile_args -daemonpidfile $pidfile"
        run_rc_command "$1"
    else
        echo "--- No arguments for profile $profile - nothing to do ---"
    fi
done
