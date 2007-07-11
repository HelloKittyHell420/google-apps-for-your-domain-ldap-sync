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
#

""" The module that talks to the LDAP server

class LdapContext:  class that encapsulates all LDAP info

"""


import ConfigParser
import ldap
import logging
import messages
import time
import userdb
import utils

SLEEP_TIME = 0.1
TIMEOUT_SECS = 15


class LdapContext(utils.Configurable):

  """ Maintains the current context for LDAP connection and
  performs all operations against the LDAP server. LDAP data
  is returned as an userdb.UserDB() object, so the caller need
  not know anything about the ldap module's data structures.

  As a subclass of Configurable, LdapContext expects a utils.Config
  object in its constructor, and uses it to pull in all its configuration
  variables (enumerated in the class variable 'config_parms').
  """
  config_parms = {'ldap_admin_name': messages.MSG_LDAP_ADMIN_NAME,
                  'ldap_password': messages.MSG_LDAP_PASSWORD,
                  'ldap_url': messages.MSG_LDAP_URL,
                  'ldap_user_filter': messages.MSG_LDAP_USER_FILTER,
                  'ldap_disabled_filter': messages.MSG_LDAP_DISABLED_FILTER,
                  'ldap_base_dn': messages.MSG_LDAP_BASE_DN,
                  'ldap_timeout': messages.MSG_LDAP_TIMEOUT}

  def __init__(self, config, **moreargs):
    """ Constructor
    Args:
      config: a utils.Config object, which should have been initialized with
        the Sync Tool's configuration.
    """
    self.ldap_admin_name = ''
    self.ldap_password = ''
    self.ldap_user_filter = None
    self.ldap_disabled_filter = None
    self.ldap_base_dn = None
    self.ldap_timeout = TIMEOUT_SECS
    self.ldap_url = None
    super(LdapContext, self).__init__(config=config,
                                      config_parms=self.config_parms,
                                      **moreargs)

    self._config = config
    self._required_config = ['ldap_url', 'ldap_user_filter', 'ldap_base_dn']
    self.config_changed = False
    self.conn = None

  def SetConfigVar(self, attr, val):
    """ Overrides: the superclass method, in order to provide more
    validation
    Args
      attr: name of config variable
      val: value
    Raises:
      ValueError: if the value is not valid, e.g. not a number
        when a number is required.
    """
    if not attr in self.config_parms:
      return messages.msg(messages.ERR_NO_SUCH_ATTR, attr)
    try:
      if attr == 'ldap_timeout':
         try:
           self.ldap_timeout = float(val)
         except ValueError:
           return messages.msg(messages.ERR_ENTER_NUMBER, val)
      else:
        setattr(self, attr, val)
    except ValueError:
        return messages.msg(messages.ERR_INVALID_VALUE, attr)

  def Connect(self):
    """ Connects to the current LDAP server and binds.
    Returns:
      None if success, -1 if error occurred
    Raises:
      utils.ConfigError: if any required config items are not
        present.
    """
    try:
      self._config.TestConfig(self, ['ldap_url'])
      self.conn = ldap.initialize(self.ldap_url)
      self.conn.bind_s(self.ldap_admin_name, self.ldap_password,
        ldap.AUTH_SIMPLE);
      return None
    except ldap.INVALID_CREDENTIALS, e:
      logging.exception('Invalid credentials error:\n%s' % str(e))
      return -1
    except ldap.LDAPError, e:
      logging.exception('LDAP connection error: %s', str(e))
      return -1

  def Disconnect(self):
    """ Disconnects from the current LDAP server and releases all
    resources.
    Raises:
      ldap.LDAPError
    """
    if not self.conn:
      return
    try:
      self.conn.unbind_s()
      self.conn = None
    except ldap.LDAPError, e:
      logging.exception('LDAP disconnection error: %s', str(e))

  def GetUserFilter(self):
    """
    Returns: the current ldap_user_filter
    """
    return self.ldap_user_filter

  def SetUserFilter(self, filter):
    """ Sets the current ldap_user_filter
    Args:
      filter: a string containing a standard LDAP filter expression
    """
    self.ldap_user_filter = filter

  def AsyncSearch(self, filter_arg, sizelimit, attrlist=None):
    """  Does an async search, which, at least currently, we have to do to
    impose a sizelimit, since the 'sizelimit' argument on the search*()
    calls doesn't appear to work.
    Args:
      sizelimit: max # of users to return.
      attrlist: list of attributes to return.  If null, all attributes
        are returned
    Returns:
      a userdb.UserDB object, or None if errors are encountered
    Raises:
      utils.ConfigError: if any required config items are not present
      RuntimeError: if not connected
    """
    self._config.TestConfig(self, self._required_config)
    filter = filter_arg
    if not filter:
      filter = self.ldap_user_filter
    if not filter:
      raise utils.ConfigError(['ldap_user_filter'])
    if not self.conn:
      raise RuntimeError('Not connected')
    try:
      logging.debug('searching in %s\n\tfor%s\n\twith %s' % (self.ldap_base_dn,
                                              filter, str(attrlist)))
      msgid = self.conn.search_ext(self.ldap_base_dn, ldap.SCOPE_SUBTREE, 
                                   filter, attrlist=attrlist)
      u = []
      for ix in range(sizelimit):
        ix += 1
        time.sleep(SLEEP_TIME)
        res = self.conn.result(msgid=msgid, all=0, timeout=self.ldap_timeout)
        code, l = res
        if len(l):
          u.append(l[0])
          if len(u) >= sizelimit:
            u = u[:sizelimit]
            break
    except ldap.INSUFFICIENT_ACCESS, e:
      logging.exception('User %s lacks permission to do this search\n%s' %
                        (self.ldap_admin_name, str(e)))
      return None
    except ldap.LDAPError, e:
      logging.exception('LDAP error searching %s: %s', filter, str(e))
      return None
    return userdb.UserDB(config=self._config, users=u)

  def Search(self, filter_arg=None, sizelimit=0, attrlist=None):
    """ Given the configured user search filter, return the list
    of users matching it.  Call ready_status() before this, if you
    want to avoid an exception from lack of configuration.
    Args:
      filter_arg: LDAP search filter to use. If not provided, the
        configured ldap_user_filter is used.
      sizelimit: limits the number of users returned. If zero,all
        users matching the user search filter are returned
      attrlist: attributes to return for each user.  If None, all
        attribute are returned
    Raises:
      utils.ConfigError: if any required config items are not present
      RuntimeError:  if not connected
    """
    self._config.TestConfig(self, self._required_config)
    if not self.conn:
      raise RuntimeError('Not connected')
    filter = filter_arg
    if not filter:
      filter = self.ldap_user_filter
    if not filter:
      raise utils.ConfigError(['ldap_user_filter'])
    self.conn.network_timeout = self.ldap_timeout
    try:
      if sizelimit:
        u = self.AsyncSearch(filter=filter, sizelimit=sizelimit,
                             attrlist=attrlist)
        return u
      else:
        logging.debug('searching in %s\n\tfor%s\n\twith %s' %
                      (self.ldap_base_dn, filter, str(attrlist)))
        u = self.conn.search_ext_s(self.ldap_base_dn, ldap.SCOPE_SUBTREE, filter,
                                 attrlist=attrlist, timeout=self.ldap_timeout)
        return userdb.UserDB(config=self._config, users=u)
    except ldap.INSUFFICIENT_ACCESS, e:
      logging.exception('User %s lacks permission to do this search\n%s' %
                        (self.ldap_admin_name, str(e)))
      return None
    except ldap.SIZELIMIT_EXCEEDED, e:
      logging.exception('Size limit exceeded on your server:\n%s' % str(e))
      return None
    except ldap.LDAPError, e:
      logging.exception('LDAP error searching %s: %s', filter, str(e))
      return None
