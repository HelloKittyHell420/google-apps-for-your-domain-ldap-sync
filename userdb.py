#!/usr/bin/python2.4
#
# Copyright 2006, 2007 Google, Inc.
# All Rights Reserved

""" Contains the UserDB, or user database.  The heart of the Sync Tool.

Methods not tied to a UserDB instance:
  GetTextFromNodeList: part of XML parsing code
  AttrListCompare: for comparing two UserDB records (which are
    really just dictionaries)

  5 routines which are only used in the testFilter command, to
    suggest to the user which LDAP attributes should be used
    for various things:
  SuggestGoogleUsername
  SuggestGoogleLastName
  SuggestGoogleFirstName
  SuggestGooglePassword
  SuggestTimestamp

class UserDB: the main class
"""

import codecs
import csv
import logging
import messages
import os
import random
import re
import threading
import time
import traceback
import types
import utils
import xml.dom
import xml.dom.minidom
from xml.sax._exceptions import *


def GetText(node_list):

  """ Collect the text from (possibly) multiple Text nodes inside an element,
  into a single string.

  Args:
    nodelist:  the list of children of a node in a DOM tree

  Returns:
    A string containing the concatenated contents, with leading and trailing
    whitespace removed.
  """

  rc = ""
  enc, dec = codecs.lookup('iso-8859-1')[:2]
  for node in node_list:
    if node.nodeType == node.TEXT_NODE:
      rc = rc + enc(node.data)[0]
  return rc.strip()

def GetTextFromNodeList(node_list):

  """ similar to the above, but handles the return value from
  a getElementsByTagName() call, which is itself a node list
  """
  if not node_list:
    return ""
  return GetText(node_list.item(0).childNodes)

def SuggestGoogleUsername(dictLower):

  """ Suggest an expression to serve as the GoogleUsername
  attribute
  Args:
    dictLower : dictionary mapping lower-case versions of
    the attrs to the real attr names
  Return: attribute name, or None if none looked suitable
  """
  attrs = dictLower.values()
  if "mail" in attrs:
    return "mail[:mail.find('@')]"

def SuggestGoogleLastName(dictLower):

  """ Suggest an expression to serve as the GoogleLastname
  attribute
  Args:
    dictLower : dictionary mapping lower-case versions of
      the attrs to the real attr names
  Return: attribute name, or None if none looked suitable
  """
  attrs = dictLower.values()
  if "sn" in attrs:
    return "sn"

def SuggestGoogleFirstName(dictLower):

  """ Suggest an expression to serve as the GoogleFirstName
  attribute
  Args:
    dictLower : dictionary mapping lower-case versions of
      the attrs to the real attr names
  Return: attribute name, or None if none looked suitable
  """
  attrs = dictLower.values()
  if "givenName" in attrs:
    return "givenName"

def SuggestGooglePassword(dictLower):
  """ Suggest an expression to serve as the GooglePassword
  attribute
  Args:
    dictLower : dictionary mapping lower-case versions of
      the attrs to the real attr names
  Return: attribute name, or None if none looked suitable
  """
  attrs = dictLower.values()
  if "password" in attrs:
    return "password"

def SuggestTimestamp(attrs):
  """ Suggest a "last updated" attribute to use for later sync'ing
  Return: attribute name, or None if none looked suitable
  """
  if attrs.count('modifyTimestamp'):
    return 'modifyTimestamp'
  elif attrs.count('whenChanged'):
    return 'whenChanged'

def SuggestPrimaryKey(attrs):
  """ Suggest a "primary key" attribute to use for detecting renames
  Return: attribute name, or None if none looked suitable
  """
  if attrs.count('entryUUID'):
    return 'entryUUID'

def AttrListCompare(attrList, first, second):
  """ Compare two user records (actually any dictionary) on a
  list of attribute names:
  Args:
    attrList: list of attribute names
    first: first record
    second: second record
  Return:
    -1 if first < second
    0  if equal
    1  if first > second
  Raises:
    RuntimeError: if any member of attrList is not present in both
    records
  """
  for attr in attrList:
    if attr not in first or attr not in second:
      raise RuntimeError('attr %s not present' % attr)
    val_first = first[attr]
    val_second = second[attr]
    if val_first < val_second:
      return -1
    elif val_first > val_second:
      return 1
  return 0


