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

""" Default GoogleAction for users who've exited

  ExitedUserGoogleAction: the class implementing the default action

** Consult <TBD> for overall documentation on this package.
"""

import google_action
import google_result_queue
import logging
from google.appsforyourdomain import provisioning
from google.appsforyourdomain import provisioning_errs


class ExitedUserGoogleAction(google_action.GoogleAction):

  """ The default "GoogleAction" for users who've exited (quit,
  been terminated, retired, died, etc.)
  This object does a LockAccount on the user and queues results
  on the GoogleResultQueue object.
  """
  def __init__(self, api, result_queue, thread_stats, **moreargs):
    """
    Args:
      api: a google.appsforyourdomain.provisioning.API object
      result_queue:  a google_result_queue.GoogleResultQueue object,
        for writing results back to a status handler
    """
    super(ExitedUserGoogleAction, self).__init__(api=api,
                                    result_queue=result_queue,
                                    thread_stats=thread_stats,
                                    **moreargs)
    self._api = api
    self._result_queue = result_queue

  def Handle(self, dn, attrs):
    """ Override of superclass.Handle() method
    Args:
      dn: distinguished name of the user
      attrs: dictionary of all the user's attributes
    """
    self.dn = dn
    self.attrs = attrs
    try:
      logging.debug('about to LockAccount for %s' % \
                    self.attrs['GoogleUsername'])
      self._api.LockAccount(self.attrs['GoogleUsername'])
      # report success
      logging.debug('locked %s' % self.attrs['GoogleUsername'])
      self._thread_stats.IncrementStat('exits', 1)
      self._result_queue.PutResult(self.dn, 'exited')
    except provisioning_errs.ProvisioningApiError, e:
      # report failure
      logging.error('error: %s' % str(e))
      self._thread_stats.IncrementStat('exit_fails', 1)
      self._result_queue.PutResult(self.dn, 'exited', str(e))

if __name__ == '__main__':
  pass
