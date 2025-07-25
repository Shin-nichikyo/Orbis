import asyncpg
from discord.ext import commands

DB_CONFIG = {
    "user": "orbisuser",
    "password": "orbispass",
    "database": "orbis",
    "host": "orbis-db",
    "port": 5432,
}

class DBHandler(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.pool = None

    async def cog_load(self):
        self.pool = await asyncpg.create_pool(**DB_CONFIG)
        async with self.pool.acquire() as conn:
            # settingsテーブル作成
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS settings (
                    guild_id BIGINT,
                    key TEXT,
                    value TEXT,
                    PRIMARY KEY (guild_id, key)
                );
            """)

            # petsテーブル作成
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS pets (
                    guild_id BIGINT PRIMARY KEY,
                    pet_name TEXT,
                    level INT DEFAULT 1,
                    experience INT DEFAULT 0,
                    affection INT DEFAULT 0,
                    stage TEXT DEFAULT 'egg',
                    emotion TEXT DEFAULT 'neutral',
                    last_fed TIMESTAMP,
                    last_battle TIMESTAMP,
                    created_at TIMESTAMP DEFAULT NOW()
                );
            """)

    # === settings系 ===
    async def set_setting(self, guild_id: int, key: str, value: str):
        query = """
            INSERT INTO settings (guild_id, key, value)
            VALUES ($1, $2, $3)
            ON CONFLICT (guild_id, key)
            DO UPDATE SET value = EXCLUDED.value
        """
        async with self.pool.acquire() as conn:
            await conn.execute(query, guild_id, key, value)

    async def get_setting(self, guild_id: int, key: str) -> str | None:
        query = "SELECT value FROM settings WHERE guild_id = $1 AND key = $2"
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(query, guild_id, key)
            return row["value"] if row else None

    async def delete_setting(self, guild_id: int, key: str):
        query = "DELETE FROM settings WHERE guild_id = $1 AND key = $2"
        async with self.pool.acquire() as conn:
            await conn.execute(query, guild_id, key)

    async def delete_all_settings_for_guild(self, guild_id: int):
        query = "DELETE FROM settings WHERE guild_id = $1"
        async with self.pool.acquire() as conn:
            await conn.execute(query, guild_id)

    # === pets系 ===

    async def create_pet(self, guild_id: int, pet_name: str):
        query = """
            INSERT INTO pets (guild_id, pet_name)
            VALUES ($1, $2)
            ON CONFLICT (guild_id) DO NOTHING
        """
        async with self.pool.acquire() as conn:
            await conn.execute(query, guild_id, pet_name)

    async def get_pet(self, guild_id: int) -> dict | None:
        query = "SELECT * FROM pets WHERE guild_id = $1"
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(query, guild_id)
            if row:
                return dict(row)
            else:
                return None

    async def update_pet(self, guild_id: int, **kwargs):
        # kwargsには更新したいカラム名:値を渡す
        if not kwargs:
            return
        set_clause = ", ".join(f"{key} = ${idx+2}" for idx, key in enumerate(kwargs.keys()))
        query = f"UPDATE pets SET {set_clause} WHERE guild_id = $1"
        values = [guild_id, *kwargs.values()]
        async with self.pool.acquire() as conn:
            await conn.execute(query, *values)

    async def delete_pet(self, guild_id: int):
        query = "DELETE FROM pets WHERE guild_id = $1"
        async with self.pool.acquire() as conn:
            await conn.execute(query, guild_id)

async def setup(bot):
    await bot.add_cog(DBHandler(bot))
