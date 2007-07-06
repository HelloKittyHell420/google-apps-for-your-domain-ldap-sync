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

""" Main code for controlling the synchronization of users with Google

class SyncGoogle:  the class that does it

"""


import added_user_google_action
import exited_user_google_action
import updated_user_google_action
import renamed_user_google_action
import logging
import messages
import Queue
import threading
import google_result_handler
import google_result_queue
import utils
from google.appsforyourdomain import provisioning
from google.appsforyourdomain import provisioning_errs
from google.appsforyourdomain import provisioning_auth
from google.appsforyourdomain import provisioning_backend

# globals governing the threading system
QUEUE_TIMEOUT = 20
THREAD_JOIN_TIMEOUT = 120
STAT_UPDATE_TIMEOUT = 0.2

class ThreadStats(object):

  """ Object for communicating between a "worker thread" and the main
  program, in a thread-safe way.  The worker threads can post their current
  status such that it can be aggregated and reported back to the user while
  the threads are still busy (as well as when they're done).
  """

  # all legal stats which can be accumulated
  stat_names = frozenset(('adds', 'exits', 'renames', 'updates',
                          'add_fails', 'exit_fails', 'rename_fails',
                          'update_fails',
                          'authentications'))
  def __init__(self):
    self._condition = threading.Condition()
    self._stats = {}
    for stat in self.stat_names:
      self._stats[stat] = 0

  def IncrementStat(self, stat, inc):
    """ increment a stat in a thread-safe way. Do not wait more than
    STAT_UPDATE_TIMEOUT to get access to the object.
    Args:
      stat: name of the stat, which must be one of the stat_names set.
      inc: integer to be added to the stat.  It can be negative, but
          the underlying number if never allowed to become negative.
    """
    self._condition.acquire()
    self._condition.wait(STAT_UPDATE_TIMEOUT)
    if stat not in self.stat_names:
      logging.error('Invalid stat name: %s' % stat)
    else:
      self._stats[stat] += inc
      if self._stats[stat] < 0:
        logging.error('%s prevented from going negative' % stat)
        self._stats[stat] = 0;
    self._condition.notifyAll()
    self._condition.release()

  def GetStats(self):
    """ obtain a copy of the current stats in a thread-safe way.
    """
    self._condition.acquire()
    self._condition.wait(STAT_UPDATE_TIMEOUT)
    copy_stats = self._stats.copy()
    self._condition.notifyAll()
    self._condition.release()
    return copy_stats

