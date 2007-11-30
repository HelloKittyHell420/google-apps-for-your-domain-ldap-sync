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

def msg(id, args=()):

  """ Given a message id and some arguments, return the completed message.
  This is a stub implementation, and will certainly change when we do
  real I18N.
  """
  return id % args


# generic messages

CMD_PROMPT = "Command: "

MSG_DONE = "Done"

ERR_FILE_NOT_FOUND = "File '%s' not found"

ERR_USER_NOT_FOUND = "User '%s' not found"

ERR_ENTER_NUMBER_OR_PCT = "Please enter a number or a percentage"

ERR_ENTER_NUMBER = "Invalid number: '%s'"

ERR_NO_SUCH_ATTR = "No such variable: '%s'"

ERR_NO_DATA_FILE = "No file name.  Please specify one."

ERR_YES_OR_NO = "Please answer yes or no"

ERR_NUMBER_OUT_OF_RANGE = "%s is not a valid user number"

ERR_NO_USER_FILTER = """You haven't specified a user filter. This is
an LDAP search filter describing your user records.  Example:
(objectclass=organizationalPerson)
"""

ERR_NO_ATTR_FOR_USER = 'No %s attribute for this user'

MSG_TRY_AGAIN = "Try again? "

CHAR_YES = 'y'   # translate this to first letter of "yes" in your language

ERR_INVALID_VALUE = "Invalid value for %s"

MSG_Q_SAVE_CONFIG= """You did not supply a config file on the command line
(via the '-c' argument).
A config file will capture all your LDAP and user settings so that you don't
need to run commands next time to set them. Do you want to save your
configuration in a file (y/n) """

MSG_Q_SAVE_CONFIG_2= "Update your config file %s (y/n)"

MSG_GIVE_A_FILE_NAME= "Enter a file name: "

ERR_NOT_VALID_FILE_NAME= 'Not a valid file name: %s'

MSG_MISSING_CONFIG = 'Some configuration items need to be supplied:'

MSG_WRITE_CONFIG_FILE = "Writing config file to %s"

# config item documentation
MSG_LOG_FILE="""Log file to which message are written.  Defaults to stdout/stderr
"""

MSG_LOG_LEVEL="""Controls the amount of information written to the logfile.
Some common levels (in increasing levels of verbosity):
50: critial errors only
40: errors
30: warnings
20: info messages
10: debug messages
0: all messages
"""

MSG_SYNC_GOOGLE_ADMIN = """The name of the administrator for this domain,
in the form user@domain.com."""

MSG_SYNC_GOOGLE_PASSWORD = "The password for the administrator for this domain,"

MSG_SYNC_GOOGLE_DOMAIN = "The target domain in Google Apps for Your Domain."

MSG_SYNC_GOOGLE_MAX_THREADS = """The maximum number of threads to be created at
any one time for communication with Google."""

MSG_SYNC_GOOGLE_ALLOWED = """The operations permitted to be performed on
Google Apps for Your Domain. Must be a comma-separated list comprised of the
following keywords:  added,updated,exited,renamed.  If not provided, all operations
are performed."""

MSG_USERDB_MAPPING = """The mappings of Google attributes to your LDAP attributes.
For example, if you have an LDAP attribute 'mailNickname', you might map
GoogleUsername to mailNickname.
This attribute has a complicated syntax;  do not edit it directly.
Instead, use the mapGoogleAttribute command.
"""

MSG_USERDB_PRIMARY_KEY = """Optional. The LDAP attribute which always stays the same
for a user.  If set, the tool will look for cases where the primary key
stays the same but the distinguished name and other identifying information
changes, and uses that to generate a "Rename" call to Google.
"""

MSG_USERDB_ATTRS = """The set of attributes which the tool fetches from
your LDAP server for each user, and writes to the CSV or XML file. Since
unnecessary attributes slow down the tool and make the files larger, it's
good to make the list as small as possible.
This attribute has a complicated syntax;  do not edit it directly.
Instead, use the attrList command.
"""

ERR_NO_SET_ATTRS = """The 'attrs' variable may not be set directly
like this.  Consult the help for the correct command."""

