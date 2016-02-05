
```
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
[ldap-sync]
domain = 'yourgoogleappsdomain.com'
ldap_url = 'ldap://yourldapserver.yourdnsdomain.com'
timestamp = 'whenChanged'
google_operations = ['added', 'exited', 'updated', 'renamed']
mapping = {'GoogleUsername': "mail[:mail.find('@')]", 'GoogleFirstName': 'givenName', 'GoogleOldUsername': None, 'GoogleLastName': '"google"', 'GooglePassword': '"password"', 'GoogleApplyIPWhitelist': False, 'GoogleQuota': 'GoogleQuotaCallback'}
ldap_timeout = 15
ldap_password = 'yourldaproleaccountpassword'
max_threads = 10
ldap_admin_name = ' CN=yourldaproleaccount,DC=yourdnsdomain,DC=COM'
attrs = set(['mailNickname', 'primaryGroupID', 'cn', 'userPrincipalName', 'GoogleApplyIPWhitelist', 'meta-Google-action', 'distinguishedName', 'uSNCreated', 'mail', 'GoogleLastName', 'badPasswordTime', 'pwdLastSet', 'sAMAccountName', 'meta-last-updated', 'GoogleFirstName', 'badPwdCount', 'whenChanged', 'GoogleUsername', 'displayName', 'name', 'userAccountControl', 'uSNChanged', 'sn', 'GoogleOldUsername', 'givenName', 'GooglePassword', 'GoogleQuota', 'displayName'])
ldap_disabled_filter = '(&(objectClass=organizationalPerson)(badPwdCount>=1))'
ldap_user_filter = '(&(objectClass=organizationalPerson)(userAccountControl:1.2.840.113556.1.4.804:=512))'
password = 'yourgoogleappsroleaccountpassword'
admin = 'yourgoogleappsroleaccount@yourgoogleappsdomain.com'
ldap_base_dn = 'DC=yourdnsdomain,DC=COM'
```