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

""" Default action for users who've been added.

  AddedUserGoogleAction: the class implementing the default action

** Consult <TBD> for overall documentation on this package.
"""

import google_action
import logging
import updated_user_google_action
from google.appsforyourdomain import provisioning
from google.appsforyourdomain import provisioning_errs


class AddedUserGoogleAction(google_action.GoogleAction):

  """ The default GoogleAction for users who've been added. This object
  does a CreateAccountWithEmail on the user,
  and queues a message back on the GoogleResultQueue.
  """
  def __init__(self, api, result_queue, thread_stats, **moreargs):
    """ Constructor
    Args:
      api: a google.appsforyourdomain.provisioning.API object
      result_queue:  a google_result_queue.GoogleResultQueue object,
        for writing results back to a status handler
    """
    super(AddedUserGoogleAction, self).__init__(api=api,
                                result_queue=result_queue,
                                thread_stats=thread_stats,
                                **moreargs)
    self.dn = None # public; caller can change
    self.attrs = None # public
    self._api = api
    self._result_queue = result_queue

  def Handle(self, dn, attrs):
    """ Override of superclass.Handle() method.
    Args:
      dn: distinguished name of the user, usually from UserDB
      attrs: dictionary of all the user's attributes
    """
    self.dn = dn
    self.attrs = attrs
    try:
      logging.debug('about to CreateAccount for %s' % 
                    self.attrs['GoogleUsername'])
      moreargs = {}
      if 'GoogleQuota' in self.attrs:
        moreargs['quota'] = self.attrs['GoogleQuota']
      self._api.CreateAccountWithEmail(self.attrs['GoogleFirstName'],
          self.attrs['GoogleLastName'], self.attrs['GooglePassword'],
          self.attrs['GoogleUsername'], **moreargs)
      self._result_queue.PutResult(self.dn, 'added', None, self.attrs)
      self._thread_stats.IncrementStat('adds', 1)
    except provisioning_errs.ProvisioningApiError, e:
      # report failure
      if str(e).find('UserAlreadyExists') >= 0:
        # TODO(rescorcio): what about DeletedUserExists errors?

        logging.info(
           'Attempted add of existing user.  Syncing attrs instead. %s' %
           str(e))

        # Make sure the account is unlocked if it is a valid user.
        # Note: users are exited in only one of two ways:
        # 1) the user matches an exit filter
        # 2) the user disappeared from the ldap search filter that lists all 
        #    users
        # This method is never called on an account in state #1.  
        # Consequently, we can safely unlock this account since
        # it must have reappeared in our ldap query result (hence rebecame a 
        # user) in order to be added.
        logging.info('Making sure this account unlocked: %s' %
            self.attrs['GoogleUsername'])
        self._api.UnlockAccount(self.attrs['GoogleUsername'])

        # Make sure that the user's attributes are synced because there is 
        # no other time that this will get done.
        try:
          updated_user_google_action.Update(self._api, attrs)
        except provisioning_errs.ProvisioningApiError, e:
          logging.error('error during update: %s' % str(e)) 
          self._thread_stats.IncrementStat('add_fails', 1)
          self._result_queue.PutResult(self.dn, 'added', str(e))
          return

        # trying to add a user that is already there is not an error
        self._result_queue.PutResult(self.dn, 'added')

      logging.error('error: %s' % str(e))
      self._thread_stats.IncrementStat('add_fails', 1)
      self._result_queue.PutResult(self.dn, 'added', str(e))
      return

if __name__ == '__main__':
  pass
