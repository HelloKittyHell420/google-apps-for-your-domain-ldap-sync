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
import provisioning_api_mock
import string
import random

from src import ldap_ctxt
from src import commands
from src import sync_ldap

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
    users = self.ctxt.Search(filter_arg=query, attrlist=['userAccountControl'])
    if not users or len(users) == 0:
      self.fail('failed to lookup %s' % dn)
    acct = int(users.db[dn]['userAccountControl'])
    acct = acct | 2  # disabled
    modlist = [(ldap.MOD_REPLACE, 'userAccountControl', str(acct))]
    self.ctxt.conn.modify_s(dn, modlist)

  def CleanOutLDAP(self):
    """ for the current LDAP server (a connection to which must already be
    open, remove all objects passing the given filter)
    """
    query = ('(&(objectClass=organizationalPerson)(cn=tuser%s*))' %
        self.suffix)
    saved = self.ctxt.ldap_page_size
    self.ctxt.ldap_page_size = 1000   # in case there are a lot of leftovers
    dns = self.ctxt.Search(filter_arg=query, attrlist=[])
    if dns:
      self.DeleteUsersLDAP(dns.db)
    self.ctxt.ldap_page_size = saved  # change back to previous value

  def MultiplyUser(self, dn, modlist, base, multiple=1, suffix=None):
    """ for a given dn/modlist, "multiply" it, and add a (presumably
    unique-ifying) suffix to it.  By "multiply" we mean, create a bunch
    of copies of it, with different names.
    Args:
      parser: a ModlistFromLDIF object,which should have already
        parsed an LDIF file.
      base: the base part of the user name, e.g. 'mailuser', which
        must match the ldif record username
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
      rep = '%s%s%d' % (base, suffix, count)
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
          logging.debug('MOD_REPLACE in ldap %s' % dn)
          self.ctxt.conn.modify_s(dn, modlist)
        elif mod_op == ldap.MOD_DELETE:
          logging.debug('MOD_DELETE in ldap %s' % dn)
          self.ctxt.conn.delete_s(dn)
      else:
        logging.debug('adding in ldap dn=%s' % dn)
        self.ctxt.conn.add_s(dn, modlist)
      changes.add(dn.lower())
    f.close()
    return changes

  def InitWithCfg(self, cfg_name, init_api=False):
    """ for a given config file name, do all the setup
    Args:
      cfg_name: name of config file
      init_api: boolean for whether to initialize the provisioning api or not.
    """
    self.cname = os.path.join(self.datapath, cfg_name)
    if not os.path.exists(self.cname):
      raise RuntimeError('no file %s' % self.cname)
    parser = sync_ldap.GetParser()
    arg_str = '-c %s' % self.cname
    args = arg_str.split(' ')
    (options, args) = parser.parse_args(args)
    self.provisioning_api = provisioning_api_mock
    (self.cfg, self.ctxt, self.userdb, self.google, self.log) =\
        sync_ldap.SetupMain(options, api=self.provisioning_api)
    self.cmd = commands.Commands(self.ctxt, self.userdb, self.google, self.cfg)
    self.ctxt.Connect()

    # we need our own instance of provisioning.API, so we can check
    # that things actually got done
    if init_api:
      self.admin = self.cfg.GetAttr('admin')
      self.domain = self.cfg.GetAttr('domain')
      self.password = self.cfg.GetAttr('password')
      self.cfg.TestConfig(self, ['admin', 'domain', 'password'])
      self.api = provisioning.API(self.admin, self.password, self.domain)

  def InitTUserFilter(self):
    self.cmd.onecmd(
        'set ldap_user_filter (&%s(|(cn=tuser%s*)(cn=tuserb%s*)))' % (
            self.ctxt.ldap_user_filter, self.suffix, self.suffix))

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
    """ Get the name of a tempfile to use, given the test environment's
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
    self.tmppath = './'
    self.api = None
    self.skip_deleting_test_accounts = False

    # only want to do this once, so suffixes will stay the same
    rand_gen = random.Random()
    if not hasattr(self, 'suffix'):
      self.suffix = "%s" % rand_gen.randint(0, 1000000)

  def tearDown(self):
    provisioning_api_mock.CREATE_USER_EXCEPTION = None
    logging.debug("tearDown: called")
    if hasattr(self,'ctxt'):
      self.ctxt.Disconnect()
      self.ctxt = None
    if not self.api: 
      logging.warn("api not initialized!")
      return
    if self.skip_deleting_test_accounts:
      return
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

  def testOpenLdapNonPaging(self):
    """ Directories that don't require paging can retrieve more than 1000 users.
    """
    logging.debug('testOpenLdapNonPaging: **********')
    self.InitWithCfg('openldap.cfg', False)
    found = self.ctxt.Search(attrlist=[], sizelimit=1002)
    if not found:
      self.fail('Empty results retruned from paged ldap search')
    self.assertTrue(len(found.UserDNs()) >= 1001)

  def testAddsUpdatesAndRenamesWithNoPrimaryKey(self):
    """ Adds, updates and renames work on a CFG file with no primary key.  """
    # TODO: this test is flakey.  Get ProvisioningApiError: Object does not
    # exist error.  Often.
    logging.debug("testAddsUpdatesAndRenamesWithNoPrimaryKey: **********")
    self.verifyAddsUpdatesRenames('yourdomain.cfg', outfile='noprikey')

  def testAddsUpdatesAndRenamesWithUtf8FirstAndLastNamesInXmlFile(self):
    """ All operations work on an XML userdb containing utf8 chars. """
    # TODO: this test is flakey
    logging.debug("testAddsUpdatesAndRenamesWithUtf8FirstAndLastNames: *******")
    self.verifyAddsUpdatesRenames('yourdomain.cfg', 
        ldifbasename='userspec_utf-8', outfile='utf-8')

  def testAddsUpdatesAndRenamesWithUtf8FirstAndLastNamesInCsvFile(self):
    """ All operations work on a CSV userdb containing utf8 chars."""
    logging.debug("testAddsUpdatesAndRenamesWithUtf8FirstAndLastNames: *******")
    self.verifyAddsUpdatesRenames('yourdomain.cfg', 
        ldifbasename='userspec_utf-8', outfile='utf-8', ext='csv')

  def testLdapPagingForAddsModsAndRenames(self):
    """ Paging of LDAP results works for adds, renames, and updates.  """
    logging.debug("testLdapPagingForAddsModsAndRenames: **********")
    # The following tests adds, updates, and renames page properly
    # because ldap_page_size is 2 in paging.cfg.
    self.verifyAddsUpdatesRenames('paging.cfg', usersadded=4, usersmoded=3,
        outfile='ldapPaging')

  def testLdapPagingWorksOnAdFor1001Users(self):
    """ Paging of LDAP results works for the 1002 user case.  """
    logging.debug("testLdapPagingWorksOnAdFor1002Users: **********")
    self.skip_deleting_test_accounts = True
    # The following tests added users page properly
    # because ldap_page_size is 1000 in paging1000.cfg.
    self.addUsersAndVerifyTheyShowInUserDb('paging1000.cfg', usersadded=1002)

  def testAddsUpdatesAndRenamesWithPrimaryKey(self):
    """ Adds, updates and renames work on a CFG file with a primary key.
    """
    logging.debug("testAddsUpdatesAndRenamesWithPrimaryKey: **********")
    self.verifyAddsUpdatesRenames('primarykey.cfg', outfile='prikey')

  def testExitsAreNotRetriedOnSubsequentRuns(self):
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
    self.assertActionIs(dn, 'previously-exited')

  def IsAction(self, dn, action):
    if self.isMetaGoogleActionEmpty(dn): 
      return False
    attrs = self.userdb.LookupDN(dn)
    if 'meta-Google-action' in attrs:
      if action == attrs['meta-Google-action']:
        return True
    return False

  def assertActionIs(self, dn, action):
    self.assertTrue(self.IsAction(dn, action))

  def assertActionIsNot(self, dn, action):
    self.assertFalse(self.IsAction(dn, action))

  def assertMetaLastUpdatedUnset(self, dn):
    attrs = self.userdb.LookupDN(dn)
    if not 'meta-last-updated' in attrs:
      return
    logging.debug("assertMetaLastUpdatedUnset: meta-last-updated=[%s]" %
      attrs['meta-last-updated'])
    if not attrs['meta-last-updated']:
      return
    if not string.strip(attrs['meta-last-updated']):
      return
    self.fail("meta-last-updated was set after an error")

  def testAttributesInvaldatedOnError(self):
    """ meta-last-updated is unset on an error (to invalidate attributes). """
    logging.debug("testAttributesInvaldatedOnError*******")
    self.verifyBasicConnectivity('yourdomain.cfg')

    # add one user to the directory
    added_dns = self.ModUsersLDAP('userspec.ldif', 'tuser', 1)

    # pull in the users via updateUsers command
    self.cmd.onecmd('updateUsers')

    # write it out to a tempfile
    self.cmd.onecmd('writeUsers %s' % self.GetTempFile('resetonerr','1','xml'))

    # do the sync to Google
    self.cmd.onecmd('syncAllUsers')

    # write it out to a tempfile
    self.cmd.onecmd('writeUsers %s' % self.GetTempFile('resetonerr','2','xml'))

    # verify that meta-last-updated was set
    dn = added_dns.pop()
    attrs = self.userdb.LookupDN(dn)
    if not 'meta-last-updated' in attrs:
      self.fail("meta-last-updated was not set")
    
    # now delete user in LDAP
    logging.debug("deleting the old dn = %s" % dn)
    self.ctxt.conn.delete_s(dn)
    self.cmd.onecmd('updateUsers')

    # make sure action is handled
    self.assertActionIsNot(dn, 'added')

    # do the sync to Google
    self.cmd.onecmd('syncAllUsers')

    # add same user back to the directory
    added_dns = self.ModUsersLDAP('userspec.ldif', 'tuser', 1, 
        suffix=self.suffix)

    # pull in the users via updateUsers command
    self.cmd.onecmd('updateUsers')

    # write it out to a tempfile
    self.cmd.onecmd('writeUsers %s' % self.GetTempFile('resetonerr','3','xml'))

    # setup an exception
    provisioning_api_mock.SetCreateUserException(
       provisioning_errs.ProvisioningApiError, "fake reason", "fake ext msg")

    # do the sync to Google
    self.cmd.onecmd('syncAllUsers')

    # write it out to a tempfile
    self.cmd.onecmd('writeUsers %s' % self.GetTempFile('resetonerr','4','xml'))

    # verify that meta-last-updated was unset
    self.assertMetaLastUpdatedUnset(dn)
    
    # do not throw an exception
    provisioning_api_mock.SetCreateUserException(None)

    # pull in the users via updateUsers command
    self.cmd.onecmd('updateUsers')

    # write it out to a tempfile
    self.cmd.onecmd('writeUsers %s' % self.GetTempFile('resetonerr','5','xml'))

    # do the sync to Google
    self.cmd.onecmd('syncAllUsers')

    # TODO: this test is flakey.  Sometimes the create account succeeds but
    # the action remains 'added'

    # make sure added action was handled
    self.assertActionIsNot(dn, 'added')

  # TODO: need to add tests of non-ProvisioningApiErrors that can happen
  # to verify they clear out meta-last-updated on error

  def testUserAlreadyExistsErrorOnAddIsTreatedAsSuccess(self):
    """ After UserAlreadyExists error during add the added action is cleared."""
    logging.debug("testUserAlreadyExistsErrorOnAddIsTreatedAsSuccess*******")
    self.verifyBasicConnectivity('yourdomain.cfg')

    # add one user to the directory
    added_dns = self.ModUsersLDAP('userspec.ldif', 'tuser', 1)

    # pull in the users via updateUsers command
    self.cmd.onecmd('updateUsers')

    # write it out to a tempfile
    self.cmd.onecmd('writeUsers %s' % self.GetTempFile('actncleared','1','xml'))

    # do the sync to Google
    self.cmd.onecmd('syncAllUsers')

    dn = added_dns.pop()

    # delete the user in userdb
    self.userdb.DeleteUser(dn)

    # Force ldap user time stamp to change so that it appears in the search.
    # Because the userdb entry is deleted, it doesn't know this is a mod
    # and treats it as an add
    time.sleep(2)  # so as to detect a time difference in whenChanged!
    mods = self.ModUsersLDAP('userspec-mod.ldif', 'tuser', 1, ldap.MOD_REPLACE)

    # pull in the users via updateUsers command
    self.cmd.onecmd('updateUsers')

    # write it out to a tempfile
    self.cmd.onecmd('writeUsers %s' % self.GetTempFile('actncleared','2','xml'))

    # do the sync to Google, resulting in UserAlreadyExists error
    self.cmd.onecmd('syncAllUsers')

    # write it out to a tempfile
    self.cmd.onecmd('writeUsers %s' % self.GetTempFile('actncleared','3','xml'))

    # make sure added action is cleared
    self.assertActionIsNot(dn, 'added')

  def testAddedActionPreservedAfterError(self):
    """ After an error during add the added action remains as long as it is 
    not handled."""
    logging.debug("testAddedActionPreservedAfterError*******")
    self.verifyBasicConnectivity('yourdomain.cfg')

    # add one user to the directory
    added_dns = self.ModUsersLDAP('userspec.ldif', 'tuser', 1)

    # pull in the users via updateUsers command
    self.cmd.onecmd('updateUsers')

    # write it out to a tempfile
    self.cmd.onecmd('writeUsers %s' % self.GetTempFile('actnpersist','1','xml'))

    # do the sync to Google
    self.cmd.onecmd('syncAllUsers')

    # now delete user in Google Apps
    dn = added_dns.pop()
    attrs = self.userdb.LookupDN(dn)
    self.api.DeleteAccount(attrs['GoogleUsername'])

    # delete the user in userdb
    self.userdb.DeleteUser(dn)

    # Force ldap user time stamp to change so that it appears in the search.
    # Because the userdb entry is deleted, it doesn't know this is a mod
    # and treats it as an add
    time.sleep(2)  # so as to detect a time difference in whenChanged!
    mods = self.ModUsersLDAP('userspec-mod.ldif', 'tuser', 1, ldap.MOD_REPLACE)

    # pull in the users via updateUsers command
    self.cmd.onecmd('updateUsers')

    # write it out to a tempfile
    self.cmd.onecmd('writeUsers %s' % self.GetTempFile('actnpersist','2','xml'))

    # do the sync to Google, resulting in DeletedUserExists error
    self.cmd.onecmd('syncAllUsers')

    # write it out to a tempfile
    self.cmd.onecmd('writeUsers %s' % self.GetTempFile('actnpersist','3','xml'))

    # make sure added action is still shown 
    self.assertActionIs(dn, 'added')

    # pull in the users via updateUsers command
    self.cmd.onecmd('updateUsers')

    # write it out to a tempfile
    self.cmd.onecmd('writeUsers %s' % self.GetTempFile('actnpersist','4','xml'))

    # do the sync to Google, resulting in DeletedUserExists error
    self.cmd.onecmd('syncAllUsers')

    # make sure added action is still shown 
    self.assertActionIs(dn, 'added')

  def testReaddedUsersWithNoQuotaAreReadded(self):
    """ Readded users that have no quota are readded """
    logging.debug("testReaddedUsersWithNoQuotaAreReadded*******")
    self.verifyBasicConnectivity('yourdomainNoQuota.cfg')

    # add one user to the directory
    added_dns = self.ModUsersLDAP('userspec.ldif', 'tuser', 1)

    # pull in the users via updateUsers command
    self.cmd.onecmd('updateUsers')

    # write it out to a tempfile
    self.cmd.onecmd('writeUsers %s' % 
        self.GetTempFile('readdnoquota','1','xml'))

    # do the sync to Google
    self.cmd.onecmd('syncAllUsers')

    # now delete user in LDAP
    dn = added_dns.pop()
    logging.debug("deleting the old dn = %s" % dn)
    self.ctxt.conn.delete_s(dn)
    self.cmd.onecmd('updateUsers')

    # make sure action is handled
    self.assertActionIsNot(dn, 'added')

    # do the sync to Google
    self.cmd.onecmd('syncAllUsers')

    # add same user back to the directory
    added_dns = self.ModUsersLDAP('userspec.ldif', 'tuser', 1, 
        suffix=self.suffix)

    self.cmd.onecmd('updateUsers')

    # write it out to a tempfile
    self.cmd.onecmd('writeUsers %s' % 
        self.GetTempFile('readdnoquota','2','xml'))

    # make sure added action is shown
    attrs = self.userdb.LookupDN(dn)
    self.assertActionIs(dn, 'added')

    # do the sync to Google
    self.cmd.onecmd('syncAllUsers')

    # make sure no action is shown (it was handled)
    attrs = self.userdb.LookupDN(dn)
    self.assertMetaGoogleActionEmpty(dn)


  def testExitedUsersThatAreReaddedAreNotSkipped(self):
    """ Exited users that are readded are not skipped due to same attrs """
    logging.debug(
        "testExitedUsersThatAreReaddedAreNotSkipped*******")
    self.verifyBasicConnectivity('yourdomain.cfg')

    # add one user to the directory
    added_dns = self.ModUsersLDAP('userspec.ldif', 'tuser', 1)

    # pull in the users via updateUsers command
    self.cmd.onecmd('updateUsers')

    # write it out to a tempfile
    self.cmd.onecmd('writeUsers %s' % 
        self.GetTempFile('readdreattempts','1','xml'))

    # do the sync to Google
    self.cmd.onecmd('syncAllUsers')

    dn = added_dns.pop()

    # make sure action is handled
    self.assertActionIsNot(dn, 'added')

    # now delete user in LDAP
    logging.debug("deleting the old dn = %s" % dn)
    self.ctxt.conn.delete_s(dn)
    self.cmd.onecmd('updateUsers')

    # TODO: this test is flakey.  Inexplicably the following assertion often 
    # fails

    # make sure action is handled
    self.assertActionIsNot(dn, 'added')

    # do the sync to Google
    self.cmd.onecmd('syncAllUsers')

    # add same user back to the directory
    added_dns = self.ModUsersLDAP('userspec.ldif', 'tuser', 1, 
        suffix=self.suffix)

    self.cmd.onecmd('updateUsers')

    # write it out to a tempfile
    self.cmd.onecmd('writeUsers %s' % 
        self.GetTempFile('readdreattempts','2','xml'))

    # make sure added action is shown
    attrs = self.userdb.LookupDN(dn)
    self.assertActionIs(dn, 'added')

  def testExitingAUserThatNoLongerExistsResultInNoError(self):
    """ Exiting a user that no longer exists results in no error.  """
    logging.debug("testingExitingAUserThatNoLongerExistsResultInNoError: ****")
    self.verifyBasicConnectivity('yourdomain.cfg')

    # add one user to the directory
    added_dns = self.ModUsersLDAP('userspec.ldif', 'tuser', 1)

    # pull in the users via updateUsers command
    self.cmd.onecmd('updateUsers')

    # write it out to a tempfile
    self.cmd.onecmd('writeUsers %s' % self.GetTempFile('readd2','1','xml'))

    # do the sync to Google
    self.cmd.onecmd('syncAllUsers')

    # write it out to a tempfile
    self.cmd.onecmd('writeUsers %s' % self.GetTempFile('readd2','2','xml'))

    # now delete user in LDAP
    dn = added_dns.pop()
    logging.debug("deleting the old dn = %s" % dn)
    self.ctxt.conn.delete_s(dn)
    self.cmd.onecmd('updateUsers')

    # write it out to a tempfile
    self.cmd.onecmd('writeUsers %s' % self.GetTempFile('readd2','3','xml'))

    # now delete user in Google Apps
    attrs = self.userdb.LookupDN(dn)
    self.api.DeleteAccount(attrs['GoogleUsername'])

    # do the sync to Google
    self.cmd.onecmd('syncAllUsers')

    # write it out to a tempfile
    self.cmd.onecmd('writeUsers %s' % self.GetTempFile('readd2','4','xml'))

    # make sure change action is previously-exited
    self.assertActionIs(dn, 'previously-exited')

  def testExitedUsersThatAreReAddedAreUnlockedInGoogleApps(self):
    """ Exited users that are subsequently re-added get their accounts unlocked.
    """
    logging.debug(
        "testExitedUsersThatAreReAddedAreUnlockedInGoogleApps: **********")
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

  def testRenamesUsingCnAsUsernameIfCnIsPartOfDn(self):
    """A rename that changes both username and dn results in GoogleUsername
    rename.
    """
    logging.debug("testRenamesUsingCnAsUsernameIfCnIsPartOfDn: **********")
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
      self.assertMetaGoogleActionEmpty(dn)
      attrs = self.userdb.LookupDN(dn)
      self.assertAccountExists(attrs['GoogleUsername'])

  def testRenamesWithObjectGUIDAsPrimaryKey(self):
    """ Adds, updates and renames work on a CFG file with objectGUID as primary
    key.  """
    logging.debug("testRenamesWithObjectGUIDAsPrimaryKey: **********")
    self.verifyAddsUpdatesRenames('objectGUID.cfg', outfile='objectguidprikey')

  def testBasicTls(self):
    """ Connecting to ldap via TLS throws no errors."""
    logging.debug("testBasicTls: **********")
    self.verifyBasicConnectivity('yourdomainTls.cfg')

  def testDeleteOfUser(self):
    """ Deletion of user in ldap propagates to google apps """
    logging.debug("testDeleteOfUser: **********")
    self.InitWithCfg('yourdomain.cfg', True)
    self.InitTUserFilter()
    
    # clean out all the DNs currently in this branch of the tree
    self.CleanOutLDAP()

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

    # write it out to a tempfile
    self.cmd.onecmd('writeUsers %s' % self.GetTempFile('delete','2','xml'))

    # delete the user at this dn
    logging.debug('--- deleting users for deletion test')
    self.ctxt.conn.delete_s(dn)

    # TODO: this test is flakey.  Inexplicably the following command results in 
    # "Ignoring request to set action to exited because action already set to
    # " added"

    # write it out to a tempfile
    self.cmd.onecmd('writeUsers %s' % self.GetTempFile('delete','3','xml'))

    # pull in the users via updateUsers command
    self.cmd.onecmd('updateUsers')

    # write it out to a tempfile
    self.cmd.onecmd('writeUsers %s' % self.GetTempFile('delete','4','xml'))

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
    self.InitTUserFilter()

    # clean out all the DNs currently in this branch of the tree
    self.CleanOutLDAP()

    # test connection
    self.cmd.onecmd('connect')

  def _assertSetEmpty(self, value):
    if value:
      self.assertEqual(value, set([]))
      return
    self.assertEqual(value, None)

  def testAddWithNoGoogleQuotaHandled(self):
    """ Test that an add of a user with no google quota is handled. """
    logging.debug("testAddWithNoGoogleQuotaHandled: **********")
    self.verifyBasicConnectivity('yourdomainNoQuota.cfg')

    # add a user to the directory
    added_dns = self.ModUsersLDAP('userspec.ldif', 'tuser', 1)

    # pull in the users via updateUsers command
    self.cmd.onecmd('updateUsers')

    # write it out to a tempfile
    self.cmd.onecmd('writeUsers %s' % self.GetTempFile('quota','1', 'xml'))

    # do the sync to Google
    self.cmd.onecmd('syncAllUsers')
    _LogObjectValue('added_dns=', added_dns)
    self.VerifyUsersInGoogle(added_dns)

  def testModificationTimeIsUpdatedOnlyAfterCompleteSuccess(self):
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
    self.cmd.onecmd('writeUsers %s' % self.GetTempFile('timing','1', 'xml'))

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
      self.assertMetaGoogleActionEmpty(dn)

      # make sure it was pushed to Google
      gattrs = self.api.RetrieveAccount(attrs['GoogleUsername'])
      logging.debug('gattrs=%s' % str(gattrs))
      self.assertNotEqual(gattrs, None)
      self.assertEqual(str(gattrs['firstName']), attrs['GoogleFirstName'])

  def addUsersAndVerifyTheyShowInUserDb(self, file, ldifbasename='userspec',
      usersadded=2, outfile='basic'):
    self.verifyBasicConnectivity(file)

    # If the user is using an old ldap library and requested paging its not a
    # bug
    if (self.ctxt.ldap_page_size != 0 and 
        not self.ctxt.IsUsingLdapLibThatSupportsPaging()):
      return 

    # add some users to the directory
    added_dns = self.ModUsersLDAP('%s.ldif' % ldifbasename, 'tuser', usersadded)

    # pull in the users via updateUsers command
    self.cmd.onecmd('updateUsers')

    # write it out to a tempfile
    self.cmd.onecmd('writeUsers %s' % self.GetTempFile(outfile,'1','xml'))

    # we should now have exactly the ones we added in our userdb:
    (userdb_not_in_added, added_not_in_userdb) = (
        self.CompareUserdbToTarget(added_dns))
    self._assertSetEmpty(added_not_in_userdb)
    self._assertSetEmpty(userdb_not_in_added)
    return added_dns

  def verifyAddsUpdatesRenames(self, file, ldifbasename='userspec', 
      usersadded=2, usersmoded=1, outfile='basic', userbasename='tuser', 
      ext='xml'):

    self.verifyAdds(file, ldifbasename, usersadded, outfile, ext=ext)
    
    # If the user is using an old ldap library and requested paging its not a 
    # bug
    if (self.ctxt.ldap_page_size != 0 and 
        not self.ctxt.IsUsingLdapLibThatSupportsPaging()):
      return 

    self.verifyUpdates(file, ldifbasename, usersmoded, outfile, ext=ext)
    self.verifyRenames(file, ldifbasename, usersmoded, outfile, ext=ext)

  def verifyAdds(self, file, ldifbasename, usersadded, outfile, ext='xml'):
    added_dns = self.addUsersAndVerifyTheyShowInUserDb(file, ldifbasename, 
        usersadded, outfile=outfile)

    # If the user is using an old ldap library and requested paging its not a
    # bug
    if (self.ctxt.ldap_page_size != 0 and 
        not self.ctxt.IsUsingLdapLibThatSupportsPaging()):
      return 

    # unfortunately, AD will change this account, anywhere up to 30 seconds
    # later, and we really need things to stabilize for the time-based
    # filter to work.  So:
    self.WaitForAD(30)

    # do the sync to Google
    self.cmd.onecmd('syncAllUsers')
    self.VerifyUsersInGoogle(added_dns)

    # write it out to a tempfile
    self.cmd.onecmd('writeUsers %s' % self.GetTempFile(outfile, 'add', ext))

  def verifyUpdates(self, file, ldifbasename, usersmoded, outfile, ext='xml'):
    # now modify some of them, and make sure those get flagged properly
    time.sleep(2)  # so as to detect a time difference in whenChanged!
    mods = self.ModUsersLDAP('%s-mod.ldif' % ldifbasename, 'tuser', usersmoded, 
        ldap.MOD_REPLACE)
    self.cmd.onecmd('updateUsers')

    # write it out to a tempfile
    self.cmd.onecmd('writeUsers %s' % self.GetTempFile(outfile, 'mod-1', ext))

    # do the sync to Google
    self.cmd.onecmd('syncAllUsers')

    # write it out to a tempfile
    self.cmd.onecmd('writeUsers %s' % self.GetTempFile(outfile, 'mod-2', ext))

    # we should have the users we just modded as 'update'
    for dn in mods:
      attrs = self.userdb.LookupDN(dn)

      # syncAllUsers should have nulled-out the meta-Google-action field
      self.assertMetaGoogleActionEmpty(dn)

      # make sure it was pushed to Google
      gattrs = self.api.RetrieveAccount(attrs['GoogleUsername'])
      logging.debug('gattrs=%s' % str(gattrs))
      self.assertNotEqual(gattrs, None)
      self.assertEqual(gattrs['firstName'], attrs['GoogleFirstName'])

    # write it out to a tempfile
    self.cmd.onecmd('writeUsers %s' % self.GetTempFile(outfile, 'mod-3', ext))

  def verifyRenames(self, file, ldifbasename, usersmoded, outfile, ext='xml'):
    # now force a rename:
    time.sleep(2)  # so as to detect a time difference in whenChanged!
    mods = self.ModUsersLDAP('%s-rename.ldif' % ldifbasename, 'tuser', 
        usersmoded, ldap.MOD_REPLACE)
    self.cmd.onecmd('updateUsers')

    # write it out to a tempfile
    self.cmd.onecmd('writeUsers %s' % self.GetTempFile(outfile, 'ren-1', ext))

    # do the sync to Google
    self.cmd.onecmd('syncAllUsers')

    # write it out to a tempfile
    self.cmd.onecmd('writeUsers %s' % self.GetTempFile(outfile, 'ren-2', ext))

    # check the users we just modded & be sure they were renamed
    for dn in mods:
      # syncAllUsers should have nulled-out the meta-Google-action field
      self.assertMetaGoogleActionEmpty(dn)
      attrs = self.userdb.LookupDN(dn)
      self.assertAccountExists(attrs['GoogleUsername']) 

  def testNoDisabledFilter(self):
    """ Users get marked as exited when deleted from ldap (no disabled filter).

    Since the algorithm for detecting exited employees is different
    if there's no 'ldap_disabled_filter' parm, this tests that case
    """
    logging.debug("testNoDisabledFilter: ************")
    self.InitWithCfg('yourdomain-no-disabled.cfg', True)
    self.InitTUserFilter()
    # clean out all the DNs currently in this branch of the tree
    self.CleanOutLDAP()

    # add two users to the directory
    added = self.ModUsersLDAP('no-disabled.ldif', 'tuser', 2)

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

    # write it out to a tempfile
    self.cmd.onecmd('writeUsers %s' % self.GetTempFile('no-disabled','2','xml'))

    # delete one of the users from LDAP
    exited = self.ModUsersLDAP('no-disabled.ldif', 'tuser', 1, ldap.MOD_DELETE)

    # pull in the users via updateUsers command
    self.cmd.onecmd('updateUsers')

    # write it out to a tempfile
    self.cmd.onecmd('writeUsers %s' % self.GetTempFile('no-disabled','3','xml'))

    # be sure our exited really is marked 'exited', and nothing else is
    for dn in self.userdb.UserDNs():
      if dn in exited:
        self.assertActionIs(dn, 'exited')
      else:
        self.assertMetaGoogleActionEmpty(dn)

  def assertMetaGoogleActionEmpty(self, dn):
    attrs = self.userdb.LookupDN(dn)
    self.assertTrue('Expected empty action', self.isMetaGoogleActionEmpty(dn))

  def isMetaGoogleActionEmpty(self, dn): 
    attrs = self.userdb.LookupDN(dn)
    if not attrs:
      return True
    if 'meta-Google-action' in attrs:
      return not attrs['meta-Google-action']
    return True

  def assertMetaGoogleActionNotEmpty(self, dn):
    self.assertTrue(not self.isMetaGoogleActionEmpty(dn))

  def testNoExceptions(self):
    """ Try lots of misuses of the tool, and be sure exceptions are caught.
    """
    logging.debug("testNoExceptions: **************")

    try:
      # all sorts of LDAP abuse:
      try:
        self.InitWithCfg('bad1.cfg')
        self.InitTUserFilter()
        self.fail('should have failed for lack of ldap_url')
      except utils.ConfigError:
        pass
      try:
        self.InitWithCfg('bad2.cfg')
        self.InitTUserFilter()
        self.fail('should have failed for lack of ldap_url')
      except utils.ConfigError:
        pass

      self.cmd.onecmd('updateUsers')
      self.InitWithCfg('bad6.cfg')
      self.InitTUserFilter()
      self.cmd.onecmd('updateUsers')
      self.InitWithCfg('bad7.cfg')
      self.InitTUserFilter()
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
      self.InitTUserFilter()
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

  def testSyncOne(self):
    """ Test deletion and updates of ldap users propagate with SyncOneUser cmd.
    """
    logging.debug("testSyncOne: **********")
    self.InitWithCfg('yourdomain.cfg', True)
    self.InitTUserFilter()

    # clean out all the DNs currently in this branch of the tree
    self.CleanOutLDAP()

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
