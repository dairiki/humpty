*******
History
*******

Next Release
============

Bugs Fixed
----------

* Fix parsing of markers in ``EggInfo_Legacy.requires``.  Apparently,
  as ``of distlib==0.2.6``, ``distlib.markers.interpret`` no longer
  handles leading whitespace in the marker string well.

* Fix failing test ``test_humpty:TestScriptCopyer.test_copies_script``.
  Apparently, ``distlib.markers.interpret==0.2.6`` now just prepends
  the new hashbang line to the copied script, but does not remove
  the original hashbang.

Release 0.1 (2015-07-16)
========================

Initial release.
