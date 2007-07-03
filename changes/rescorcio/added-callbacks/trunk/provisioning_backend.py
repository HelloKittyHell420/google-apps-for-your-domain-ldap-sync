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

"""A python wrapper around the Google Apps for Your Domain Provisioning API.
This module should normally not be used directly, since the
module 'provisioning.py' provides a more convenient interface.
"""


import cStringIO
from provisioning_errs import *
import types
import urllib2
import xml.sax.saxutils
import xml.sax.xmlreader


# XML namespace for Provisioning requests and responses
NS = u'google:accounts:rest:protocol'

# Base URL for Provisioning requests
BASEURL = 'https://www.google.com/a/services/v1.0/'



class Request(object):
  """Base class for a Provisioning request. Normally the applicable
  subclass, e.g. CreateAccountWithEmailRequest should be used in preference
  to this.
  """

  def __init__(self, domain, auth, **moreargs):
    """Create a request.

    Args:
      domain: string containing the domain to operate on
      auth: string containing your current auth token
    """

    super(Request, self).__init__(domain=domain, auth=auth,
                                  **moreargs)
    self.domain = domain
    self.auth = auth
    self._posturl = None
    self._type = None
    self._restdata = None

  # getters & setters:
  def GetPosturl(self):
    return self._posturl

  def SetPosturl(self, u):
    self._posturl = u

  def GetType(self):
    return self._type

  def SetType(self, t):
    self._type = t

  def GetRestdata(self):
    return self._restdata

  def SetRestdata(self, r):
    self._restdata = r

  def _SimpleElement(self, doc, tag, content):
    """Generate simple XML for a tag with some content:
    <hs:tag>content</hs:tag>

    Args:
      doc: XMLGenerator object
      tag: XML tag to use
      content: The content to put inside the tag
    """

    emptyattr = xml.sax.xmlreader.AttributesNSImpl({}, {})
    doc.startElementNS((NS, unicode(tag)), u'hs:' + unicode(tag), emptyattr)
    doc.characters(unicode(content))
    doc.endElementNS((NS, unicode(tag)), u'hs:' + unicode(tag))

  def ToXML(self):
    """Generate XML for this request.
    Returns:
      a string
    """

    # Set up the XML document
    output = cStringIO.StringIO()
    doc = xml.sax.saxutils.XMLGenerator(output, 'UTF-8')
    doc.startDocument()
    doc.startPrefixMapping(u'hs', NS)
    emptyattr = xml.sax.xmlreader.AttributesNSImpl({}, {})
    doc.startElementNS((NS, u'rest'), u'hs:rest', emptyattr)

    # Generate the common Provisioning bits
    self._SimpleElement(doc, 'type', self._type)
    self._SimpleElement(doc, 'token', self.auth)
    self._SimpleElement(doc, 'domain', self.domain)

    # Generate the XML inside the <rest> element
    self._HandleRestData(doc, self._restdata)

    # Finish up
    doc.endElementNS((NS, u'rest'), u'hs:rest')
    doc.endPrefixMapping(u'hs')
    doc.endDocument()

    output.seek(0)
    return output.read()

  def _HandleRestData(self, doc, data):
    """Generate the XML from self._restdata

    Args:
      doc: XMLGenerator object generating our request
      data: A list of (tag, content) pairs, where tag is a string and content is
            either a string or a list of pairs
    """

    emptyattr = xml.sax.xmlreader.AttributesNSImpl({}, {})
    for (tag, content) in data:

      # Recursive content
      if isinstance(content, list):
        doc.startElementNS((NS, unicode(tag)), u'hs:' + unicode(tag), emptyattr)
        self._HandleRestData(doc, content)
        doc.endElementNS((NS, unicode(tag)), u'hs:' + unicode(tag))

      # Nonrecursive content
      else:
        self._SimpleElement(doc, tag, content)

  def _CreateException(self, resp):

    """ From the XML failure response, create an exception that's specific
    to what happened
    Args:
      resp: parsed response
    """
    if resp.reason.startswith('UserDoesNotExist'):
      return ObjectDoesNotExistError(resp.message)
    elif resp.reason.startswith('InvalidData'):
      return InvalidDataError(resp.message)
    else:  # just return the generic error
      return ProvisioningApiError(resp.reason, resp.message)

  def Send(self):
    """Send this Provisioning request.
    Returns:
      a Response object
    """

    try:
      f = urllib2.urlopen(self._posturl, self.ToXML())
      res = f.read()
      f.close()
    except urllib2.URLError, e:
      raise ConnectionError(str(e))
    except Exception, e:
      raise ProvisioningApiError('**Error: ', str(e))

    resobj = Response()
    xml.sax.parseString(res, _ResponseParser(resobj))
    if not resobj.success:
      raise self._CreateException(resobj)
    return resobj

