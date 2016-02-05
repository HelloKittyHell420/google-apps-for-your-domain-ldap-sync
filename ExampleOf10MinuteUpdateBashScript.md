#A bash script that can be setup to run every 10 minutes (via your favorite cron) to sync users.

# Introduction #
Organizations may want to setup ldap\_sync to synchronize their users on a rapid schedule.  This outlines some examples of how one might do this


# Details #

You can setup a cron job to run every 10 minutes (or whatever) to sync your users.  Here's how:

```
#!/bin/bash
#
# Copyright 2006 Google, Inc.
# All Rights Reserved
#
# Licensed under the Apache License, Version 2.0 (the "License")
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#
# Author: Robert Escorcio
#
# This script assumes google-apps-for-your-domain code has been placed in $BASEDIR/src

# Set implementation-specific params
cd `dirname $0` 
. ../sync_ldap_env

LDAPFILTER="(objectclass=organizationalPerson)"
RUNTIME=`date +"%Y%m%d%H%M%S"`
DELETELOGSOLDERTHANDAYS=30
export PYTHONPATH=$BASEDIR:${PYTHONPATH#$BASEDIR}
PROGRAM=`basename $0`
RUNDIR=$BASEDIR                           # replace with /var/run maybe someday
PIDFILE=$RUNDIR/pid/$PROGRAM.pid

echo "Pythonpath is $PYTHONPATH"

# Process management stuff first.  Ensure the program is being run exactly
# once on this machine.
[ -e $PIDFILE ] && {
  ps -p `cat $PIDFILE` | grep $PROGRAM && {
    echo "There is already a version of $PROGRAM running.  Aborting..."
    exit 0
  }
}
echo "$$" > $PIDFILE


set -x

# clean up old logfiles left over
[ -e $LOGFILE ] && ( mv $LOGFILE $LOGDIR/sync_ldap_prior_run_$RUNTIME.log )

# If no config file make one off of the params above.
[ -e $CONFIGFILE ] || {
  $BASEDIR/src/sync_ldap.py >> $LOGFILE 2<&1 << EOF  
set loglevel 9
set ldap_url $LDAPURL
set ldap_base_dn dc=yourdomain,dc=com
set ldap_user_filter $LDAPFILTER
set ldap_timeout 180
set primary_key employeeNumber
connect
testFilter
y
set google_operations updated
stop
y
$CONFIGFILE
EOF
}

# If no user database create one.
# Add any users that are in ldap but missing from our database.  'add' as in
# the sense of adding to the database only, not to Google Apps
[ -e $USERDATABASE ] || {
  $BASEDIR/src/sync_ldap.py -c $CONFIGFILE >> $LOGFILE 2<&1 << EOF
connect
updateUsers
attrList remove networkPortMD5Password
attrList remove networkPortPassword
writeUsers $USERDATABASE
set admin $ADMINUSER
set domain $DOMAIN
set password $ADMINPASSWORD
syncAllUsers
stop
n
EOF
}


# Update attributes 
$BASEDIR/src/sync_ldap.py -c $CONFIGFILE -f $USERDATABASE >> $LOGFILE 2<&1 << EOF
connect
mapGoogleAttribute GoogleLastName GoogleLastNameCallback
mapGoogleAttribute GoogleFirstName GoogleFirstNameCallback
updateUsers
set admin $ADMINUSER
set domain $DOMAIN
set password $ADMINPASSWORD
syncAllUsers
stop
n
EOF

grep -i "ERROR" $LOGFILE && {
  mail $MAILTO -s "$0 error" < $LOGFILE
}

# rename the log file to make it unique
[ -e $LOGFILE ] && ( mv $LOGFILE $LOGDIR/sync_ldap_$RUNTIME.log )

# delete old log files last modified more than n days ago
find $LOGDIR -mtime +$DELETELOGSOLDERTHANDAYS | xargs -r rm > /dev/null

rm $PIDFILE
```

This script references `../sync_ldap_env` which should contain something like

```
#!/bin/bash
#
# Copyright 2006 Google, Inc.
# All Rights Reserved
#
# Licensed under the Apache License, Version 2.0 (the "License")
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#
# Author: Robert Escorcio
#

BASEDIR=~/google-apps-for-your-domain-ldap-sync
DOMAIN=yourdomain.com
ADMINUSER=google-apps-admin-role-account@$DOMAIN
ADMINPASSWORD=google-apps-admin-role-account-password
LDAPURL=LDAP://yourldap.$DOMAIN
CONFIGFILE=$DOMAIN.cfg
USERDATABASE=$DOMAIN.user.csv
LOGDIR=$BASEDIR/log
LOGFILE=$LOGDIR/sync_ldap.log
MAILTO=root@$DOMAIN
```
