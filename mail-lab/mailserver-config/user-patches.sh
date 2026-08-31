#!/usr/bin/env bash
set -euo pipefail

# Dedicated SMTP transport from Postfix to the Magika filter.
postconf -M 'magikafilter/unix=magikafilter unix - - n - 4 smtp'
postconf 'magikafilter_destination_concurrency_limit=4'
postconf 'magikafilter_destination_recipient_limit=100'

# Internal-only SMTP listener used by the filter to return analyzed mail.
postconf -M '10026/inet=10026 inet n - n - - smtpd'
postconf -P '10026/inet/syslog_name=postfix/10026'
postconf -P '10026/inet/content_filter='
postconf -P '10026/inet/receive_override_options=no_unknown_recipient_checks,no_header_body_checks,no_milters'
postconf -P '10026/inet/smtpd_client_restrictions=permit'
postconf -P '10026/inet/smtpd_helo_restrictions='
postconf -P '10026/inet/smtpd_sender_restrictions='
postconf -P '10026/inet/smtpd_recipient_restrictions=reject_unauth_destination'
postconf -P '10026/inet/smtpd_relay_restrictions=reject_unauth_destination'
postconf -P '10026/inet/smtpd_milters='
postconf -P '10026/inet/local_header_rewrite_clients='
