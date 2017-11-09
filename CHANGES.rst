*******
History
*******

Release 0.2 (2017-11-08)
========================

Python 2.6 is no longer supported.  We now test under cpython 2.7
and cpython 3.3 through 3.6.

Changed Behavior
----------------

* The strict check for wheel binary compatibility with the current platform
  has been removed.  Now a warning is printed in this case.
  When running under py35 or py36, distlib sometimes falsely reports
  that some wheels are not binary compatible. See distlib ticket `#93`__.

__ https://bitbucket.org/pypa/distlib/issues/93

Bugs Fixed
----------

* Fix ``EggInfo_Legacy.requires`` to work with recent versions of
  ``distlib``.  With ``distlib<=0.2.4``,
  ``distlib.wheel.Wheel.metadata.run_requires`` is a list of strings,
  taken from lines of the RFC822 style metadata.  With recent versions
  of ``distlib``, ``run_requires`` is a list of dicts in the "JSON"
  format described in :pep:`426`.  This addresses `#1`__.

__ https://github.com/dairiki/humpty/issues/1

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
