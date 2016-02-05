# Help for Google Apps Sync Tool

# Google Apps LDAP Synchronization Tool #




## Objective ##

The LDAP Synchronization Tool is designed to facilitate the initial provisioning of an enterprise on Google Apps, and ongoing maintainance thereafter.  Its goal is to be a scriptable tool which fits into an IT department's overall chain of tools for employee management, rather than an all-encompassing product.  For this reason, it does not have a GUI.  The intent is that the source code for the tool be made freely available.

## Background ##
Many organizations use an LDAP server for maintaining and serving data on employees, computers, printers, mail accounts, and much more.  Particularly, almost any Windows shop is very likely using Exchange with ActiveDirectory.
Google Apps currently has an administrative GUI, suitable for management of individual users with some bulk-upload capabilities, and a programmatic API.  This tool is intended to fill the gaps left by those methods, by permitting the enterprise admin to regularly synchronize the LDAP server with Google:  add new employees, remove terminated employees, and update employees whose data has changed.
The tool uses only the Google Apps Provisioning API to talk to Google;  no other information is ever sent to Google.

## Overview ##

The tool is written in Python and requires 2.4 or above.  It mines an LDAP server (e.g. MS ActiveDirectory, OpenLdap, etc.) for users, according to a search filter entered by the user, and copies them into a Python dictionary.
It reads and writes its state to a CSV or XML file.  The overall workflow is:

  1. Initially read in all the email users from LDAP, and save in a file.  All users are marked for addition to Google, but not added yet.  The necessary Google provisioning data (first name, last name, email user name, etc.) is created by mapping LDAP attributes:  initially the Tool guesses how to do that, and the user can refine the mappings as desired.
  1. Look at the data in your favorite CSV reader (some popular spreadsheets can import CSV), and make any necessary changes.  Note that a lot of UI features (searching, scrolling, partial display, etc.) would be needed to make looking at the data pleasant, particularly if there were tens of thousands of users  It's explicitly not a goal to provide anything other than rudimentary display facilities.  This is a scriptable tool in a chain, not an LDAP data exploration tool.
  1. Synchronize the users with Google.  For each user marked for addition, the user is added to the domain.
  1. Subsequently, on a regular basis:  read in the user file and update it from LDAP.  New users are marked for addition to Google, terminated users are marked for deletion, users whose username has changed are marked for renaming, and users whose LDAP info has changed in other ways are marked for update.  The "synchronize with Google" command does all these changes.

## Sample workflows ##
To motivate the rest of this doc, here are two examples of how an admin might use the Tool:
### Steady state ###
In a steady state, the admin has previously mined the LDAP directory, added all the employees to Google Apps, and saved the users to a file 'yourdomain.users.csv'.  He/she has also saved a configuration file 'yourdomain.com.cfg'.  This workflow represents what would be done every day/week/whatever to sync up the LDAP directory with Google.
The commands are shown in bold.

```
$ ./sync_ldap.py -c yourdomain.com.cfg -f yourdomain.users.csv
Copyright 2006, Google, Inc.
All Rights Reserved.
Command: connect
Connected to LDAP://yourldapserver.yourdomain.com
Command: updateUsers
Add users that match your user filter of
(objectclass=organizationalPerson)
with Google attributes mapped as follows:
GoogleUsername          mail[:mail.find('@')]
GoogleFirstName         givenName
GoogleOldUsername               None
GoogleLastName          sn
GooglePassword          "password"
GoogleApplyIPWhitelist          False
Add users that match your user filter of
(&(objectclass=organizationalPerson)(modifyTimestamp>=20061101185255.0Z))
with Google attributes mapped as follows:
Added 11 new users and marked them for
addition to Google Apps.  Total is now 707.

Found 45 users in database which
have changed in LDAP, and marked them for updating in Google
Apps for Your Domain.
```

Here you need to set several variables to indicate how to login administratively to Google Apps

```
     set admin domain-admin@yourdomain.com
     set domain yourdomain.com
     set password secret
```

To configure the system to use your python code from user\_transofrmation\_rule.py instead of the default rule use something like

