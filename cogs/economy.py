import random
import datetime
from discord.ext import commands
from discord import app_commands, Interaction, Member, Message
import discord
from utils import fortune
from utils import economy_api

class Economy(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    def get_shared_id(self, user: discord.User):
        return str(user.id)

    async def ensure_user(self, shared_id: str):
        user = await economy_api.get_user(shared_id)
        if user is None:
            return await economy_api.create_user(shared_id)
        return user

    @app_commands.command(name="balance", description="あなたの所持金を表示します。")
    async def balance(self, interaction: Interaction):
        shared_id = self.get_shared_id(interaction.user)
        user = await self.ensure_user(shared_id)
        await interaction.response.send_message(
            f"💰 {interaction.user.mention} の所持金は {user['balance']} 円です。現在のレベルは Lv.{user['level']} です。"
        )

    @app_commands.command(name="work", description="働いてお金を稼ぎます。（1時間に1回）")
    async def work(self, interaction: Interaction):
        shared_id = self.get_shared_id(interaction.user)
        user = await self.ensure_user(shared_id)

        now = datetime.datetime.utcnow()
        last_str = user.get("last_work_time")
        if last_str:
            last_time = datetime.datetime.fromisoformat(last_str)
            diff = (now - last_time).total_seconds()
            if diff < 3600:
                minutes, seconds = divmod(int(3600 - diff), 60)
                return await interaction.response.send_message(
                    f"⏳ 次の /work まで {minutes}分{seconds}秒 残っています。", ephemeral=True
                )

        activity = user.get("activity_score", 100)
        level = user.get("level", 1)
        fortune_effects = await fortune.get_today_fortune_effects(interaction.user.id)
        income_multiplier = fortune_effects.get("income_multiplier", 1.0)
        income = int(random.randint(int(activity * level * 1.5 * 10), int(activity * level * 2.0 * 10)) * income_multiplier)


        await economy_api.update_user(shared_id, {
            "balance": user["balance"] + income,
            "last_work_time": now.isoformat()
        })

        await interaction.response.send_message(f"💼 お疲れさまです！{income} 円を獲得しました。")

    @app_commands.command(name="pay", description="他のユーザーにお金を送ります。")
    @app_commands.describe(target="送金相手", amount="送金金額")
    async def pay(self, interaction: Interaction, target: Member, amount: int):
        if amount <= 0 or target.bot or target.id == interaction.user.id:
            return await interaction.response.send_message("❌ 無効な送金リクエストです。", ephemeral=True)

        sender_id = self.get_shared_id(interaction.user)
        recipient_id = self.get_shared_id(target)

        sender = await self.ensure_user(sender_id)
        recipient = await self.ensure_user(recipient_id)

        if sender["balance"] < amount:
            return await interaction.response.send_message("❌ 残高不足です。", ephemeral=True)

        await economy_api.update_user(sender_id, {"balance": sender["balance"] - amount})
        await economy_api.update_user(recipient_id, {"balance": recipient["balance"] + amount})

        await interaction.response.send_message(
            f"✅ {interaction.user.mention} → {target.mention} に {amount} 円を送金しました。"
        )

    @app_commands.command(name="setbalance", description="管理者用：ユーザーの所持金を設定します。")
    @app_commands.describe(user="対象ユーザー", amount="設定金額")
    async def setbalance(self, interaction: Interaction, user: Member, amount: int):
        if not interaction.user.guild_permissions.administrator:
            return await interaction.response.send_message("🚫 管理者専用コマンドです。", ephemeral=True)

        shared_id = self.get_shared_id(user)
        await self.ensure_user(shared_id)

        await economy_api.update_user(shared_id, {"balance": amount})
        await interaction.response.send_message(
            f"✅ {user.mention} の所持金を {amount} 円に設定しました。"
        )

    @commands.Cog.listener()
    async def on_message(self, message: Message):
        if message.author.bot or len(message.content.strip()) < 5:
            return

        shared_id = self.get_shared_id(message.author)
        user = await self.ensure_user(shared_id)

        today = datetime.date.today()
        last_date_str = user.get("last_active_date")
        reset = False

        if last_date_str:
            last_date = datetime.date.fromisoformat(last_date_str)
            reset = (today - last_date).days >= 2
            activity = 100.0 if reset else user.get("activity_score", 100.0)
        else:
            activity = user.get("activity_score", 100.0)

        activity += round(random.uniform(0.5, 1.0), 2)

        # レベル再計算
        balance = user.get("balance", 0)
        total = balance + activity
        level = 1
        threshold, increment = 500, 150
        while total >= threshold:
            level += 1
            threshold += increment
            increment += 150

        # メッセージ報酬
        if random.randint(1, 10) <= 3:
            income = int(activity * level * 10)
            if reset or not last_date_str:
                income *= 10
            user["balance"] += income

        await economy_api.update_user(shared_id, {
            "activity_score": round(activity, 2),
            "last_active_date": today.isoformat(),
            "balance": user["balance"],
            "level": level
        })
    @app_commands.command(name="rank", description="ユーザーのレベルランキングを表示します。")
    @app_commands.describe(page="表示するページ番号（1ページ30人）")
    async def rank(self, interaction: Interaction, page: int = 1):
        # 全ユーザーデータ取得（economy_api側にall_users()がある前提）
        users = await economy_api.get_all_users()
        if not users:
            return await interaction.response.send_message("📉 ランキングデータが見つかりません。")

        # レベルでソート（降順）し、順位付きで整形
        users.sort(key=lambda x: x.get("level", 1), reverse=True)
        total_pages = (len(users) + 29) // 30
        page = max(1, min(page, total_pages))
        start = (page - 1) * 30
        end = start + 30
        ranking_slice = users[start:end]

        embed = discord.Embed(
            title=f"🏆 レベルランキング（ページ {page}/{total_pages}）",
            description="現在のトップユーザーたちのランキングです。",
            color=discord.Color.gold()
        )

        for i, user in enumerate(ranking_slice, start=start + 1):
            mention = f"<@{user['shared_id']}>"  # DiscordのユーザーID形式にして表示
            level = user.get("level", 1)
            embed.add_field(name=f"{i}位", value=f"{mention}：Lv.{level}", inline=False)

        await interaction.response.send_message(embed=embed)

# setup
async def setup(bot):
    await bot.add_cog(Economy(bot))