class SyncGoogle(utils.Configurable):

  """ Synchronizes the UserDB with Google Apps for Your Domain.
  The 'admin', 'password', and 'domain' properties must be set, either
  by their being in the config file 'config', or via direct attribute
  setting.

  This module doesn't contain any of the actual calls to Google (except
  for the FetchOneUser() method), beyond authenticating to Google. This
  is a deliberate choice, to make it easy for a developer to do something
  different or additional when a user is added or exited, e.g. add the
  user to mailing lists or create/remove aliases.  See google_action.py
  and the <action name>_user_google_action.py modules for details.

  If you subclass any of those modules, you must change the reference to them
  in the code reproduced below:

    # here is where we could allow other actions to be substituted:
    if action == 'added':
      gclass = added_user_google_action.AddedUserGoogleAction
    elif action == 'exited':
      gclass = exited_user_google_action.ExitedUserGoogleAction
    elif action == 'renamed':
      gclass = renamed_user_google_action.RenamedUserGoogleAction
    elif action == 'updated':
      gclass = updated_user_google_action.UpdatedUserGoogleAction

  For the same reason, this module does not do anything application-
  specific with the UserDB object after a Google operation succeeds or
  fails.  There IS a module, google_result_handler.py, that attempts to do
  something reasonable, but again, feel free to subclass it, and then
  change this line below:

      # create thread(s) to read the requests coming back
    reader = StatusReader(queue_result, self._users,
                          google_result_handler.GoogleResultHandler)

  to reference your new class.

  SyncGoogle uses multiple threads to talk to Google. This is controlled
  by the 'max_threads" config parameter, and the 'items_per_thread'
  parameter (not exposed via the config file right now).  The formula
  can be seen in _ComputeThreadCount().
  """
  config_parms = {'admin': messages.MSG_SYNC_GOOGLE_ADMIN,
                  'password': messages.MSG_SYNC_GOOGLE_PASSWORD,
                  'domain': messages.MSG_SYNC_GOOGLE_DOMAIN,
                  'max_threads': messages.MSG_SYNC_GOOGLE_MAX_THREADS,
                  'google_operations': messages.MSG_SYNC_GOOGLE_ALLOWED,
                  'endpoint': messages.MSG_SYNC_GOOGLE_ENDPOINT,
                  'authurl': messages.MSG_SYNC_GOOGLE_AUTH_URL
                  }

  def __init__(self, users, config, **moreargs):
    """ Constructor
    Args:
      users: an instance of the UserDB object
      config: an instance of ConfigParser, which must have been
        initialized from its file(s) already.
    """
    self.__admin = None
    self.__password = None
    self.__domain = None
    self.__endpoint = None
    self.__authurl = None
    self.__max_threads = 10
    self.__items_per_thread = 32
    self.__google_operations = None
    self._users = users
    self.queue_google = None
    self.queue_result = None
    self._apis = None
    self._gworkers = None
    super(SyncGoogle, self).__init__(config=config,
                                     config_parms=self.config_parms,
                                     **moreargs)

  def _GetEndpoint(self):
    return self.__endpoint

  def __GetEndpoint(self):
    return self._GetEndpoint()

  def _SetEndpoint(self, attr):
    self.__endpoint = attr
    provisioning_backend.BASEURL = attr

  def __SetEndpoint(self, attr):
    self._SetEndpoint(attr)

  endpoint = property(__GetEndpoint, __SetEndpoint, None,
                         """The provisioning API host to use""")

  def _GetAuthUrl(self):
    return self.__authurl

  def __GetAuthUrl(self):
    return self._GetAuthUrl()

  def _SetAuthUrl(self, attr):
    self.__authurl = attr
    provisioning_auth.AUTH_URL = attr

  def __SetAuthUrl(self, attr):
    self._SetAuthUrl(attr)

  authurl = property(__GetAuthUrl, __SetAuthUrl, None,
                         """The Auth URL to use""")

  # property getters & setters & overhead
  def _GetMaxThreads(self):
    return self.__max_threads

  def __GetMaxThreads(self):
    return self._GetMaxThreads()

  def _SetMaxThreads(self, attr):
    self.__max_threads = attr

  def __SetMaxThreads(self, attr):
    self._SetMaxThreads(attr)

  max_threads = property(__GetMaxThreads, __SetMaxThreads, None,
       """The max number of threads to be used for talking to Google.
If not specified, a best judgment is made, according to the volume
of work. If set to 1, only one thread will be used.
"""
   )

  def _GetItemsPerThread(self):
    return self.__items_per_thread

  def __GetItemsPerThread(self):
    return self._GetItemsPerThread()

  def _SetItemsPerThread(self, attr):
    self.__items_per_thread = attr

  def __SetItemsPerThread(self, attr):
    self._SetItemsPerThread(attr)

  items_per_thread = property(__GetItemsPerThread, __SetItemsPerThread, None,
       """The workload per thread (adds, renames, etc.)  This is used in
computing the number of threads to use.  Generally, # threads =
# items of work to perform / items_per_thread (and then capped at
max_threads)
"""
   )

  def _GetAdmin(self):
    return self.__admin

  def __GetAdmin(self):
    return self._GetAdmin()

  def _SetAdmin(self, attr):
    self.__admin = attr

  def __SetAdmin(self, attr):
    self._SetAdmin(attr)

  admin = property(__GetAdmin, __SetAdmin, None, "the administrator")

  def _GetPassword(self):
    return self.__password

  def __GetPassword(self):
    return self._GetPassword()

  def _SetPassword(self, attr):
    self.__password = attr

  def __SetPassword(self, attr):
    self._SetPassword(attr)

  password = property(__GetPassword, __SetPassword, None,
                      "administrator's password")

  def _GetDomain(self):
    return self.__domain

  def __GetDomain(self):
    return self._GetDomain()

  def _SetDomain(self, attr):
    self.__domain = attr

  def __SetDomain(self, attr):
    self._SetDomain(attr)

  domain = property(__GetDomain, __SetDomain, None,
                    "The Google Apps for Your Domain hosted domain")

  def _GetGoogleOperations(self):
    if not self.__google_operations:
      return ['added', 'exited', 'updated', 'renamed']
    else:
      return self.__google_operations

  def __GetGoogleOperations(self):
    return self._GetGoogleOperations()

  def _SetGoogleOperations(self, attrs):
    if type(attrs) is str:
      attrs = attrs.split(',') 
    try:
      for attr in attrs: # triggers TypeError if not a list
        if attr not in self._users.google_action_vals:
          logging.error('%s not a valid action name' % attr)
          return
    except TypeError:
      logging.exception('invalid format; must be a list: ' % str(attrs))
      return
    self.__google_operations = attrs

  def __SetGoogleOperations(self, attr):
    self._SetGoogleOperations(attr)

  google_operations = property(__GetGoogleOperations, __SetGoogleOperations, 
                               None,
                               ("The actions permitted to be performed by "
                                "this module."))

  def SetConfigVar(self, attr, val):
    """ Overrides: superclass (Configurable) method to enforce more
    validation.
    Args:
      attr: name of config var
      val: value to be assigned to it
    """
    if not attr in self.config_parms:
      return messages.msg(messages.ERR_NO_SUCH_ATTR, attr)
    #if attr == 'google_operations':
    #  return messages.ERR_NO_SET_OPERATIONS
    try:
      if attr == 'max_threads':
        try:
          self.max_threads = int(val)
        except ValueError:
          return messages.msg(messages.ERR_ENTER_NUMBER, val)
      else:
        setattr(self, attr, val)
    except ValueError:
      return messages.msg(messages.ERR_INVALID_VALUE, attr)

  def FetchOneUser(self, username):
    """ Special-purpose routine to query Google for status of a single
    user's account.
    Args:
      username: the GoogleUsername of the user
    Return:
      (see doc for provisioning.RetrieveAccount)
    Raises:
      None (the ObjectDoesNotExistError is caught)
    """
    self._config.TestConfig(self, ['admin', 'password', 'domain'])
    try:
      api = provisioning.API(self.admin,
                             self.password,
                             self.domain)
      return api.RetrieveAccount(username)
    except provisioning_errs.ProvisioningApiError, e:
      logging.debug(str(e))
      return None

  def TestConnectivity(self):
    """ Make sure we CAN connect to Google with these parameters. Saves
    spawning a whole bunch of threads that'll all just fail.
    Return:
      String: if error, this is the string-ified exception that was
      caught.  else None if successful
    """
    try:
      self._config.TestConfig(self, ['admin', 'password', 'domain'])
      api = provisioning.API(self.admin,
                             self.password,
                             self.domain)
      del api
      return None
    except provisioning_errs.AuthenticationError, e:
      return str(e)
    except utils.ConfigError, e:
      return str(e)

  def _ComputeThreadCount(self, item_count):
    """ for a given workload, compute the number of threads to launch
    Args:
      item_count: number of users to be handled
    Returns:
      number of threads
    """
    count = min(item_count / self.items_per_thread, self.max_threads)
    if count < 1:
      count = 1
    return count

  def _Abort(self):
    """ Safely cancels an ongoing sync operation. Removes all entries from both
    queue_google and queue_result.
    This is called when the user presses the interrupt key
    (usually control-C).
    """
    if self._apis is not null:
      del self._apis

  def DoAdds(self, dn_restrict=None):
    """ Go through the UserDB and process all the 'added' users.
    See DoAction() for more details.
    Args:
      dn_restrict: if supplied, restricts the users to just the DN
    """
    return self.DoAction('added', dn_restrict)

  def DoDeletes(self, dn_restrict=None):
    """ Go through the UserDB and process all the 'exited' users.
    See DoAction() for more details.
    Args:
      dn_restrict: if supplied, restricts the users to just the DN
    """
    return self.DoAction('exited', dn_restrict)

  def DoRenames(self, dn_restrict=None):
    """ Go through the UserDB and process all the 'renamed' users.
    See DoAction() for more details.
    Args:
      dn_restrict: if supplied, restricts the users to just the DN
    """
    return self.DoAction('renamed', dn_restrict)

  def DoUpdates(self, dn_restrict=None):
    """ Go through the UserDB and process all the 'updated' users.
    See DoAction() for more details.
    Args:
      dn_restrict: if supplied, restricts the users to just the DN
    """
    return self.DoAction('updated', dn_restrict)

  def DoAction(self, action, dn_restrict=None):
    """ For each user for which the Google action is 'action'
    handle it
    Args:
      action: the action items from self.users to pull out and do
      dn_restrict: if non-null, must be a DN which is to be the sole
      target
    Return :
      err: errors, if any
      count of successes
      count of failures
    Side-effects :
      Each user's record is updated with the results, assuming
      the default google_result_handler.py is used.
    Notes:
      Be sure to do TestConnectivity() before doing this
    """

    # count up the users, and figure out how many threads to spin up
    if dn_restrict:
      if not self._users.LookupDN(dn_restrict):
        logging.error('%s not in the user list' % dn_restrict)
      item_count = 1
    else:
      item_count = self._users.UserCount('meta-Google-action', action)

    logging.debug('Counted %d users to be %s' % (item_count, action))
    if not item_count:
      return

    # make sure we have the configuration items we need:
    self._config.TestConfig(self, ['admin', 'password', 'domain'])
    self.queue_google = Queue.Queue(item_count)
    self.queue_result = google_result_queue.GoogleResultQueue(item_count)
    thread_count = self._ComputeThreadCount(item_count)
    logging.debug('forking %d threads' % thread_count)

    # establish the ThreadStats object:
    self.thread_stats = ThreadStats()

    try:
      # create N API objects first, since that's what's most
      # likely to fail:
      self._apis = []
      errs = None
      for ix in xrange(thread_count):
        try:
          api = provisioning.API(self.admin, self.password,
                                 self.domain)
          self.thread_stats.IncrementStat('authentications', 1)
        except provisioning_errs.ProvisioningApiError, e:
          errs = str(e)
          logging.error(errs)
          break
        self._apis.append(api)

      # if we had errors creating the api objects, kill whatever
      # ones we succeeded at, and exit
      if errs:
        for ix in len(self._apis):
          del self._apis[ix]
        return self.thread_stats.GetStats()

      # create the actual threads to read requests
      self._gworkers = []

      # here is where different subclasses of GoogleAction would be substituted:
      if action == 'added':
        self.gclass = added_user_google_action.AddedUserGoogleAction
      elif action == 'exited':
        self.gclass = exited_user_google_action.ExitedUserGoogleAction
      elif action == 'renamed':
        self.gclass = renamed_user_google_action.RenamedUserGoogleAction
      elif action == 'updated':
        self.gclass = updated_user_google_action.UpdatedUserGoogleAction
      else:
        raise RuntimeError('invalid action: %s' % action)

      # actually launch the worker threads:
      for ix in xrange(thread_count):
        gworker = Gworker(self._apis[ix], self)
        gworker.setName('%s-%d' % (action, ix))
        self._gworkers.append(gworker)
        gworker.start()

      # create thread(s) to read the requests coming back
      self._reader = StatusReader(self.queue_result, self._users,
                                  google_result_handler.GoogleResultHandler)
      self._reader.start()
      logging.debug('done creating threads')

      # stuff the queue that the worker threads are reading from:
      if dn_restrict:
        dns = [dn_restrict]
      else:
        dns = self._users.UserDNs('meta-Google-action', action)
      for dn in dns:
        attrs = self._users.LookupDN(dn)
        logging.debug('queueing %s' % dn)
        self.queue_google.put((dn, attrs))

      # wait for all the threads to terminate
      for gworker in self._gworkers:
        gworker.join(THREAD_JOIN_TIMEOUT)
        if gworker.isAlive():
          logging.error('failed to join thread \'%s\'' % gworker.getName())
        else:
          logging.debug('joined thread \'%s\'' % gworker.getName())

      # join the "self._reader" thread
      self._reader.join()
      if self._reader.isAlive():
        logging.error('failed to join thread \'%s\'' % self._reader.getName())
      else:
        logging.debug('joined thread \'%s\'' % self._reader.getName())
    except KeyboardInterrupt:
      logging.error('Interrupted, cleaning up ...')
      self._Abort()
      logging.error('Done')
      pass
    return self.thread_stats.GetStats()