```
       mapGoogleAttribute GoogleLastName GoogleLastNameCallback
       mapGoogleAttribute GoogleFirstName GoogleFirstNameCallback
       mapGoogleAttribute GoogleUsername GoogleUsernameCallback
```

To finally go ahead and sync all users with Google Apps run

```
Command: syncAllUsers
# results not shown for privacy reasons
```

The syncAllUsers command would have authenticated with Google Apps, added the 11 new users, and updated the 45 whose information has changed.  The data file 'yourdomain.users.csv' is automatically saved upon exit.  Note that a perfectly reasonable variant on this workflow is to not do the syncAllUsers, and instead open up 'yourdomain.users.csv' in a CSV reader tool, and examine the 'meta-Google-action' column to make sure that the correct things will in fact be done by syncAllUsers.  The user might also want to run some other program on the CSV file, since the Tool really is just one part of a chain.

You may get an error similar to the following

```
05-16 14:37 root         ERROR    failure to handle 'added' on ...: ProvisioningApiError: Invalid character: password.newPasswords.beta: Must be at least 6 characters
password.newPasswords.alpha: Must be at least 6 characters
```

in which case you must edit the CSV file to include a password.

You may get this error

```
05-17 13:38 root         ERROR    failure to handle 'added' on ...: ProvisioningApiError: InvalidQuota(1041): Invalid quota '1024'
```

which indicates you are attempting to use a quota different than the acceptable quotas for you domain.   This is set by google.  You can set it to one of the quota options available to your domain by changing the GoogleQuota attribute via the `mapGoogleAttribute` command.  This attribute is also supported via GoogleQuotaCallback to user\_transformation\_rule.py.


### Standing start ###
There were two files used as input in the last example, yourdomain.com.cfg (the configuration) and yourdomain.users.csv (the actual employee data).  This is how we could have gotten them:

```
$ sync_ldap.py
Copyright 2006, Google, Inc.
All Rights Reserved.
Command: set ldap_url LDAP://yourldapserver.yourdomain.com
Command: set ldap_base_dn dc=yourdomain,dc=com
Command: set ldap_user_filter (objectclass=organizationalPerson)
Command: connect
05-16 12:58 root         INFO     Connected to LDAP://yourldapserver.yourdomain.com
Connected to LDAP://yourldapserver.yourdomain.com
Command: set ldap_timeout 180                         <== This is needed for large queries like the one above
Command: testFilter
Search found 706 users
Retrieving all attributes on a small sample of these...
The set of attributes defined on these users is:
[ 'accountInstance',
  'accountType',
  'adminAssistant',
  'cn',
  'ctCalMail',
  'ctCalOrgUnit2',
  'ctCalOrgUnit3',
  'ctCalOrgUnit4',
  'ctCalXItemId',
  'displayName',
  'gecos',
  'gidNumber',
  'givenName',
  'jpegPhoto',
  'l',
  'labeledURI',
  'loginShell',
  'mail',
  'o',
  'objectClass',
  'ou',
  'pager',
  'physicalDeliveryOfficeName',
  'roomNumber',
  'sn',
  'telephoneNumber',
  'title',
  'uid',
  'uidNumber',
  'createTimestamp',
  'creatorsName'
]
Google suggests retaining the following attributes:
        cn
        displayName
        gidNumber
        givenName
        googlePassExpire
        googlePassLastChg
        googlePassLastWarn
        mail
        mailHost
        mailRoutingAddress
        miMailExpirePolicy
        networkPortMD5Password
        networkPortPassword
        physicalDeliveryOfficeName
        sn
        uid
        uidNumber
Google suggests mapping Google attributes as follows:
GoogleLastName          sn
GoogleUsername          mail[:mail.find('@')]
GooglePassword          "password"
GoogleApplyIPWhitelist          False
GoogleFirstName         givenName
Google suggests as the "last updated" timestamp attribute:
        modifyTimestamp
Accept these suggestions?y
Command: attrList remove networkPortMD5Password
'networkPortMD5Password' removed. There were 0 users with non-null values
for that attribute.
Command: attrList remove networkPortPassword
'networkPortPassword' removed. There were 0 users with non-null values
for that attribute.
Command: updateUsers
Add users that match your user filter of
(objectclass=organizationalPerson)
with Google attributes mapped as follows:
GoogleLastName          sn
GoogleUsername          mail[:mail.find('@')]
GooglePassword          "password"
GoogleApplyIPWhitelist          False
GoogleFirstName         givenName
Add users that match your user filter of
(objectclass=organizationalPerson)
with Google attributes mapped as follows:
Added 706 new users and marked them for
addition to Google Apps.  Total is now 706.

Command: writeUsers yourdomain.users.csv
Writing user file to yourdomain.users.csv
Done
Command: stop
You did not supply a config file on the command line
(via the '-c' argument).
A config file will capture all your LDAP and user settings so that you don't
need to run commands next time to set them. Do you want to save your
configuration in a file (y/n) y
Enter a file name: yourdomain.cfg
```

