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
import logging
import time
import logging
import messages

"""Handles all changes to the last update time.  """

WAS_ERRORS = False
FILENAME = ""
LASTUPDATEFILE = None
NEXT_UPDATE_TIME = None

def initialize():
  """ Reset whether any errors occurred in a run."""
  global WAS_ERRORS
  WAS_ERRORS = True

def setFilename(name):
  """ Set the filename to be used to store last update time.
  Args:
    name: name of the file.
  """
  global FILENAME
  FILENAME = name
  logging.debug('last_update_time.setFilename: to %s' % name)

def _set(struct_time):
  """ Set the last update time. 
  Args:
    struct_time the time.struct_time to set the last update tiem to.
  """
  global FILENAME
  global LASTUPDATEFILE
  LASTUPDATEFILE = file(FILENAME, 'w')
  ldap_time = time.strftime('%Y%m%d%H%M%S', struct_time)
  logging.debug('last_udpate_time._set(): setting time to %s' % ldap_time)
  LASTUPDATEFILE.write('%s\n' % ldap_time)

def get():
  """ Return the last update time as a string.
  Returns:
    A string containing the last update time in YYYYMMDDHHMMSS format.
  """
  global FILENAME
  global LASTUPDATEFILE
  try:
    LASTUPDATEFILE = file(FILENAME, 'r')
  except IOError:
    return None
  time = LASTUPDATEFILE.read()
  return time

def beginNewRun():
  """ Reset error boolean and note the time the run began as the 'baseline'.
  If an error occurs
  then updateIfNoErrors() will ignore requests to update last update
  time."""
  global NEXT_UPDATE_TIME
  global WAS_ERRORS
  NEXT_UPDATE_TIME = time.gmtime()
  logging.debug('last_update_time.beginNewRun(): baseline set to %s' % 
      str(NEXT_UPDATE_TIME))
  WAS_ERRORS = False

def reportError():
  """ Mark that there were errors in a run. """
  global WAS_ERRORS
  logging.debug('last_update_time.reportError(): marking error')
  WAS_ERRORS = True
   
def updateIfNoErrors():
  """ Try to update last update time with the time that beginNewRun()
  was called.  Output a warning if errors
  prevent updating the last update time.  """
  global NEXT_UPDATE_TIME
  global WAS_ERRORS
  if WAS_ERRORS:
    logging.warn(messages.MSG_LAST_UPDATE_TIME_NOT_UPDATED)
  else:
    logging.info(messages.MSG_UPDATING_LAST_UPDATE_TIME % 
        str(NEXT_UPDATE_TIME))
    _set(NEXT_UPDATE_TIME)

def GetBaseline():
  """ Return the time that the new run started which is known as the 'baseline'.
  """
  return time.strftime('%Y%m%d%H%M%S', NEXT_UPDATE_TIME)