ERR_NO_SET_MAPPING = """The 'mapping' variable may not be set directly
like this.  Consult the help for the correct command."""

ERR_NO_SET_OPERATIONS = """The 'google_operations' variable may not be
set directly like this.  Use a configuration file."""

MSG_USERDB_TIMESTAMP = """The LDAP attribute which your server uses
to denote "last changed."  This attribute varies depending on the type of
directory server.  For example, on ActiveDirectory it is
'whenChanged' but on other servers it may be 'modifyTimestamp'.
"""

MSG_LDAP_ADMIN_NAME = """Login name for your LDAP server. The name
must have read permissions."""

MSG_LDAP_PASSWORD = "Password for the LDAP server."

MSG_LDAP_URL = "URL for your LDAP server."

MSG_LDAP_USER_FILTER = """Filter expression for your LDAP server which
returns your active users. Examples:
(objectclass=organizationalPerson)
(&(objectClass=organizationalPerson)(userAccountControl:1.2.840.113556.1.4.804:=512))
"""

MSG_LDAP_DISABLED_FILTER = """ Optional. Filter expression for your LDAP
server which returns users who have exited (quit, been terminated, etc.). Use
this if you do not delete the LDAP records for exited users, but
instead "disable" them or otherwise leave the objects in place.
"""

MSG_LDAP_BASE_DN = """Distinguished name at the root of your user records
in your LDAP server."""

MSG_LDAP_TIMEOUT = """Timeout, in seconds, for retrieving records from your
LDAP server. Note: this value may need to be large, 120 seconds or more, if
you have a lot of employees."""

MSG_TLS_OPTION = """This directive specifies what checks to perform on 
certificates from the ldap server.  It specifies whether to require TLS at all, 
just accept it, or not use it.  'never' means don't use it at all, 'demand' 
means to require that a successful TLS negotiation happens, and 'accept' means 
to accept a TLS conversation but don't require it."""

MSG_TLS_CACERTDIR = """A directory containing the CA that created the 
certificate used by the ldap server.  This directory should be managed with 
the c_rehash utility."""

MSG_TLS_CACERTFILE = """This contains the PEM format file containing
certificates for the CA that the tool will trust.  """

MSG_SYNC_GOOGLE_LAST_UPDATE_FILE = """This contains the name of the file
that will be used to store the last update time (the last point that a
completely successful sync **began** running).  The assumption is that your
ldap directory was completely up to date at that time.  This value defaults
to /var/local/ldap-sync-last-update."""

# generic 'set' message
MSG_SET_ANY= "Set a configuration variable. Choices are:"


# connect command

ERR_CONNECT_FAILED = "Connection failed"

MSG_CONNECTED = "Connected to %s"

HELP_CONNECT =  "Attempts a connection to the configured LDAP server"


# disconnect command

ERR_DISCONNECT_FAILED = "Disconnect fail"

MSG_DISCONNECTED = "Disonnected from %s"

HELP_DISCONNECT =  "Closes the connection to the configured LDAP server"



# setActiveFilter command

HELP_SET_ACTIVE_FILTER = """Sets the filter for active user accounts
in the LDAP server.  This does not test that the filter retrieves any users;
for that, use testFilter."""

# setDisabledFilter command

HELP_SET_DISABLED_FILTER = """Sets the filter for disabled user accounts
in the LDAP server. This filter is optional.  If you handle exited employees
by disabling the account this may be faster than the default method of finding
exited employees, namely, querying with your active filter and removing old
employees no longer passing the filter.
"""

# setPrimaryKey command

HELP_SET_PRIMARY_KEY = """This setting is optional. If it is used, the
tool can detect and handle changes to a user record even if the
Distinguished Name (DN) itself changes. Without this setting, a change to
the DN is handled as a new user.
Usage:
setPrimaryKey <attr-1> .. <attr-n>
where <attr-i> are added to the set of attributes maintained in the
database if not already there.
"""

# setTimestamp command

HELP_SET_TIMESTAMP = """Sets the LDAP attribute which is used to denote
"last changed."  This attribute varies depending on the type of directory
server you are using.  For example, on ActiveDirectory it is 'whenChanged'
but on other servers it may be 'modifyTimestamp'.
"""

