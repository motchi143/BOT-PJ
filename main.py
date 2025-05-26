import discord
from discord.ext import commands
import logging
from dotenv import load_dotenv
import os
import aiosqlite
import random
import shlex
from discord.ui import View, Button
import ast
import datetime

from cards.enhypen.group import cards as enhypen_cards
from cards.parkjihoon.soloist import cards as soloist_cards
from cards.straykids.group import cards as group_a_cards

cards = soloist_cards + group_a_cards + enhypen_cards  # Add more as you create more groups
print(f"Loaded {len(cards)} cards.")

load_dotenv()
token = os.getenv('DISCORD_TOKEN')
if not token:
    raise ValueError("DISCORD_TOKEN environment variable not set.")

handler = logging.FileHandler(filename='discord.log', encoding='utf-8', mode='w')
intents = discord.Intents.default()
intents.message_content = True
intents.members = True
intents.reactions = True

bot = commands.Bot(command_prefix='.', intents=intents)
bot.remove_command('help')

@bot.event
async def on_ready():
    print(f'Successfully logged in as {bot.user.name} - {bot.user.id}')
    async with aiosqlite.connect("inventory.db") as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS inventory (
                user_id INTEGER,
                card_code TEXT,
                card_name TEXT,
                card_group TEXT,
                card_rarity TEXT
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                username TEXT,
                registered_at TEXT,
                meowies INTEGER DEFAULT 0,
                last_daily TEXT,
                streak INTEGER DEFAULT 0,
                best_streak INTEGER DEFAULT 0
            )
        """)
        await db.commit()

@bot.event
async def on_member_join(member):
    await member.send(f'Welcome to the server meowie, {member.name} <3')

insults = [
    "slut", "idiot", "stupid", "dumb", "bitch", "btch", "asshole", "fool",
    "jerk", "moron", "loser", "fatty", "dickhead", "dick"
]

@bot.event
async def on_message(message):
    if message.author == bot.user:
        return

    if any(insult in message.content.lower() for insult in insults):
        await message.delete()
        await message.channel.send(f"{message.author.mention} Please meowie, refrain from using inappropriate language.")

    await bot.process_commands(message)

@bot.command(aliases=['m', 'mw'])
@commands.cooldown(1, 5*60, commands.BucketType.user)  # 5 minutes
async def meow(ctx):
    card = random.choice(cards)
    code = card.get("code", "UNKNOWN")
    async with aiosqlite.connect("inventory.db") as db:
        await db.execute(
            "INSERT INTO inventory (user_id, card_code, card_name, card_group, card_rarity) VALUES (?, ?, ?, ?, ?)",
            (ctx.author.id, code, card["name"], card["group"], card["rarity"])
        )
        await db.commit()
    embed = discord.Embed(
        title="⪩. .⪨ Meowie catch your card before its escapes!",
        description=f"⋆˚࿔ **{card['name']}** - {card['group']} ({card['rarity']})\n⋆˚࿔ **Code** - `{code}`",
        color=0xFFE529  # pastel yellow
    )
    if "link" in card:
        embed.set_image(url=card["link"])
    await ctx.send(embed=embed)

class InventoryView(View):
    def __init__(self, pages, author):
        super().__init__(timeout=60)
        self.pages = pages
        self.page = 0
        self.author = author

    async def update_page(self, interaction):
        await interaction.response.edit_message(embed=self.pages[self.page], view=self)

    @discord.ui.button(label="Previous", style=discord.ButtonStyle.secondary)
    async def previous(self, interaction: discord.Interaction, button: Button):
        if interaction.user != self.author:
            await interaction.response.send_message("This is not your inventory!", ephemeral=True)
            return
        if self.page > 0:
            self.page -= 1
            await self.update_page(interaction)
        else:
            await interaction.response.defer()

    @discord.ui.button(label="Next", style=discord.ButtonStyle.secondary)
    async def next(self, interaction: discord.Interaction, button: Button):
        if interaction.user != self.author:
            await interaction.response.send_message("This is not your inventory!", ephemeral=True)
            return
        if self.page < len(self.pages) - 1:
            self.page += 1
            await self.update_page(interaction)
        else:
            await interaction.response.defer()

@bot.command(aliases=['inv', 'i'])
async def inventory(ctx, member: discord.Member = None, *, filter: str = None):
    member = member or ctx.author
    group_filter = None
    rarity_filter = None
    name_filter = None

    if filter:
        for part in shlex.split(filter):
            if part.startswith("group="):
                group_filter = part.split("=", 1)[1].lower()
            if part.startswith("rarity="):
                rarity_filter = part.split("=", 1)[1].lower()
            if part.startswith("name="):
                name_filter = part.split("=", 1)[1].lower()

    async with aiosqlite.connect("inventory.db") as db:
        async with db.execute(
            "SELECT card_code, card_name, card_group, card_rarity FROM inventory WHERE user_id = ?",
            (member.id,)
        ) as cursor:
            cards_list = await cursor.fetchall()

    # Apply filters
    if group_filter:
        cards_list = [c for c in cards_list if c[2].lower() == group_filter]
    if rarity_filter:
        cards_list = [c for c in cards_list if c[3].lower() == rarity_filter]
    if name_filter:  # Add this block
        cards_list = [c for c in cards_list if name_filter in c[1].lower()]

    if not cards_list:
        await ctx.send("No cards found with those filters!" if filter else "Your inventory is empty!")
        return

    # Count duplicates by code
    card_counts = {}
    for code, name, group, rarity in cards_list:
        key = (code, name, group, rarity)
        card_counts[key] = card_counts.get(key, 0) + 1

    # Split into pages of 10
    items = [
        f"♡ `{code}` {name} - {group} ({rarity}) x{count}" if count > 1 else f"♡ `{code}` {name} - {group} ({rarity})"
        for (code, name, group, rarity), count in card_counts.items()
    ]
    per_page = 10
    pages = []
    for i in range(0, len(items), per_page):
        desc = "\n".join(items[i:i+per_page])
        embed = discord.Embed(
            title=">^•-•^< Kitty's Inventory",
            description=desc,
            color=0xA7C7E7  # pastel blue
        )
        embed.set_footer(text=f"Page {i//per_page+1}/{(len(items)-1)//per_page+1}")
        pages.append(embed)

    view = InventoryView(pages, ctx.author)
    await ctx.send(embed=pages[0], view=view)

@bot.command()
async def register(ctx):
    """Register yourself to the bot and save your registration date."""
    async with aiosqlite.connect("inventory.db") as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                username TEXT,
                registered_at TEXT,
                meowies INTEGER DEFAULT 0,
                last_daily TEXT,
                streak INTEGER DEFAULT 0,
                best_streak INTEGER DEFAULT 0
            )
        """)
        await db.execute("""
            INSERT OR IGNORE INTO users (user_id, username, registered_at, meowies)
            VALUES (?, ?, datetime('now'), 0)
        """, (ctx.author.id, str(ctx.author)))
        await db.commit()
    embed = discord.Embed(
        description=f"{ctx.author.mention} You are now registered ദ്ദി(• ˕ •マ.ᐟ Type `.profile` or `.purr` to view your profile.",
        color=0xD1B3FF  # pastel purple
    )
    await ctx.send(embed=embed)