Notes on the above commands:

  1. The testFilter command is very highly recommended for users who are not expert at LDAP.  First of all, it tries out the ldap\_user\_filter, which can be a very tricky thing to get right, so if you don't get back the number of users you were expecting, iterate on that.  Second, it takes a small sample of the users who did match your filter, looks at the attributes that were found on them, and guides you in choosing the ones that you'll actually want to keep.  Third, it makes an educated guess about the way to derive your Google Apps attributes from those.  Last, it suggests an LDAP attribute to use as the timestamp, which is critical in steady state operation for detecting users who have changed.
  1. The attrList remove commands just correct for the over-generosity of the "suggestions."   It's a good idea to remove unneeded attributes before retrieving users from LDAP, since it'll save time and storage space later.


## How it works ##
### Command-line options ###

The tool uses the optparse package from Python 2.4, which is why it requires that version.  Here is the output when "--help" is passed in:

```
Copyright 2006, Google, Inc.
All Rights Reserved.
usage: sync_ldap.py [-v][-q] [-f <dataFile>]
options:
  --version             show program's version number and exit
  -h, --help            show this help message and exit
  -f DATA_FILE, --dataFile=DATA_FILE
                        User data file (XML or CSV), both read from and
                        written to.
  -c CONFIG_FILE, --configFile=CONFIG_FILE
                        Configuration file (standard Python format)
  -l LOG_FILE, --logFile=LOG_FILE
                        Log file (defaults to stdout/stderr)
```

All the options really are "optional."  The tool can prompt for whatever it needs and doesn't already have.  The -c option provides a configuration file (syntax given below), which contains almost every possible setting.  If a configuration file is not supplied, you can set all the variables via the 'set' command, and on exit, a config file can be written out.

The DATA\_FILE need not be given, but if it is, the user database is populated from the file before the command interpreter starts.

### LDAP details ###

The tool does not assume that the LDAP server is ActiveDirectory, OpenLdap, or any other product, and thus it doesn't know a priori what attributes should be used to derive required Google attributes.  Furthermore, LDAP directories often have many attributes which are of no conceivable use for Google Apps provisioning, and which can be large and not even ASCII text, e.g. JPEG images, Microsoft security descriptors, etc.  Since the Tool just uses a Python dictionary for its storage rather than something more scaleable, it's desirable to not maintain more data than absolutely necessary for Google provisioning.  For this reason, a fair number of commands are aimed at discovering and managing the set of attributes to be maintained by the tool, and "mapping" (explained below) LDAP attributes to Google attributes.   This was illustrated in the Standing Start example above.
Although the admin can always use  some other tool to read in the XML or CSV file and assign Google attributes in a way that makes sense to him/her, the tool can also take mappings of one or more LDAP attributes to Google attributes.  This mapping is actually a general Python expression, as the GoogleUsername illustrates.  An example of this mapping is shown in the Standing Start section:

  * GoogleLastName comes from the 'sn' (for 'surname') attribute.
  * GoogleUsername takes the 'mail' LDAP attribute and strips off the '@' and everything after it.
  * GoogleFirstName comes from the 'givenName' LDAP attribute.

NOTE: do **not** use None for the GooglePassword.  Google Apps requires a password.  You will need to set this to a string literal as shown in the examples in this document (**not recommended**), or write a Python expression based on your ldap attributes to come up with a password.  Alternatively, you can use a user\_transformation\_rule (as described elsewhere in this document) to contruct a password based upon some authoritative source of information that only the user would know about him / herself.

