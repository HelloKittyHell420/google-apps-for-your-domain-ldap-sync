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


import ldap
import logging
import messages
import time
import userdb
import utils

# The user may have requesting LDAP results paging, so try to load the
# library for this.  But don't die yet if it's not available.
try:
  from ldap.controls import SimplePagedResultsControl
except ImportError:
  SimplePagedResultsControl = None


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
                  'ldap_timeout': messages.MSG_LDAP_TIMEOUT,
                  'ldap_page_size': messages.MSG_LDAP_PAGE_SIZE,
                  'tls_option': messages.MSG_TLS_OPTION,
                  'tls_cacertdir': messages.MSG_TLS_CACERTDIR,
                  'tls_cacertfile': messages.MSG_TLS_CACERTFILE}

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
    self.ldap_page_size = 0
    self.tls_option = 'never'
    self.tls_cacertdir = '/etc/ssl/certs'
    self.tls_cacertfile = ''
    super(LdapContext, self).__init__(config=config,
                                      config_parms=self.config_parms,
                                      **moreargs)

    self._config = config
    self._required_config = ['ldap_url', 'ldap_user_filter', 'ldap_base_dn']
    self.config_changed = False
    self.conn = None
    if self.tls_option == 'demand':
      ldap.set_option(ldap.OPT_X_TLS, ldap.OPT_X_TLS_DEMAND)
    elif self.tls_option == 'allow':
      ldap.set_option(ldap.OPT_X_TLS, ldap.OPT_X_TLS_ALLOW)
    elif self.tls_option == 'never':
      pass
    else:
      logging.error('option tls_option=%s was not understood' %
                    self.tls_option)
      return

    if self.tls_cacertdir:
      ldap.set_option(ldap.OPT_X_TLS_CACERTDIR, self.tls_cacertdir)

    if self.tls_cacertfile:
      ldap.set_option(ldap.OPT_X_TLS_CACERTFILE, self.tls_cacertfile)

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
      self.protocol_version = 3
      self.conn.bind_s(self.ldap_admin_name, self.ldap_password,
        ldap.AUTH_SIMPLE)
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

  def SetUserFilter(self, query):
    """ Sets the current ldap_user_filter
    Args:
      query: a string containing a standard LDAP filter expression
    """
    self.ldap_user_filter = query

  def _AsyncSearch(self, query, sizelimit, attrlist=None):
    """ Helper function that implements an async LDAP search for
    the Search method below.
    Args:
      query: LDAP filter to apply to the search
      sizelimit: max # of users to return.
      attrlist: list of attributes to return.  If null, all attributes
        are returned
    Returns:
      A list of users, as returned by the LDAP search
    """
    logging.debug('Search on %s for %s' % (self.ldap_base_dn, query))
    msgid = self.conn.search_ext(self.ldap_base_dn, ldap.SCOPE_SUBTREE,
                                 query, attrlist=attrlist)
    users = []

    # If we have a sizelimit, we'll get results one by one so that we
    # can stop processing once we've hit the limit.
    if sizelimit:
      all = 0
    else:
      all = 1

    while True:
      restype, resdata = self.conn.result(msgid=msgid, all=all,
                                          timeout=self.ldap_timeout)
      users.extend(resdata)
      if restype == ldap.RES_SEARCH_RESULT or not resdata:
        break
      if sizelimit and len(users) >= sizelimit:
        self.conn.abandon_ext(msgid)
        break
      time.sleep(SLEEP_TIME)
      
    return users

  def IsUsingLdapLibThatSupportsPaging(self):
    return SimplePagedResultsControl

  def _PagedAsyncSearch(self, query, sizelimit, attrlist=None):
    """ Helper function that implements a paged LDAP search for
    the Search method below.
    Args:
      query: LDAP filter to apply to the search
      sizelimit: max # of users to return.
      attrlist: list of attributes to return.  If null, all attributes
        are returned
    Returns:
      A list of users as returned by the LDAP search
    """
    if not self.IsUsingLdapLibThatSupportsPaging():
      logging.error('Your version of python-ldap is too old to support '
                    'paged LDAP queries.  Aborting search.')
      return None

    paged_results_control = SimplePagedResultsControl(
        ldap.LDAP_CONTROL_PAGE_OID, True, (self.ldap_page_size, ''))
    logging.debug('Paged search on %s for %s' % (self.ldap_base_dn, query))
    users = []
    ix = 0
    while True: 
      if self.ldap_page_size == 0:
        serverctrls = []
      else:
        serverctrls = [paged_results_control]
      msgid = self.conn.search_ext(self.ldap_base_dn, ldap.SCOPE_SUBTREE, 
          query, attrlist=attrlist, serverctrls=serverctrls)
      res = self.conn.result3(msgid=msgid, timeout=self.ldap_timeout)
      unused_code, results, unused_msgid, serverctrls = res
      for result in results:
        ix += 1
        users.append(result)
        if sizelimit and ix >= sizelimit:
          break
      if sizelimit and ix >= sizelimit:
        break
      cookie = None 
      for serverctrl in serverctrls:
        if serverctrl.controlType == ldap.LDAP_CONTROL_PAGE_OID:
          unused_est, cookie = serverctrl.controlValue
          if cookie:
            paged_results_control.controlValue = (self.ldap_page_size, cookie)
          break
      if not cookie:
        break
    return users

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
    query = filter_arg
    if not query:
      query = self.ldap_user_filter
    if not query:
      raise utils.ConfigError(['ldap_user_filter'])
    if not self.conn:
      raise RuntimeError('Not connected')

    self.conn.network_timeout = self.ldap_timeout

    users = None
    try:
      if self.ldap_page_size:
        users = self._PagedAsyncSearch(query, sizelimit, attrlist=attrlist)
      else:
        users = self._AsyncSearch(query, sizelimit, attrlist=attrlist)
      if users is None:
        return None
      if not users:
        logging.warn(messages.MSG_EMPTY_LDAP_SEARCH_RESULT)

    except ldap.SIZELIMIT_EXCEEDED, e:
      logging.exception('Size limit exceeded on your server.  '
                        'Try setting ldap_page_size.  %s' % str(e))
    except ldap.INSUFFICIENT_ACCESS, e:
      logging.exception('User %s lacks permission to do this search\n%s' %
                        (self.ldap_admin_name, str(e)))
    except ldap.LDAPError, e:
      logging.exception('LDAP error searching %s: %s' % (query, str(e)))

    return userdb.UserDB(config=self._config, users=users)