class CreateAccountWithEmailRequest(Request):
  """Account creation with email request."""

  def __init__(self, domain, auth, firstname, lastname, password, username,
               quota, **moreargs):
    """Initialize an account with email creation request.

    Args:
      domain: string containing the domain to operate on
      auth: string containing your current auth token
      firstName: new user's first name
      lastName: new user's last name
      password: new user's password
      userName: new user's username
      quota: optional email quota in megabytes
    Raises: ProvisioningError if an invalid quota was given
    """

    super(CreateAccountWithEmailRequest, self).__init__(domain=domain, auth=auth,
                                               firstname=firstname,
                                               lastname=lastname,
                                               password=password,
                                               username=username,
                                               quota=quota,
                                               **moreargs)
    self.SetPosturl(BASEURL + 'Create/Account/Email')
    self.SetType('Account')

    createsection = [
        ('firstName', firstname),
        ('lastName', lastname),
        ('password', password),
        ('userName', username),
        ]

    if quota is not None:
      try:
        createsection.append(('quota', str(int(quota))))
      except Exception, e:
        raise ProvisioningApiError("**Error on 'quota' argument",
                                   "must be an integer")

    self.SetRestdata([ ('CreateSection', createsection) ])

class CreateAliasRequest(Request):
  """Alias creation request."""

  def __init__(self, domain, auth, username, aliasname, **moreargs):
    """ Initialize an alias creation request.

    Args:
      domain: string containing the domain to operate on
      auth: string containing your current auth token
      username: username to create and alias for
      aliasname: alias to give to username
    """

    super(CreateAliasRequest, self).__init__(domain=domain, auth=auth,
                                             username=username,
                                             aliasname=aliasname,
                                             **moreargs)
    self.SetPosturl(BASEURL + 'Create/Alias')
    self.SetType('Alias')

    createsection = [
        ('userName', username),
        ('aliasName', aliasname),
        ]

    self.SetRestdata([ ('CreateSection', createsection) ])


class CreateMailingListRequest(Request):
  """Mailing list creation request."""

  def __init__(self, domain, auth, mailinglist, **moreargs):  
    """Initialize a mailing list creation request.

    Args:
      domain: string containing the domain to operate on
      auth: string containing your current auth token
      mailinglist: name of the mailing list to create
    """

    super(CreateMailingListRequest, self).__init__(domain=domain, auth=auth,
                                                   mailinglist=mailinglist,
                                                   **moreargs)
    self.SetPosturl(BASEURL + 'Create/MailingList')
    self.SetType('MailingList')

    createsection = [
        ('mailingListName', mailinglist),
        ]

    self.SetRestdata([ ('CreateSection', createsection) ])


class UpdateAccountRequest(Request):
  """Account update request."""

  def __init__(self, domain, auth, username, updatefields,
               **moreargs):
    """Initialize an account update request.

    Args:
      domain: string containing the domain to operate on
      auth: string containing your current auth token
      username: name of the user to operate on
      updatefields: dict of { fieldname: newvalue }
    """

    super(UpdateAccountRequest, self).__init__(domain=domain, auth=auth,
                                               updatefields=updatefields,
                                               **moreargs)
    self.SetPosturl(BASEURL + 'Update/Account')
    self.SetType('Account')

    validfields = ['firstName', 'lastName', 'password', 'userName']
    updatesection = []
    for (field, value) in updatefields.items():
      if field in validfields:
        updatesection.append((field, value))
      else:
        raise ValueError('Invalid account update field "%s"' % field)

    self.SetRestdata([
        ('queryKey', 'userName'),
        ('queryData', username),
        ('UpdateSection', updatesection),
        ])

class EnableEmailRequest(Request):
  """Add email to account request (Deprecated)
  Use CreateAccountWithEmailRequest instead to create a new user with Email.
  """

  def __init__(self, domain, auth, username, quota=None, 
               **moreargs):
    """Initialize a request to add email service to an account.

    Args:
      domain: string containing the domain to operate on
      auth: string containing your current auth token
      username: the user to enable email for
      quota: optional email quota in MB
    """

    super(EnableEmailRequest, self).__init__(domain=domain, auth=auth,
                                             username=username, quota=quota,
                                             **moreargs)
    self.SetPosturl(BASEURL + 'Update/Account/Email')
    self.SetType('Account')

    updatesection = [ ('shouldEnableEmailAccount', 'true') ]
    if quota is not None:
      updatesection.append(('quota', str(int(quota))))

    self.SetRestdata([
        ('queryKey', 'userName'),
        ('queryData', username),
        ('UpdateSection', updatesection),
        ])

