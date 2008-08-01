#!/usr/bin/python2.4
#
# Copyright 2008 Google Inc.
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

""" Mock provisioning.API which throws exceptions as configured.

SetCreateUserException() will configure the mock to throw the named 
exception when CreateAccountWithEmail() method is called on the API.
"""

from google.appsforyourdomain import provisioning
from google.appsforyourdomain import provisioning_errs

CREATE_USER_EXCEPTION = None
EXCEPTION_ARGS = []

class API(provisioning.API):
  def CreateAccountWithEmail(self, firstname, lastname, password, username,
      quota):
    global CREATE_USER_EXCEPTION
    global EXCEPTION_ARGS
    if CREATE_USER_EXCEPTION != None:
      raise CREATE_USER_EXCEPTION(*EXCEPTION_ARGS)
      # TODO: clean this up
      #raise provisioning_errs.ProvisioningApiError('fake reason', 
          #'fake message')
    super(API, self).CreateAccountWithEmail(firstname, lastname,
        password, username, quota)

def SetCreateUserException(exception, *moreargs):
  global CREATE_USER_EXCEPTION
  global EXCEPTION_ARGS
  CREATE_USER_EXCEPTION = exception
  EXCEPTION_ARGS = moreargs
