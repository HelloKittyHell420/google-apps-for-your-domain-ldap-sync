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

"""

  GoogleResultQueue: queue for results from GoogleAction classes

** Consult <TBD> for overall documentation on this package.
"""

import logging
import Queue

class GoogleResultQueue(Queue.Queue):

  """ A Queue for the results of GoogleAction operations. The only
  difference from the superclass is that the PutResult()/GetResult()
  methods specify the type of objects on the queue.
  """

  def PutResult(self, dn, action, failure=None, object=None,
          block=None, timeout=None):
    """ Wrapper around the Queue.put() method, so as to specify
    the objects on the queue.
    Args:
      dn: distinguished name of the user which the GoogleAction
        processed
      action: name of the action processed, one of
        userdb.UserDB.google_action_vals
      failure: text message detailing the failure, or None if
        successful
      object: additional information, if any, passed back by the
        GoogleAction handler
      block, timeout: as described in Queue.put() method documentation
    Raises:
      Full, as described in Queue.put() method documentation
    """
    self.put((dn, action, failure, object), block, timeout)

  def GetResult(self, block=None, timeout=None):
    """ Wrapper around the Queue.get() method
    Args:
      block, timeout: as described in Queue.get() method documentation
    Return:
      tuple of (dn, action, failure, object) as described above for
        PutResult().  All are guaranteed to be present, even if None
    Raises:
      Empty, as described in Queue.get() method documentation
    """
    return self.get(block, timeout)

if __name__ == '__main__':
  pass
