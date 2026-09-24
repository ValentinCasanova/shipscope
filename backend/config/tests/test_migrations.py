"""Each migration works with the release before it.

A release migrates the database while the previous release's tasks still serve traffic,
and a rollback runs the previous code against the newer schema. django-migration-linter
reads each migration's SQL and flags what breaks the previous code, such as a new NOT
NULL column without a database default, or a dropped column. infra/README.md explains
how to change the schema in steps that pass.
"""

import pytest
from django_migration_linter import MigrationLinter

# Migrations that deliberately drop something no deployed release uses any more, by name
# (such as "0007_remove_order_notes"), each with a comment saying why. The linter's
# IgnoreMigration() operation would do the same from inside the migration, but the
# production image doesn't install the linter, so `migrate` would fail to import it.
IGNORED_MIGRATIONS: list[str] = []


@pytest.mark.django_db
def test_migrations_work_with_the_previous_release():
    linter = MigrationLinter(ignore_name=IGNORED_MIGRATIONS)

    # The report goes to stdout, which pytest shows when the test fails.
    linter.lint_all_migrations()
    linter.print_summary()

    assert not linter.has_errors
