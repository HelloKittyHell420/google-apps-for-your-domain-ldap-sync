#Describes how to run the unit tests included in v1.2 of the tool

# Introduction #
This is for developers interested in enhancing the code in the project for their purposes.  Also, for developers who want to submit code back to the project,

  1. running existing unit tests successfully AND
  1. submitring additional unit tests that cover all code changes

is required (although usually not by itself sufficient) to have a code submission accepted.


# Details #

To setup for the test

```
  cd tests
  vim your_testdata_config # to change location of your ldap server etc.
  ./gen_testdata.sh your_testdata_config
```

This should produce a folder called tests/testdata/.  If you did everything correctly there should be no dollar-signs ($) in any file in tests/testdata.

Then you can run

```
python sync_ldap_unittest.py
```