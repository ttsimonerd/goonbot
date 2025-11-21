import os
try:
    import discord
    from discord.ext import commands
except ImportError as e:
    raise ImportError("discord.py is not installed.") from e

TOKEN = os.getenv('MTQ0MDc4NDU4NDE1NjM4NTQ3Mg.Gzxf0b.-lRwDTmnDZe0JevcKkPljZm-TArBHHzEuEDVbc')

intents = discord.Intents.default()
intents.message_content = True

bot = commands.Bot(command_prefix='^', intents=intents)

@bot.event
async def on_ready():
    print(f'Logged as {bot.user}')

@bot.command()
async def ping(ctx):
    await ctx.send('Pong!')

if __name__ == '__main__':
    if TOKEN is None:
        raise ValueError("Dev env token not set.")
    bot.run(TOKEN)

