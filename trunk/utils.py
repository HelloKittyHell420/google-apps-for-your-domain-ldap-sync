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

""" various utilities needed for the LDAP Sync tool, esp. configuration

class ConfigError: an exception for "insufficient configuration"
class Configurable: superclass of all configurable objects
class Config: the actual object holding the app's configuration
class LogConfig: a Configurable class holding the logging configuration

Configuration files are done via the standard Python ConfigParser
library

** Consult <TBD> for overall documentation on this package.
"""

import ConfigParser
import logging
import messages

# the section header [ldap-sync] required in our config files
CONFIG_SECTION = 'ldap-sync'


class ConfigError(Exception):
  """ An exception raised by any component which says "I need the
  following items of configuration".
  Args:
    missing: a dictionary, where the key is the name of the config
    item, and the value is a documentation string
  """
  def __init__(self, missing):
    Exception.__init__(self, messages.MSG_MISSING_CONFIG)
    self._missing = missing

  def __str__(self):
    return '%s\n%s' % (messages.MSG_MISSING_CONFIG,
      '\n'.join(['%s:\t%s' % (k,v) for (k,v) in self._missing.iteritems()]))

class Configurable(object):

  """ An object which can be configured via the utils.Config object.
  This is deliberately a "lightweight" object; it doesn't impose a lot of
  semantics on config variables. The values are fetched from the utils.Config
  object only when you ask for them, and validation, or lack of it, is
  completely up to you.

  Subclasses must:
  * call the __init__() method from somewhere in their own constructor.
  This will populate the object with variables drawn from the config file,
  each named according to config variable.  ONLY variable appearing in
  'config_parms' will be so populated, in order to minimize potential
  damage from errant config files, so it's critical that config_parms
  be filled in.
  """

  def __init__(self, config, config_parms):
    """ Constructor. This should be called somewhere in the subclass's
    constructor, wherever is appropriate.
    Args:
      config: a utils.Config object
      config_parms: dictionary of config variables, where the values are
      documentation strings
    """
    self._config = config
    self._config_parms = config_parms
    config.SetOwner(self._config_parms, self)
    self.ReadConfig()

  def ReadConfig(self):
    """ Initialize from the utils.Config object
    Args:
      config: an instance of utils.Config, which has been initialized
      from a file (or wherever)
    """
    for attr in self._config_parms:
      val = self._config.GetAttr(attr)
      if val:
        setattr(self, attr, val)

  def WriteConfig(self):
    """ Make sure the config object has current copies of our config
    """
    for attr in self._config_parms:
      self._config.SetAttr(attr, getattr(self, attr))

  def SetConfigVar(self, attr, val):
    """ To be called AFTER initial config, e.g. when the user does
    something to change a variable.
    Args:
      attr: name of variable
      val: the value
    """
    if not attr in self._config_parms:
      return messages.msg(messages.ERR_NO_SUCH_ATTR, attr)
    try:
      setattr(self, attr, val)
    except ValueError:
        return messages.msg(messages.ERR_INVALID_VALUE, attr)

class LogConfig(Configurable):

  """ Object whose sole purpose is to hold the logging configuration
  variables.
  """
  config_parms = {'logfile': messages.MSG_LOG_FILE ,
                  'loglevel': messages.MSG_LOG_LEVEL}

  def __init__(self, config, **moreargs):
    """ Constructor.
    Args:
      config: a utils.Config object
    """
    self.loglevel = logging.INFO
    self.logfile = None
    self._config = config
    super(LogConfig, self).__init__(config=config,
                                    config_parms=self.config_parms,
                                    **moreargs)
  def ConfigureBasicLogging(self):
    """configure the logging system according to our settings
    """
    # logging.basicConfig(level=self.loglevel,
    logging.basicConfig(level=int(self.loglevel),
                        format='%(asctime)s %(name)-12s %(levelname)-8s %(message)s',
                        datefmt='%m-%d %H:%M',
                        filename=self.logfile,
                        filemode='w')
    # define a Handler which writes INFO messages or higher to the sys.stderr
    console = logging.StreamHandler()
    console.setLevel(self.loglevel)

    # set a format which is simpler for console use
    formatter = logging.Formatter('%(message)s')
    # tell the handler to use this format
    console.setFormatter(formatter)
    # add the handler to the root logger
    logging.getLogger('').addHandler(console)
    # now we're ready for the Config object to log errors, if any
    self._config.StartLogging()

