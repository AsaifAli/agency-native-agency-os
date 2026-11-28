from alembic.config import Config
from alembic.script import ScriptDirectory


def test_alembic_migration_graph_has_one_head():
    config = Config("alembic.ini")
    script = ScriptDirectory.from_config(config)

    assert len(script.get_heads()) == 1
