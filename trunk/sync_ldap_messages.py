#!/usr/bin/python2.4
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

# This package requires Python 2.4 or above, and the "python-ldap" package,
# which can be downloaded from http://python-ldap.sourceforge.net/

""" Holds all the text messages that are displayed to the user, for
Internationalization (aka 'i18n')

msg: function for inserting arguments into a message

"""

CHAR_PROGRESS = '#' # an indication of progress for long-running operations

MSG_WRITE_CONFIG_FILE = "Writing config file to %s"

MSG_SYNC_GOOGLE_QUOTA = ("The quota to be used for new users in the Google "
                         "Apps domain.  If your administrator has set a quota, "
                         "then this must match exactly one of the options "
                         "he / she set.")

MSG_SYNC_GOOGLE_ENDPOINT = ("The Google Apps host to target.   This is almost "
                            "always unset unless you are a google developer "
                            "working in the google private network.")

MSG_SYNC_GOOGLE_AUTH_URL = ("The Google Apps Client Auth URL to target. "
                            "This is almost always unset unless you are a "
                            "google developer working in the google private "
                            "network.")

MSG_SYNC_RESULTS = "Results of synchronization operation with Google:"
MSG_ADD_RESULTS = "%s users added successfully. %s users could not be added."
MSG_EXITED_RESULTS = ("%s users exited successfully. %s users could not be "
                      "exited.")
MSG_RENAME_RESULTS = ("%s users renamed successfully. %s users could not be "
                      "renamed.")
MSG_UPDATE_RESULTS = ("%s users updated successfully. %s users could not be "
                      "updated.")
MSG_CONSULT_LOG = "Consult log file for details."

