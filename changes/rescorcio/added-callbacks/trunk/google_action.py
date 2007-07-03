#!/usr/bin/python2.4
#
# Copyright 2006 Google, Inc.
# All Rights Reserved

""" Contains superclass for all "GoogleActions"

 GoogleAction: the superclass

** Consult <TBD> for overall documentation on this package.
"""


import provisioning
import provisioning_errs


class GoogleAction(object):

  """ Superclass for all "Google Actions", i.e. the class that knows what
  to do to the Google Apps for Your Domain domain
  for an "added" or "exited" (or whatever) user.
  The class should normally not perform actions on the UserDB or LDAP, but should
  instead rely on the handler on the other end of the google_result_queue
  to do that. This permits differing numbers of threads for the two types
  of activity:  (1) talking to Google, and (2) maintaining local databases.
  """
  def __init__(self, api, result_queue, thread_stats, **moreargs):
    """ Constructor.
    Args:
      api: a google.appsforyourdomain.provisioning.API object
      result_queue:  a google_result_queue.GoogleResultQueue
       object
    """
    self.dn = None
    self.attrs = None
    self._api = api
    self._result_queue = result_queue
    self._thread_stats = thread_stats
    super(GoogleAction, self).__init__(api=api,
                                    result_queue=result_queue,
                                     **moreargs)

  def Handle(self, dn, attrs):
    """ Handle a single user with Distinguished Name 'dn' and attributes
    'attrs'
    This is an abstract method; subclasses MUST override.
    Args:
      dn: distinguished name of the user
      attrs: dictionary of all the user's attributes
    """
    raise RuntimeError('Unimplemented')

if __name__ == '__main__':
  pass