The admin can always modify the list of attributes and the mappings, whether or not he/she accepts the Google suggestions.
Commands

The tool uses the cmd package from the Python standard library to implement a fairly nice command interpreter, with command-line editing and recall ala GNU readline.  Here is the output from "?" (or equivalently, "help"):

```
Copyright 2006, Google, Inc.
All Rights Reserved.
Command: ?

Documented commands (type help <topic>):
========================================
attrList    mapGoogleAttribute  showLastUpdate  syncAllUsers
batch       markUsers           showUsers       testFilter
connect     readUsers           stop            updateUsers
disconnect  set                 summarizeUsers  writeUsers

Undocumented commands:
======================
EOF  help

Command: help attrList
Configures the LDAP attributes that are retrieved
from your server and stored in the database and in your XML file.  If an
attribute is not needed for configuring Google Apps,
consider removing it.
Usage:
attrList add <attrName>
attrList remove <attrName>
attrList show  (displays the current list)

Command: help batch
Executes commands from a text file
```


As the example shows, the help for any command can be seen by typing `help <command>`


The command names should be considered provisional and subject to change!  I'm not going to claim that a whole lot of thought's gone into them, so far.

### Configuration variables ###
In general, you set a configuration variable via the 'set' command, and configure it permanently via a standard Python Library "ConfigParser" file.  Here are all possible variables, only some of which are required for any given run of the Tool:

```
admin
attrs
domain
ldap_admin_name
ldap_disabled_filter
ldap_host
ldap_password
ldap_port
ldap_root_dn
ldap_timeout
ldap_user_filter
ldap_page_size
logfile
loglevel
mapping
max_threads
password
primary_key
timestamp
tls_option
tls_cacertdir
tls_cacertfile
```

To get a comprehensive description of these parameters type

```
set
```

at the "Command:" prompt within the tool.

Here is an example of the config file:

```
[ldap-sync]
max_threads = 10
primary_key = 'uidNumber'
ldap_port = 389
loglevel = 11
logfile = '/bob/log.txt'
timestamp = 'modifyTimestamp'
mapping = {'GoogleUsername': "mail[:mail.find('@')]", 'GoogleFirstName': 'givenName', 'GoogleLastName': 'sn', 'GooglePassword': '"password"', 'GoogleApplyIPWhitelist': False}
ldap_host = 'yourldapserver.yourdomain.com'
attrs = set(['cn', 'meta-last-updated', 'uidNumber', 'GoogleFirstName', 'gidNumber',  'GoogleApplyIPWhitelist', 'meta-Google-action', 'uid', 'GoogleUsername', 'displayName', 'modifyTimestamp', 'sn', 'mail', 'GoogleLastName', 'givenName', 'GooglePassword'])
ldap_disabled_filter = '(objectclass=organizationalPerson)'
ldap_user_filter = '(objectclass=organizationalPerson)'
ldap_timeout = 180.0
ldap_root_dn = 'dc=yourdomain,dc=com'
```

The astute observer will recognize that, especially for 'attrs' and 'mapping', this is just the output of a Python 'repr' command.  In fact all these parameter values are gotten that way, and the strings are 'eval' -ed on the way in to recover the values.  This is tolerable for simple numbers and strings, but probably not for the more complex syntaxes, unless the admin is very fluent with Python.  For this reason, it's disallowed to set 'attrs' and 'mapping' via the 'set' command, and you have to use commands that are tailored specifically for those variables ('attrList' and 'mapGoogleAttribute' respectively).

### LDAP config variables ###
These are, hopefully, pretty well explained just by their names:

  * LDAP hostname or IP address (ldap\_host)
  * Name of an administrator (ldap\_admin\_name) with at least enough permissions to read objects under the ...
  * root distinguished name (ldap\_root\_dn) under which all subsequent queries are issued
  * Password of the administrator (ldap\_password)
  * Timeout for talking to the LDAP server (ldap\_timeout)
  * Filter for an employee who should be added to Google Apps (ldap\_user\_filter)
  * Filter for an employee who has exited the company or otherwise become ineligible for Google Apps (ldap\_disabled\_filter)
  * Retrieve n results from the ldap server at a time (ldap\_page\_size).  This is required by directories like Active Directory which by default have a server-side limit of 1000 results per page.  If your directory does not need this you can leave this at the default of 0.
  * Require TLS negotiation for connecting to ldap (tls\_option)
  * Location of the Certificate Authority certificate file directory (tls\_cacertdir)
  * Specify a specific Certificate Authority certificate file (tls\_cacertfile)

