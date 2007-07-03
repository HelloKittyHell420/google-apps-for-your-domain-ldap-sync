#!/usr/bin/python2.4
#
# Copyright 2006 Google Inc.
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


"""An interface for obtaining and caching a Provisioning authentication token.
"""


from provisioning_errs import *
import sys
import time
import urllib
import urllib2


DEFAULT_EXPIRATION = 3600 * 12
"""Default expiration for auth tokens.  12 hours."""

AUTH_URL = 'https://www.google.com/accounts/ClientAuth'
"""Default URL for fetching an auth token."""


class RestAuthTokenError(Exception):
  pass


class RestAuthToken:
  """Fetches and caches a Provisioning authentication token and caches it.  Handles
  fetching a new token after a specified expiration time."""

  def __init__(self, user, password, authurl=None, expiretime=None,
               debug=False):
    """Initialize a new RestAuthToken object.  Initialization does not
    fetch a new auth thoken.

    Args:
      user: admin user to authenticate at in the form username@domain
      password: password for user
      expiretime: how long to cache the auth token before fetching a new one
    """

    self.__authtoken = None
    self.__authtime = 0
    self.__user = user
    self.__password = password
    if not authurl:   # This allows changing AUTH_URL externally and it working
      authurl = AUTH_URL
    self.__authurl = authurl
    self.__debug = debug

    if expiretime is None:
      self.__expiretime = DEFAULT_EXPIRATION
    else:
      self.__expiretime = expiretime

  def __str__(self):
    return self.Token()

  def Token(self):
    """Returns the current authorization token as a string."""

    if time.time() - self.__authtime > self.__expiretime:
      self.__authtoken = self._Fetch()
      self.__authtime = time.time()

    return self.__authtoken

  def _Fetch(self):
    """Do the dirty work of actually obtaining an auth token.

    Returns the auth token as a string or throws an AuthenticationError
    """

    reqdata = { 'accountType': 'HOSTED',
                'Email': self.__user,
                'Passwd': self.__password,
                }

    req = urllib2.Request(self.__authurl, urllib.urlencode(reqdata))

    if self.__debug:
      sys.stderr.write('%sing %s to %s\n' % (req.get_method(), req.get_data(),
                                             req.get_full_url()))

    try:
      f = urllib2.urlopen(req)
      authdata = f.read()
    except urllib2.URLError, e:
      raise AuthenticationError('Failed to open auth URL: %s' % e.msg)

    if self.__debug:
      sys.stderr.write('Response was:\n%s\n' % authdata)

    token = None
    for line in authdata.split('\n'):
      try:
        (tag, value) = line.split('=', 2)
      except ValueError:
        continue
      if tag == 'SID':
        token = value
    if token is None:
      raise AuthenticationError('Response did not contain an auth token')

    return token

if __name__ == '__main__':
  pass
