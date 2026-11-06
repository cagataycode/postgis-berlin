"""Enable pg_stat_statements (slowest-query inspection after a demo session).

Needs shared_preload_libraries=pg_stat_statements, which docker-compose.yml sets.
Without the preload the extension still installs but its view errors on read, so
this is skipped quietly if the migrating role cannot create extensions.
"""

from alembic import op

revision = "0013_pg_stat_statements"
down_revision = "0012_tree_stats_view"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.get_bind().exec_driver_sql(
        """
        DO $$
        BEGIN
          CREATE EXTENSION IF NOT EXISTS pg_stat_statements;
        EXCEPTION WHEN insufficient_privilege OR undefined_file THEN
          RAISE NOTICE 'skipping pg_stat_statements';
        END
        $$;
        """
    )


def downgrade() -> None:
    op.get_bind().exec_driver_sql("DROP EXTENSION IF EXISTS pg_stat_statements")