The ldap\_disabled\_filter in particular is optional.  It's intended for environments where former employees are kept in the directory but one of their variables is changed to reflect their employment status.  If there is no ldap\_disabled\_filter, exited employees are assumed to be deleted, and discovered by their absence in a scan.
Google config variables
These are only required when the syncAllUsers command is issued:

  * admin : the name of the administrator for the Google Apps domain.
  * password: the admin's password
  * domain: the Google Apps domain being administered
  * max\_threads: (optional)  the maximum number of threads to be spawned for talking to Google.  The default is one for every 32 transactions to be carried out, to a maximum of 10.


## User database config variables ##
Some of these could equally well be considered "LDAP variables", I suppose, but they're mainly looked at by the "userdb" module:

  * attrs: the set of user attributes to be fetched from LDAP and written to the CSV or XML file.
  * mapping:  the mapping from LDAP attributes to the Google Apps variables that are ultimately pushed to Google.
  * primary\_key:  (optional)  If supplied, this is the LDAP attribute of a user that never changes, even if the employee gets married, divorced, and changes every possible other attribute including "distinguishedName".  An example would be the "uid" or "employeeNumber" attribute.  The primary\_key is helpful in finding users whose GoogleUsername must change;  without it, they may be incorrectly treated as an exit and a new hire.
  * timestamp: the LDAP attribute which is used on your system to record when a record was last changed.  This is critical since it's the way the Tool does the "Steady State" operation shown above.  Note the line "(&(objectclass=organizationalPerson)(modifyTimestamp>=20061101185255.0Z))" "modifyTimestamp" is the timestamp variable here.

NOTE: there are differences in the way the filter string above is constructed based on the type of ldap directory being accessed.  This is due to slight differences in handling the format of the modifyTimestamp.  At the moment the tool tries to guess whether Active Directory is being accessed and formats the query string appropriately.  It uses the presence of the sAMAccountName field in your "attrs" config variable as an indicator that Active Directory is being accessed.  For more details about these slight differences, see the _AndUpdateTime() method in commands.py._

Also you may want to restrict the types of operations allowed by the sync.  Specifically the google\_operations variable setting below will restrict changes to updates only.

```
[ldap-sync]
google_operations = ['updated']
```

Miscellaneous config variables

  * logfile: (optional)  If given,  messages are written to the logfile as well as to stdout/stderr.  Their verbosity is controlled by:
  * loglevel:  a non-zero number, whose meaning is as given in the Python 'logging' Library

Reference for the 'logging' module:

```
50: critial errors only
40: errors
30: warnings
20: info messages
10: debug messages
0: all messages
```

### LDAP searching ###
_testFilter, attrList, updateUsers  commands_

If you think of the ultimate result of a tool session, it's an NxM table.  There are N rows, each row being a user, and M columns, each column an LDAP attribute, meta-attribute (more on this below), or Google attribute (some piece of data that's going to be uploaded to Google).  As we said earlier, it's important as a practical matter to keep M under control, since LDAP directories can have a lot of attributes of no possible use in Google provisioning, and those attributes can be large.  Thinking of it that way, set ldap\_user\_filter is for controlling N, attrList is for viewing and controlling M, and testFilter does a little of both, and is optional.  updateUsers is the payoff from almost all the commands mentioned so far.

`set ldap_user_filter` just sets the LDAP filter that is used in updateUsers, and has the same syntax as a filter for the ldapsearch utility.  An example for Google might be "(objectClass=googleOrgPerson)"

`attrList show` displays the attributes that will be saved on the next updateUsers call.

`attrList add` adds an additional LDAP attribute.

`attrList remove` removes an attribute.  This actually goes through the Python dictionary and removes existing attributes of that name.

