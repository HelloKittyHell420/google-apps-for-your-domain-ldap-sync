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

""" Unittest for sync_ldap.py

This takes several minutes to run. The reasons for this are unavoidable:
1) it has to add, modify, and retrieve users in Google Apps for Your Domain,
which can consume several seconds per operation.
2) to make results reproducible, it has to add entries to the Active Directory
system which serves as a test server.  AD, unfortunately, will change a user
record after it's inserted, to disable it until the user changes his password,
or whatever it thinks it's doing.  (It might be possible to disable this
behavior, but I think it's desirable to operate on a "stock" AD installation,
as much as possible, since that's probably what our users will have.) This
change can happen 30 seconds or more after you insert the user, and since the
tool relies heavily on the 'whenChanged' timestamp, we just have to allow time
for AD to quiesce before we start fetching from AD.
"""

import ldap
import ldif
import logging
import os
import sys
import time
import unittest
from traceback import print_exc
from google.appsforyourdomain import provisioning
from google.appsforyourdomain import provisioning_errs
from src import utils
import pprint

from src import ldap_ctxt
from src import commands
from src import sync_ldap

#keep_attrs = set(['name', 'objectClass', 'distinguishedName',
                  #'cn', 'givenName', 'sn', 'mail', 'mailNickname',
                  #'displayName'])


###############################################################################

class ModlistFromLDIF(ldif.LDIFParser):

  """ Reads an LDIF file and creates a "modlist" suitable for the ldap.add
  or modify method.  This entails keeping only the attributes
  that can be set (e.g. 'whenChanged' can't be set).  By default it will
  generate a modlist for adds.  Call SetForMods() to make it generate a
  modify modlist (where the first entry in each tuple is MOD_ADD, MOD_REPLACE,
  or MOD_DELETE)
  """
  def __init__(self, input):
    """ Constructor.
    Args:
      input: name of ldif file
      do_mod: if true, each tuple modlist 
    """
    ldif.LDIFParser.__init__(self, input)
    self.users = {}
    self.mod_op = None

  def SetForMods(self, op):
    """ If this is set, each tuple will be a 3-tuple, where the first entry
    is MOD_ADD, MOD_REPLACE, or MOD_DELETE
    Args:
      op: one of ldap.MOD_ADD, ldap.MOD_DELETE, or ldap.MOD_REPLACE
    """
    if op == ldap.MOD_ADD or op == ldap.MOD_DELETE or op == ldap.MOD_REPLACE:
      self.mod_op = op
    else:
      raise RuntimeError('Invalid op: %d' % op)

  def handle(self, dn, entry):
    """ Reserved method name for ldif.LDIFParser
    Args:
      dn: DN of the LDAP entry
      entry: dictionary of the attributes for that entry
    """
    self.users[dn] = []
    for (attr, val) in entry.iteritems():
      if self.mod_op:
        self.users[dn].append((self.mod_op, attr, val))
      else:
        self.users[dn].append((attr, val))

