import discord
from discord.ext import commands
import os
from dotenv import load_dotenv

load_dotenv()

TOKEN = os.getenv('DISCORD_TOKEN')
GUILD_ID = os.getenv('GUILD_ID')
ALLOWED_CATEGORY_ID = os.getenv('ALLOWED_CATEGORY_ID')
PLAYER_ROLE_NAME = os.getenv('PLAYER_ROLE_NAME', 'i play mafia')

# Bot setup with required intents
intents = discord.Intents.default()
intents.members = True
intents.message_content = True

bot = commands.Bot(command_prefix='!', intents=intents)

@bot.event
async def on_ready():
    """Called when the bot is ready."""
    print(f'{bot.user} has connected to Discord!')
    print(f'Bot is in {len(bot.guilds)} guild(s)')
    print(f'Player role: {PLAYER_ROLE_NAME}')
    if ALLOWED_CATEGORY_ID:
        print(f'Restricted to category ID: {ALLOWED_CATEGORY_ID}')
    else:
        print('No category restriction (bot works in all channels)')
    
    # Load Cogs
    try:
        await bot.load_extension('cogs.admin')
        await bot.load_extension('cogs.gameplay')
        print("Loaded cogs: AdminCog, GameplayCog")
    except Exception as e:
        print(f"Failed to load cogs: {e}")

    # Sync slash commands
    if GUILD_ID:
        guild = discord.Object(id=int(GUILD_ID))
        bot.tree.copy_global_to(guild=guild)
        await bot.tree.sync(guild=guild)
        print(f'Synced commands to guild {GUILD_ID}')
    else:
        await bot.tree.sync()
        print('Synced commands globally')

if __name__ == '__main__':
    if not TOKEN:
        print("ERROR: DISCORD_TOKEN not found in environment variables!")
        print("Create a .env file with:")
        print("  DISCORD_TOKEN=your_bot_token_here")
        print("  GUILD_ID=your_guild_id_here (optional, for faster command sync)")
        print("  PLAYER_ROLE_NAME=i play mafia (optional, default is 'i play mafia')")
        print("  ALLOWED_CATEGORY_ID=123456789 (optional, restricts bot to specific category)")
        exit(1)
    
    bot.run(TOKEN)