class UserDB(utils.Configurable):

  """ Canonical dictionary of users & their LDAP attributes. This is NOT
  identical to the data structure returned by the ldap package, and in
  fact, this module insulates callers from that structure, and lets them
  use an object with defined interfaces instead.

  A UserDB contains a dictionary, where the keys are the DNs
  (Distinguished Names), and the values are a dictionary of attribute
  name / value.  The UserDB also has other features,
  like a mapping of LDAP attributes to Google-required attributes.

  There are also "meta-attributes" maintained on users;  these are data
  not necessarily derived from LDAP. Examples are the "meta-Google-action"
  (the last LDAP action detected on this user and pending for
  Google), and the "last updated" time (when we last updated the user
  from LDAP).  The meta-attributes' names are all prefixed by "meta-".
  To make the namespace of meta-attributes at least slightly understandable,
  a meta-attribute's value is always set via a call to
  SetMetaAttribute() -- never directly.

  A UserDB can have a "primary key" (consult <TBD> for documentation). This
  significantly changes the operation of AnalyzeChangedUsers().

  UserDB has one thread-safe method for changing the 'meta-Google-*' attributes.
  This is intended for the sync_google module, since it can spawn multiple threads
  for talking to Google.

  ********************  Code documentation ********************************
  UserDB is the heart of the Sync Tool, with all the application
  logic having to do with users, some of which is unavoidably complex.  The code
  is divided into sections for readability, and within each section the
  methods are in alphabetical order.  The sections are:

   * Basic operations: getting the user count, looking up a user,
     managing the attribute list, etc. All are called from some other module,
     generally the "commands" module.

   * Bulk operations on users (merging, determining which users have been added,
     exited, renamed, or updated, etc.).

   * "Mapping", or creating the Google attributes from the LDAP attributes

   * Internal routines for file reading and writing

   * Private housekeeping routines

   * Miscellaneous code with no other obvious home

  """

  # needed for the Configurable superclass:
  config_parms = {'mapping': messages.MSG_USERDB_MAPPING,
                  'primary_key': messages.MSG_USERDB_PRIMARY_KEY,
                  'attrs': messages.MSG_USERDB_ATTRS,
                  'timestamp': messages.MSG_USERDB_TIMESTAMP}

  meta_attrs = frozenset(('meta-last-updated', 'meta-Google-action', \
                          'meta-Google-old-username'))

  # these are all the "Google actions" there are:
  google_action_vals = frozenset(('added', 'exited', 'updated',
                                  'renamed'))

  # all the Google variables which we can use to provision users:
  google_update_vals = frozenset(('GoogleFirstName','GoogleLastName',
                    'GooglePassword', 'GoogleUsername',
                    'GoogleApplyIPWhitelist'))

  # map of google_update_vals to the variables returned by
  # provisioning.RetrieveAccount():
  google_val_map = {'GoogleFirstName' : 'firstName',
                    'GoogleLastName' : 'lastName',
                    'GoogleUsername' : 'userName'}

  def __init__(self, config, users=None, **moreargs):
    """ Constructor
    Args:
      config: an instance of utils.Config, which must have already
        read its config file
      users: output of the ldap.search* routines.  This is one of the
        most common ways a UserDB is created:  from the ldap module's
        output (in ldap_ctxt.py)
    """
    self.attrs = set()
    self.timestamp = None
    self.primary_key = None

    # 'mapping' is the relationship of LDAP attributes to Google-required
    self.mapping = {'GoogleFirstName': None, 'GoogleLastName': None,
                    'GooglePassword': None, 'GoogleUsername': None,
                    'GoogleApplyIPWhitelist': False}

    super(UserDB, self).__init__(config=config,
                                 config_parms=self.config_parms,
                                 **moreargs)
    self._config = config
    self.db = {}

    # for thread-safe access from sync_google
    self._cond = threading.Condition()

    # if we do have a primary key, we need a lookup of key -> DN
    self.primary_key_lookup = {}
    if users:
      self._AddUsers(users)

  def SetConfigVar(self, attr, val):
    """ Overrides: Configurable.SetConfigVar
    Imposes some rules on which config vars can be set via the 'set'
    command, mainly for the multi-valued ones, whose syntax would be
    very difficult for users to get right (so there are special routines
    provided)
    """
    if not attr in self.config_parms:
      return messages.msg(messages.ERR_NO_SUCH_ATTR, attr)
    if attr == 'mapping':
      return messages.ERR_NO_SET_MAPPING
    elif attr == 'attrs':
      return messages.ERR_NO_SET_ATTRS
    else:
      try:
        setattr(self, attr, val)
      except ValueError:
        return messages.msg(messages.ERR_INVALID_VALUE, attr)

  """
  *********************************************************************
  Basic operations: getting the user count, looking up a user,
  managing the attribute list, etc.

  *********************************************************************
  """

  def AddAttribute(self, attr):

    """ add another attribute to the set we maintain (and which
    get retrieved in future LDAP calls, although that's not the
    responsibility of this module)
    Args:
     attr : attribute name
    """
    self.config_changed = True
    self.attrs.add(str(attr))  # eliminate Unicode strings

  def DeleteUser(self, dn):
    """ Delete a user.
    Args:
      dn: the user's DN
    """
    attrs = self.LookupDN(dn)
    if attrs:
      self._DeletePrimaryKey(attrs)
      del self.db[dn]

  def GetAttributeMinMax(self, attr, fmin=False):
    """ For a given attribute (e.g. meta-last-updated), get the
    (min / max) of it across the database.  Typically you'd use this to get
    the time the database was last sync'ed.
    Args:
      attr : attribute
      fmin : if true, the minimum is returned; else the max
    Return : the minimum or maximum value for the given attribute.  If
      the value can be made into a float, it is;  otherwise it's a string
    """
    val = None
    for (dn, attrs) in self.db.iteritems():
      new_val = attrs[attr]
      if not val:
        val = new_val
      else:
        if not fmin:
          if new_val > val:
            val = new_val
        else:
          if new_val < val:
            val = new_val
    try:
      if val:
        val = float(val)
    except ValueError:
      pass
    return val

  def GetAttributes(self):
    """ Returns a set of all the attributes defined for any user
    Returns:
      sorted list of attributes configured for this UserDB
    """
    lst = list(self.attrs)
    lst.sort()
    return lst

  def GetTimestamp(self):
    """
    Returns:
      the attribute to be used as the timestamp, or None if none was
      set
    """
    return self.timestamp

  def LookupAttrVal(self, attr, val):
    """ The slow & painful way of looking up a user.  This does a
    sequential search.  Intended mainly for the syncOneUser command.
    Args:
      attr: name of attribute
      val: value of 'attr' to be looked up
    Return:
      dns: list of DNs of the users who were found
    """
    dns = []
    for (dn, attrs) in self.db.iteritems():
      if attr in attrs:
        if attrs[attr].lower() == val.lower():
          dns.append(dn)
    return dns

  def LookupDN(self, dn):
    """ Lookup a user by DN.  This is a lower-case lookup, and all
    DNs are lower-cased before insertion.
    Args:
      dn: DN of the user
    Returns:
      dictionary of all the attributes for this user, or None if
      not found.
    """
    if dn not in self.db:
      return None
    return self.db[dn.lower()]

  def ReadDataFile(self, fname):
    """ Read in a saved file of users, either XML or CSV.
    Args:
      fname: name of the file, which must end in .xml or .csv
    Raises:
      IOError: if file can't be opened
      RuntimeError: if not an xml or csv file
    """
    (root, ext) = os.path.splitext(fname)
    lext = ext.lower()
    if lext != ".xml" and lext != ".csv":
      raise RuntimeError("Unrecognized file type: " + ext)
    if lext == ".csv":
      (added, excluded) = self._ReadCSVFile(fname)
    else:
      (added, excluded) = self._ReadXMLFile(fname)
    return (added, excluded)

  def RemoveAllAttributes(self):
    """ Zero out the set of attributes maintained by this UserDB.
    Usually you'd do this only on testFilter when the user has
    accepted our suggestions, and you're about to call AddAttribute
    a number of times.
    """
    self.attrs = set()

  def RemoveAttribute(self, attr):
    """ remove attribute from the set we maintain (and which
    get retrieved in future LDAP calls, although that's not the
    responsibility of this module).  Does not raise error if the attr
    is not in the set.

    This is a storage operation:  each user is visited and the
    attribute, if present, is deleted.
    Args:
      attr : attribute name
    Return : number of users with a non-null value for this
      attr (which were cleared)
    """

    self.config_changed = True
    try:
      self.attrs.remove(attr)
    except KeyError:
      return 0
    count = 0
    for (dn, attrs) in self.db.iteritems():
      if attr in attrs:
        del attrs[attr]
        count += 1

    # delete any mappings that require this attr
    for (gattr, expr) in self.mapping.iteritems():
      if expr:
        toks = expr.split(" ")
        if toks.count(attr):
          self.mapping[gattr] = None
    return count

  def SetGoogleAction(self, dn_arg, val):
    """ Set the intended Google action for a user
    (attribute = meta-Google-action)
    Args:
      dn_arg: DN of the user to be set
      val: value to set it to.  Must be one of the values of the
        class variable 'google_action_vals'
    """
    if val != None and val not in self.google_action_vals:
      raise RuntimeError("Invalid Google action value: %s" + str(val))
    dn = dn_arg.lower()
    if not dn in self.db:
      self.db[dn] = {"meta-Google-action":val}
    else:
      self.db[dn]["meta-Google-action"] = val

  def SetMetaAttribute(self, dn_arg, name, val):
    """ Set a meta-attr, i.e. those not found in LDAP or
    derived from those in LDAP, for a user
    Args:
      dn_arg: DN of the user to be set
      name: name of the meta-attribute to be set, which must be a
        member of the class variable 'meta_attrs'
      val: value to set it to
    """
    dn = dn_arg.lower()
    if name not in self.meta_attrs:
      raise RuntimeError("Invalid meta-attr: " + name)
    if not dn in self.db:
      self.db[dn] = {name:val}
    else:
      self.db[dn][name] = val

  def SetTimestamp(self, t):
    """ Set an attribute as the 'timestamp'
    args:
      t: an LDAP attribute, which will be added to the attrlist
        if not already there.
    """
    self.timestamp = t
    if t:
      self._UpdateAttrList([t])

  def UserCount(self, attr=None, val=None):
    """ return the # of DNs.  If attr & val are supplied,
    this is a filter-count operation.
    Args:
      attr: name of attribute to be filtered on
      val: filter value
    Returns:
      integer count of the users.
    """
    if not attr and not val:
      return len(self.db)
    count = 0
    for dn in self.db.iterkeys():
      attrs = self.db[dn]
      if attr not in attrs:
        continue
      if attrs[attr] == val:
        count += 1
    return count

  def UserDNs(self, attr=None, val=None):
    """ return the DNs of all users in the database.
    If attr & val are supplied, this is a filter operation.
    Args:
      attr: name of attribute to be filtered on
      val: filter value
    Returns:
      Unsorted list of the user DNs
    """
    if not attr and not val:
      return self.db.keys()
    keys = []
    for dn in self.db.iterkeys():
      attrs = self.db[dn]
      if attr not in attrs:
        continue
      if attrs[attr] == val:
        keys.append(dn)
    return keys

  def WriteDataFile(self, fname):

    """ Write to a file, either XML or CSV (and the extension must be one
    or the other)
    Args;
      fname: name of the file to write
    Return:
      set of attributes which couldn't be written out
    Raises:
      IOError: if the file couldn't be written
    """
    (root, ext) = os.path.splitext(fname)
    lext = ext.lower()
    if lext != ".xml" and lext != ".csv":
      raise RuntimeError("Unrecognized file type: " + ext)
    dns = self.UserDNs()
    dns.sort()
    if lext == ".xml":
      return self._WriteXMLFile(fname, dns)
    else:
      return self._WriteCSVFile(fname, dns)

  """
  *********************************************************************
  Bulk operations on users.  If you're looking for the down & dirty details
  on how we decide what constitutes an 'renamed' or an 'exited', this is
  the place.
  
  The algorithms are extensively commented.  If you change the code, please
  change the comments to match it.
  *********************************************************************
  """
  def AnalyzeChangedUsers(self, other_db):
    """ For a list of users passing some filter meaning "changed recently",
    analyze each as to whether it represents (a) a change to an
    existing user's parameters, or (b) a rename of the user's email name, or
    (c) a new user.  Return three lists accordingly.
    For (a) it's an update
    For (b) it's a rename
    For (c) it's an add

    Algorithm is as follows:
    if it's a new DN:
      if there is a PrimaryKey defined
        if the primary key of the entry matches that of an existing user
          if the GoogleUsername did not change
            if any other Google attr changed
              it's an update
            else
              it's a no-op (ignore it)
          else
            it's a rename
        else
          it's an add
      else  (no primary key defined)
        it's an add
    else (it's an existing DN)
      if the GoogleUsername has changed
        it's a rename
      else if ANY Google attribute has changed
        it's an update
      else
        ignore

    Args:
      other_db: another instance of UserDB, presumably created by
      an LdapContext.Search() call with a filter on "changed recently"
    Return:
      adds: list of dns that are additions to this UserDB
      mods: list of dns that appear to be modifications of
        users in this list
      renames: list of dns that require a rename of an existing user
    Not every DN in other_db need appear in one of these lists;  there can
    be a harmless update to some LDAP parameter, "harmless" meaning
    it doesn't require any updates to Google
    """

    adds = []
    mods = []
    renames = []
    for (dn, attrs) in other_db.db.iteritems():
      dn = dn.lower()
      if dn not in self.db:
        res = self._AnalyzeNewDN(dn, attrs)
        if res == 'added':
          adds.append(dn)
        elif res == 'updated':
          mods.append(dn)
        elif res == 'renamed':
          renames.append(dn)
      else: # an existing DN
        logging.debug('existing dn: %s' % dn)
        if attrs['GoogleUsername'] != self.db[dn]['GoogleUsername']:
          self.db[dn]['meta-Google-old-username'] = self.db[dn]['GoogleUsername']
          renames.append(dn)
        elif self._GoogleAttrsCompare(dn, attrs):
          mods.append(dn)
    return (adds, mods, renames)

  def _AnalyzeNewDN(self, dn_arg, attrs):
    """ See description of AnalyzeChangedUsers();  this handles the
    "if it's a new DN" part.
    Args:
      dn: DN of the new DN
      attrs: attrs of the new DN
    Return:
     'added', 'renamed', or 'updated' or None
    """
    dn = dn_arg.lower()
    if self.primary_key:
      dn = self._FindPrimaryKey(attrs)
      if dn:
        if self.db[dn]['GoogleUsername'] == attrs['GoogleUsername']:
          if self._GoogleAttrsCompare(dn, attrs):
            return 'updated'
          else:
            return None
        else:
          self.db[dn]['meta-Google-old-username'] = self.db[dn]['GoogleUsername']
          return 'renamed'
      else:
        return 'added'
    else: # no primary key
      return 'added'

  def FindDeletedUsers(self, new_db):
    """ Use this after getting a complete list of users who pass
    your filter; this will find the users in the database NOT in
    that list, which you'll presumably then mark for deletion from
    Google.
    Args:
      new_db : output of LdapContext.Search or AsyncSearch (which
        should be an unrestrictive search that finds all your
        current users)
    Return:
      list of DNs who are not in new_db
    """
    deleted = []
    old = new_db.UserDNs()
    for dn in self.UserDNs():
      if dn not in old:
        deleted.append(dn)
    return deleted

  def MergeUsers(self, other_db, timestamp=None):
    """ Merge another UserDB into this one.
    Unlike _AddUsers, which takes the native data structure returned by
    the ldap module, this takes another instance of UserDB.
    Args:
      other_db: a second instance of UserDB.
      timestamp: the value to assign to the 'meta-
    """
    if timestamp is not None:
      now = time.time()
    else:
      now = timestamp
    for (dn, attrs) in other_db.db.iteritems():

      # need to preserve meta-Google-old-username, if old name & it exists:
      dn = dn.lower()
      old_username = None
      if dn in self.db:
        if 'meta-Google-old-username' in self.db[dn]:
          old_username = self.db[dn]['meta-Google-old-username']
      self.db[dn] = self._MapUser(attrs)
      self._UpdatePrimaryKeyLookup(dn, attrs)
      self.SetMetaAttribute(dn, "meta-last-updated", now)
      if old_username is not None:
        self.db[dn]['meta-Google-old-username'] = old_username
      self._UpdateAttrList(attrs)


  """
  *******************************************************************************
   "mapping", or creating the Google attributes from the LDAP attributes
  *******************************************************************************
  """
  def GetGoogleMappings(self):
    """ return a dictionary of the "Google attributes" with their
    mappings, or None if they have none.
    Returns:
      dictionary, where keys are the Google attributes and the values
        are the expressions defined for each one.
    """
    return self.mapping

  def MapAttr(self, gattr, expr):
    """ Map a Google attribute to an expression, which is limited to being
    a function of the LDAP attributes on that user object.
    NOTE: the expression is NOT tested in this function.  Call TestMapping()
    to do that.
    Args:
      gattr : name of the Google attribute
      expr : a Python expression, whose globals are set to that object's
        LDAP record
    """
    self.mapping[gattr] = expr
    for (dn, attrs) in self.db.iteritems():
      self.db[dn] = self._MapUser(attrs)
    self.config_changed = True

  def MapGoogleAttrs(self, other_db):
    """ go through all the users in a second UserDB, and create their
    Google attrs, using the mappings defined for this UserDB instance.
    Args:
      other_db: a different UserDB, presumably created by an LDAP search
    """
    for (dn, attrs) in other_db.db.iteritems():
      dn = dn.lower()
      other_db.db[dn] = self._MapUser(attrs)

  def TestMapping(self, mapping, fraction=0.1):
    """ try out a user-supplied mapping, and see if it works.
    Args:
      mapping : the mapping
      fraction : what part of the users to try it out on.
        default = 10%
    Return : None if success, error message if not
    """
    dns = self.UserDNs()
    if not dns:
      return
    count = max(int(len(dns) * fraction),10)
    for i in xrange(count):
      dn = dns[random.randrange(len(dns))]
      attrs = self.db[dn]
      try:
        eval(mapping, attrs.copy())
      except Exception,e:
        return str(e)

  """
  *********************************************************************
  File reading and writing
  *********************************************************************
  """
  def _CreateUserDOM(self, doc, dn, attrs):
    """ Create a DOM subtree from the DN and its attrs. This is a part
      of the "write to XML" function.
    Args:
      doc : the Document node
      dn : distinguished name of the user
      attrs : dictionary of its Google attributes
    Return:
      1) DOM node for the user. The attrs within the
       DOM node are in order of attr name
      2) set of attributes which could not be encoded into
       utf-8
    """

    rejected_attrs = set()
    user_node = doc.createElement("user")
    dn_node = doc.createElement("DN")
    user_node.appendChild(dn_node)

    dn_node.appendChild(doc.createTextNode(dn))

    attr_names = attrs.keys()
    attr_names.sort()

    for attr in attr_names:
      value = attrs[attr]
      attr_node = doc.createElement(attr)
      if value:
        text_value = str(value)
      else:
        text_value = ""
      try:
        u_value = unicode(text_value, 'utf-8')
      except UnicodeDecodeError:
        rejected_attrs.add(attr)
        continue
      attr_node.appendChild(doc.createTextNode(u_value))
      user_node.appendChild(attr_node)
    return (user_node, rejected_attrs)

  def _ExtendListIfNecessary(self, lst, new_lst):
    """ Append the items in one list to the second, but only
    if not already there (i.e. union the two lists)
    Args:
      lst: the target list, which is extended if necessary
      new_lst: second list, whose objects are added to lst
        if not already present
    Returns:
      the union of the two lists
    """
    for item in new_lst:
      if lst.count(item) == 0:
        lst.append(item)
    return lst

  def _ReadAddUser(self, dn_arg, row, enforceAttrList=False):
    """ Common utility for XML and CSV: put in the user, and
    update all necessary data structures
    Args:
      dn: DN of the user
      row: a dictionary of the attributes
      enforceAttrList: if true, only attributes in self.attrs
      are kept
    """
    dn = dn_arg.lower()
    if enforceAttrList:
      for attr in row.keys():
        if attr not in self.attrs:
          del row[attr]
    self.db[dn] = row
    self._UpdateAttrList(row)
    if self.primary_key:
      self._UpdatePrimaryKeyLookup(dn, row)

  def _ReadCSVFile(self, fname):
    """ Reads in a CSV file, as long as it's "regular", i.e. the goal
    is to accept CSVs written by other applications, not only from
    this program.  The one rule we impose is that the "dn" attribute
    must always be present, since that's how we know where the user
    comes from in LDAP.
    Args:
      name of file
    Return : (# users added, # users excluded)
      Users are excluded primarily for lack of a "dn" attribute
    """
    f = open(fname, "rb")
    reader = csv.DictReader(f)
    added = 0
    excluded = 0
    if len(self.attrs):
      enforceAttrList = True
    else:
      enforceAttrList = False
    for row in reader:
      if "dn" not in row:
        excluded += 1
      else:
        dn = row["dn"]
        del row["dn"]
        self._ReadAddUser(dn, row, enforceAttrList)
        added += 1
    f.close()
    return (added, excluded)

  def _ReadUserXML(self, dom):
    """ Read in a single <user> element.
    Args:
      user : the DOM tree for a <user> element
    Return: dictionary, where keys are the element names and
      the values are the text values of the elements, if any
    """
    user = {}
    dn = GetTextFromNodeList(dom.getElementsByTagName("DN"))
    if not dn:
      return (None, None)
    for child in dom.childNodes:
      if child.nodeType != xml.dom.Node.ELEMENT_NODE:
        continue
      # the DN is special; don't include that
      if child.tagName != "DN":
        self._SaveElement(child, user)
    return (dn, user)

  def _ReadXMLFile(self, fname):
    """ Reads in an XML file.
    Args:
      name of file
    Return : (# users added, # users excluded)
      Users are excluded primarily for lack of a "dn" attribute
    """
    f = codecs.open(fname, 'r', 'utf-8')
    dom = xml.dom.minidom.parseString(f.read())
    users = dom.getElementsByTagName("user")
    added = 0
    excluded = 0
    if len(self.attrs):
      enforceAttrList = True
    else:
      enforceAttrList = False

    for user in users:
      dn, db_user = self._ReadUserXML(user)
      if not dn:
        excluded += 1
      else:
        self._ReadAddUser(dn, db_user, enforceAttrList)
        added += 1
    f.close()
    return (added, excluded)

  def _SaveElement(self, elt, user):
    """ read an element from an XML file
    Args:
      elt : the DOM element
      user : current user dictionary
    Notes: only handles "simple" elements, for now.  No nested elts.
    If we start keeping history or other complicated stuff in the user
    rec, this will have to change.
    """
    if not elt.firstChild:
      user[elt.tagName] = ""
      return
    if elt.firstChild.nodeType != xml.dom.Node.TEXT_NODE:
      return # silently drop
    user[str(elt.tagName)] = GetText(elt.childNodes)

  def _WriteCSVFile(self, fname, dns):
    """ Write the users to an XML file
    Args;
      fname: name of the file to write
      dns: a list of DNs to be written out
    Return:
      set of attributes which couldn't be written out
    Raises:
      IOError: if the file couldn't be written
    """
    f = open(fname, "wb")
    fieldnames = ["dn"]
    fieldnames = self._ExtendListIfNecessary(fieldnames, list(self.attrs))
    fieldnames = self._ExtendListIfNecessary(fieldnames, list(self.meta_attrs))
    fieldnames = self._ExtendListIfNecessary(fieldnames, list(self.mapping.keys()))
    fieldnames.sort()
    dw = csv.DictWriter(f, fieldnames, dialect="excel")

    # since DictWriter is too stupid to write out the header row,
    # we have to fake one
    header = {}
    for name in fieldnames:
      header[name] = name
    dw.writerow(header)
    for dn in dns:
      row = self.db[dn]
      row["dn"] = dn
      dw.writerow(row)
    f.close()

  def _WriteXMLFile(self, fname, dns):
    """ writes an XML file with the user database. The XML file is
    in order of DN.
    Args:
      fname: name of the file to be written
      dns: the DNs to be written out
    Return:
      Set of attributes which could not be encoded into utf-8
    Raises:
      IOError: if the file couldn't be written
    """

    rejected_attrs = set()
    doc = xml.dom.minidom.Document()
    top_node = doc.createElement("Users")
    doc.appendChild(top_node)
    for dn in dns:
      attrs = self.db[dn]
      (domNode, bad_attrs) = self._CreateUserDOM(doc, dn, attrs)
      rejected_attrs = rejected_attrs.union(bad_attrs)
      top_node.appendChild(domNode)
    f = codecs.open(fname, 'w', 'utf-8')
    f.write(doc.toprettyxml(encoding="utf-8"))
    f.close()
    return rejected_attrs

  """
  *********************************************************************
  Private housekeeping routines
  *********************************************************************
  """
  def _AddUsers(self, ldap_users, timestamp=None):
    """ Converts the returned value from an LDAP search into our dictionary
    format. In the process, all attribute values are "de-listified", i.e.
    ['Fred'] is converted to 'Fred'.
    Args:
      ldap_users : returned value from LdapContext.Search or AsyncSearch.
      timestamp : the desired value of the 'meta-last-updated' attribute
        (Normally this should be the time at which the last LDAP sync
        was done)
    """
    if not timestamp:
      now = time.time()
    else:
      now = timestamp
    for user in ldap_users:
      dn, attrs = user
      dn = dn.lower()
      self._UpdateAttrList(attrs)
      for (attr, val) in attrs.iteritems():
        if isinstance(val, types.ListType) and len(val) == 1:
          attrs[attr] = val[0]

      self.db[dn] = self._MapUser(attrs)
      self._UpdatePrimaryKeyLookup(dn, attrs)

      # set the meta-attributes
      self.SetMetaAttribute(dn, "meta-last-updated", now)

  def _DeletePrimaryKey(self, attrs):
    """ Delete the primary key found in 'attrs' from the primary key
    lookup table.  Part of deleting a user
    Args:
      attrs: dictionary of attributes about a user
    """
    dn = self._FindPrimaryKey(attrs)
    if dn:
      del self.primary_key_lookup[attrs[self.primary_key]]

  def _FindPrimaryKey(self, attrs):
    """ For a (presumably) new set of attributes, see if it matches
    on primary key with anything else in the database
    Args:
      attrs: dictionary of attributes about a user
    Returns:
      DN of the user found, or None if none found
    """
    if not self.primary_key or self.primary_key not in attrs:
      return
    if attrs[self.primary_key] in self.primary_key_lookup:
      return self.primary_key_lookup[attrs[self.primary_key]]

  def _GoogleAttrsCompare(self, dn_arg, attrs):
    """ Compare the Google attributes (other than GoogleUsername)
    of (dn, attrs) to self.db[dn]
    Args:
      dn: a DN which MUST be in self
      attrs: a set of attributes, which may or may not match
        self.db[dn]
    Returns:
      -1 if dn_arg is less than attrs, +1 if greater, 0 if equal
    Raises:
      KeyError: if DN is not in self.db
    """
    dn = dn_arg.lower()
    return AttrListCompare(self.google_update_vals, self.db[dn], attrs)

  def _MapUser(self, attrs):
    """ Given a user DN and dict of attrs about that user,
    do the mapping of LDAP attrs to Google attrs that
    was configured in self.mapping.
    Args:
      dn : string with the DN (not used at present)
      attrs : dictionary of LDAP attr values
    Returns:
      dictionary with (mapped) Google attributes added

    Coding note: the attrs.copy() below is because Python inserts a copy of the
    globals "builtin" member if not already there!   This is quite unwelcome
    since we want to use that object for other things.
    """

    result = {}
    for (attr, value) in attrs.iteritems():
      result[attr] = value

    # if there were a naming conflict, the Google attrs would trump:
    for (key, expr) in self.mapping.iteritems():
      if expr:
        try:
          result[key] = eval(expr, attrs.copy()).strip()
        except (NameError, SyntaxError):
          result[key] = None  # make sure it's got something
          pass
      else:
        result[key] = None
    return result

  def _UpdateAttrList(self, attrs):
    """ Merge a set of attributes into UserDB's configured list
    Args:
      attrs : iterable list of attribute names
    """
    new_attrs = set()
    # de-Unicode them all
    for attr in attrs:
      new_attrs.add(str(attr))
    self.attrs = self.attrs.union(new_attrs)

  def _UpdatePrimaryKeyLookup(self, dn_arg, attrs):
    """ Given a new user, update the "primary key lookup", i.e.
    the hash table mapping primary key value to DN.
    Args:
      dn_arg:  the DN of the user
      attrs: dictionary of all attributes of the user
    """
    dn = dn_arg.lower()
    if not self.primary_key:
      return
    if self.primary_key not in attrs:
      return
    self.primary_key_lookup[attrs[self.primary_key]] = dn


  """
  *********************************************************************
  miscellaneous code, doesn't fit anywhere else
  *********************************************************************
  """

  def RestrictUsers(self, dn, other_db=None):
    """ Remove all users except 'dn'. This is mostly for the "syncOneUser"
    command, where a UserDB is set up with just that user
    Args:
      dn: the DN to be kept, all others to be deleted
      other_db: if non-null, restrict from this other UserDB.
    Returns:
      A new UserDB object containing only the DN and its attrs
    """
    new_db = UserDB(self._config)
    if other_db:
      the_db = other_db
    else:
      the_db = self
    new_db.attrs = the_db.attrs.copy()
    new_db.timestamp = the_db.timestamp
    new_db.primary_key = the_db.primary_key
    new_db.mapping = the_db.mapping.copy()
    new_db.db[dn] = the_db.LookupDN(dn)
    return new_db

  def SuggestAttrs(self):
    """ Try to guess which attributes to keep, and which
    of those map to Google-required attributes.

    The matching algorithm is a little crude, for now.  Hopefully we can
    improve it and use the schemas in common use, esp. ActiveDirectory.
    Returns:
      trial : set of the proposed attributes to keep
      mappings : proposed mapping of GoogleAttributes to those attributes
    """

    exp = re.compile(".*(uid|mail|group|name|gid|pass|pwd|user|sn|cn).*")
    trial = set()  # our 'trial set'
    dictLower = {} # temporary lower-case version of trial
    for attr in self.attrs:
      if attr in set(['objectGUID', 'msExchMailboxSecurityDescriptor',
         'msExchMailboxGuid']):
        continue
      attrLower = attr.lower()
      if exp.match(attrLower):
        trial.add(attr)
        dictLower[attrLower] = attr
    mapping = self.mapping.copy()

    if not mapping["GoogleUsername"]:
      mapping["GoogleUsername"] = SuggestGoogleUsername(dictLower)
    if not mapping["GoogleLastName"]:
      mapping["GoogleLastName"] = SuggestGoogleLastName(dictLower)
    if not mapping["GoogleFirstName"]:
      mapping["GoogleFirstName"] = SuggestGoogleFirstName(dictLower)
    if not mapping["GooglePassword"]:
      mapping["GooglePassword"] = SuggestGooglePassword(dictLower)
    return (trial, mapping)
