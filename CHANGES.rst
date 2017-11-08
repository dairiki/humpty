*******
History
*******

Next Release
============

Bugs Fixed
----------

* Always create eggs with ``zip_safe=False``.  There currently seems
  to be no robust way to determine whether a package is zip_safe from
  its wheel. See `#3`__ for further discussion.
  (Thank you to immerrr.)

__ https://github.com/dairiki/humpty/pull/3

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
