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

""" Default action for checking status on a user

  GoogleActCheck: the class implementing the default action
"""

import google_action
import logging
from google.appsforyourdomain import provisioning
from google.appsforyourdomain import provisioning_errs


class CheckUserGoogleAcion(google_action.GoogleAction):

  """ The default "GoogleAct" for checking status on a user.
  Args:
    dn: distinguished name of the user
    attrs: dictionary of all the user's attributes
    api: a google.appsforyourdomain.provisioning.API object
    result_queue
  """
  def __init__(self, api, result_queue, **moreargs):
    super(CheckUserGoogleAction, self).__init__(api=api,
                                    result_queue=result_queue,
                                    **moreargs)
    self.dn = None # public; caller can change
    self.attrs = None # public
    self._api = api
    self._result_queue = result_queue
    logging.debug('instantiated GoogleActCheck')

  def Handle(self, dn, attrs):
    """ Override of superclass.Handle() method
    Args:
      dn: distinguished name of the user
      attrs: dictionary of all the user's attributes
    """
    self.dn = dn
    self.attrs = attrs
    try:
      result = self._api.RetrieveAccount(self.attrs['GoogleUsername'])
      # report success
      logging.debug('Checked for and found %s' % self.attrs['GoogleUsername'])
      self._result_queue.PutResult(self.dn, 'checked', None, result)
    except provisioning_errs.ObjectDoesNotExistError, e:
      # not a failure
      logging.info('Checked for and failed to find %s' % self.attrs['GoogleUsername'])
      self._result_queue.PutResult(self.dn, 'checked')
    except provisioning_errs.ProvisioningApiError, e:
      # report failure
      logging.error('error: %s' % str(e))
      self._result_queue.PutResult(self.dn, 'checked', str(e))

if __name__ == '__main__':
  pass