# setTimeout command

HELP_SET_TIMEOUT = """Sets the time, in seconds, to wait for operations
on the LDAP server.
"""

# showLastUpdate command

MSG_SHOW_LAST_UPDATE = """The most recent sync on the user database
appears to have been done on %s (local time).
"""

MSG_SHOW_NO_LAST_UPDATE = """The database is empty or doesn't contain
a last-update timestamp.
"""

HELP_SHOW_LAST_UPDATE = """Displays the last time that an LDAP sync
was done on the user database.  This timestamp is used to find new,
updated, renamed, and deleted users, by appending a ">" condition to the query
issued during the syncUsers command.
"""

# testFilter command

MSG_TEST_FILTER_ATTRS = "The set of attributes defined on these users is:"

MSG_SET_YOUR_ATTRS = """You should set the number of attributes retrieved
from LDAP and stored in the database and in the XML file, via the
setAttrList command. This will speed up processing and reduce the size of
the XML file."""

HELP_TEST_FILTER = """Tests a search filter, and displays the number
of users that match it.  Shows all attributes found on them, so that you
can determine how to map your LDAP attributes to the necessary
Google attributes
Example: testFilter [-f] (objectclass=inetOrgPerson)
 If -f is specified, the user is not prompted and the suggestions
 are automatically accepted.  (This is mainly for batch processing.)
"""

ERR_TEST_FILTER_SAMPLING = """Retrieving all attributes on a small sample of 
these..."""

MSG_ATTR_SET_IS = """The set of unique attributes on a sample of %s
users matching this filter is:"""

MSG_SUGGESTED_ATTRS = """The following attributes are suggested for keeping
in your database:"""

MSG_SUGGESTED_MAPPINGS = """The Google user attributes (first name, last name, 
etc.) could be derived from your LDAP attributes as follows:"""

MSG_SUGGESTED_TIMESTAMP = """The 'last updated' timestamp attribute could be:
"""

MSG_SUGGESTED_PRIMARY_KEY = 'The "primary_key" attribute could be:'

MSG_NO_TIMESTAMP = "(none found)"

MSG_ACCEPT_SUGGESTIONS = "Accept these suggestions?"

MSG_SAID_NO_SUGGESTIONS = """You can use the attrList and mapGoogleAttribute 
commands later to tailor the lists as you need them."""

# attrList command:

MSG_ATTR_REMOVED = """'%s' removed. There were %s users with non-null values
for that attribute."""


MSG_USAGE_ATTR_LIST = """Usage:
attrList add <attrName>
attrList remove <attrName>
attrList show  (displays the current list)
"""

HELP_ATTR_LIST = """Configures the LDAP attributes that are retrieved
from your server and stored in the database and in your XML file.  If an
attribute is not needed for configuring Google Apps for Your Domain,
consider removing it.
Usage:
attrList add <attrName>
attrList remove <attrName>
attrList show  (displays the current list)
"""





# show users command

ERR_SHOW_USERS_ARGS = "Invalid arguments. Enter one or two numbers."

HELP_SHOW_USERS = """Usage: showNewUsers [start [end]] where 'start'
and 'end' are numbers.  Displays some or all of the users.
"""

ERR_TOO_MANY_USERS = "There are %s users.  Show them all?"

ERR_NO_USERS = 'There are no users in the database.'

# summarize users command

MSG_USER_SUMMARY = """Total users: %s
Marked as added: %s
Marked as exited: %s
Marked as renamed: %s
Marked as updated: %s
"""

HELP_SUMMARIZE_USERS = """Displays summary information about user database:
Total number of users, Number of users marked added/exited/renamed/updated
"""


# show attributes command

MSG_UNIQUE_ATTRS_ARE = "Unique attributes on user objects are:"

HELP_UNIQUE_ATTRS =  """Shows all attributes found on user objects discovered 
so far"""


# showAttributes command:

MSG_MAPPINGS = "All attributes, with current Google attribute mappings:"

HELP_MAPPINGS = """Shows all LDAP attributes found on users in the database
with the current mappings from Google attributes to LDAP attributes """

