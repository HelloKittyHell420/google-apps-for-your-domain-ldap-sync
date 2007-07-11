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
#

import logging
import userdb

""" Contains superclass for GoogleResult:
 class GoogleResult: superclass for all "GoogleResultHandlers"
"""

class GoogleResult(object):

  """ Superclass for all "GoogleResultHandlers", the classes that
  handle a result from a google_action handler, be it successful or 
  unsuccessful.  The default action is simply to log the result and, if it
  was successful, null out the 'meta-Google-action' attribute in the userdb
  for that user.  However, some organizations may wish to do other actions,
  e.g. record them in LDAP.
  """
  def __init__(self, userdb, **moreargs):
    """ Constructor.  Call this after acquiring access to the userdb
    object, however that's guarded (threading.Condition, whatever)
    Args:
      userdb: the userdb.userdb object
    """
    super(GoogleResult, self).__init__(userdb=userdb,
                                  **moreargs)
    self._userdb = userdb

  def Handle(self, dn, action, failure=None, object=None):
    """ Subclass may override this, but the default action, to clear
    the meta-Google-action attribute, may be sufficient for
    most applications.
    This method is called after the result has already been dequeued
    by another component in the system. There may be other instances
    of this method operating in different threads, so care must be taken
    to do things in a thread-safe way.
    Args:
      dn: distinguished name of the user
      action: one of the action types enumerated in userdb.UserDB 
        ('added', 'updated', 'exited', 'renamed')
      failure: failure message, or None if successful
      object: additional information passed by the google_action
        handler. One example is the GoogleActionCheck object, which passes
        back the account status from Google.
    """
    if not failure:
      self._userdb.SetGoogleAction(dn, None)
      logging.info('successfully handled \'%s\' on %s' %
                    (action, dn))
    else:
      logging.error('failure to handle \'%s\' on %s: %s' %
                    (action, dn, failure))

if __name__ == '__main__':
  pass
