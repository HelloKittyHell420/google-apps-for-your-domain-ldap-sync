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

""" LDAP Sync Tool.  For synchronizing your LDAP directory with Google
Apps for Your Domain.  This is the main module.

Key objects used by this module:

  config: object holding all configuration variables for the Tool. An instance 
    of the utils.Config() class.

  ldap_context: object holding runtime context for the LDAP server

  user_database: an instance of the userdb.UserDB() class, holding all 
    information about users.

  google_context: an instance of the sync_google.SyncGoogle() class, which 
    handles interaction with Google Apps for Your Domain.

  log_config: an instance of utils.LogConfig(), holding the configuration for
    logging for the Tool
"""

import ldap_ctxt
import logging
from optparse import OptionParser
import messages
import sys
import commands
import sync_google
import userdb
import utils


def SetupMain(options):

  """ This is called from the unit test, since it doesn't go into
  reading from the keyboard
  """
  parms = {}
  parms.update(ldap_ctxt.LdapContext.config_parms)
  parms.update(userdb.UserDB.config_parms)
  parms.update(sync_google.SyncGoogle.config_parms)
  parms.update(utils.LogConfig.config_parms)
  config = utils.Config(parms)
  if options.config_file:
    config.ReadConfig(options.config_file)

  log_config = utils.LogConfig(config)

  # configure the logging system accordingly:
  log_config.ConfigureBasicLogging()

  ldap_context = ldap_ctxt.LdapContext(config)
  user_database = userdb.UserDB(config)
  google_context = sync_google.SyncGoogle(user_database, config)

  if options.data_file:
    user_database.ReadDataFile(options.data_file)
  return (config, ldap_context, user_database, google_context, log_config)

def GetValidFileFromUser():

  """ Prompt the user for a writeable file name, until he/she either
  does, or gives up
  Return:
    fname: name of the file
  """
  fname = None
  while not fname:
    fname = raw_input(messages.msg(messages.MSG_GIVE_A_FILE_NAME))
    if not fname:
      return None
    try:
      f = open(fname, 'w')
      f.close()
      return fname
    except IOError:
      sys.stderr.write('%s\n' % 
                       messages.msg(messages.ERR_NOT_VALID_FILE_NAME, fname))
      fname = None

def DoMain(options):
  """ main module. A client of the optparse module for command-line
  parsing.
  Args:
    options: first return value from parser.parse_args(), where 'parser' is a
      optparse.OptionParser
  """
  (config, ldap_context, user_database, google_context, log_config) = \
    SetupMain(options)
  cmd = commands.Commands(ldap_context, user_database, google_context, config)
  cmd.cmdloop()

  # write out the config parms:
  save_config = False
  if not options.config_file:
    ans = raw_input(messages.msg(messages.MSG_Q_SAVE_CONFIG))
    first = ans[:1].lower()
    if first == messages.CHAR_YES:
      options.config_file = GetValidFileFromUser()
      save_config = True
  else:
    ans = raw_input(messages.msg(messages.MSG_Q_SAVE_CONFIG_2, 
                    options.config_file))
    first = ans[:1].lower()
    if first == messages.CHAR_YES:
      save_config = True

  # if the files can't be written (e.g. on Windows it's open in another window)
  # we want to allow user to rectify the situation.
  if save_config and options.config_file:
    logging.info(messages.msg(messages.MSG_WRITE_CONFIG_FILE, 
                              options.config_file))
    ldap_context.WriteConfig()
    user_database.WriteConfig()
    google_context.WriteConfig()
    log_config.WriteConfig()
    while True:
      try:
        config.WriteConfig(options.config_file)
        break
      except IOError, e:
        logging.error(str(e))
        ans = raw_input(messages.MSG_TRY_AGAIN)
        if ans[:1] != messages.CHAR_YES:
          break
    logging.info(messages.MSG_DONE)

  if options.data_file:
    while True:
      try:
        user_database.WriteDataFile(options.data_file)
        break
      except IOError, e:
        logging.error(str(e))
        ans = raw_input(messages.MSG_TRY_AGAIN)
        if ans[:1] != messages.CHAR_YES:
          break

  return (config, ldap_context, user_database, google_context, log_config)

def GetParser():

  """ Return a parser that's set up with our options.  This is a separate method
  so the unit tester can call it.
  """
  parser = OptionParser(usage='%prog [-v][-q] [-f <dataFile>]'
                        '[-c <configFile>]',
                        version="%prog 0.9")
  parser.add_option("-f", "--dataFile", dest="data_file",
    help="User data file (XML or CSV), both read from and written to.")
  parser.add_option("-c", "--configFile", dest="config_file",
    help="Configuration file (standard Python format)")
  parser.add_option("-l", "--logFile", dest="log_file",
    help="Log file (defaults to stdout/stderr)")

  return parser

if __name__ == '__main__':
  print "Copyright 2006, Google, Inc.\nAll Rights Reserved."
  parser = GetParser()
  (options, args) = parser.parse_args()
  (config, ldap_context, user_database, google_context, log_config) = \
      DoMain(options)