`testFilter` is an attempt at "LDAP discovery" for first-time users.  Once you've used the tool and gotten your user filter and attribute set the way you want it, you wouldn't use this.  testFilter is intended to help you find out reasonably quickly which attributes are in your schema.  testFilter 

&lt;filter&gt;

 queries the LDAP server for objects matching the filter, and then it fetches all attributes for a small number of them to see what attributes are in use.  The inset above ("Retrieving all attributes on a small sample of these...  The set of attributes defined on these users") is output from the testFilter command.  If you don't accept the suggestions, you can always do attrList add/remove to put in or take out whatever attributes you want.

## Viewing the users ##
_showUsers, summarizeUsers  commands_

This is not a data exploration tool.  Save the file and open it in some CSV reader if you really want to look at your data.

`showUsers <start number> <end number>` displays the users from 

&lt;start&gt;

 to 

&lt;end&gt;

.  It's intended just to get some rough idea what the user data looks like.  Here's an example:

```
Command: showUsers 1
Display new users 1 to 1
1: cn=Fred299 Flinstone,o=Acme Inc.,c=US
{ 'GoogleFirstName': '',
  'GoogleLastName': 'Flintstone',
  'GooglePassword': '',
  'GoogleRole': '',
  'GoogleUsername': 'fred299',
  'cn': 'Fred299 Flinstone',
  'gidNumber': '800',
  'mail': 'fred299@yourdomain.com',
  'meta-Google-action': 'add',
  'meta-Google-status': '',
  'meta-last-updated': '1159480585.93',
  'modifyTimestamp': '20060622180843Z',
  'sn': 'Flintstone',
  'uid': 'fred299',
  'uidNumber': '800',
  'userPassword': 'abc123'}
```

If you don't supply 

&lt;start&gt;

 and 

&lt;end&gt;

, it displays them all, after first confirming that that is what you want (assuming there are more than 10 or so).

summarizeUsers provides an overview of the data (more explanation below on what the Google data means):

```
Command: summarizeUsers
Total users: 1003
Marked for addition to Google: 1003
Marked for deletion from Google: 0
Marked for update: 0
Deriving Google attributes
testFilter, mapGoogleAttribute commands
```

Although probably for most installations, the 'sn' attribute can be mapped directly to GoogleLastName and 'givenName' can be mapped to GoogleFirstName, we can't assume anything, and getting the customer's desired GoogleUsername is even dicier.  But we want this tool to be useful, so there's a way that, when a user is added, his or her Google attributes can be derived from the LDAP attributes, and this derivation can be any legal Python expression, e.g. the "mail[:mail.find('@')]" example above, which takes "fred@acme.com" and produces "fred."

Technical details:  this is actually done with a Python 'eval' statement, making the global namespace the set of attributes for that user.  So your expression can pull in any other data about the user, but nothing else.
testFilter suggests a set of mappings, using some very simple heuristics.

`mapGoogleAttribute  <attr> <expression>` derives  

&lt;attr&gt;

 by running 

&lt;expression&gt;

 on each user record.  It first tests the expression on a small sample of the users, since it's quite likely the admin will get it wrong the first few times, and only if there are no errors in that test phase is the mapping actually accepted.

### Picking up changes in LDAP ###
_showLastUpdate, updateUsers  commands_

When we want to pick up "changes" in LDAP since we last did an updateUsers, we have to answer the question "changes since when?"   There are a lot of possible ways to answer the "when" question, and we can and should debate that, but the provisional answer is "since you last did updateUsers."  So there is a meta-attribute "meta-last-updated" added to each user record giving the time that the updateUsers that brought in this user was issued.
showLastUpdate displays the highest value of meta-last-updated.

