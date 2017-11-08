*******
History
*******

Next Release
============

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
