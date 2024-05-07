#!/bin/bash

LOG_ONLY_TO_CONSOLE="${CONSOLE_LOGGING_ONLY:-"true"}"

if [ "$LOG_ONLY_TO_CONSOLE" = "true" ]; then
	/usr/bin/supervisord -c /etc/supervisor/conf.d/supervisord.conf
else
	/usr/bin/supervisord -c /etc/supervisor/conf.d/supervisord_filelog.conf
fi