class Gworker(threading.Thread):

  """ a single thread that consumes users from a queue. "Consuming"
  in this case means adding them to Google Apps for Your Domain,
  locking their account, or whatever the 'handleClass' class does.
  This is where the <action>GoogleAction classes are called.
  """
  def __init__(self, api, sync_google):
    """ Constructor.
    Args:
      api: instance of google.appsforyourdomain.provisioning.API
      (which means the caller must have already authenticated with
      Google)
      sync_google: instance of SyncGoogle object containing
        queueIn: a queue for reading
        gclass: a new-style Class object, which must be a subclass of
          GoogleAct
        thread_stats: an object of class ThreadStats, to be used for
          accumulating statistics while we're running
    """
    threading.Thread.__init__(self)
    self._queueIn = sync_google.queue_google
    self._queueOut = sync_google.queue_result
    self._timeout = QUEUE_TIMEOUT
    self._api = api
    self._handleClass = sync_google.gclass
    self._handler = sync_google.gclass(api, self._queueOut, 
                                       sync_google.thread_stats,
                                       vars=sync_google)

  def run(self):
    """ Starts the thread. This will keep reading the queue until it's
    empty and then return.
    """
    logging.debug('thread %s started' % self.getName())
    while True:
      try:
        item = self._queueIn.get(block=True, timeout=self._timeout)
        (dn, attrs) = item
        self._handler.Handle(dn, attrs)
      except Queue.Empty:
        break

class StatusReader(threading.Thread):

  """ An object that sits on the end of the queue with status results
  coming back, e.g. "added user X" or "failed to rename user Y"
  """
  def __init__(self, queue, userdb, handle_class, timeout=QUEUE_TIMEOUT):
    """ Constructor
    Args:
      queue: an instance of google_result_queue.GoogleResultQueue
      userdb: an instance of userdb.UserDB
      handle_class: class to instantiate to handle results (note this
        is a class variable, not an instance of the class). This must
        be a new-style Class object and a subclass of GoogleResultHandler
      timeout: time, in seconds, to wait for queue results
    """
    threading.Thread.__init__(self)
    self._queue = queue
    self._userdb = userdb
    self._handle_class = handle_class
    self._handler = handle_class(userdb)
    self._timeout = timeout

  def run(self):
    """ Starts the thread
    """
    logging.debug('thread %s started' % self.getName())
    while True:
      try:
        (dn, act, failure, obj) = self._queue.get(block=True,
                                                  timeout=self._timeout)
        self._handler.Handle(dn, act, failure, obj)
      except Queue.Empty:
        break

if __name__ == '__main__':
  pass
