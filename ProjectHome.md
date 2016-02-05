# Features #
  * synchronizes users from Active Directory or openldap into Google Apps
  * detects new and exited users automatically and changes Google Apps accounts accordingly
  * handles user id / account renames automatically
  * handles attribute updates automatically
  * keeps track of changes and only propagates deltas (to allow syncing every 10 minutes for example)

This tool uses an API that is deprecated (see [GData Provisioning API 1.0](http://code.google.com/apis/apps/google_apps_provisioning_api_v1.0_reference.html)).  You might want to consider using the following alternative:

[Google Apps Directory Sync](http://www.google.com/support/a/bin/answer.py?&answer=106368)

# Installation #

Be sure you have Python 2.4 or later installed.

Download a read only copy of ldap-sync with

> `svn checkout http://google-apps-for-your-domain-ldap-sync.googlecode.com/svn/trunk/ google-apps-for-your-domain-ldap-sync`

You can also download the [tarball](http://code.google.com/p/google-apps-for-your-domain-ldap-sync/downloads) if you prefer.

You must use the python client of the Google Apps provisioning API v1.0.  To download a copy use

> `svn checkout http://google-apps-provisioning-api-client.googlecode.com/svn/trunk/python google-apps-provisioning-api-client`

or download the [latest provisioning api python client library](http://code.google.com/p/google-apps-provisioning-api-client/downloads/list).

Be sure to set your PYTHONPATH to the root of where the python client library is loaded (there should be a google/appsforyourdomain subfolder below wherever PYTHONPATH points if you've done it correctly).

Finally, download and install the latest [python-ldap](http://sourceforge.net/projects/python-ldap/) from sourceforge.

# Usage #
> See the document [How to Use It](http://code.google.com/p/google-apps-for-your-domain-ldap-sync/wiki/HowToUseIt)