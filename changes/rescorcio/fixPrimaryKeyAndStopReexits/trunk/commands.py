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

# This package requires:
# 1) Python 2.4 or above,
# 2) the "python-ldap" package,
#     which can be downloaded from http://python-ldap.sourceforge.net/
# 3) Google Apps for Your Domain Provisioning API, version 1, Python
#     bindings.

""" Command-line module for the LDAP Sync Tool

class Commands: main class, subclass of the Python cmd.Cmd class

"""

import cmd
import last_update_time
import logging
import messages
import os
from google.appsforyourdomain import provisioning
import pprint
import time
import userdb
import utils

pp = pprint.PrettyPrinter(indent=2)

# the most user records to be displayed at a time
MAX_USER_DISPLAY = 32

class Commands(cmd.Cmd):

  """ main class, subclass of the Python cmd.Cmd class.
  Most of the methods in this module are either "do_<command>"
  or "help_<command", which is the cmd.Cmd convention for the
  <command> method or the <command> help.  The commands are organized
  into groups, and within each group in alphabetical order by
  <command>.  The groups are:
  1) constructors & overhead
  2) Configuration variable-setting
  3) LDAP connections
  4) LDAP searching and checking
  5) Viewing the users
  6) Managing attributes and mappings
  7) Synchronizing with Google
  8) Reading and writing the users to a file
  9) Miscellaneous commands (batch & stop)
  10) Utility methods
  """
  def __init__(self, ldap_context, users, google, config):
    """ Constructor.
    Args:
      ldap_context: LDAPCtxt object
      users: Users object
      google: sync_google object
      config: utils.Config object
    """
    cmd.Cmd.__init__(self)
    self.ldap_context = ldap_context
    self.users = users
    self.sync_google = google
    self._config = config

    self.new_users = None
    self.last_update = None

    # stuff needed by the Cmd superclass:
    self.completekey = None
    self.cmdqueue = []
    self.prompt = "Command: "
    self.prompt = messages.msg(messages.CMD_PROMPT)

    # code only for use of the unittest:
    self._testing_last_update = None

  def precmd(self, line):
    """Print the line just entered for debugging purposes.
    Args:
      line which is simply returned unchanged.
    """
    if line.lower().find('password') >= 0:
      logging.debug("command: (command involving password not shown)")
    else:
      logging.debug("command: " + line)
    return line

  """
  ******************  Configuration variable-setting
  Commands:
    set
  """
  def ShowConfigVars(self):
    cvars = self._config.attrs.keys()
    cvars.sort()
    for var in cvars:
      print '%s:\t%s\n' % (var, self._config.attrs[var])

  def do_set(self, rest):
    args = rest.strip()
    if not len(args):
      self.help_set()
      return
    toks = rest.split(' ')

    # see if it's a real variable
    owner = self._config.FindOwner(toks[0])
    if owner == None:
      logging.error(messages.msg(messages.ERR_NO_SUCH_ATTR, toks[0]))
      return
    value = ' '.join(toks[1:])
    msg = owner.SetConfigVar(toks[0], value)
    if msg:
      logging.error(msg)

  def help_set(self):
    print messages.MSG_SET_ANY
    self.ShowConfigVars()

  """
  ******************  LDAP connections
  Commands:
    connect
    disconnect
  """

  # *******************                    connect command

  def do_connect(self, unused_rest):
    try:
      if self.ldap_context.Connect():
        logging.error(messages.msg(messages.ERR_CONNECT_FAILED))
      else:
        logging.info(messages.msg(messages.MSG_CONNECTED, 
                     self.ldap_context.ldap_url))
    except utils.ConfigError, e:
      logging.error(str(e))

  def help_connect(self):
    print messages.msg(messages.HELP_CONNECT)

  # *******************                    disconnect command

  def do_disconnect(self, unused_rest):
    if self.ldap_context.Disconnect():
      logging.error(messages.msg(messages.ERR_DISCONNECT_FAILED))
    logging.info(messages.msg(messages.MSG_DISCONNECTED, 
                 self.ldap_context.ldap_url))

  def help_disconnect(self):
    print messages.msg(messages.HELP_DISCONNECT)


  """
  ******************  LDAP searching and checking
  Commands:
    testFilter: test an LDAP filter, and get a suggested list of LDAP
      attributes to use, plus Google mappings
    updateUsers: pull in users from LDAP and update the UserDB,
      marking users with appropriate Google actions (added/exited/renamed/
      updated)
  """

  # *******************                    testFilter command

  def do_testFilter(self, rest):
    (args, force_accept) = self._ProcessArgs(rest)
    if len(args):
      self.ldap_context.SetUserFilter(args)
    try:
      self.new_users = self.ldap_context.Search(attrlist=['cn'])
    except RuntimeError,e:
      logging.exception('**Error: %s\n', str(e))
      return
    except utils.ConfigError,e:
      logging.exception(str(e))
      return

    if not self.new_users or self.new_users.UserCount() == 0:
      print messages.msg(messages.MSG_FIND_USERS_RETURNED, "0")
      return

    print messages.msg(messages.MSG_FIND_USERS_RETURNED, 
                       str(self.new_users.UserCount()))

    # do it again with a small set, but get all attrs this time
    try:
      print messages.msg(messages.ERR_TEST_FILTER_SAMPLING)
      sample_full_attrs = self.ldap_context.AsyncSearch(rest,
           min(10, self.new_users.UserCount()))
      if not sample_full_attrs:
        return

      # and since 'all attrs' doesn't include important stuff like
      # the modifyTimestamp, we have to do that separately:
      sample_top_attrs = self.ldap_context.AsyncSearch(rest, 1, ['+'])
      if not sample_top_attrs:
        return
    except utils.ConfigError,e:
      logging.error(str(e))
      return

    # and then union the two sets:
    full_attr_set = sample_full_attrs.GetAttributes()
    top = sample_top_attrs.GetAttributes()
    full_attr_set.extend(top)
    print messages.msg(messages.MSG_TEST_FILTER_ATTRS)
    pp.pprint(full_attr_set)
    (self.trialAttrs, self.trialMappings) = sample_full_attrs.SuggestAttrs()

    print messages.msg(messages.MSG_SUGGESTED_ATTRS)
    lst = list(self.trialAttrs)
    lst.sort()
    for attr in lst:
      print '\t%s' % attr
    print messages.msg(messages.MSG_SUGGESTED_MAPPINGS)
    for (gattr, lattr) in self.trialMappings.iteritems():
      print "%-30s %s" % (gattr, lattr)

    self.users.SetTimestamp(userdb.SuggestTimestamp(full_attr_set))
    print messages.msg(messages.MSG_SUGGESTED_TIMESTAMP)
    if self.users.GetTimestampAttributeName():
      print '\t%s' % self.users.GetTimestampAttributeName()
    else:
      print messages.MSG_NO_TIMESTAMP

    self.users.primary_key = userdb.SuggestPrimaryKey(full_attr_set)
    if self.users.primary_key:
      print messages.msg(messages.MSG_SUGGESTED_PRIMARY_KEY)
      print '\t%s' % self.users.primary_key

    first = " "
    while first != "y" and first != "n":
      if not force_accept:
        ans = raw_input(messages.msg(messages.MSG_ACCEPT_SUGGESTIONS))
      else:
        ans = 'y'
      first = ans[:1].lower()
      if first == "y":
        self._SetSuggestedAttrs()
        self._SetSuggestedMappings()
      elif first == "n":
        print messages.msg(messages.MSG_SAID_NO_SUGGESTIONS)
      else:
        print messages.msg(messages.ERR_YES_OR_NO)


  def help_testFilter(self):
    print messages.msg(messages.HELP_TEST_FILTER)

  # *******************                    updateUsers command

  def do_updateUsers(self, unused_rest):
    try:
      if not self.ldap_context.GetUserFilter():
        logging.error(messages.ERR_NO_USER_FILTER)
        return
      print messages.msg(messages.MSG_ADDING, self.ldap_context.GetUserFilter())
      self._ShowGoogleAttributes()
      last_update_time.beginNewRun()
      self.errors = False

      # add in the condition for "> lastUpdate"
      search_filter = self.ldap_context.ldap_user_filter
      attrTime = self.users.GetTimestampAttributeName()
      if not attrTime:
        attrTime = 'meta-last-updated'
      self.last_update = None
      if last_update_time.get():
        self.last_update = self._TimeFromLDAPTime(last_update_time.get())

      logging.debug('last_update time=%s' % str(self.last_update))
      attrs = self.users.GetAttributes()
      directory_type = _GetDirectoryType(attrs)
      if self.last_update:
        search_filter = self._AndUpdateTime(search_filter,
                   self.users.GetTimestampAttributeName(), self.last_update,
                   directory_type)
      try:
        found_users = self.ldap_context.Search(filter_arg=search_filter,
                                attrlist=attrs)
      except RuntimeError,e:
        logging.exception(str(e))
        return

      if not found_users or found_users.UserCount() == 0:
        print messages.msg(messages.MSG_FIND_USERS_RETURNED, "0")

      if found_users:
        # we need to compute the Google attrs now, since
        # userdb.AnalyzeChangedUsers uses that:
        self.users.MapGoogleAttrs(found_users)
        (adds, mods, renames) = self.users.AnalyzeChangedUsers(found_users)

        # mark new uses as "to be added to Google"
        for dn in adds:
          found_users.SetGoogleAction(dn, 'added')
        for dn in mods:
          found_users.SetGoogleAction(dn, 'updated')
        for dn in renames:
          found_users.SetGoogleAction(dn, 'renamed')
        self.users.MergeUsers(found_users)
        if adds:
          print messages.msg(messages.MSG_NEW_USERS_ADDED, (str(len(adds)), 
            str(self.users.UserCount())))
        if mods:
          print messages.msg(messages.MSG_UPDATED_USERS_MARKED, 
              (str(len(mods))))
        if renames:
          print messages.msg(messages.MSG_RENAMED_USERS_MARKED,
                             (str(len(renames))))

      # find exited users & lock their accounts
      self._FindExitedUsers()
    except utils.ConfigError, e:
      logging.error(str(e))

  def help_updateUsers(self):
    print messages.msg(messages.HELP_ADD_USERS)

  """
  ****************** Viewing the users
  Commands:
    showLastUpdate: displays the time of the last updateUsers
    showUsers: (very limited) display of contents of the UserDB
    summarizeUsers: shows total users, and #'s of added/exited/renamed/updated
  """

  # *******************                    showLastUpdate command
  def do_showLastUpdate(self, unused_rest):
    self.last_update = last_update_time.get()
    if not self.last_update:
      print messages.MSG_SHOW_NO_LAST_UPDATE
    else:
      try:
        self.last_update = float(self.last_update)
      except ValueError:
        logging.exception('bad update time: %s', str(self.last_update))
        self.last_update = 0
      tstr = time.asctime(time.localtime())
      print messages.msg(messages.MSG_SHOW_LAST_UPDATE, tstr)

  def help_showLastUpdate(self):
    print messages.msg(messages.HELP_SHOW_LAST_UPDATE)

  # *******************                    showUsers command

  def do_showUsers(self, rest):
    args = rest.strip()
    start = 1
    user_count = self.users.UserCount()
    if not user_count:
      logging.info(messages.ERR_NO_USERS)
      return
    end = self.users.UserCount()
    if args:
      nums = self._GetNumArgs(rest, 2)
      if not nums:
        logging.error(messages.msg(messages.ERR_SHOW_USERS_ARGS))
        return
      start = nums[0]
      if len(nums) > 1:
        end = nums[1]
      else:
        end = start
      user_count = end - start + 1

    # don't just spew out 20,000 users without a warning:
    if user_count > 10:
      ans = raw_input(messages.msg(messages.ERR_TOO_MANY_USERS, 
                      str(user_count)))
      first = ans[:1].lower()
      if first != "y":
        return
    dns = self.users.UserDNs()
    print "Display new users %d to %d" % (start, end)
    for ix in xrange(start-1, end):
      print "%d: %s" % (ix+1, dns[ix])
      pp.pprint(self.users.LookupDN(dns[ix]))

  def help_showUsers(self):
    print messages.msg(messages.HELP_SHOW_USERS)

  # *******************                    summarizeUsers command

  def do_summarizeUsers(self, unused_rest):
    total = 0
    added = 0
    exited = 0
    updated = 0
    renamed = 0
    for (dn, attrs) in self.users.db.iteritems():
      total += 1
      if 'meta-Google-action' in attrs:
        action = attrs['meta-Google-action']
        if action == 'added':
          added += 1
        elif action == 'exited':
          exited += 1
        elif action == 'renamed':
          renamed += 1
        elif action == 'updated':
          updated += 1
    print messages.msg(messages.MSG_USER_SUMMARY,
        (str(total), str(added), str(exited), str(renamed), 
          str(updated)))

  def help_summarizeUsers(self):
    print messages.msg(messages.HELP_SUMMARIZE_USERS)

  """
  ******************  Managing attributes and mappings
  Commands:
    attrList: display & edit the list of attributes
    mapGoogleAttribute: set the mapping from LDAP attributes to
      Google attributes
    markUsers: manually set the 'Google action' for one or more users
  """

  # *******************                    attrList command
  def do_attrList(self, rest):
    args = rest.strip()
    if args:
      toks = args.split(" ")
      if toks[0].lower() == "show":
        attrs = self.users.GetAttributes()
        print messages.msg(messages.MSG_MAPPINGS)
        pp.pprint(attrs)
        self._ShowGoogleAttributes()
        return

    # if here, we require a second argument
    if len(toks) < 2:
      logging.error(messages.msg(messages.MSG_USAGE_ATTR_LIST))
      return
    attr = toks[1]

    if toks[0].lower() == "add":
      self.users.AddAttribute(attr)
    elif toks[0].lower() == "remove":
      if not attr in self.users.GetAttributes():
        logging.error(messages.msg(messages.ERR_NO_SUCH_ATTR, attr))
        return
      count = self.users.RemoveAttribute(attr)
      print messages.msg(messages.MSG_ATTR_REMOVED, (attr, str(count)))
    else:
      logging.error(messages.msg(messages.MSG_USAGE_ATTR_LIST))


  def help_attrList(self):
    print messages.msg(messages.HELP_ATTR_LIST)


  # *******************                    mapGoogleAttribute command

  def do_mapGoogleAttribute(self, rest):
    line = rest.strip()
    if not line:
      print messages.msg(messages.ERR_MAP_ATTR)
      return

    toks = line.split(" ")
    attr = toks[0]
    if not attr in self.users.GetGoogleMappings():
      print messages.msg(messages.ERR_NO_SUCH_ATTR, attr)
      return

    if len(toks) > 1:
      mapping = rest.replace(attr, "", 1)
    else:
      mapping = raw_input(messages.MSG_ENTER_EXPRESSION)

    # test the expression
    print messages.msg(messages.MSG_TESTING_MAPPING)
    err = self.users.TestMapping(mapping.strip())
    if err:
      logging.error(messages.msg(messages.ERR_MAPPING_FAILED))
      logging.error(err)
      return
    self.users.MapAttr(attr, mapping)
    print messages.MSG_DONE

  def help_mapGoogleAttribute(self):
    print messages.HELP_MAP_ATTR

  # *******************                    markUsers command

  def do_markUsers(self, rest):
    args = rest.strip()
    if not args:
      logging.error(messages.msg(messages.ERR_MARK_USERS))
      logging.error(messages.msg(messages.HELP_MARK_USERS))
      return
    toks = args.split(' ')
    if len(toks) < 2 or len(toks) > 3:
      logging.error(messages.msg(messages.ERR_MARK_USERS))
      logging.error(messages.msg(messages.HELP_MARK_USERS))
      return
    first_str = toks[0]
    second_str = None
    second = None
    if len(toks) == 3:
      second_str = toks[1]
      action = toks[2]
    else:
      action = toks[1]
    try:
      s = first_str
      first = int(first_str)
      second = first
      if second_str:
        s = second_str
        second = int(second_str)
    except ValueError:
      logging.exception('%s\n' % messages.msg(messages.ERR_ENTER_NUMBER, s))
      return

    # parse the action
    if action != 'added' and action != 'exited' and action != 'update':
      logging.error(messages.msg(messages.ERR_MARK_USERS_ACTION))
      logging.error(messages.msg(messages.HELP_MARK_USERS))
      return
    else:
      dns = self.users.UserDNs()
      if first < 0 or first > len(dns):
        logging.error(messages.msg(messages.ERR_NUMBER_OUT_OF_RANGE, first_str))
        return
      if second:
        if second < 0 or second > len(dns) or second < first:
          logging.error(messages.msg(messages.ERR_NUMBER_OUT_OF_RANGE, 
                        second_str))
          return
      for ix in xrange(first, second+1):
        self.users.SetGoogleAction(dns[ix], action)

  def help_markUsers(self):
    print messages.HELP_MARK_USERS

  """
  ******************  Synchronizing with Google
  Commands:
    syncOneUser: sync a single user with UserDB AND with Google.  This is a 
      two-way sync, meaning it fetches the user's information from Google and 
      compares it to the current LDAP information.
    syncAllUsers: sync all users with Google.  This is a one-way sync, i.e. it 
      does not fetch the list of users from Google and compare.  (in a future 
      version of the Provisioning API, this will be feasible;  right now (late 
      2006), it would be too slow.
  """


  def do_syncOneUser(self, rest):
    """ This is the one example of a two-way sync in this tool. It compares
    LDAP to the UserDB, and it also goes to GAFYD for the status of the
    user.
    Args:
      -f:  "force" acceptance by the user.  This is mainly for the unittest
        so it doesn't wait for human input. End users: use at your own risk!
    """
    (args, force_accept) = self._ProcessArgs(rest)
    if not args:
      logging.error(messages.ERR_SUPPLY_VALID_USER)
      return
    the_user = self._FindOneUser(args)
    old_username = None
    if not the_user:  # not found in LDAP
      # see if it's in UserDB, but deleted from LDAP:
      dn = self._AnalyzeUserMissingInLDAP(args)
      if not dn:
        return
      the_user = self.users.RestrictUsers(dn)
      act = 'exited'
    else:  # it IS in LDAP; see what's up with it
      dn = the_user.UserDNs()[0]

      # save the GoogleUsername value before we (potentially) overwrite it:
      attrs = self.users.LookupDN(dn)
      if attrs:
        if 'GoogleUsername' in attrs:
          old_username = attrs['GoogleUsername']

      self.users.MapGoogleAttrs(the_user)
      (added, modded, renamed) = self.users.AnalyzeChangedUsers(the_user)
      act = None
      if added:
        act = 'added'
      elif modded:
        act = 'updated'
      elif renamed:
        act = 'renamed'

    the_user.SetGoogleAction(dn, act)
    self.users.MergeUsers(the_user)

    attrs = self.users.LookupDN(dn)
    print messages.msg(messages.MSG_USER_IS_NOW, dn)
    if 'GoogleUsername' not in attrs:
      logging.error(messages.msg(messages.ERR_NO_ATTR_FOR_USER, 
                                 'GoogleUsername'))
      return
    username = attrs['GoogleUsername']

    # what if this is a rename?
    old_user_rec = None
    if old_username:
      if old_username != username:
        old_user_rec = self._FetchOneUser(old_username)
      user_rec = self._FetchOneUser(username)
    else:  # new user
      user_rec = self._FetchOneUser(username)
    act = self._TwoWayCompare(dn, user_rec, old_user_rec)
    if not act:
      print messages.MSG_UP_TO_DATE
      return

    # give admin a chance to approve the action:
    print messages.msg(messages.MSG_RECOMMENDED_ACTION_IS, act)
    if not force_accept:  # normal case: ask the human
      ans = raw_input(messages.MSG_PROCEED_TO_APPLY)
      if ans[:1] != messages.CHAR_YES:
        return
    self.sync_google.DoAction(act, dn)

  def help_syncOneUser(self):
    print messages.HELP_SYNC_ONE_USER

  # *******************                    syncAllUsers command
  def do_syncAllUsers(self, rest):
    args = rest.strip().lower()
    if args:
      if args == 'added':
        actions = ['added']
      elif args == 'exited':
        actions = ['exited']
      elif args == 'updated':
        actions = ['updated']
      elif args == 'renamed':
        actions = ['renamed']
      elif args == 'all':
        actions = self.sync_google.google_operations
      else:
        logging.error(messages.msg(messages.ERR_SYNC_USERS_ACTION))
        return
    else:
      actions = self.sync_google.google_operations

    # be sure we can connect, before we spawn a bunch of threads that'll try:
    errs = self.sync_google.TestConnectivity()
    if errs:
      logging.error(messages.msg(messages.ERR_CONNECTING_GOOGLE, errs))
      return

    try:
      for action in actions:
        stats = self.sync_google.DoAction(action)
        if stats is not None:
          self._ShowSyncStats(stats)

    except utils.ConfigError, e:
      logging.error(str(e))
      return

    last_update_time.updateIfNoErrors()

  def help_syncAllUsers(self):
    print messages.HELP_SYNC_USERS_GOOGLE

  """
  ******************  Reading and writing the users to a file
  Commands:
    readUsers
    writeUsers
  """

  # *******************                    readUsers command

  def do_readUsers(self, rest):
    args = rest.strip()
    if not args:
      logging.error(messages.MSG_GIVE_A_FILE_NAME)
      return
    else:
      fname = rest.split(" ")[0]
    print messages.msg(messages.MSG_READ_USERS, fname)
    try:
      self.users.ReadDataFile(fname)
    except RuntimeError, e:
      logging.exception(str(e))
      return
    print messages.msg(messages.MSG_DONE)

  def help_readUsers(self):
    print messages.msg(messages.HELP_READ_USERS)


  # *******************                    writeUsers command

  def do_writeUsers(self, rest):
    args = rest.strip()
    if not args:
      logging.error(messages.MSG_GIVE_A_FILE_NAME)
      return
    else:
      fname = rest.split(" ")[0]
    print messages.msg(messages.MSG_WRITE_USERS, fname)
    try:
      rejected_attrs = self.users.WriteDataFile(fname)
    except RuntimeError, e:
      logging.exception(str(e))
      return
    print messages.msg(messages.MSG_DONE)
    if rejected_attrs and len(rejected_attrs):
      print messages.MSG_REJECTED_ATTRS
      for attr in rejected_attrs:
        print '\t%s' % attr

  def help_writeUsers(self):
    print messages.msg(messages.HELP_WRITE_USERS)

  """
  ******************   Miscellaneous commands
  Commands:
    batch: a file of commands can be executed as a batch
    stop: exit the command interpreter
  """

  # *******************                    batch command

  def do_batch(self, rest):
    args = rest.strip()
    if not args:
      logging.error(messages.msg(messages.ERR_BATCH_ARG_NEEDED))
      return
    fname = args.split(" ")[0]
    if not os.path.exists(fname):
      logging.error(messages.msg(messages.ERR_FILE_NOT_FOUND, fname))
      return
    f = open(fname, "r")
    for line in f.readlines():
      print line
      self.onecmd(line)
    f.close()

  def help_batch(self):
    print messages.msg(messages.HELP_BATCH)

  # *******************                    stop command

  def do_stop(self, unused_rest):
    print messages.msg(messages.MSG_STOPPING)

    # don't know where this is documented, but returning something
    # other than None stops the cmdloop()
    return -1

  def help_stop(self):
    print messages.msg(messages.HELP_STOP)

  def do_EOF(self, rest):
    return self.do_stop(rest)

  """
  ******************  Utility methods
  _AnalyzeUserMissingInLDAP
  _AndUpdateTime
  _ChooseFromList
  _CompareWithGoogle
  _FetchOneUser
  _FindExitedUsers
  _FindOneUser
  _GetNumArgs
  _ProcessArgs
  _SetSuggestedAttrs
  _SetSuggestedMappings
  _ShowGoogleAttributes
  _SplitExpression
  _TwoWayCompare
  _ValidateLDAPTime
  """

  def _AnalyzeUserMissingInLDAP(self, args):
    """ For the syncOneUser command: if the admin has entered an
    expression which didn't map to any LDAP users, figure out what's
    what.  Is it a user who's in the UserDB but no longer in LDAP?
    If so, that's probably an exited.
    Args:
      args: stripped version of the expression the admin entered
    Returns:
      dn of user,  or None if a user in UserDB couldn't be found
    Side effects:
      displays message to the admin if more than one DN matches
        the expression, and waits for him to choose one.
    """
    # see if it's in UserDB, but deleted from LDAP:
    comps = self._SplitExpression(args)
    if not comps:
      return
    (attr, val) = comps
    if not attr:
      return
    dns = self.users.LookupAttrVal(attr, val)
    if not dns:
      return None
    print messages.msg(messages.MSG_FOUND_IN_USERDB, str(len(dns)))
    return self._ChooseFromList(dns)


  def _AndUpdateTime(self, search_filter, timeStampAttr, ts, directoryType):
    """ AND in the "modifyTimestamp > time" condition
    to the filter
    Args:
      search_filter: LDAP filter expression
      timeStampAttr: name of LDAP attribute containing the timestamp
      ts: what the value of the attribute indicated by timeStampAttr must be 
          greater than.
      directoryType: one of 'ad', 'openldap', 'eDirectory'. This is used to 
          deal with differences in directories around querying 
          modifyTimestamp
    """
    if self._testing_last_update:
      stamp = self._testing_last_update
    else:
      stamp = ts
    # NOTE: The following table summarizes the format the modifyTimestamp
    #       filter needs to be in for various directories
    #
    #                    %sZ  %s.Z   %s.0Z
    #  ad                 N     Y      Y
    #  edirectory         Y     N      N
    #  openldap           Y     N      Y
    if directoryType == 'ad':
      cond = '%s>=%s.Z' % (timeStampAttr, time.strftime('%Y%m%d%H%M%S',
                          time.localtime(stamp)))
    else:
      cond = '%s>=%sZ' % (timeStampAttr, time.strftime('%Y%m%d%H%M%S',
                          time.localtime(stamp)))
    s = "(&%s(%s))" % (search_filter, cond)
    logging.debug("new filter is: %s" % s)
    return s

  def _ChooseFromList(self, dns):
    """ Utility to present the user with a list of DNs and ask them
    to choose one
    Args:
      dns: list of DNs
    Return:
      dn of the one chosen, or None if none chosen
    """
    count = len(dns)
    if count == 1:
      return dns[0]
    else:
      if count > MAX_USER_DISPLAY:
        logging.info(messages.msg(messages.MSG_HERE_ARE_FIRST_N, 
                     str(MAX_USER_DISPLAY)))
        limit = MAX_USER_DISPLAY
      for i in xrange(limit):
        print '%d: %s' % (i, dns[i])
      ans = raw_input(messages.MSG_WHICH_USER)
      try:
        num = int(ans)
        if num < 0 or num >= limit:
          return None
        return dns[num]
      except ValueError,e:
        logging.error(str(e))
        return None

  def _CompareWithGoogle(self, attrs, google_result):
    """ Compare the list of attributes for a user in the users database with
    the results from Google.  (Obviously this only compares the Google
    attributes)
    """
    for (attr, gattr) in self.users.google_val_map.iteritems():
      if attr not in attrs or not attrs[attr]:
        if gattr in google_result and google_result[gattr]:
          return 1
        else:
          continue
      if gattr not in google_result or not google_result[gattr]:
        if attr in attrs and attrs[attr]:
          return -1
        else:
          continue
      if attrs[attr].lower() < google_result[gattr].lower():
        return -1
      elif attrs[attr].lower() > google_result[gattr].lower():
        return 1
    return 0

  def _FetchOneUser(self, username):
    """ Fetch info on a single username from Google, with user feedback
    """
    print messages.msg(messages.MSG_LOOKING_UP, username)
    user_rec = self.sync_google.FetchOneUser(username)
    if not user_rec:
      print messages.msg(messages.ERR_USER_NOT_FOUND, username)
    else:
      print messages.MSG_GOOGLE_RETURNED
      #pp.pprint(user_rec)
      self._PrintGoogleUserRec(user_rec)
    return user_rec

  def _FindExitedUsers(self):
    """
    Finding "exited" users: if we have a special filter for that, use it.
    Else do the search without the "> lastUpdate" filter, to find
    users no longer in the DB.
    Even if we DO have a ldap_disabled_filter, still check for deleted
    entries, since you never know what might have happened.

    """
    total_exits = 0
    if (self.ldap_context.ldap_disabled_filter and 
        self.users.GetTimestampAttributeName()):
      attrs = self.users.GetAttributes()
      directory_type = _GetDirectoryType(attrs)
      search_filter = self._AndUpdateTime(
          self.ldap_context.ldap_disabled_filter, 
          self.users.GetTimestampAttributeName(), self.last_update,
          directory_type)
      try:
        logging.debug(messages.msg(messages.MSG_FIND_EXITS,
                                   self.ldap_context.ldap_disabled_filter))
        userdb_exits = self.ldap_context.Search(filter_arg=search_filter,
                                                attrlist=attrs)
        if not userdb_exits:
          return
        logging.debug('userdb_exits=%s' % userdb_exits.UserDNs())
        exited_users = userdb_exits.UserDNs()
        for dn in exited_users:
          # Note: users previously marked added can be reset to exited
          # if they match the exit filter.  This ensures 
          # added_user_google_action is never called on a locked user that 
          # exists in Google Apps 
          self.users.SetGoogleAction(dn, 'exited')
          total_exits += 1
      except RuntimeError,e:
        logging.exception(str(e))
        return

    # Also: find ALL the users, and see which old ones are no longer
    # there:
    exited_users = self.users.FindDeletedUsers(self.ldap_context)
    if not exited_users:
      return
    logging.debug('deleted users=%s' % str(exited_users))
    for dn in exited_users:
      self.users.SetIfUnsetGoogleAction(dn, 'exited')
      total_exits += 1
    if total_exits:
      logging.info(messages.msg(messages.MSG_OLD_USERS_MARKED, 
                                str(total_exits)))

  def _FindOneUser(self, expr):
    """ Utility for determining a single DN from a (presumably user-typed)
    search expression.  If more than one hit, asks the user to choose one.
    Args:
      expr: a user-typed search expression
    Return:
      a new instance of UserDB containing just the single DN, or none if
      none could be found and selected by the user
    """
    try:
      user_hits = self.ldap_context.Search(filter_arg=expr,
                                   attrlist=self.users.GetAttributes())
    except RuntimeError, e:
      logging.error(str(e))
      return
    if not user_hits:
      print messages.msg(messages.MSG_FIND_USERS_RETURNED, '0')
    count = user_hits.UserCount()
    dns = user_hits.UserDNs()
    if count == 0:
      print messages.msg(messages.MSG_FIND_USERS_RETURNED, str(count))
      return None
    elif count > 1:
      print messages.msg(messages.MSG_FIND_USERS_RETURNED, str(count))
      dn = self._ChooseFromList(dns)
    else:  # the preferred case: just one hit to the query
      dn = dns[0]
    if not dn:
      logging.error(messages.msg(messages.MSG_FIND_USERS_RETURNED, '0'))
      return None
    return self.users.RestrictUsers(dn, user_hits)

  def _GetNumArgs(self, rest, countMax):
    """ utility routine to extract up to countMax integers from
    the arguments.  Returns None if too many, or they're not ints
    Args:
      rest : as passed by Cmd module
      countMax : the most ints allowed
    Return:
      list of the args
    """
    result = []
    toks = rest.strip().split(" ")
    if len(toks) > countMax:
      return None
    for tok in toks:
      try:
        result.append(int(tok))
      except ValueError:
        return None
    return result

  def _PrintGoogleUserRec(self, rec):
    if not rec:
      return
    for (key, val) in rec.iteritems():
      print '%-30s: %s' % (str(key), str(val))

  def _ProcessArgs(self, rest):
    """ Utility for commands that may have a '-f' flag, for
    'force a yes to any question to the user' (which is mainly for
    the unit-test).  
    Args:
      rest: as passed by the cmd.Cmd module
    Returns:
      lower-cased, stripped version of 'rest', with the -f removed
        if it was there
      boolean for whether -f was there
    """
    force = False
    args = rest.strip()
    if args.find('-f') >= 0:
      force = True
      args = args.replace('-f', '').strip()
    args = args.strip().lower()
    return (args, force)

  def _SetSuggestedAttrs(self):
    self.users.RemoveAllAttributes()
    for attr in self.trialAttrs:
      self.users.AddAttribute(attr)
    if self.users.GetTimestampAttributeName():
      self.users.AddAttribute(self.users.GetTimestampAttributeName())
    del self.trialAttrs

  def _SetSuggestedMappings(self):
    for (gattr, expr) in self.trialMappings.iteritems():
      self.users.MapAttr(gattr, expr)
    del self.trialMappings

  def _ShowGoogleAttributes(self):
    for (gattr, lattr) in self.users.GetGoogleMappings().iteritems():
      print "%-30s %s" % (gattr, lattr)

  def _ShowSyncStats(self, stats):
    """ Display the results of a "sync to Google" operation. The
    assumption is that 'stats' will contain all members of
    ThreadStats.stat_names but that some will be zero. If either
    <op>s or <op>_fails is non-zero, then a line concerning <op>
    will be displayed, op in {'add', 'exit', 'rename', 'update'}
    Args:
      stats: return value of all sync_google.Do_<operation>. An
      instance of sync_google.ThreadStats.
    """
    if stats['adds'] > 0 or stats['add_fails'] > 0:
      print messages.msg(messages.MSG_ADD_RESULTS, (stats['adds'],
                         stats['add_fails']))
    if stats['exits'] > 0 or stats['exit_fails'] > 0:
      print messages.msg(messages.MSG_EXITED_RESULTS, (stats['exits'],
                         stats['exit_fails']))
    if stats['renames'] > 0 or stats['rename_fails'] > 0:
      print messages.msg(messages.MSG_RENAME_RESULTS, (stats['renames'],
                         stats['rename_fails']))
    if stats['updates'] > 0 or stats['update_fails'] > 0:
      print messages.msg(messages.MSG_UPDATE_RESULTS, (stats['updates'],
                         stats['update_fails']))

  def _SplitExpression(self, expr):
    """ For an admin-typed expression, e.g. givenName=joe, split it
    into two components around the equals sign.
    Args:
      expr: as entered by the admin
    Returns: (None, None) if the expression couldn't be split, or
      attr: name of the attribute
      value: value
    """
    ix = expr.find('=')
    if ix <= 0:
      logging.error(messages.msg(messages.ERR_CANT_USE_EXPR, expr))
      return (None, None)
    attr = expr[:ix].strip()
    val = expr[ix+1:].strip()
    return (attr, val)

  def _TwoWayCompare(self, dn, google_result, google_result_old=None):
    """ Having retrieved the GAFYD result for a given user (which may be None),
    determine the correct thing to do, in consulation with the user.
    NOTE that the UserDB already has our analysis of what needs to be done for
    this user, but that was based solely on our own data. Now we have the
    google_result as well, so we get to figure it out more accurately.
    The case are, if we consider the user:
    'added'
       - google already has it, all the same data.
         Nothing to do
       - google does not have it.
         'added' is correct
       - google has it, but some data is different.
         change to 'updated'
    'exited'
      - google does not have it at all.
        Nothing to do
      - google has it.
        'exited' is correct
    'updated':
      - Google does not have it.
        change to 'added'
      - Google has it and all data is the same as we show it.
        Nothing to do
      - Google has it and it needs updating
        'updated' is correct
    'renamed'
      - Google already has the new username.
        Nothing to do (it might be we should update the new one, but not in
         this version)
      - Google does not have the old username:
        Nothing to do
      - Google has the old username
        'renamed' is correct
    Args:
      dn: DN of the user
      google_result: return value from provisioning.RetrieveAccount()
      google_result_old: return value from provisioning.RetrieveAccount()
    Return:
      act: one of ('added','exited','renamed','updated', None)
    """
    attrs = self.users.LookupDN(dn)
    for gattr in ['GoogleFirstName', 'GoogleLastName', 'GoogleUsername',
                  'GooglePassword', 'GoogleQuota']:
      if gattr not in attrs:
        logging.error(messages.msg(messages.ERR_NO_ATTR_FOR_USER, gattr))
        return

    if 'meta-Google-action' not in attrs:
      act = None
    else:
      act = attrs['meta-Google-action']

    # this code follows the comments at the top, rigorously.  If you change
    # either, please change the other
    if act == 'added':
      if google_result:
        comp = self._CompareWithGoogle(attrs, google_result)
        if not comp:
          act = None
        else:
          act = 'added'
    elif act == 'exited':
      if not google_result:
        act = None
    elif act == 'updated':
      if not google_result:
        act = 'added'
      else:
        comp = self._CompareWithGoogle(attrs, google_result)
        if not comp:
          act = None
    elif act == 'renamed':
      if google_result:
        act = None
      elif not google_result_old:
        act = None
    return act

  def _TimeFromLDAPTime(self, num):
    """ Take a time from LDAP, like 20061207194034.0Z, and convert
    to a regular Python time module time.
    Args:
      num: an LDAP time-valued attribute, or a float
    Return:
      floating point time value, per the time module
    """
    if not num:
      return None
    stime = str(num)
    try:
      tups = time.strptime(stime[:stime.find('.')], '%Y%m%d%H%M%S')
      ft = time.mktime(tups)
    except ValueError:
      logging.error('Unable to convert %s to a time' % stime)
      ft = None
    return ft

def _GetDirectoryType(attrs):
  directory_type = 'openldap'
  if 'sAMAccountName' in attrs:
    directory_type = 'ad'
  return directory_type
