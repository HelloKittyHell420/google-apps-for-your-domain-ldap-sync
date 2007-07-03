#!/usr/bin/python2.4
#
# Copyright 2006 Google Inc.
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

""" Python wrapper around the Google Apps for Your Domain API.
In general, unless otherwise specified, public methods either succeed and
return nothing, or they raise a ProvisioningApiError exception.
The list of all exceptions
specific to Google Apps for Your Domain is given in the provisioning_errs module.
  The Retrieve<type-of-object> <name> operations raise
  ObjectDoesNotExistError if a <type-of-object> object with name <name> does
  not exist.
"""


import provisioning_backend
import provisioning_auth
import types


class API(object):

  """ Object capable of holding domain information and invoking
  API calls for provisioning Google Apps for Your Domain accounts.
  Initiates a connection to Google, obtains an authorization token,
  and caches it.
  Raises provisioning_errs.AuthenticationError if domain doesn't
  exist or user/password is invalid.
  """

  def __init__(self, user, password, domain, debug=False, **moreargs):

    super(API, self).__init__(user=user, password=password,
                              domain=domain, **moreargs)
    self._user = user
    self._password = password
    self._domain = domain
    tok = provisioning_auth.RestAuthToken(self._user, self._password,
                                          debug=debug)
    self._token = tok.Token()

  def GetDomain(self):
    return self._domain

  def _ListifyAttr(self, resp, fromStr, toStr):

    """  the XML parser will only make items in the RetrievalSection into
    lists if there is more than one value (since it doesn't know what items
    are inherently multi-valued).  So here we convert, e.g. 'aliases' into
    a list, from the 'alias' attribute, which might or might not be a list.
    Args:
      resp: dictionary representing the parsed answer from Google
      fromStr: the attribute to find the data in
      toStr: the attribute to move it to, as a list
    """

    if fromStr in resp:
      val = resp[fromStr]
      if not isinstance(val, types.ListType):
        resp[toStr] = [val]
      else:
        resp[toStr] = val
      del resp[fromStr]

  def _ListifyAccount(self, resp):

    """ the XML parser will only make items in the RetrievalSection into
    lists if there is more than one value (since it doesn't know what items
    are inherently multi-valued).  So here we convert 'aliases' and
    'emailLists' into lists, even if there is only one entry.
    Args:
      resp: dictionary representing the parsed answer from Google
    """

    self._ListifyAttr(resp, 'alias', 'aliases')
    self._ListifyAttr(resp, 'emailAddress', 'emailAddresses')
    self._ListifyAttr(resp, 'emailList', 'emailLists')
    return resp

  ##############################################  Accounts

  def RetrieveAccount(self, username):

    """Account retrieval

    Args:
      username: name of the user to retrieve
    Return: dictionary, with the following keys:
      'firstName'    : string
      'lastName'     : string
      'userName'     : string
      'aliases'      : list of strings (the user's aliases)
      'emailLists' : list of strings (mailing lists the user belongs to)
    Raises: ObjectDoesNotExistError if there is no user with the given name
    """
    obj = provisioning_backend.RetrieveAccountRequest(domain=self.GetDomain(),
       auth=self._token, username=username)
    resp = obj.Send()
    return self._ListifyAccount(resp)

  def CreateAccountWithEmail(self, firstname, lastname, password, username,
			     quota=None):

    """ Create a new account with Email
    Args:
      firstName: new user's first name
      lastName: new user's last name
      password: new user's password
      userName: new user's username
      quota: optional email quota in megabytes for domains with custom email
             quotas only
    Raises: ProvisioningError if an invalid quota was given
    """
    obj = provisioning_backend.CreateAccountWithEmailRequest(domain=self.GetDomain(),
       auth=self._token,
       firstname=firstname, lastname=lastname, password=password,
       username=username, quota=quota)
    obj.Send()

  def EnableEmail(self, username, quota=None):

    """ Add email service to an account (Deprecated). Use
    CreateAccountWithEmail to create new accounts with Email.

    Args:
      username: the user to enable email for
      quota: optional email quota in MB
    """
    obj = provisioning_backend.EnableEmailRequest(domain=self.GetDomain(),
       auth=self._token, username=username, quota=quota)
    obj.Send()

  def DeleteAccount(self, username):

    """ Delete an account

    Args:
      userName: user's username
    """
    obj = provisioning_backend.DeleteAccountRequest(domain=self.GetDomain(),
       auth=self._token,  username=username)
    obj.Send()

  def UpdateAccount(self, username, updatefields):

    """ Account update

    Args:
      username: name of the user
      updatefields: dict of { fieldname: newvalue }.  Legal keys are:
        firstName: user's first name
        lastName: user's last name
        password: user's password
        NOT username -- use RenameAccount to update that.
    """
    obj = provisioning_backend.UpdateAccountRequest(domain=self.GetDomain(),
       auth=self._token, username=username, updatefields=updatefields)
    obj.Send()

  def LockAccount(self, username):

    """ Lock an account. Users cannot access email if their account
    is locked.
    Locking an account which is already locked has no effect (but raises
    no exception)
    Args:
      username: the username to lock
    """
    obj = provisioning_backend.UpdateAccountStatusRequest(domain=self.GetDomain(),
       auth=self._token, username=username, locked=True)
    obj.Send()

  def UnlockAccount(self, username):

    """ Unlock an account.
    Unlocking an account which is not locked has no effect (but raises
    no exception)
    Args:
      username: the username to unlock
    """
    obj = provisioning_backend.UpdateAccountStatusRequest(domain=self.GetDomain(),
       auth=self._token, username=username, locked=False)
    obj.Send()

  def RenameAccount(self, oldname, newname, alias=False):

    """ Username change. Note that this feature must be explicitly
    enabled by the domain administrator, and is not enabled by
    default.

    Args:
      oldname: user to rename
      newname: new username to set for the user
      alias: if True, create an alias of oldname for newname
    """
    obj = provisioning_backend.RenameAccountRequest(domain=self.GetDomain(),
       auth=self._token, oldname=oldname, newname=newname, alias=alias)
    obj.Send()

  def ChangePassword(self, username, newpass):

    """ Change a user's password
    Args:
      username: user whose password is being changed
      newpass: new password
    """

    # First fetch information about the user.  We need this to get his full
    # name for the update request.
    obj = provisioning_backend.RetrieveAccountRequest(domain=self.GetDomain(),
       auth=self._token, username=username)
    resp = obj.Send()
    update = {
      'firstName': resp['firstName'],
      'lastName': resp['lastName'],
      'userName': username,
      'password': newpass,
      }
    obj = provisioning_backend.UpdateAccountRequest(domain=self.GetDomain(),
       auth=self._token, username=username, updatefields=update)
    obj.Send()

  ############################################# Aliases

  def RetrieveAlias(self, alias):

    """Alias retrieval

    Args:
      alias: name of the alias to retrieve
    Return: dictionary, with the following keys:
      'firstName'    : string
      'lastName'     : string
      'userName'     : string
      'aliases'      : list of strings (the user's aliases)
      'emailLists'   : list of strings (mailing lists the user belongs to)
    Raises: ObjectDoesNotExistError if there is no user with the given alias
    """
    obj = provisioning_backend.RetrieveAliasRequest(domain=self.GetDomain(),
       auth=self._token, alias=alias)
    resp = obj.Send()
    return self._ListifyAccount(resp)

  def CreateAlias(self, username, aliasname):

    """
    Args:
      username: username to create and alias for
      aliasname: alias to give to username
    """
    obj = provisioning_backend.CreateAliasRequest(domain=self.GetDomain(),
       auth=self._token, username=username, aliasname=aliasname)
    obj.Send()

  def DeleteAlias(self, alias):

    """ Alias deletion

    Args:
      alias: name of the alias to delete
    """
    obj = provisioning_backend.DeleteAliasRequest(domain=self.GetDomain(),
       auth=self._token, alias=alias)
    obj.Send()

  ############################################# Mailing lists

  def CreateMailingList(self, mailinglist):

    """ Mailing list retrieval

    Args:
      mailinglist: name of the mailing list to create
    """
    obj = provisioning_backend.CreateMailingListRequest(domain=self.GetDomain(),
       auth=self._token, mailinglist=mailinglist)
    obj.Send()

  def RetrieveMailingList(self, mailinglist):

    """mailing list retrieval
    Args:
      mailinglist: name of the mailing list to retrieve
    Return:
      dictionary with at least one key:
        'emailAddresses': a list of email addresses belonging to the
        mailing list.
        NOTE: emailAddresses end in '@<domain>'
    Raises: ObjectDoesNotExistError if the mailing list
    does not exist
    """
    obj = provisioning_backend.RetrieveMailingListRequest(domain=self.GetDomain(),
       auth=self._token, mailinglist=mailinglist)
    resp = obj.Send()
    return self._ListifyAccount(resp)

  def DeleteMailingList(self, mailinglist):

    """ mailing list deletion

    Args:
      mailinglist: name of the mailing list to delete
    """
    obj = provisioning_backend.DeleteMailingListRequest(domain=self.GetDomain(),
            auth=self._token, mailinglist=mailinglist)
    obj.Send()

  def UpdateMailingList(self, mailinglist, username, op):

    """update a mailing list.

    Args:
      mailinglist: name of the mailing list to operate on
      username: user to add or remove
      op: "add" or "remove"
    """
    obj = provisioning_backend.UpdateMailingListRequest(domain=self.GetDomain(),
       auth=self._token, mailinglist=mailinglist, username=username, op=op)
    obj.Send()

if __name__ == '__main__':
  pass