class UpdateAccountStatusRequest(Request):
  """Update account status request."""

  def __init__(self, domain, auth, username, locked, **moreargs):
    """Initialize a request to update account status (lock and unlock)

    Args:
      domain: string containing the domain to operate on
      auth: string containing your current auth token
      username: the user to operate on
      locked: boolean, true to lock account, false to unlock
    """
    
    super(UpdateAccountStatusRequest, self).__init__(domain=domain, auth=auth,
                                                     username=username,
                                                     locked=locked,
                                                     **moreargs)
    self.SetPosturl(BASEURL + 'Update/Account/Status')
    self.SetType('Account')

    if locked:
      lockval = 'locked'
    else:
      lockval = 'unlocked'

    self.SetRestdata([
        ('queryKey', 'userName'),
        ('queryData', username),
        ('UpdateSection', [
            ('accountStatus', lockval),
            ]),
        ])


class RenameAccountRequest(Request):
  """Usename change request."""

  def __init__(self, domain, auth, oldname, newname, alias=False,
               **moreargs):
    """Initialize a username change request.

    Args:
      domain: string containing the domain to operate on
      auth: string containing your current auth token
      oldname: user to rename
      newname: new username to set for the user
      alias: if True, create an alias of oldname for newname
    """

    super(RenameAccountRequest, self).__init__(domain=domain, auth=auth,
                                               newname=newname, alias=alias,
                                               **moreargs)
    self.SetPosturl(BASEURL + 'Update/Account/Username')
    self.SetType('Account')

    self.SetRestdata([
        ('queryKey', 'userName'),
        ('queryData', oldname),
        ('UpdateSection', [
            ('userName', newname),
            ('shouldCreateAlias', str(bool(alias)).lower()),
            ]),
        ])


class UpdateMailingListRequest(Request):
  """Update mailing list request."""

  def __init__(self, domain, auth, mailinglist, username, op,
               **moreargs):
    """Initialize a request to update a mailing list.

    Args:
      domain: string containing the domain to operate on
      auth: string containnig your current auth token
      mailinglist: name of the mailing list to operate on
      username: user to add or remove
      op: 'add' or 'remove'
    """

    super(UpdateMailingListRequest, self).__init__(domain=domain, auth=auth,
                                                   mailinglist=mailinglist,
                                                   username=username, op=op,
                                                   **moreargs)
    self.SetPosturl(BASEURL + 'Update/MailingList')
    self.SetType('MailingList')

    if op != 'add' and op != 'remove':
      raise ValueError('Bad value for op: %s' % op)

    self.SetRestdata([
        ('queryKey', 'mailingListName'),
        ('queryData', mailinglist),
        ('UpdateSection', [
            ('userName', username),
            ('listOperation', op),
            ]),
        ])


class RetrieveAccountRequest(Request):
  """Account retrieval request."""

  def __init__(self, domain, auth, username, **moreargs):
    """Initialize an account retrieval request.

    Args:
      domain: string containing the domain to operate on
      auth: string containing your current auth token
      username: name of the user to retrieve
    """

    super(RetrieveAccountRequest, self).__init__(domain=domain, auth=auth,
                                                 username=username,
                                                 **moreargs)
    self.SetPosturl(BASEURL + 'Retrieve/Account')
    self.SetType('Account')

    self.SetRestdata([
        ('queryKey', 'userName'),
        ('queryData', username),
        ])


class RetrieveAliasRequest(Request):
  """Alias retrieval request."""

  def __init__(self, domain, auth, alias, **moreargs):
    """Initialize an alias retrieval request.

    Args:
      domain: string containing the domain to operate on
      auth: string containing your current auth token
      alias: name of the alias to retrieve
    """

    super(RetrieveAliasRequest, self).__init__(domain=domain, auth=auth,
                                               alias=alias,
                                               **moreargs)
    self.SetPosturl(BASEURL + 'Retrieve/Alias')
    self.SetType('Alias')

    self.SetRestdata([
        ('queryKey', 'aliasName'),
        ('queryData', alias),
        ])


class RetrieveMailingListRequest(Request):
  """Mailing list retrieval request."""

  def __init__(self, domain, auth, mailinglist, **moreargs):
    """Initialize a mailing list retrieval request.
    
    Args:
      domain: string containing the domain to operate on
      auth: string containing your current auth token
      mailinglist: name of the mailing list to retrieve
    """

    super(RetrieveMailingListRequest, self).__init__(domain=domain, auth=auth,
                                                     mailinglist=mailinglist,
                                                     **moreargs)
    self.SetPosturl(BASEURL + 'Retrieve/MailingList')
    self.SetType('MailingList')

    self.SetRestdata([
        ('queryKey', 'mailingListName'),
        ('queryData', mailinglist),
        ])


