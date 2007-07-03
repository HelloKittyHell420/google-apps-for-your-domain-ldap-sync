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
# Author: Robert Escorcio

""" Callbacks for setting Google* attributes based on ldap attributes. 

This is where you would put any hooks into XML-RPC or SOAP calls to support
setting these attributes via another language.  The idea is to add any
SOAP calls to a web server implemented in the language of your choice.
"""

# Original author: Steve Atwell
def NameSplit(given_name, surname, display_name):
  """ Formulate the preferred first and last names of a user from display_name.

  Args:
    given_name - string containing the person's legal name
    surname - string containing the person's legal last name
    display_name - string containing the name the user likes to be known as.

  Returns
    a tuple containing the first and last names that should be used in GAFYD.
  """
  if '%s %s' % (given_name, surname) == display_name:
    return (given_name, surname)

  pieces = display_name.split()
  num_pieces = len(pieces)

  # We need two pieces, so displayName isn't going to work
  if num_pieces < 2:
    return (given_name, surname)

  # Trivial split
  if num_pieces == 2:
    return (pieces[0], pieces[1])

  # If there are 3 or more pieces, things get complicated.  This is
  # where the magic happens
  if num_pieces >= 3:
    surname_pieces = surname.split()
    given_name_pieces = given_name.split()
    if surname_pieces == pieces[-len(surname_pieces):]:
      split_point = num_pieces - len(surname_pieces)
    elif given_name_pieces == pieces[:len(given_name_pieces)]:
      split_point = len(given_name_pieces)
    else:
      # guess; assume last name in displayName is the same length as sn
      split_point = num_pieces - len(surname_pieces)
    
    firstname = ' '.join(pieces[:split_point])
    lastname = ' '.join(pieces[-(num_pieces-split_point):])
    return (firstname, lastname)

class UserTransformationRule(object):
  """Defines a rule that maps ldap attributes to Google Apps."""

  def MeetsPrereqs(self, ldap):
    """ Prerequisits are met for any of the methods in the class to be called.

    Args:
      ldap - a dict containing attribute, value pairs from ldap

    Returns
      True if the prereqs are met
    """
    return 'displayName' in ldap

  def GoogleUsername(self, ldap):
    """ Callback for GoogleUsername.

    Args:
      ldap - a dict containing attribute, value pairs from ldap

    Returns
      The value to set GoogleUsername to
    """
    if 'mail' in ldap:               # ldap or AD users with mail
      mail = ldap['mail']
      if mail.find('@') > 0:
        return mail[:mail.find('@')]
    if 'uid' in ldap:                # ldap users without mail
      return ldap['uid']
    if 'sAMAccountName' in ldap:     # AD users without mail 
      return ldap['sAMAccountName']
    return None                      # okay I give up

  def GoogleFirstName(self, ldap):
    """ Callback for GoogleFirstname.

    Args:
      ldap - a dict containing attribute, value pairs from ldap

    Returns
      The value to set GoogleFirstname to
    """
    return NameSplit(ldap['givenName'], ldap['sn'], ldap['displayName'])[0]

  def GoogleLastName(self, ldap):
    """ Callback for GoogleLastname.

    Args:
      ldap - a dict containing attribute, value pairs from ldap

    Returns
      The value to set GoogleLastname to
    """
    return NameSplit(ldap['givenName'], ldap['sn'], ldap['displayName'])[1]

  def GooglePassword(self, ldap):
    """ Callback for GooglePassword.

    Args:
      ldap - a dict containing attribute, value pairs from ldap

    Returns
      The value to set GooglePassword to
    """
    return None

  def _TransformAttr(self, callback_name, attrs):
    """ Return the value returned by the callback function when passed attrs.

    Args:
      callback_name - a string representing one of the Google* callback methods.
      attrs - the argument to pass to the callback function

    Returns:
      A string containing the Google attribute to use.
    """
    try:
      r = eval('self.%s(attrs)' % callback_name)
      return r
    except NameError:
      return attrs[callback_name]

  def Callbacks(self):
    """ Return a list of all callback function names.

    Returns:
      a list of all callback function names.
    """
    return [attr + "Callback" for attr in self.google_attributes]

  def Mapping(self, attrs):
    """ Return a dict containing callback function name, value for attrs.

    Args:
      attrs - a dict containing all ldap attributes that will be passed to
        callback functions.

    Returns
      A dict containing callback function name, value pairs
    """
    mappings = {}
    for attr in self.google_attributes:
      mappings[attr + 'Callback'] = self._TransformAttr(attr, attrs)
    return mappings

  def __init__(self):
    self.google_attributes = ['GoogleUsername', 'GoogleFirstName',
                              'GoogleLastName', 'GooglePassword']