class Config(object):
  """ Maintains the list of configurable variables for the LDAP sync
  tool. Each is associated with an object owner, if the owner is a
  subclass of utils.Configurable.
  """

  def __init__(self, attrs, section=CONFIG_SECTION):
    """ Constructor for the LDAP Sync Tool's config object.
    Due to circularity problems with configuration of logging,
    errors in the configuration are not logged until StartLogging()
    is called.  Normally this is done by the LogConfig object
    itself.
    Args:
      attrs: dictionary of attr_name --> doc strings
      section: section title of the config file (defaults
      to 'ldap-sync'
    """
    self.attrs = attrs

    self._section = section
    self._owners = {}
    self._parms = {}
    self._dirty = False # if any config attrs have been changed
    self._log_errors = False

  def StartLogging(self):
    self._log_errors = True

  def FindOwner(self, attr):
    """ For a given config variable, return the var's owner, if any
    Args:
      attr: name of a config variable
    Return:
      owner: the object owning this variable
    """
    if attr not in self._owners:
      return None
    return self._owners[attr]

  def ReadConfig(self, filename):
    """ Read all attributes in the config file. Only the
    ones that we're programmed to read are saved; the rest are
    ignored and an 'info' message is written to the log.
    Args:
      filename: name of file to which config is to be written
    Raises:
      IOError: if filename does not exist or is not readable
    """
    self._filename = filename
    config_parser = ConfigParser.RawConfigParser()
    config_parser.read(filename)

    if not config_parser.has_section(self._section):
      raise RuntimeError('missing config section: %s' % self._section)
    items = config_parser.items(self._section)
    for (name, val) in items:
      if name not in self.attrs:
        if self._log_errors:
          logging.info('Unrecognized property: %s ignored' % name)
        continue
      try:
        self._parms[name] = eval(val)
      except (SyntaxError, NameError):
        if self._log_errors:
          logging.error('syntax error in config file for %s: %s' % (name, val))
        continue  # read the rest of the config
    return None

  def SetOwner(self, attrs, owner):
    """ Set the owner for a set of variables
    Args:
      attrs: iterable container of config variable names
      owner: the object to be their owner
    """
    for attr in attrs.iterkeys():
      self._owners[attr] = owner

  def WriteConfig(self, filename):
    """ Write current configurable attributes
    to the passed-in ConfigParser object. Note that this is done via a repr()
    call on the write side, and an eval() on the read side.
    Args:
      filename: filename to be written to
    Raises:
      IOError: if filename is not writeable
    """
    if not self._dirty:
      return
    self._filename = filename
    f = open(filename, 'w')
    config_parser = ConfigParser.RawConfigParser()
    if not config_parser.has_section(self._section):
      config_parser.add_section(self._section)
    for attr in self.attrs:
      if attr in self._parms:
        if self._parms[attr] != None:
          config_parser.set(self._section, attr, repr(self._parms[attr]))
    config_parser.write(f)
    self._dirty = False
    f.close()

  def GetAttr(self, attr):
    """ Get the value of a config variable.
    Args:
      attr: name of the variable
    Returns:
      value of the variable, or None if not found
    """
    if not attr in self.attrs:
      return None
    if attr not in self._parms:
      return None
    return self._parms[attr]

  def SetAttr(self, attr, val):
    """ Set the value of a config variable
    Args:
      attr: name of the variable
      val: its value
    """
    self._parms[attr] = val
    self._dirty = True

  def TestConfig(self, obj, parms):
    """ for a given object, test that it has all the items of configuration
    that it requires.  If not, raise a ConfigError enumerating the ones
    missing.
    Args:
      obj:  the object
      parms: list of parm names. Each must be a key of self.attrs.  (if
      it isn't, the item will not be checked.)
    """
    missing = {}
    for item in parms:
      if item not in self.attrs:
        continue
      if not hasattr(obj, item) or not getattr(obj, item):
        missing[item] = self.attrs[item]
    if len(missing) == 0:
      return None
    raise ConfigError(missing)