class DeleteAccountRequest(Request):
  """Account deletion request."""

  def __init__(self, domain, auth, username, **moreargs):
    """Initialize an account deletion request.

    Args:
      domain: string containing the domain to operate on
      auth: string containing your current auth token
      username: user to delete
    """

    super(DeleteAccountRequest, self).__init__(domain=domain, auth=auth,
                                               username=username,
                                               **moreargs)
    self.SetPosturl(BASEURL + 'Delete/Account')
    self.SetType('Account')

    self.SetRestdata([
        ('queryKey', 'userName'),
        ('queryData', username),
        ])


class DeleteAliasRequest(Request):
  """Alias deletion request."""

  def __init__(self, domain, auth, alias, **moreargs):
    """Initialize an alias deletion request.

    Args:
      domain: string containing the domain to operate on
      auth: string containing your current auth token
      alias: name of the alias to delete
    """

    super(DeleteAliasRequest, self).__init__(domain=domain, auth=auth,
                                             alias=alias,
                                             **moreargs)
    self.SetPosturl(BASEURL + 'Delete/Alias')
    self.SetType('Alias')

    self.SetRestdata([
        ('queryKey', 'aliasName'),
        ('queryData', alias),
        ])


class DeleteMailingListRequest(Request):
  """Mailing list deletion request."""

  def __init__(self, domain, auth, mailinglist, **moreargs):
    """Initialize a mailing list deletion request.

    Args:
      domain: string containing the domain to operate on
      auth: string containing your current auth token
      mailinglist: name of the mailing list to delete
    """

    super(DeleteMailingListRequest, self).__init__(domain=domain, auth=auth,
                                                   mailinglist=mailinglist,
                                                   **moreargs)
    self.SetPosturl(BASEURL + 'Delete/MailingList')
    self.SetType('MailingList')

    self.SetRestdata([
        ('queryKey', 'mailingListName'),
        ('queryData', mailinglist),
        ])


class Response(dict):
  """Models the response from a Provisioning API call."""

  def __init__(self, **moreargs):
    """Create a Response object.

    Args:
      **moreargs: unused; for inheritance
    """

    super(Response, self).__init__(**moreargs)
    self.success = False
    self.reason = None
    self.message = None

  def __repr__(self):
    if self.success:
      return 'Success: %s' % dict.__repr__(self)
    else:
      return 'Failure: %s' % self.reason

class _ResponseParser(xml.sax.handler.ContentHandler):
  """SAX ContentHandler for parsing Provisioning API response messages.

  Note that we should be using proper namespaces, but the expat
  sax driver does not support this, so we will just assume that there is
  an hs: prefix on all tags.
  """

  def __init__(self, resobj):
    """Initialize a _ResponseParser object.

    Args:
      resobj: a Response object that the parser will populate
    Note: superclass initializer not called;
    there's no interesting default behavior there.
    """

    self._resobj = resobj
    self._tagstack = []
    self._data = ''

  def startElement(self, name, attrs):
    """
    Override of the class method.
    Handles the start of an XML element.  Just pushes the tag on the
    tag stack.
    """

    self._tagstack.append(name)

  def endElement(self, name):
    """
    Override of the class method.
    Handles the end of an XML element.  Pop the tag of the stack, and assign
    the collected data as appropriate.
    NOTE:  this code will not handle XML that's structured like this:
    <hs:RetrievalSection>
      <elem> data
         <subelem> more data</subelem>
      </elem>
    </hs:RetrievalSection>
    i.e. where both the parent element and the subelement contain character
    data. However, this case does not occur in the Google Apps for
    Your Domain API, and will not be added to the 1.0 version.
    """

    poppedtag = self._tagstack.pop()
    assert name == poppedtag

    if name == 'hs:status':
      if self._data == 'Success(2000)':
        self._resobj.success = True
      else:
        self._resobj.success = False

    elif name == 'hs:reason':
      self._resobj.reason = self._data

    elif name == 'hs:extendedMessage':
      self._resobj.message = self._data

    else:

      # if we're in the <RetrievalSection>, record as data
      if self._tagstack.count('hs:RetrievalSection') > 0:
        (unused, recordname) = name.split(':', 1)

        # listify if more than one value.
        if recordname in self._resobj:
          val = self._resobj[recordname]
          if isinstance(val, types.ListType):
            self._resobj[recordname].append(self._data)
          else:
            self._resobj[recordname] = [val, self._data]
        else:
          self._resobj[recordname] = self._data

    self._data = ''

  def characters(self, content):
    """
    Override of the class method.
    Handle characters.  Shove them into self._data where they can be used
    later.
    """

    self._data += content

if __name__ == '__main__':
  pass
