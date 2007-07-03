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

""" Python wrapper around the Google Apps for Your Domain API.
"""


""" Exceptions that can be raised from this API.  ProvisioningApiError is the base
class, and there are subclasses for each unique type of error, so that client
code can, if it likes, catch either specific errors or the general error.
"""

class ProvisioningApiError(Exception):

  """Exception base class for errors received from the
  Google Apps for Your Domain API.
  """

  def __init__(self, reason, msg):
    """Create a ProvisioningApiError exception.

    Args:
      reason: reason
      msg: extendedMessage
    """

    Exception.__init__(self, msg)
    self.reason = reason
    self.msg = msg

  def __str__(self):
    return 'ProvisioningApiError: %s: %s' % (self.reason, self.msg)

class AuthenticationError(ProvisioningApiError):

  """ The user, password, or domain information supplied was rejected
  by Google.
  """

  def __init__(self, msg):
    ProvisioningApiError.__init__(self, reason='Authentication error', msg=msg)

class ConnectionError(ProvisioningApiError):

  """ The API was unable to connect to Google
  """

  def __init__(self, msg):
    ProvisioningApiError.__init__(self, reason='Connection error', msg=msg)

class UserAlreadyExistsError(ProvisioningApiError):

  """ Exception raised on any API method attempting to add a user
  or alias that already exists, or renaming an account to a name that
  already exists.
  """

  def __init__(self, user):
    ProvisioningApiError.__init__(self, reason='User already exists', msg=user)

class ObjectDoesNotExistError(ProvisioningApiError):
  """ Exception raised on any API method attempting to access a user,
  alias, mailing list, or any object that does not exist.
  """
  def __init__(self, msg):
    ProvisioningApiError.__init__(self, reason='Object does not exist', msg=msg)

class InvalidDataError(ProvisioningApiError):
  """ Exception raised on any API method attempting to use characters
  that are not allowed.
  """
  def __init__(self, msg):
    ProvisioningApiError.__init__(self, reason='Invalid character', msg=msg)