MSG_ENTER_MAPPING = "Expression:"


# map attr command:

MSG_ENTER_EXPRESSION = "Expression: "

ERR_MAP_ATTR = "Enter a Google attribute to map. Choices are:"

ERR_MAPPING_FAILED = "Test failed.  Error was"

HELP_MAP_ATTR= """Map a Google attribute to an LDAP attribute.
You can also use a Python expression on several attributes. Consult
the documentation for details."""

MSG_TESTING_MAPPING = "Testing your mapping on a random sample of users..."

# syncOneUser command


MSG_FIND_USERS_RETURNED = "Search in LDAP found %s users"

MSG_HERE_ARE_FIRST_N = "Here are the first %s of them:"

MSG_WHICH_USER = 'Which user did you mean?  Enter the number, or -1 for none: '

ERR_SUPPLY_VALID_USER= """Please supply a unique query expression for the user
you want to synchronize. The expression should be in the form:
<attribute>=<value> """

MSG_FOUND_IN_USERDB = """There are %s users in the user database that match
your query."""

MSG_USER_IS_NOW = 'The user record for %s is now:'

MSG_RECOMMENDED_ACTION_IS = """The recommended action for this user is to
treat user as having been: %s
"""

MSG_UP_TO_DATE = """Google Apps for Your Domain matches your database, and
your database matches LDAP. No action needed."""

MSG_PROCEED_TO_APPLY = 'Proceed with that action (y/n) '


MSG_GOOGLE_RETURNED = 'Google Apps for Your Domain returned the following data:'

MSG_LOOKING_UP = 'Now looking up \'%s\' in Google Apps for Your Domain...'

MSG_NOTHING_TO_DO = """User record for %s was already correct in the
user database."""

ERR_CANT_USE_EXPR = 'Can\'t parse %s into required form "<attribute>=<value>"'


HELP_SYNC_ONE_USER= """Synchronize a single user. Go to LDAP and retrieve
the information on the user, and sync the user with Google.  Conceptually,
this is equivalent to an updateUsers followed by syncUsersGoogle, if
there happened to be only one changed user.
Usage:
  syncOneUser <ldap filter>
  where <ldap filter> is a single-attribute filter that fetches that user. Example:
  syncOneUser uid=jjones
"""


# updateUsers command:

MSG_ADDING = """Add users that match your user filter of
%s 
with Google attributes mapped as follows:"""

MSG_FIND_EXITS = """Finding users whose accounts have been disabled,
using your filter of %s."""

MSG_NEW_USERS_ADDED = """Added %s new users to your database.
These users are marked to be added to Google Apps for Your Domain, the
next time you execute the 'syncAllUsers' command.
The total number of users is now %s.
"""

MSG_OLD_USERS_MARKED = """Found %s users in database which no
longer match your user filter, and marked them 'exited'.
"""

MSG_UPDATED_USERS_MARKED = """%s users in your database
have changed in LDAP. Changes have been incorporated in the database,
and those users are now marked for updating in Google
Apps for Your Domain, the next time you run the 'syncAllUsers'
command."""

MSG_RENAMED_USERS_MARKED = """Found %s users in database which
have changed in LDAP, and marked them for renaming in Google
Apps for Your Domain."""

HELP_ADD_USERS = """Adds users to the database that match
your User Filter.  Google attributes are mapped according to
the mappings you have set up.  If a user is already in the database,
the attributes are updated. You can optionally limit the number of users
you add.
Usage: addUsers [max number]
where [max number] is the most that will be added. If not given, all
users passing the filter are added."""



# readUsers: read in the users from XML or CSV file

MSG_READ_USERS = "Reading user file from %s"

HELP_READ_USERS = "Read the users from an XML or CSV file."



# markUsers: mark certain users for addition, deletion, or update
# to Google

ERR_MARK_USERS = "Please supply details.  Here is the Help for this command:"

ERR_MARK_USERS_ACTION = """Valid action types are: added, exited, renamed, 
and updated."""