@bot.command(aliases=['profile', 'p'])
async def purr(ctx, member: discord.Member = None):
    """View your profile or someone else's."""
    member = member or ctx.author
    async with aiosqlite.connect("inventory.db") as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                username TEXT,
                registered_at TEXT,
                meowies INTEGER DEFAULT 0,
                last_daily TEXT,
                streak INTEGER DEFAULT 0,
                best_streak INTEGER DEFAULT 0
            )
        """)
        async with db.execute("SELECT registered_at, meowies, streak, best_streak FROM users WHERE user_id = ?", (member.id,)) as cursor:
            row = await cursor.fetchone()
        if not row:
            if member == ctx.author:
                await ctx.send("Meowie you're not registered yet, silly you ૮₍ ˃ ⤙ ˂ ₎ა use `.register` first <3")
            else:
                await ctx.send(f"{member.display_name} is not registered yet.")
            return

        reg_date, meowies, streak, best_streak = row
        async with db.execute("SELECT COUNT(*) FROM inventory WHERE user_id = ?", (member.id,)) as cursor:
            card_count = (await cursor.fetchone())[0]

    embed = discord.Embed(
        title=f"/ᐠ > ˕ <マ ₊˚⊹♡ {member.display_name}'s profile",
        color=0xFFB7CE  # pastel pink
    )
    embed.add_field(name="⋆˙⟡ Username", value=str(member), inline=False)
    embed.add_field(name="✮⋆˙ Registered At", value=reg_date, inline=False)
    embed.add_field(name="⋆˙⟡ Total Cards", value=str(card_count), inline=False)
    embed.add_field(name="✮⋆˙ Meowies", value=str(meowies), inline=False)
    embed.add_field(name="⋆˙⟡ Current Streak", value=f"{streak} days", inline=False)
    embed.add_field(name="✮⋆˙ Best Streak", value=f"{best_streak} days", inline=False)
    await ctx.send(embed=embed)

@bot.command(aliases=['add', 'u'])
@commands.has_permissions(administrator=True)
async def update(ctx, *, args):
    """
    Add a new card to the bot.
    Usage: .update code=CODE name=NAME group=FOLDER_NAME groupname="DISPLAY NAME" rarity=RARITY [version=1] [event=true/false] [link=URL]
    """
    params = {}
    for part in shlex.split(args):
        if '=' in part:
            k, v = part.split('=', 1)
            params[k.lower()] = v

    required = ['code', 'name', 'group', 'rarity']
    if not all(k in params for k in required):
        await ctx.send("Missing required parameters! Usage: .update code=CODE name=NAME group=FOLDER_NAME groupname=\"DISPLAY NAME\" rarity=RARITY [version=1] [event=true/false] [link=URL]")
        return

    code = params['code']
    name = params['name']
    folder = params['group'].replace(" ", "").lower()  # folder name, no spaces
    group_display = params.get('groupname', params['group'])  # display name, can have spaces
    rarity = params['rarity']
    event = params.get('event', 'false').lower() == 'true'
    link = params.get('link', '')
    version = str(params.get('version', '1'))

    folder_path = f"cards/{folder}"
    file_path = f"{folder_path}/group.py"

    os.makedirs(folder_path, exist_ok=True)

    card_dict = f"""{{
        "code": "{code}",
        "name": "{name}",
        "group": "{group_display}",
        "rarity": "{rarity}",
        "version": {version},
        "event": {str(event)},
        "link": "{link}"
    }},"""

    if not os.path.exists(file_path):
        with open(file_path, "w", encoding="utf-8") as f:
            f.write("cards = [\n")
            f.write(card_dict + "\n")
            f.write("]\n")
    else:
        with open(file_path, "r+", encoding="utf-8") as f:
            lines = f.readlines()
            while lines and lines[-1].strip() == "]":
                lines.pop()
            if lines and not lines[-1].strip().endswith(","):
                lines[-1] = lines[-1].rstrip("\n") + ",\n"
            lines.append(card_dict + "\n")
            lines.append("]\n")
            f.seek(0)
            f.writelines(lines)
            f.truncate()

    await ctx.send(f"Card for **{name}** added to `{file_path}` with code `{code}`!")

@bot.command()
@commands.has_permissions(administrator=True)
async def clean_duplicates(ctx):
    """
    Remove duplicate cards with different casing for Park Jihoon and other known duplicates.
    """
    async with aiosqlite.connect("inventory.db") as db:
        # Normalize all Park Jihoon entries to "Park Jihoon"
        await db.execute("""
            UPDATE inventory
            SET card_name = 'Park Jihoon'
            WHERE LOWER(card_name) = 'park jihoon' OR card_name = 'PARK JIHOON'
        """)
        # Remove exact duplicates (same user, name, group, rarity)
        await db.execute("""
            DELETE FROM inventory
            WHERE rowid NOT IN (
                SELECT MIN(rowid)
                FROM inventory
                GROUP BY user_id, card_name, card_group, card_rarity
            )
        """)
        await db.commit()
    await ctx.send("Duplicates cleaned and card names normalized!")

@bot.command()
@commands.has_permissions(administrator=True)
async def normalize(ctx, *, args):
    """
    Normalize card fields in the inventory.
    Usage: .normalize field=card_group old="STRAY" new="STRAY KIDS"
    """
    params = {}
    for part in shlex.split(args):
        if '=' in part:
            k, v = part.split('=', 1)
            params[k.lower()] = v

    field = params.get('field')
    old = params.get('old')
    new = params.get('new')

    allowed_fields = ['card_name', 'card_group', 'card_rarity']
    if field not in allowed_fields or not old or not new:
        await ctx.send("Usage: .normalize field=card_group old=\"STRAY\" new=\"STRAY KIDS\"")
        return

    async with aiosqlite.connect("inventory.db") as db:
        await db.execute(
            f"UPDATE inventory SET {field} = ? WHERE {field} = ?",
            (new, old)
        )
        await db.commit()
    await ctx.send(f"All `{old}` in `{field}` have been changed to `{new}`.")

help_pages = [
    discord.Embed(
        title="(づ> v <)づ♡ User Commands - Page 1",
        description=(
            "**.meow** — Receive a random card. (aliases: .m, .mw)\n"
            "**.inventory [filters]** — Check your (or someone else) cards. Example: `.inv group=\"STRAY KIDS\"` (aliases: .inv, .i)\n"
            "**.register** — Register yourself to the bot.\n"
            "**.purr [user]** — Display your (or another user's) profile (aliases: .profile, .p)\n"
            "**.view code** — View a card you own by its code. (aliases: .v)\n"
            "**.balance [user]** — Check your (or another user's) meowie balance. (aliases: .bal, .b)\n"
        ),
        color=0xF9D8A7
    ),
    discord.Embed(
        title="(づ> v <)づ♡ User Commands - Page 2",
        description=(
            "**.allcards [filters]** — List all available cards on the bot. (aliases: .all, .ac, .a)\n"
            "**.cardcount** — Show how many cards are loaded.\n"
            "**.cooldown** — Show your cooldowns for daily and meow. (aliases: .cd)\n"
            "**.daily** — Claim your daily reward. (aliases: .d)\n"
            "**.paws** — Gift a card you own to another user. (aliases: .pawsgift, .trade, .pg)\n"
            "**.send** — Send meowies to another user.\n"
            "**.help** — Show this help message hehe.\n"
        ),
        color=0xF9D8A7
    ),
    discord.Embed(
        title="(づ> v <)づ♡ Admin Commands - Page 3",
        description=(
            "**.update ...** — Add a new card (admin only). (aliases: .add, .u)\n"
            "**.meowies add/remove @user amount** — Add or remove meowies from a user (admin only).\n"
            "**.gift @user code [amount]** — Gift one or more copies of a card to a user (admin only). (aliases: .give, .giftcard, .gc, .g)\n"
            "**.removecard @user code [amount]** — Remove one or more copies of a card from a user (admin only). (aliases: .removec, .remove, .rc, .r)\n"
            "**.massgift @user CODE1:AMOUNT1 ...** — Gift multiple cards at once (admin only). (aliases: .mass, .mg)\n"
            "**.massremovecards @user CODE1:AMOUNT1 ...** — Remove multiple cards at once (admin only). (aliases: .massrc, .massremovec, .massremove, .mrc)\n"
            "**.clean_duplicates** — Remove duplicate cards (admin only).\n"
            "**.normalize field=... old=... new=...** — Normalize card fields (admin only).\n"
            "**.resetcooldown [@user] [command]** — Reset cooldowns for yourself or another user (admin only). (aliases: .resetcd, .resetcooldowns, .rcd, .reset)\n"
        ),
        color=0xF9D8A7
    ),
    discord.Embed(
        title="(づ> v <)づ♡ Owner/Utility Commands - Page 4",
        description=(
            "**.reload** — Reload all cogs (dev/owner only).\n"
            "**.unload extension** — Unload a cog (dev/owner only).\n"
            "**.load extension** — Load a cog (dev/owner only).\n"
        ),
        color=0xF9D8A7
    ),
]

class HelpView(View):
    def __init__(self):
        super().__init__(timeout=60)
        self.page = 0

    async def update_embed(self, interaction):
        await interaction.response.edit_message(embed=help_pages[self.page], view=self)

    @discord.ui.button(label="Previous", style=discord.ButtonStyle.secondary)
    async def previous(self, interaction: discord.Interaction, button: Button):
        if self.page > 0:
            self.page -= 1
            await self.update_embed(interaction)
        else:
            await interaction.response.defer()

    @discord.ui.button(label="Next", style=discord.ButtonStyle.secondary)
    async def next(self, interaction: discord.Interaction, button: Button):
        if self.page < len(help_pages) - 1:
            self.page += 1
            await self.update_embed(interaction)
        else:
            await interaction.response.defer()

@bot.command()
async def help(ctx):
    """Show help pages with navigation buttons."""
    view = HelpView()
    await ctx.send(embed=help_pages[0], view=view)

@bot.command(aliases=['v'])
async def view(ctx, code: str):
    """View a card by its code if you own it."""
    code = code.upper()
    async with aiosqlite.connect("inventory.db") as db:
        async with db.execute(
            "SELECT card_name, card_group, card_rarity FROM inventory WHERE user_id = ? AND card_code = ?",
            (ctx.author.id, code)
        ) as cursor:
            row = await cursor.fetchone()
    if not row:
        await ctx.send(f"You don't own a card with code `{code}`!")
        return

    # Find the card in your loaded cards list to get the image/link
    card = next((c for c in cards if c.get("code", "").upper() == code), None)
    if not card:
        await ctx.send("Card data not found.")
        return

    embed = discord.Embed(
        title=f"{card['name']} - {card['group']} ({card['rarity']})",
        color=0xFF6785  # pastel blue or any pastel color you want
    )
    if "link" in card:
        embed.set_image(url=card["link"])
    embed.set_footer(text=f"Code: {code}")
    await ctx.send(embed=embed)

@bot.command()
async def cardcount(ctx):
    await ctx.send(f"Loaded {len(cards)} cards.")

@bot.command(aliases=['bal', 'b'])
async def balance(ctx, member: discord.Member = None):
    """Check your (or another user's) meowie balance."""
    member = member or ctx.author
    async with aiosqlite.connect("inventory.db") as db:
        async with db.execute(
            "SELECT meowies FROM users WHERE user_id = ?",
            (member.id,)
        ) as cursor:
            row = await cursor.fetchone()
    if not row:
        await ctx.send(f"{member.display_name} is not registered yet.")
        return
    meowies = row[0]
    embed = discord.Embed(
        title=f"/ᐠ˵> ˕ <˵マ {member.display_name}'s meowie balance",
        description=f"💰 **{meowies} meowies**",
        color=0xFFB7CE  # pastel pink
    )
    await ctx.send(embed=embed)

@bot.command()
@commands.has_permissions(administrator=True)
async def meowies(ctx, action: str, member: discord.Member, amount: int):
    """
    Add or remove meowies from a user.
    Usage: .meowies add @user 50
           .meowies remove @user 20
    """
    action = action.lower()
    if action not in ["add", "remove"]:
        await ctx.send("Action must be 'add' or 'remove'.")
        return

    async with aiosqlite.connect("inventory.db") as db:
        async with db.execute("SELECT meowies FROM users WHERE user_id = ?", (member.id,)) as cursor:
            row = await cursor.fetchone()
        if not row:
            await ctx.send(f"{member.display_name} is not registered.")
            return
        current = row[0]
        if action == "add":
            new_amount = current + amount
        else:
            new_amount = max(0, current - amount)
        await db.execute("UPDATE users SET meowies = ? WHERE user_id = ?", (new_amount, member.id))
        await db.commit()
    await ctx.send(f"{member.display_name} now has {new_amount} meowies.")

@bot.command(aliases=['give', 'giftcard', 'gc', 'g'])
@commands.has_permissions(administrator=True)
async def gift(ctx, member: discord.Member, code: str, amount: int = 1):
    """Gift one or more copies of a card (by code) to a user."""
    code = code.upper()
    card = next((c for c in cards if c.get("code", "").upper() == code), None)
    if not card:
        await ctx.send("Card code not found.")
        return
    async with aiosqlite.connect("inventory.db") as db:
        for _ in range(amount):
            await db.execute(
                "INSERT INTO inventory (user_id, card_code, card_name, card_group, card_rarity) VALUES (?, ?, ?, ?, ?)",
                (member.id, code, card["name"], card["group"], card["rarity"])
            )
        await db.commit()
    await ctx.send(f"Gave `{card['name']}` ({code}) x{amount} to {member.display_name}.")

@bot.command(aliases=['pawsgift', 'trade', 'pg'])
async def paws(ctx, member: discord.Member, code: str, amount: int = 1):
    """Gift a card you own to another user."""
    if member.id == ctx.author.id:
        await ctx.send("What are you trying to do huh ? /ᐠ - ˕ -マ Ⳋ You can't gift cards to yourself, silly kitty !")
        return

    code = code.upper()
    async with aiosqlite.connect("inventory.db") as db:
        # Check if sender owns enough copies
        async with db.execute(
            "SELECT COUNT(*) FROM inventory WHERE user_id = ? AND card_code = ?",
            (ctx.author.id, code)
        ) as cursor:
            count = (await cursor.fetchone())[0]
        if count < amount:
            await ctx.send(f"Oopsies, you are so broke lol. (˵ •̀ ᴗ - ˵ ) You don't have {amount} of `{code}` to gift!")
            return

        # Remove from sender
        for _ in range(amount):
            await db.execute(
                "DELETE FROM inventory WHERE rowid IN (SELECT rowid FROM inventory WHERE user_id = ? AND card_code = ? LIMIT 1)",
                (ctx.author.id, code)
            )
        # Get card info for recipient
        card = next((c for c in cards if c.get("code", "").upper() == code), None)
        if not card:
            await ctx.send("Card data not found.")
            return
        # Add to recipient
        for _ in range(amount):
            await db.execute(
                "INSERT INTO inventory (user_id, card_code, card_name, card_group, card_rarity) VALUES (?, ?, ?, ?, ?)",
                (member.id, code, card["name"], card["group"], card["rarity"])
            )
        await db.commit()
    await ctx.send(f"{ctx.author.display_name} gifted `{code}` x{amount} to {member.display_name}!")

@bot.command(aliases=['mass', 'mg'])
@commands.has_permissions(administrator=True)
async def massgift(ctx, member: discord.Member, *args):
    """
    Gift multiple cards to a user.
    Usage: .massgift @user CODE1:AMOUNT1 CODE2:AMOUNT2 ...
    Example: .massgift @user SOLPJF1:2 STRFXF1:1
    """
    if not args:
        await ctx.send("Usage: .massgift @user CODE1:AMOUNT1 CODE2:AMOUNT2 ...")
        return
    async with aiosqlite.connect("inventory.db") as db:
        for arg in args:
            if ':' in arg:
                code, amount = arg.split(':', 1)
                try:
                    amount = int(amount)
                except ValueError:
                    await ctx.send(f"Invalid amount for {code}.")
                    continue
            else:
                code = arg
                amount = 1
            code = code.upper()
            card = next((c for c in cards if c.get("code", "").upper() == code), None)
            if not card:
                await ctx.send(f"Card code `{code}` not found.")
                continue
            for _ in range(amount):
                await db.execute(
                    "INSERT INTO inventory (user_id, card_code, card_name, card_group, card_rarity) VALUES (?, ?, ?, ?, ?)",
                    (member.id, code, card["name"], card["group"], card["rarity"])
                )
        await db.commit()
    await ctx.send(f"Gifted cards to {member.display_name}!")

@bot.command(aliases=['removecard', 'removec', 'remove', 'rc', 'r'])
@commands.has_permissions(administrator=True)
async def remove_card(ctx, member: discord.Member, code: str, amount: int = 1):
    """Remove one or more copies of a card (by code) from a user's inventory."""
    code = code.upper()
    async with aiosqlite.connect("inventory.db") as db:
        for _ in range(amount):
            await db.execute(
                "DELETE FROM inventory WHERE rowid IN (SELECT rowid FROM inventory WHERE user_id = ? AND card_code = ? LIMIT 1)",
                (member.id, code)
            )
        await db.commit()
    await ctx.send(f"Removed `{code}` x{amount} from {member.display_name}'s inventory.")

@bot.command(aliases=['massrc', 'massremovec', 'massremove', 'mrc'])
@commands.has_permissions(administrator=True)
async def massremovecards(ctx, member: discord.Member, *args):
    """
    Remove multiple cards from a user.
    Usage: .massremovecards @user CODE1:AMOUNT1 CODE2:AMOUNT2 ...
    Example: .massremovecards @user SOLPJF1:2 STRFXF1:1
    """
    if not args:
        await ctx.send("Usage: .massremovecards @user CODE1:AMOUNT1 CODE2:AMOUNT2 ...")
        return
    async with aiosqlite.connect("inventory.db") as db:
        for arg in args:
            if ':' in arg:
                code, amount = arg.split(':', 1)
                try:
                    amount = int(amount)
                except ValueError:
                    await ctx.send(f"Invalid amount for {code}.")
                    continue
            else:
                code = arg
                amount = 1
            code = code.upper()
            for _ in range(amount):
                await db.execute(
                    "DELETE FROM inventory WHERE rowid IN (SELECT rowid FROM inventory WHERE user_id = ? AND card_code = ? LIMIT 1)",
                    (member.id, code)
                )
        await db.commit()
    await ctx.send(f"Removed specified cards from {member.display_name}'s inventory.")

@bot.command(aliases=['d'])
@commands.cooldown(1, 24*3600, commands.BucketType.user)  # 24 hours cooldown
async def daily(ctx):
    """Claim your daily reward: meowies and cards. Keep your streak for bonuses!"""
    user_id = ctx.author.id
    now = datetime.datetime.utcnow()
    async with aiosqlite.connect("inventory.db") as db:
        # Ensure user exists
        await db.execute("""
            INSERT OR IGNORE INTO users (user_id, username, registered_at, meowies, last_daily, streak, best_streak)
            VALUES (?, ?, datetime('now'), 0, NULL, 0, 0)
        """, (user_id, str(ctx.author)))
        await db.commit()

        # Get user info
        async with db.execute("SELECT meowies, last_daily, streak, best_streak FROM users WHERE user_id = ?", (user_id,)) as cursor:
            row = await cursor.fetchone()
        meowies, last_daily, streak, best_streak = row
        bonus = ""
        # Check streak
        if last_daily:
            last_daily_dt = datetime.datetime.fromisoformat(last_daily)
            delta = now - last_daily_dt
            if delta.total_seconds() < 23*3600:  # less than 23h, prevent early claim
                hours = int((23*3600 - delta.total_seconds()) // 3600)
                minutes = int(((23*3600 - delta.total_seconds()) % 3600) // 60)
                await ctx.send(f"Hey!ㅤ/ᐠ - ˕ -マ Your greed sickens me, you already claimed your daily duh! Come back in {hours}h {minutes}m.")
                return
            elif delta.total_seconds() < 48*3600:
                streak += 1
            else:
                streak = 1
        else:
            streak = 1

        # Update best streak
        if streak > (best_streak or 0):
            best_streak = streak

        # Calculate rewards
        reward_meowies = 100
        reward_cards = 1 + (streak // 30)  # +1 card every 30 days
        card_list = [random.choice(cards) for _ in range(reward_cards)]
        bonus_cards = []

        # 7-day streak bonus
        if streak % 7 == 0:
            reward_meowies += 300
            purrfect_cards = [c for c in cards if c.get("rarity", "").lower() == "purrfect"]
            if purrfect_cards:
                bonus_card = random.choice(purrfect_cards)
                bonus_cards.append(bonus_card)
                bonus = " and a special Purrfect card!"

        # Update user data
        meowies += reward_meowies
        await db.execute("UPDATE users SET meowies = ?, last_daily = datetime('now'), streak = ?, best_streak = ? WHERE user_id = ?",
                         (meowies, streak, best_streak, user_id))
        await db.commit()

        # Prepare card embeds
        card_embeds = []
        for card in card_list:
            code = card.get("code", "UNKNOWN")
            embed = discord.Embed(
                title="⪩. .⪨ You got a new card!",
                description=f"⋆˚࿔ **{card['name']}** - {card['group']} ({card['rarity']})\n⋆˚࿔ **Code** - `{code}`",
                color=0xFFE529  # pastel yellow
            )
            if "link" in card:
                embed.set_image(url=card["link"])
            card_embeds.append(embed)

        # Send reward message
        reward_embed = discord.Embed(
            title="/ᐠ≽•ヮ•≼マ Daily Reward Claimed!",
            description=f"You succefully claimed your daily reward of **{reward_meowies} meowies** and {len(card_list)} card(s){bonus}!",
            color=0xbbff86  # pastel green
        )
        await ctx.send(embed=reward_embed)

        # Send cards in separate messages if multiple
        if len(card_embeds) > 1:
            for embed in card_embeds:
                await ctx.send(embed=embed)
        elif card_embeds:
            await ctx.send(embed=card_embeds[0])

@bot.command()
@commands.is_owner()
async def reload(ctx):
    """Reload all cogs (modules)."""
    for filename in os.listdir('./cogs'):
        if filename.endswith('.py'):
            await bot.reload_extension(f'cogs.{filename[:-3]}')
    await ctx.send("All cogs reloaded.")

@bot.command()
@commands.is_owner()
async def unload(ctx, extension):
    """Unload a cog (module)."""
    try:
        await bot.unload_extension(f'cogs.{extension}')
        await ctx.send(f"Unloaded cog: {extension}")
    except Exception as e:
        await ctx.send(f"Error unloading cog: {extension}\n{str(e)}")

@bot.command()
@commands.is_owner()
async def load(ctx, extension):
    """Load a cog (module)."""
    try:
        await bot.load_extension(f'cogs.{extension}')
        await ctx.send(f"Loaded cog: {extension}")
    except Exception as e:
        await ctx.send(f"Error loading cog: {extension}\n{str(e)}")

# Error handling for commands
@bot.event
async def on_command_error(ctx, error):
    if isinstance(error, commands.CommandOnCooldown):
        # Check which command triggered the cooldown
        cmd = ctx.command.qualified_name if ctx.command else ""
        if cmd in ["daily", "d"]:
            hours = int(error.retry_after // 3600)
            minutes = int((error.retry_after % 3600) // 60)
            if hours > 0:
                time_left = f"{hours}h {minutes}m"
            else:
                time_left = f"{minutes}m"
            await ctx.send(f"Hold on kitty, you can't use it yet hehe! (づ> v <)づ Try again in {time_left}")
        else:
            minutes = int(error.retry_after // 60)
            seconds = int(error.retry_after % 60)
            if minutes > 0:
                time_left = f"{minutes}m {seconds}s"
            else:
                time_left = f"{seconds}s"
            await ctx.send(f"Hold on kitty, you can't use it yet hehe! (づ> v <)づ Try again in {time_left}")
    elif isinstance(error, commands.MissingPermissions):
        await ctx.send("Pookie.. now what are you trying to do huh ? You don't have permission to use this command, sucks to be you.")
    elif isinstance(error, commands.BadArgument):
        await ctx.send("Invalid argument passed. Please check and try again.")
    else:
        # Print the error to the console for debugging
        import traceback
        traceback.print_exception(type(error), error, error.__traceback__)
        await ctx.send(f"An error occurred: {error}")

# Add this to handle uncaught exceptions
@bot.event
async def on_error(event, *args, **kwargs):
    import traceback
    traceback.print_exc()

@bot.command(aliases=['cd'])
async def cooldown(ctx):
    """Show your cooldowns for daily and meow."""
    # Daily cooldown
    async with aiosqlite.connect("inventory.db") as db:
        async with db.execute("SELECT last_daily FROM users WHERE user_id = ?", (ctx.author.id,)) as cursor:
            row = await cursor.fetchone()
    now = datetime.datetime.utcnow()
    daily_left = None
    if row and row[0]:
        last_daily = datetime.datetime.fromisoformat(row[0])
        delta = now - last_daily
        if delta.total_seconds() < 24*3600:
            seconds_left = int(24*3600 - delta.total_seconds())
            hours = seconds_left // 3600
            minutes = (seconds_left % 3600) // 60
            daily_left = f"{hours}h {minutes}m"
        else:
            daily_left = "Ready!"
    else:
        daily_left = "Ready!"

    # Meow cooldown (does NOT trigger the cooldown!)
    meow_cooldown = bot.get_command('meow')._buckets.get_bucket(ctx.message).get_retry_after()
    if meow_cooldown:
        minutes = int(meow_cooldown // 60)
        seconds = int(meow_cooldown % 60)
        meow_left = f"{minutes}m {seconds}s"
    else:
        meow_left = "Ready!"

    embed = discord.Embed(
        title="/ᐠ ˵> ˕ <˵マ Cooldowns",
        description=(
            f"**Daily:** {daily_left}\n"
            f"**Meow:** {meow_left}"
        ),
        color=0xA7C7E7
    )
    await ctx.send(embed=embed)

@bot.command(aliases=['resetcd', 'resetcooldowns', 'rcd', 'reset'])
@commands.has_permissions(administrator=True)
async def resetcooldown(ctx, member: discord.Member = None, command: str = "all"):
    """
    Reset cooldowns for yourself or another user.
    Usage: .resetcooldown [@user] [command]
    Example: .resetcooldown @username meow
             .resetcooldown daily
             .resetcooldown @username all
    """
    member = member or ctx.author
    commands_to_reset = []
    if command == "all":
        commands_to_reset = ["meow", "daily"]
    else:
        commands_to_reset = [command.lower()]

    # Helper class to simulate a message object for cooldown reset
    class FakeMsg:
        def __init__(self, author, channel, guild):
            self.author = author
            self.channel = channel
            self.guild = guild

    for cmd_name in commands_to_reset:
        cmd = bot.get_command(cmd_name)
        if cmd:
            # Reset the cooldown bucket for the target member
            fake_msg = FakeMsg(member, ctx.channel, ctx.guild)
            bucket = cmd._buckets.get_bucket(fake_msg)
            bucket.reset()

    # For daily, also reset the last_daily in the database
    if "daily" in commands_to_reset:
        async with aiosqlite.connect("inventory.db") as db:
            await db.execute("UPDATE users SET last_daily = NULL WHERE user_id = ?", (member.id,))
            await db.commit()

    await ctx.send(f"Cooldowns reset for {member.display_name} ({', '.join(commands_to_reset)})!")

class AllCardsView(View):
    def __init__(self, pages, author):
        super().__init__(timeout=60)
        self.pages = pages
        self.page = 0
        self.author = author

    async def update_page(self, interaction):
        await interaction.response.edit_message(embed=self.pages[self.page], view=self)

    @discord.ui.button(label="Previous", style=discord.ButtonStyle.secondary)
    async def previous(self, interaction: discord.Interaction, button: Button):
        if interaction.user != self.author:
            await interaction.response.send_message("This is not your session!", ephemeral=True)
            return
        if self.page > 0:
            self.page -= 1
            await self.update_page(interaction)
        else:
            await interaction.response.defer()

    @discord.ui.button(label="Next", style=discord.ButtonStyle.secondary)
    async def next(self, interaction: discord.Interaction, button: Button):
        if interaction.user != self.author:
            await interaction.response.send_message("This is not your session!", ephemeral=True)
            return
        if self.page < len(self.pages) - 1:
            self.page += 1
            await self.update_page(interaction)
        else:
            await interaction.response.defer()

@bot.command(aliases=['all', 'ac', 'a'])
async def allcards(ctx, *, filter: str = None):
    """List every card available, grouped by group, paginated. Supports filters: group=, rarity=, name="""
    group_filter = None
    rarity_filter = None
    name_filter = None

    if filter:
        for part in shlex.split(filter):
            if part.startswith("group="):
                group_filter = part.split("=", 1)[1].lower()
            if part.startswith("rarity="):
                rarity_filter = part.split("=", 1)[1].lower()
            if part.startswith("name="):
                name_filter = part.split("=", 1)[1].lower()

    # Use all loaded cards, not just those in the database
    rows = [(c["code"], c["name"], c["group"], c["rarity"]) for c in cards]

    # Apply filters
    filtered = []
    for code, name, group, rarity in rows:
        if group_filter and group.lower() != group_filter:
            continue
        if rarity_filter and rarity.lower() != rarity_filter:
            continue
        if name_filter and name_filter not in name.lower():
            continue
        filtered.append((code, name, group, rarity))

    if not filtered:
        await ctx.send("No cards found with those filters!")
        return

    # Group cards by group name
    from collections import defaultdict
    group_cards = defaultdict(list)
    for code, name, group, rarity in filtered:
        group_cards[group].append((code, name, rarity))

    # Sort groups and cards
    sorted_groups = sorted(group_cards.keys())
    items = []
    for group in sorted_groups:
        items.append(f"**{group}**")
        for code, name, rarity in sorted(group_cards[group], key=lambda x: (x[1].lower(), x[0])):
            items.append(f"・`{code}` {name} ({rarity})")

    # Paginate (10 cards per page)
    per_page = 10
    pages = []
    for i in range(0, len(items), per_page):
        desc = "\n".join(items[i:i+per_page])
        embed = discord.Embed(
            title="𓆩♡𓆪 All Cards in Database",
            description=desc,
            color=0xd0ff79
        )
        embed.set_footer(text=f"Page {i//per_page+1}/{(len(items)-1)//per_page+1}")
        pages.append(embed)

    view = AllCardsView(pages, ctx.author)
    await ctx.send(embed=pages[0], view=view)

@bot.command()
async def send(ctx, member: discord.Member, amount: int):
    """Send meowies to another user."""
    if member.id == ctx.author.id:
        await ctx.send("What are you trying to do huh ? /ᐠ - ˕ -マ Ⳋ You can't send meowies to yourself, silly kitty !")
        return
    if amount <= 0:
        await ctx.send("Mmh.. okay why not ? Go girl, give us nothing (¬`‸´¬) (Amount must be greater than zero).")
        return

    async with aiosqlite.connect("inventory.db") as db:
        # Check sender balance
        async with db.execute("SELECT meowies FROM users WHERE user_id = ?", (ctx.author.id,)) as cursor:
            row = await cursor.fetchone()
        if not row or row[0] < amount:
            await ctx.send("You don't have enough meowies to send (*cough* broke.. *cough*) !")
            return

        # Deduct from sender
        await db.execute("UPDATE users SET meowies = meowies - ? WHERE user_id = ?", (amount, ctx.author.id))
        # Add to recipient
        await db.execute("UPDATE users SET meowies = meowies + ? WHERE user_id = ?", (amount, member.id))
        await db.commit()

    await ctx.send(f"{ctx.author.display_name} sent {amount} meowies to {member.display_name} !")

bot.run(token)