class SyncLdapUnitTest(unittest.TestCase):

  def DeleteUsersLDAP(self, dns):
    """ Delete users from the LDAP server.  Usually used to reset the server
    back to a null state.
    Args:
      dns: iterable list of DNs to delete
    """
    for dn in dns:
      logging.debug("deleting in ldap user %s" % dn)
      self.ctxt.conn.delete_s(dn)

  def DisableUserLDAP(self, dn):
    """ set the various bits in the userAccountControl attr that
    correspond to an account being disabled & locked
    Args:
      dn: DN to disable.
    """
    dn = dn.lower()
    query = '(distinguishedName=%s)' % dn
    users = self.ctxt.Search(filter_arg=query,
                                  attrlist=['userAccountControl'])
    if not users or len(users) == 0:
      self.fail('failed to lookup %s' % dn)
    acct = int(users.db[dn]['userAccountControl'])
    acct = acct | 2  # disabled
    modlist = [(ldap.MOD_REPLACE, 'userAccountControl', str(acct))]
    self.ctxt.conn.modify_s(dn, modlist)

  def CleanOutLDAP(self, query):
    """ for the current LDAP server (a connection to which must already be
    open, remove all objects passing the given filter)
    Args:
      query: LDAP search filter defining the users to be removed
    """
    dns = self.ctxt.Search(filter_arg=query, attrlist=[])
    self.DeleteUsersLDAP(dns.db)

  def MultiplyUser(self, dn, modlist, base, multiple=1, suffix=None):
    """ for a given dn/modlist, "multiply" it, and add a (presumably
    unique-ifying) suffix to it.  By "multiply" we mean, create a bunch
    of copies of it, with different names.
    Args:
      parser: a ModlistFromLDIF object,which should have already
        parsed an LDIF file.
      base: the base part of the user name, e.g. 'mailuser', which
        presumably appears multiple times in the LDAP record
      multiple: the number of unique copies of each user to make
      suffix: text to be appended to base to make it unique.  If none then
        self.suffix is used
    Requires:
      self.suffix: should be a unique suffix which you want appended
        to each name, to make it unique for this run.  A good choice
        is the date-time down to the second.
    """
    new_db = {}
    for count in xrange(multiple):
      if not suffix:
        suffix = self.suffix
      rep = '%s%d-%s' % (base, count, suffix)
      self.usernames_created.insert(0, rep)
      new_dn = dn.replace(base, rep)
      rmodlist = repr(modlist)
      rmodlist = rmodlist.replace(base, rep)
      new_modlist = eval(rmodlist)
      new_db[new_dn.strip()] = new_modlist
    return new_db

  def ModUsersLDAP(self, ldif_name, base, multiple=1, mod_op=None, suffix=None):
    """ take an LDIF file and add all the users to the LDAP directory.  
    Optionally "multiply" the user, i.e. create
    a whole bunch of copies of it
    Args:
      ldif_name: unqualified name of the LDIF file to import
      base:
      multiple: # copies to make
      mod_op: if non-null, the users are modified or deleted, not added
      uniquified: a string that is appended to base to make it unique
    Return:
      set of dns of the users added
    """
    fname = os.path.join(self.datapath, ldif_name)
    f = open(fname, 'r')
    parser = ModlistFromLDIF(f)
    if mod_op:
      parser.SetForMods(mod_op)
    parser.parse()

    # make sure we got something:
    if len(parser.users) == 0:
      raise RuntimeError('No users found in %s' % ldif_name)

    #  multiply the first user in the ldif:
    dn = parser.users.keys()[0]
    modlist = parser.users[dn]
    new_users = self.MultiplyUser(dn, modlist, base, multiple, suffix)
    changes = set()
    for (dn, modlist) in new_users.iteritems():
      dn = dn.strip()
      if mod_op:
        if mod_op == ldap.MOD_REPLACE:
          logging.debug('modding in ldap %s' % dn)
          self.ctxt.conn.modify_s(dn, modlist)
        elif mod_op == ldap.MOD_DELETE:
          logging.debug('deleting in ldap %s' % dn)
          self.ctxt.conn.delete_s(dn)
      else:
        logging.debug('adding in ldap %s' % dn)
        self.ctxt.conn.add_s(dn, modlist)
      changes.add(dn.lower())
    f.close()
    return changes

  def InitWithCfg(self, cfg_name, sync=False):
    """ for a given config file name, do all the setup
    Args:
      cfg_name: name of config file
      sync: boolean for whether to sync with Google or not.
    """
    self.cname = os.path.join(self.datapath, cfg_name)
    if not os.path.exists(self.cname):
      raise RuntimeError('no file %s' % self.cname)
    parser = sync_ldap.GetParser()
    arg_str = '-c %s' % self.cname
    args = arg_str.split(' ')
    (options, args) = parser.parse_args(args)
    (self.cfg, self.ctxt, self.userdb, self.google, self.log) =\
               sync_ldap.SetupMain(options)
    self.cmd = commands.Commands(self.ctxt, self.userdb, self.google,
                                 self.cfg)
    self.ctxt.Connect()

    # we need our own instance of provisioning.API, so we can check
    # that things actually got done
    if sync:
      self.admin = self.cfg.GetAttr('admin')
      self.domain = self.cfg.GetAttr('domain')
      self.password = self.cfg.GetAttr('password')
      self.cfg.TestConfig(self, ['admin', 'domain', 'password'])
      self.api = provisioning.API(self.admin, self.password, self.domain)

  def CompareUserdbToTarget(self, target):

    """ Check that the UserDB contains exactly the DNs
    passed in, and nothing else
    Args;
      target: a set of the DNs expected to be in self.userdb
    Return:
      1) a set of those DNs in self.userdb but not in target
      2) a set of those DNs in target but not in self.users
      if the sets are equal, returns (None, None)
    """
    userdns = set(self.userdb.UserDNs())
    if userdns == target:
      return (None, None)
    else:
      return (userdns.difference(target), target.difference(userdns))

  def VerifyUsersInGoogle(self, added):
    """ for a set of DNs that should have been added to the Google
    domain, make sure they were, via asserts
    Args:
     added: iterable list of DNs
    """
    for dn in added:
      attrs = self.userdb.LookupDN(dn)
      self.assertNotEqual(attrs, None)
      self.assertAccountExists(attrs['GoogleUsername'])

  def assertAccountExists(self, account):
    try:
      gattrs = self.api.RetrieveAccount(account)
    except provisioning_errs.ObjectDoesNotExistError, e:
      self.fail(str(e))
    self.assertNotEqual(gattrs, None)

  def GetTempFile(self, test, phase, extension):
    """ Get the name of a tempfile to use, given the testing environment's
    preferences for use of temp files.
    Args:
      test: name of the test, e.g. 'basic'
      phase: a unique string for the "phase" of the test, usually
        just '1', '2', '3' etc.
      extension: the file's extension
    Returns:
      fully qualified name of temp file
    """
    fname = os.path.join(self.tmppath, '%s-%s.%s' %(test, phase, extension))
    return fname

  def WaitForAD(self, secs):
    logging.info('waiting %d seconds for ActiveDirectory to stabilize...' % 
                 secs)
    time.sleep(secs)
    logging.info('done waiting')

  def setUp(self):
    """ This unit test may want to use the same names over & over, so we need to
    start from a clean place.  So this setUp() deletes all the names under
    OU=Unittest,${LDAPDN}.
    Then it finds each ldif file in the test directory, and unique-ifies all
    the names, because when we delete a name from Dasher, we can't re-add it
    later.  It does the unique-ifying by adding in the date-time, to the
    second.
    """
    self.datapath = os.path.join('.', "testdata")
    self.usernames_created = []
    self.tmppath = '/tmp/'
    self.api = None

    # only want to do this once, so suffixes will stay the same
    if not hasattr(self, 'suffix'):
      self.suffix = time.strftime('%Y-%m-%d-%H-%M-%S')

  def tearDown(self):
    logging.debug("tearDown: called")
    if hasattr(self,'ctxt'):
      self.ctxt.Disconnect()
      self.ctxt = None
    if not self.api: 
      logging.warn("api not initialized!")
    logging.debug("tearDown: about to start deleting test accounts")
    for username in self.usernames_created:
      logging.debug("tearDown: deleting %s" % username);
      try:
        self.api.DeleteAccount(username)
      except provisioning_errs.ObjectDoesNotExistError:
        logging.debug("tearDown: deleting new%s" % username);
        try:
          self.api.DeleteAccount("new%s" % username)
        except provisioning_errs.ObjectDoesNotExistError:
          continue
        continue

    self.users = None

  def testingAddsUpdatesAndRenamesWithNoPrimaryKey(self):
    """ Adds, updates and renames work on a CFG file with no primary key.
    """
    logging.debug("testAddsUpdatesAndRenamesWithNoPrimaryKey: **********")
    self.verifyAddsUpdatesRenames('yourdomain.cfg')

  def testingAddsUpdatesAndRenamesWithPrimaryKey(self):
    """ Adds, updates and renames work on a CFG file with a primary key.
    """
    logging.debug("testAddsUpdatesAndRenamesWithPrimaryKey: **********")
    self.verifyAddsUpdatesRenames('primarykey.cfg')

  def testingExitsAreNotRetriedOnSubsequentRuns(self):
    """ Exits are not retried over and over again.  """
    self.verifyBasicConnectivity('yourdomain.cfg')

    # add one user to the directory
    added_dns = self.ModUsersLDAP('userspec.ldif', 'tuser', 1)

    # pull in the users via updateUsers command
    self.cmd.onecmd('updateUsers')

    # write it out to a tempfile
    self.cmd.onecmd('writeUsers %s' % self.GetTempFile('exitonce','1','xml'))

    # do the sync to Google
    self.cmd.onecmd('syncAllUsers')
    self.VerifyUsersInGoogle(added_dns)

    # now delete user
    dn = added_dns.pop()
    logging.debug("deleting the old dn = %s" % dn)
    self.ctxt.conn.delete_s(dn)
    self.cmd.onecmd('updateUsers')

    # write it out to a tempfile
    self.cmd.onecmd('writeUsers %s' % self.GetTempFile('exitonce','2','xml'))

    # do the sync to Google
    self.cmd.onecmd('syncAllUsers')

    # check for re-exits
    self.cmd.onecmd('updateUsers')

    # make sure the action is set to previously-exited and not exited
    attrs = self.userdb.LookupDN(dn)
    logging.debug('attrs=%s' % str(attrs))
    self.assertEquals(attrs['meta-Google-action'], 'previously-exited')

  def testingExitedUsersThatAreReExitedResultInNoError(self):
    """ Exited users that are subsequently re-exited produce no error.
    """
    self.verifyBasicConnectivity('yourdomain.cfg')

    # add one user to the directory
    added_dns = self.ModUsersLDAP('userspec.ldif', 'tuser', 1)

    # pull in the users via updateUsers command
    self.cmd.onecmd('updateUsers')

    # write it out to a tempfile
    self.cmd.onecmd('writeUsers %s' % self.GetTempFile('re-exits','1','xml'))

    # do the sync to Google
    self.cmd.onecmd('syncAllUsers')

    # now delete user in LDAP
    dn = added_dns.pop()
    logging.debug("deleting the old dn = %s" % dn)
    self.ctxt.conn.delete_s(dn)
    self.cmd.onecmd('updateUsers')

    # write it out to a tempfile
    self.cmd.onecmd('writeUsers %s' % self.GetTempFile('re-exits','2','xml'))

    # now delete user in Google Apps
    attrs = self.userdb.LookupDN(dn)
    self.api.DeleteAccount(attrs['GoogleUsername'])

    # do the sync to Google
    self.cmd.onecmd('syncAllUsers')

    # make sure no pending change action
    attrs = self.userdb.LookupDN(dn)
    if 'meta-Google-action' in attrs:
      self.assertEqual(attrs['meta-Google-action'], 'previously-exited')

  def testingExitedUsersThatAreReAddedAreUnlockedInGoogleApps(self):
    """ Exited users that are subsequently re-added get their accounts unlocked.
    """
    self.verifyBasicConnectivity('yourdomain.cfg')

    # add one user to the directory
    added_dns = self.ModUsersLDAP('userspec.ldif', 'tuser', 1)

    # pull in the users via updateUsers command
    self.cmd.onecmd('updateUsers')

    # write it out to a tempfile
    self.cmd.onecmd('writeUsers %s' % self.GetTempFile('unlocks','1','xml'))

    # do the sync to Google
    self.cmd.onecmd('syncAllUsers')

    # now delete user
    dn = added_dns.pop()
    logging.debug("deleting the old dn = %s" % dn)
    self.ctxt.conn.delete_s(dn)
    self.cmd.onecmd('updateUsers')

    # do the sync to Google
    self.cmd.onecmd('syncAllUsers')

    # reset userdb 
    self.userdb.DeleteUser(dn)

    # re-add in the users via updateUsers command
    added_dns = self.ModUsersLDAP('userspec.ldif', 'tuser', 1)
    self.cmd.onecmd('updateUsers')

    # write it out to a tempfile
    self.cmd.onecmd('writeUsers %s' % self.GetTempFile('unlocks','2','xml'))

    # do the sync to Google
    self.cmd.onecmd('syncAllUsers')

    # make sure the user is unlocked in Google Accounts
    attrs = self.userdb.LookupDN(dn)
    self.assertLockStatus(attrs['GoogleUsername'], 'unlocked')

  def testingRenamesUsingCnAsUsernameIfCnIsPartOfDn(self):
    """A rename that changes both username and dn results in GoogleUsername
    rename.
    """
    self.verifyBasicConnectivity('dnrename.cfg')

    # add one user to the directory
    added_dns = self.ModUsersLDAP('dnrename.ldif', 'tuser', 1)

    # pull in the users via updateUsers command
    self.cmd.onecmd('updateUsers')

    # write it out to a tempfile
    self.cmd.onecmd('writeUsers %s' % self.GetTempFile('dnrename','1','xml'))

    # we should now have exactly the ones we added in our userdb:
    (userdb_not_in_added, added_not_in_userdb) = (
      self.CompareUserdbToTarget(added_dns))
    self._assertSetEmpty(added_not_in_userdb)
    self._assertSetEmpty(userdb_not_in_added)

    # do the sync to Google
    self.cmd.onecmd('syncAllUsers')
    self.VerifyUsersInGoogle(added_dns)

    # now force a rename:
    time.sleep(2)  # so as to detect a time difference in whenChanged!
    # Because we cannot change the cn without doing an rdn move, fake it
    # by doing a delete and recreate of a user with the same primary_key
    dn = added_dns.pop()
    logging.debug("deleting the old dn = %s" % dn)
    self.ctxt.conn.delete_s(dn)
    mods = self.ModUsersLDAP('dnrename.ldif', 'tuser', 1, 
        suffix='%s-B' % self.suffix)
    self.cmd.onecmd('updateUsers')

    # write it out to a tempfile
    self.cmd.onecmd('writeUsers %s' % self.GetTempFile('dnrename','3','xml'))

    # do the sync to Google
    self.cmd.onecmd('syncAllUsers')

    # check the users we just modded & be sure they were renamed
    logging.debug("renamed users are %s" % str(mods))
    for dn in mods:
      attrs = self.userdb.LookupDN(dn)
      logging.debug('attrs=%s' % str(attrs))
      self.assertMetaGoogleActionEmpty(attrs)
      self.assertAccountExists(attrs['GoogleUsername'])

  def testingRenamesWithObjectGUIDAsPrimaryKey(self):
    """ Adds, updates and renames work on a CFG file with objectGUID as primary
    key.  """
    logging.debug("testRenamesWithObjectGUIDAsPrimaryKey: **********")
    self.verifyAddsUpdatesRenames('objectGUID.cfg')

  def testingBasicTls(self):
    """ Connecting to ldap via TLS throws no errors."""
    logging.debug("testBasicTls: **********")
    self.verifyBasicConnectivity('yourdomainTls.cfg')

  def testingDeleteOfUser(self):
    """ Deletion of user in ldap propagates to google apps """
    logging.debug("testDeleteOfUser: **********")
    self.InitWithCfg('yourdomain.cfg', True)
    
    # clean out all the DNs currently in this branch of the tree
    logging.debug('--- cleanning up users in this part of ldap tree')
    self.CleanOutLDAP('(objectclass=organizationalPerson)')

    # add some users to the directory
    added = self.ModUsersLDAP('userspec.ldif', 'tuser', 1)
    dn = added.pop()  

    # pull in the users via updateUsers command
    self.cmd.onecmd('updateUsers')

    # write it out to a tempfile
    self.cmd.onecmd('writeUsers %s' % self.GetTempFile('delete','1','xml'))

    # do the sync to Google
    self.cmd.onecmd('syncAllUsers')
    self.VerifyUsersInGoogle(added)

    # get username
    attrs = self.userdb.LookupDN(dn)
    username = attrs['GoogleUsername']

    # delete the user at this dn
    logging.debug('--- deleting users for deletion test')
    self.ctxt.conn.delete_s(dn)
    #self.CleanOutLDAP('(objectclass=organizationalPerson)')

    # pull in the users via updateUsers command
    self.cmd.onecmd('updateUsers')

    # write it out to a tempfile
    self.cmd.onecmd('writeUsers %s' % self.GetTempFile('delete','2','xml'))

    # do the sync to Google
    logging.debug('--- running syncAllUsers')
    self.cmd.onecmd('syncAllUsers')
 
    # make sure the delete was pushed to Google
    logging.debug('--- searching google for deleted account %s' % username)
    self.assertLockStatus(username, 'locked')

  def assertLockStatus(self, username, status):
    gattrs = self.api.RetrieveAccount(username)
    self.assertEqual(gattrs['accountStatus'], status)

  def verifyBasicConnectivity(self, file):
    """ test that connecting to ldap works 
    """

    self.InitWithCfg(file, True)

    # clean out all the DNs currently in this branch of the tree
    self.CleanOutLDAP('(objectclass=organizationalPerson)')

    # test connection
    self.cmd.onecmd('connect')

  def _assertSetEmpty(self, value):
    if value:
      self.assertEqual(value, set([]))
      return
    self.assertEqual(value, None)

  def testingModificationTimeIsUpdatedOnlyAfterCompleteSuccess(self):
    """ Test that modification time is not updated if an error occurs. """
    logging.debug("testModificationTime...: **********")
    self.verifyBasicConnectivity('yourdomain.cfg')

    # add some users to the directory
    added_dns = self.ModUsersLDAP('userspec.ldif', 'tuser', 1)
    added_dns.update(self.ModUsersLDAP('userspecb.ldif', 'tuserb', 1))
    logging.debug(
        "testModificationTimeTimingUnderErrorForFirstLastNameRename:"
        "added_dns=%s" % str(added_dns))

    # pull in the users via updateUsers command
    self.cmd.onecmd('updateUsers')

    # write it out to a tempfile
    self.cmd.onecmd('writeUsers %s' % self.GetTempFile('timing','1',
      'xml'))

    # do the sync to Google
    self.cmd.onecmd('syncAllUsers')
    _LogObjectValue('added_dns=', added_dns)
    self.VerifyUsersInGoogle(added_dns)

    # now modify some of them, and make sure those get flagged properly
    time.sleep(2)  # so as to detect a time difference in whenChanged!
    mods = self.ModUsersLDAP('userspec-mod.ldif', 'tuser', 1, ldap.MOD_REPLACE)
    time.sleep(2)  # so as to detect a time difference in whenChanged!
    to_be_changed = self.ModUsersLDAP('userspec-modb.ldif', 'tuserb', 1, 
      ldap.MOD_REPLACE)
    mods.update(to_be_changed)
    _LogObjectValue('mods are ', mods)

    # pull in the users via updateUsers command
    self.cmd.onecmd('updateUsers')

    # create a condition where the second user fails in syncAllUsers
    dn_to_change = to_be_changed.pop()
    logging.debug("dn_to_change: %s" % dn_to_change)
    attr_values = self.userdb.LookupDN(dn_to_change)
    changed_username = attr_values["GoogleUsername"]
    self.userdb.db[dn_to_change]["GoogleUsername"] = "tuser-hidden"
    _LogObjectValue('userdb after creating bad condition: ', self.userdb.db)

    # write it out to a tempfile
    self.cmd.onecmd('writeUsers %s' % self.GetTempFile('timing','2', 'xml'))

    # do a sync to Google
    self.cmd.onecmd('syncAllUsers')

    # fix the condition where the second user had failed
    attr_values = self.userdb.LookupDN(dn_to_change)
    self.userdb.db[dn_to_change]["GoogleUsername"] = changed_username
    
    # do a sync to Google.  The second user should be handled.  If not it is
    # a problem with tracking last modified time
    self.cmd.onecmd('syncAllUsers')

    # verify that Google got both changes
    for dn in mods:
      logging.debug("checking dn = %s" % dn)
      attrs = self.userdb.LookupDN(dn)

      # syncAllUsers should have nulled-out the meta-Google-action field
      self.assertMetaGoogleActionEmpty(attrs)

      # make sure it was pushed to Google
      gattrs = self.api.RetrieveAccount(attrs['GoogleUsername'])
      logging.debug('gattrs=%s' % str(gattrs))
      self.assertNotEqual(gattrs, None)
      self.assertEqual(str(gattrs['firstName']), attrs['GoogleFirstName'])

  def verifyAddsUpdatesRenames(self, file, ldifbasename='userspec'):
    self.verifyBasicConnectivity(file)

    # add some users to the directory
    added_dns = self.ModUsersLDAP('%s.ldif' % ldifbasename, 'tuser', 2)

    # unfortunately, AD will change this account, anywhere up to 30 seconds
    # later, and we really need things to stabilize for the time-based
    # filter to work.  So:
    self.WaitForAD(30)

    # pull in the users via updateUsers command
    self.cmd.onecmd('updateUsers')

    # write it out to a tempfile
    self.cmd.onecmd('writeUsers %s' % self.GetTempFile('basic','1','xml'))

    # we should now have exactly the ones we added in our userdb:
    (userdb_not_in_added, added_not_in_userdb) = (
      self.CompareUserdbToTarget(added_dns))
    self._assertSetEmpty(added_not_in_userdb)
    self._assertSetEmpty(userdb_not_in_added)

    # do the sync to Google
    self.cmd.onecmd('syncAllUsers')
    self.VerifyUsersInGoogle(added_dns)

    # now modify some of them, and make sure those get flagged properly

    time.sleep(2)  # so as to detect a time difference in whenChanged!
    mods = self.ModUsersLDAP('%s-mod.ldif' % ldifbasename, 'tuser', 1, 
        ldap.MOD_REPLACE)

    self.cmd.onecmd('updateUsers')

    # write it out to a tempfile
    self.cmd.onecmd('writeUsers %s' % self.GetTempFile('basic','2','xml'))

    # do the sync to Google
    self.cmd.onecmd('syncAllUsers')

    # we should have the users we just modded as 'update'
    for dn in mods:
      attrs = self.userdb.LookupDN(dn)

      # syncAllUsers should have nulled-out the meta-Google-action field
      self.assertMetaGoogleActionEmpty(attrs)

      # make sure it was pushed to Google
      gattrs = self.api.RetrieveAccount(attrs['GoogleUsername'])
      logging.debug('gattrs=%s' % str(gattrs))
      self.assertNotEqual(gattrs, None)
      self.assertEqual(str(gattrs['firstName']), attrs['GoogleFirstName'])

    # now force a rename:
    time.sleep(2)  # so as to detect a time difference in whenChanged!
    mods = self.ModUsersLDAP('%s-rename.ldif' % ldifbasename, 'tuser', 1,
                             ldap.MOD_REPLACE)
    self.cmd.onecmd('updateUsers')

    # do the sync to Google
    self.cmd.onecmd('syncAllUsers')

    # write it out to a tempfile
    self.cmd.onecmd('writeUsers %s' % self.GetTempFile('basic','3','xml'))

    # check the users we just modded & be sure they were renamed
    for dn in mods:
      attrs = self.userdb.LookupDN(dn)
      logging.debug('attrs=%s' % str(attrs))

      # syncAllUsers should have nulled-out the meta-Google-action field
      self.assertMetaGoogleActionEmpty(attrs)

      self.assertAccountExists(attrs['GoogleUsername'])


  def testingNoDisabledFilter(self):
    """ Users get marked as exited when deleted from ldap (no disabled filter).

    Since the algorithm for detecting exited employees is different
    if there's no 'ldap_disabled_filter' parm, this tests that case
    """
    logging.debug("testNoDisabledFilter: ************")
    self.InitWithCfg('yourdomain-no-disabled.cfg', True)
    # clean out all the DNs currently in this branch of the tree
    self.CleanOutLDAP('(objectclass=organizationalPerson)')

    # add two users to the directory
    added = self.ModUsersLDAP('no-disabled.ldif', 'tuser', 2)

    # unfortunately, AD will change this account, anywhere up to 30 seconds
    # later, and we really need things to stabilize for the time-based
    # filter to work.  So:
    #self.WaitForAD(30)

    # pull in the users via updateUsers command
    self.cmd.onecmd('updateUsers')

    # write it out to a tempfile
    self.cmd.onecmd('writeUsers %s' % self.GetTempFile('no-disabled','1','xml'))

    # we should now have exactly the ones we added in our userdb:
    (userdb_not_in_added, added_not_in_userdb) = (
      self.CompareUserdbToTarget(added))
    self._assertSetEmpty(added_not_in_userdb)
    self._assertSetEmpty(userdb_not_in_added)

    # do the sync to Google
    self.cmd.onecmd('syncAllUsers')

    # delete one of the users from LDAP
    exited = self.ModUsersLDAP('no-disabled.ldif', 'tuser', 1, ldap.MOD_DELETE)

    # pull in the users via updateUsers command
    self.cmd.onecmd('updateUsers')

    # write it out to a tempfile
    self.cmd.onecmd('writeUsers %s' % self.GetTempFile('no-disabled','2','xml'))

    # be sure our exited really is marked 'exited', and nothing else is
    for dn in self.userdb.UserDNs():
      attrs = self.userdb.LookupDN(dn)
      logging.debug('dn=%s, attrs=%s' % (dn, str(attrs)))
      if dn in exited:
        self.assertEqual(attrs['meta-Google-action'], 'exited')
      else:
        self.assertMetaGoogleActionEmpty(attrs)

  def assertMetaGoogleActionEmpty(self, attrs):
    if not attrs:
      self.fail()
    if 'meta-Google-action' in attrs:
      self.assertTrue(not attrs['meta-Google-action'])
    # TODO(rescorcio): come back to this.  This used to check for not 'exited'

  def testingNoExceptions(self):
    """ Try lots of misuses of the tool, and be sure exceptions are caught.
    """
    logging.debug("testNoExceptions: **************")

    try:
      # all sorts of LDAP abuse:
      try:
        self.InitWithCfg('bad1.cfg')
        self.fail('should have failed for lack of ldap_url')
      except utils.ConfigError:
        pass
      try:
        self.InitWithCfg('bad2.cfg')
        self.fail('should have failed for lack of ldap_url')
      except utils.ConfigError:
        pass

      self.cmd.onecmd('updateUsers')
      self.InitWithCfg('bad6.cfg')
      self.cmd.onecmd('updateUsers')
      self.InitWithCfg('bad7.cfg')
      self.cmd.onecmd('updateUsers')
      self.cmd.onecmd('disconnect')
      self.cmd.onecmd('updateUsers')

      # giving bad data to the various commands:
      self.cmd.onecmd('attrList foo')
      self.cmd.onecmd('attrList add lkjskjsdfsd')
      self.cmd.onecmd('attrList remove oajdaksdjf')
      self.cmd.onecmd('attrList foo')
      self.cmd.onecmd('mapGoogleAttribute GoogleUserklsjfsjdf foo')
      self.cmd.onecmd('mapGoogleAttribute GoogleUsername foo')
      self.cmd.onecmd('mapGoogleAttribute GoogleFirstName foo')
      self.cmd.onecmd('mapGoogleAttribute GoogleUsername 1/0')
      self.cmd.onecmd('markUsers foobar')
      self.cmd.onecmd('readUsers foobar')
      self.cmd.onecmd('writeUsers foobar')
      self.cmd.onecmd('setTimestamp foobar')
      self.cmd.onecmd('showUsers foobar')
      self.cmd.onecmd('testFilter oiajdfojadflkajdfajdf')

      # now read in a good config file, so we can try other stuff:
      self.InitWithCfg('yourdomain.cfg')
      self.cmd.onecmd('mapGoogleAttribute GoogleUsername mailNickname')
      # a non-existent attribute:
      self.cmd.onecmd('mapGoogleAttribute GoogleUsername lkjsdkljsdfjsdf')
    except Exception, e:
      """ Yes, this really does want to be "except Exception". We want to catch
      any exceptions raised by the tool, REGARDLESS of what they are, and have 
      the test tool's output give us useful data.
      """
      print_exc()
      self.fail('Exception not caught that should have been: %s' % str(e))

  def testingSyncOne(self):
    """ Test deletion and updates of ldap users propagate with SyncOneUser cmd.
    """
    logging.debug("testSyncOne: **********")
    self.InitWithCfg('yourdomain.cfg', True)

    # clean out all the DNs currently in this branch of the tree
    self.CleanOutLDAP('(objectclass=organizationalPerson)')

    # add one user to the directory
    added = self.ModUsersLDAP('syncspec.ldif', 'tuser', 1)
    logging.debug('added=%s' % str(added))
    self.WaitForAD(30)

    # pull in the users via updateUsers command
    self.cmd.onecmd('updateUsers')

    # write it out to a tempfile
    self.cmd.onecmd('writeUsers %s' % self.GetTempFile('sync','1','xml'))

    # if we sync this one user, it should add him to the database and then
    # to google

    # first we want to be sure what the username is:
    for dn in added:
      break
    attrs = self.userdb.LookupDN(dn)
    self.assertNotEqual(attrs, None)
    name = attrs['name']
    username = attrs['GoogleUsername']
    mail = attrs['mail']
    index_of_at = mail.find('@')
    if index_of_at == -1:
      self.fail('mail field must contain an @ sign')
      return
    self.assertEqual(mail[:index_of_at], username)

    # now delete it from userdb, so sync will have something to do:
    self.userdb.DeleteUser(dn)
    self.cmd.onecmd('syncOneUser -f name=%s' % name)
    self.VerifyUsersInGoogle(added)

    # update it in LDAP, so we can test that
    self.ModUsersLDAP('syncspec-mod.ldif', 'tuser', 1, ldap.MOD_REPLACE)
    self.cmd.onecmd('syncOneUser -f name=%s' % name)
    self.assertAccountExists(attrs['GoogleUsername'])

def _LogObjectValue(message, value):
  pp = pprint.PrettyPrinter()
  logging.debug('%s %s' % (message, pp.pformat(value)))


def main():
  logging.basicConfig(level=9,
      format='%(asctime)s %(levelname)-8s %(message)s', datefmt='%m-%d %H:%M')
  unittest.main()

if __name__ == '__main__':
  main()