HELP_MARK_USERS = """Mark some or all users as added, exited, renamed,
or updated.  Usage:
markUsers <first user>[-<last user>] <added|exited|renamed|updated>
where <first users> and <last user> are user numbers.

Note that, by default, new users from LDAP are marked
'added', old users no longer in LDAP are marked 'exited', 
users whose GoogleUsernames have changed are marked 'renamed', and
users whose LDAP records have changed in other ways are marked 'updated', 
so that this command may not be necessary normally.
"""

# syncUsersGoogle : add, delete, update to Google

ERR_SYNC_USERS_ACTION = """Please specify added, exited, renamed,
updated, or all."""

ERR_ENTER_DOMAIN = "Enter your domain name: "
ERR_ENTER_ADMIN_USER = "Enter the admin name for your domain: "
ERR_ENTER_ADMIN_PASSWORD = "Enter the admin password for your domain: "

MSG_CONNECTED_GOOGLE = "Connected"

MSG_SYNC_RESULTS = "Results of synchronization operation with Google:"
MSG_ADD_RESULTS = "%s users added successfully. %s users could not be added."
MSG_EXITED_RESULTS = """%s users exited successfully. %s users could not be 
exited."""
MSG_RENAME_RESULTS = """%s users renamed successfully. %s users could not be 
renamed."""
MSG_UPDATE_RESULTS = """%s users updated successfully. %s users could not be 
updated."""
MSG_CONSULT_LOG = "Consult log file for details."

ERR_CONNECTING_GOOGLE = "Problem connecting to your Google domain: %s"

HELP_SYNC_USERS_GOOGLE = """Synchronize the user database with Google Apps for
Your Domain.  This involves processing users according
to how they're marked.  Usage:
syncUsersGoogle [added|exited|renamed|updated|all]
where the argument defines which of the marked actions are carried out;
for example, if "added" is specified, only those users marked "added" are
processed (by adding them to Google Apps for Your Domain).
The default actions with respect to Google Apps for Your Domain are:
added: add the user.
exited: lock the user's account, but do not delete it.
renamed: rename the user's mail username, and create an alias of the old
one.
updated: update the user's account.
Since this is an open source package, you are welcome to change these actions
to fit your organization's policies and practices.
"""


# writeUsers: write out the users to XML file
MSG_WRITE_USERS = "Writing user file to %s"

MSG_REJECTED_ATTRS = """The following attributes were not written out because
of problems encoding them into utf-8:"""

HELP_WRITE_USERS = "Write the users to an XML or CSV file"


# batch command

ERR_BATCH_ARG_NEEDED = "Please supply a batch file name"

HELP_BATCH = "Executes commands from a text file"

#stop

MSG_STOPPING = "Stopping"

HELP_STOP = "Exits"


MSG_WRITE_CONFIG_FILE = "Writing config file to %s"

MSG_SYNC_GOOGLE_ENDPOINT = """The Google Apps host to target.   This is almost 
always unset unless you are a google developer working in the google private 
network."""

MSG_SYNC_GOOGLE_AUTH_URL = """The Google Apps Client Auth URL to target. 
This is almost always unset unless you are a google developer working in the 
google private network."""

MSG_SYNC_RESULTS = "Results of synchronization operation with Google:"
MSG_ADD_RESULTS = "%s users added successfully. %s users could not be added."
MSG_EXITED_RESULTS = """%s users exited successfully. %s users could not be 
exited."""
MSG_RENAME_RESULTS = """%s users renamed successfully. %s users could not be 
renamed."""
MSG_UPDATE_RESULTS = """%s users updated successfully. %s users could not be 
updated."""
MSG_CONSULT_LOG = "Consult log file for details."

MSG_EXIT_EXITED_USER = """Attempted exit of %s which does not exist in 
Google Apps."""

MSG_LAST_UPDATE_TIME_NOT_UPDATED = """Not updating last update time due to
prior errors or inactivity."""

MSG_UPDATING_LAST_UPDATE_TIME = "Updating last update time to %s"

MSG_EMPTY_LDAP_SEARCH_RESULT = "Empty ldap search result"
MSG_SUCCESSFULLY_HANDLED = "Successfully handled action '%s' on dn %s"