Furthermore, as far as I can tell there is no uniformity among LDAP schemas on the attribute representing "last changed" time  In openldap it's "modifyTimestamp" but with ActiveDirectory it seems to be "whenChanged" (among other attributes that also have that information!), and LDAPv3 has a "modifiedTime" standard attribute (but of course v3 is hardly universal yet).  So one of the "attribute discovery" functions the tool does is suggest which attribute you want to use to denote "last changed".
updateUsers, then, finds T, the latest meta-last-updated attribute in the user database, and adds a term to the user filter "(modifyTimestamp>=T)" or "(whenChanged>=T)" or whatever attribute is being used for "last changed."  (It really ought to be ">" and not ">=", but for some reason LDAP doesn't support ">" and "<" in filters.)   Each user found by that query is added to the database with the value of another meta-attribute, "meta-Google-action", set to "add".
After that, we want to find the users that are no longer active, so another query is done, in one of two ways, depending on whether the ldap\_disabled\_filter variable is defined:
If there is both a ldap\_disabled\_filter and a timestamp defined:  a query is done on users passing the disabled filter, and having a timestamp greater than the last time we did updateUsers.    Those users are considered exited.
Otherwise, a query is done on ldap\_user\_filter, and all old users no longer passing the query are considered exits.

### Synchronizing with Google ###
_summarizeUsers, markUsers, syncAllUsers, syncOneUser  commands_

Each user has a meta-Google-action attribute, which is used by syncAllUsers, and as mentioned above, updateUsers tries to be smart about setting it appropriately.  Furthermore, the admin can always save the file and open it in a CSV reader that makes it easy to search and edit en masse.  But for single user changes, markUsers can be used to change the meta-Google-action attribute.

summarizeUsers displays what your workload with respect to Google is:

```
Command: summarizeUsers
Total users: 1003
Marked for addition to Google: 1003
Marked for deletion from Google: 0
Marked for update: 0
Marked for rename: 0
```

syncAllUsers is the ultimate goal of the tool.  It uses the Provisioning API to actually go to Google and add, delete, update and rename the users according to their meta-Google-action attribute.  Once the meta-Google-action has been successfully carried out on the user, the meta-Google-action attribute is set to null.

syncAllUsers works as follows (the same logic is followed in turn for adds, exits, updates, and renames):

  1. The number of threads N to be used is determined, based on the max\_thread\_count variable and the amount of work to do
  1. There are N copies of the google.appsforyourdomain.API object created, each with its own authorization token.
  1. N threads are created, each with its own API object.  For each thread, there is an in-queue, an out-queue, and a "handler class".  The handler class, by default, is GoogleActAdded / GoogleActExited / GoogleActRenamed / GoogleActUpdated, depending on the type of action we're doing.   (Although this isn't a full extensibility scheme yet, it wouldn't be hard to make the Tool accept the name of any class which is a subset of GoogleAct.  For now, you just have to edit the relevant file if the default handling isn't exactly what you want.)
  1. A StatusReader thread is created to read the status reports coming back from the worker threads.  (it would certainly possible to spin up multiple StatusReader threads if the need arose, but right now there's only one.)
  1. The in-queue is stuffed by the caller with all the work that the threads need to do.  The threads each instantiate a handler, read from the queue, and call the handlers "handle()" method for each item of work.
  1. When the thread succeeds or fails with each item of work, it writes a status report into its out-queue.  This status report is read by the StatusReader thread, which logs the result and updates the user database (generally, by zeroing the meta-Google-action attribute on success, so we don't try to act on it again.


The default handling of each possible action is:
added:  CreateAccount(), EnableEmail()
exited: LockAccount()
updated: UpdateAccount()
renamed: RenameAccount()

### syncOneUser  command ###
This is for the case of "a new user doesn't have his/her mail account yet, they're standing right there in my office, and we need to enable them now."  Or, "someone was just terminated, and we need them removed now."
The working assumption here is that the user's record in LDAP should be assumed correct, so the task is to sync it with Google.  (If the LDAP record is not correct, that should be taken care of before executing this command.)
syncOneUser is somewhat involved, since there are a lot of cases to consider.  In general, the command updates the user's record from LDAP, queries Google and displays the results it gets back, and then displays its conclusion as to what happened with this user (was he/she added, exited, etc.?)  The admin gets a chance to OK it before the result is executed.

Here are some examples:
User already present in UserDB and in Google:

```
Command: syncOneUser name=Anew User
Now looking up 'anewuser' in Google Apps...
Google Apps returned the following data:
userName        : anewuser
firstName       : Anew
lastName        : google
accountStatus   : unlocked
emailLists      :
aliases :
Google Apps is up to date. No action needed.
```

User's LDAP record has been changed (new first name):

```
Command: syncOneUser name=Anew User
The user record for cn=anew user,ou=unittest,dc=yourdomain,dc=com is now:
{ 'GoogleApplyIPWhitelist': None,
  'GoogleFirstName': 'Anewer',
  'GoogleLastName': 'google',
  'GoogleOldUsername': None,
  'GooglePassword': 'password',
  'GoogleUsername': 'anewuser',
  'badPasswordTime': '0',
  'badPwdCount': '0',
  'cn': 'Anew User',
  'displayName': 'Anew User',
  'distinguishedName': 'CN=Anew User,OU=Unittest,DC=yourdomain,DC=com',
  'givenName': 'Anewer',
  'mail': 'anewuser@yourdomain.com',
  'mailNickname': 'anewuser',
  'meta-Google-action': 'updated',
  'meta-last-updated': 1164846094.3949389,
  'name': 'Anew User',
  'sn': 'Formeruser',
  'userPrincipalName': 'anewuser@yourdomain.com',
  'whenChanged': '20061130002558.0Z'}
Now looking up 'anewuser' in Google Apps...
Google Apps returned the following data:
userName        : anewuser
firstName       : Anew
lastName        : google
accountStatus   : unlocked
emailLists      :
aliases :
The recommended action for this user is to
treat user as having been: updated

Proceed with that action (y/n) y
```

User's LDAP record gets deleted

```
Command: syncOneUser name=Anew User
Search in LDAP found 0 users
There are 1 users in the user database that match
your query.
The user record for cn=anew user,ou=unittest,dc=yourdomain,dc=com is now:
{ 'GoogleApplyIPWhitelist': None,
  'GoogleFirstName': 'Anewer',
  'GoogleLastName': 'google',
  'GoogleOldUsername': None,
  'GooglePassword': 'password',
  'GoogleUsername': 'anewuser',
  'badPasswordTime': '0',
  'badPwdCount': '0',
  'cn': 'Anew User',
  'displayName': 'Anew User',
  'distinguishedName': 'CN=Anew User,OU=Unittest,DC=yourdomain,DC=com',
  'givenName': 'Anewer',
  'mail': 'anewuser@yourdomain.com',
  'mailNickname': 'anewuser',
  'meta-Google-action': 'exited',
  'meta-last-updated': 1164846561.784775,
  'name': 'Anew User',
  'sn': 'Formeruser',
  'userPrincipalName': 'anewuser@yourdomain.com',
  'whenChanged': '20061130002558.0Z'}
Now looking up 'anewuser' in Google Apps ...
Google Apps  returned the following data:
userName        : anewuser
firstName       : Anewer
lastName        : google
accountStatus   : locked
emailLists      :
aliases :
The recommended action for this user is to
treat user as having been: exited

Proceed with that action (y/n) n
```

### Loading and unloading your data ###
_readUsers, writeUsers  commands_

User data can be saved in either of two popular forms:  XML and CSV.
readUsers 

&lt;filename&gt;

 , where 

&lt;filename&gt;

 must end in ".xml" or ".csv", loads the database from the named file, and writeUsers 

&lt;filename&gt;

 stores it to that file in the indicated format.
Admins are more than welcome to edit the XML or CSV files with some other tool before running this tool again;  in fact, we encourage it, since we can't possibly anticipate and implement everything they'd ever want to do.

### Miscellaneous commands ###
_batch, stop  commands_

You can batch up a set of frequently-used commands into a file and run that:
batch 

&lt;filename&gt;

 reads each line from 

&lt;filename&gt;

 and runs it just as though you'd typed it.  Here's an example of using that to automate connecting to the Google LDAP server:

```
setHost yourldapserver.yourdomain.com
setRootDN dc=yourdomain,dc=com
connect
setFilter (objectclass=inetOrgPerson)
```

stop exits the command interpreter. (as does control-D on Linux and control-Z on Windows)

## Possible Improvements ##

  * Need to retrofit to support Provisioning API v2 once the Python client wrappers are written.  Java wrappers are already in place.
  * Need to integrate mailman list and ldap groups sync into this
  * Perform a reverse-sync into LDAP from Google Apps, for organizations that want to make Google Apps their authoritative source for users.